#!/usr/bin/env python3
"""iPhone 照片视频 → 移动硬盘 迁移工具 (本机版)

用法:  python3 app.py   然后浏览器打开 http://127.0.0.1:8787
"""
import asyncio, datetime, json, os, struct, threading, time

import uvicorn
from fastapi import FastAPI, Body
from fastapi.responses import FileResponse, JSONResponse
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.afc import AfcService

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "last_run_manifest.json")
STAGING = ".iPhone迁移暂存"
CHUNK = 4 * 1024 * 1024
VIDEO_EXT = {".mov", ".mp4", ".m4v"}
PHOTO_EXT = {".heic", ".jpg", ".jpeg", ".png", ".dng"}

STATE = {
    "phase": "idle",          # idle|scanning|pulling|classifying|done|deleting|deleted|error|cancelled
    "running": False,
    "total_files": 0, "done_files": 0,
    "bytes_done": 0, "total_bytes": 0,
    "current": "", "log": [], "summary": "",
    "verify_ok": 0, "deleted": 0,
    "dest": "", "split_cuts": True,
}
CANCEL = {"flag": False}
LOCK = threading.Lock()

app = FastAPI()


def log(msg):
    with LOCK:
        STATE["log"].append(f'{datetime.datetime.now().strftime("%H:%M:%S")}  {msg}')
        STATE["log"] = STATE["log"][-200:]


def set_state(**kw):
    with LOCK:
        STATE.update(kw)


def default_dest():
    """Pick the first writable external volume under /Volumes (excludes the
    system volume). Users can always override it in the web UI."""
    best = ""
    for n in sorted(os.listdir("/Volumes")):
        if n in ("Macintosh HD", "Recovery"):
            continue
        p = os.path.join("/Volumes", n)
        if os.path.isdir(p) and os.access(p, os.W_OK):
            return p
    return best


# ---------- AFC helpers ----------

async def walk_meta(afc, path):
    for name in await afc.listdir(path):
        if name in (".", ".."):
            continue
        p = path.rstrip("/") + "/" + name
        try:
            info = await afc.stat(p)
        except Exception:
            continue
        if info.get("st_ifmt") == "S_IFDIR":
            async for item in walk_meta(afc, p):
                yield item
        else:
            mt = info.get("st_mtime")
            yield p, int(info.get("st_size", 0)), (mt.timestamp() if mt else 0)


def moov_blob(path):
    try:
        with open(path, "rb") as f:
            total = os.path.getsize(path)
            while True:
                pos = f.tell()
                hdr = f.read(8)
                if len(hdr) < 8:
                    return None
                size, typ = struct.unpack(">I4s", hdr)
                if size == 1:
                    size = struct.unpack(">Q", f.read(8))[0]
                elif size == 0:
                    size = total - pos
                if typ == b"moov":
                    return f.read(min(size - 8, 2 * 1024 * 1024))
                if size < 8:
                    return None
                f.seek(pos + size)
    except Exception:
        return None


def is_export(path):
    """成片 = 剪映/App 导出(Lavf/Insta360 标记、.MP4、或无相机标记)"""
    if path.lower().endswith(".mp4"):
        return True
    blob = moov_blob(path)
    if blob is None:
        return False
    if b"Lavf" in blob or b"Insta360" in blob or b"JianYing" in blob or b"lv.encoder" in blob:
        return True
    if b"com.apple.quicktime" in blob or b"Apple" in blob:
        return False
    return True


def uniq_target(dstdir, name):
    os.makedirs(dstdir, exist_ok=True)
    tgt = os.path.join(dstdir, name)
    if os.path.exists(tgt):
        base, ext = os.path.splitext(tgt)
        tgt = base + "__dup" + ext
    return tgt


# ---------- 主任务: 扫描→拷贝→分类 ----------

async def job_pull(dest, split_cuts):
    afc = AfcService(await create_using_usbmux())
    staging = os.path.join(dest, STAGING)

    # 1) 扫描
    set_state(phase="scanning")
    log("正在扫描 iPhone DCIM ...")
    entries = []
    async for p, sz, mt in walk_meta(afc, "/DCIM"):
        entries.append({"path": p, "size": sz, "mtime": mt})
    total_bytes = sum(e["size"] for e in entries if e["size"] > 0)
    set_state(total_files=len(entries), total_bytes=total_bytes)
    log(f"发现 {len(entries)} 个文件, 共 {total_bytes/1e9:.1f} GB")
    if not entries:
        set_state(phase="done", running=False, summary="iPhone 上没有可迁移的照片/视频")
        return

    # 2) 拷贝
    set_state(phase="pulling")
    os.makedirs(staging, exist_ok=True)
    fails = []
    t0 = time.time()
    done_bytes = 0
    for i, e in enumerate(entries):
        if CANCEL["flag"]:
            set_state(phase="cancelled", running=False, summary="已取消")
            log("任务已取消")
            return
        rp, sz = e["path"], e["size"]
        lp = os.path.join(staging, rp[len("/DCIM"):].lstrip("/"))
        set_state(current=rp, done_files=i)
        if os.path.exists(lp) and (sz < 0 or os.path.getsize(lp) == sz):
            done_bytes += max(sz, 0)
            set_state(bytes_done=done_bytes)
            continue
        try:
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            handle = await afc.fopen(rp, "r")
            written = 0
            try:
                with open(lp + ".tmp", "wb") as lf:
                    while True:
                        buf = await afc.fread(handle, CHUNK)
                        if not buf:
                            break
                        lf.write(buf)
                        written += len(buf)
                        done_bytes += len(buf)
                        set_state(bytes_done=done_bytes)
            finally:
                await afc.fclose(handle)
            if sz >= 0 and written != sz:
                raise IOError("size mismatch")
            os.rename(lp + ".tmp", lp)
        except Exception as ex:
            fails.append(f"{rp}: {ex}")
            try:
                os.remove(lp + ".tmp")
            except OSError:
                pass
    set_state(done_files=len(entries) - len(fails), verify_ok=len(entries) - len(fails))
    el = time.time() - t0
    log(f"拷贝完成: {len(entries)-len(fails)}/{len(entries)} 个, 平均 {done_bytes/1e6/max(el,1):.0f} MB/s")
    if fails:
        log(f"失败 {len(fails)} 个: {fails[0][:120]}")
        set_state(phase="error", running=False, summary=f"{len(fails)} 个文件拷贝失败, 未分类未删除")
        return

    # 3) 分类
    set_state(phase="classifying")
    log("正在按日期分类 ...")
    for e in entries:
        if CANCEL["flag"]:
            break
        rp, mt = e["path"], e["mtime"]
        sp = os.path.join(staging, rp[len("/DCIM"):].lstrip("/"))
        if not os.path.exists(sp):
            continue
        day = datetime.datetime.fromtimestamp(mt).strftime("%Y-%m-%d") if mt else "未知日期"
        ext = os.path.splitext(rp)[1].lower()
        if ext in VIDEO_EXT:
            sub = os.path.join("视频", "成片" if (split_cuts and is_export(sp)) else ("素材" if split_cuts else ""))
            ddir = os.path.join(dest, day, "视频", sub) if split_cuts else os.path.join(dest, day, "视频")
        elif ext in PHOTO_EXT:
            ddir = os.path.join(dest, day, "照片")
        else:
            ddir = os.path.join(dest, day)
        tgt = uniq_target(ddir, os.path.basename(rp))
        os.rename(sp, tgt)
        e["final"] = tgt
    json.dump(entries, open(MANIFEST, "w"), ensure_ascii=False)
    # 清理暂存空目录
    for dirpath, dirs, files in os.walk(staging, topdown=False):
        for f in files:
            if f.startswith("._") or f.endswith(".tmp"):
                try:
                    os.remove(os.path.join(dirpath, f))
                except OSError:
                    pass
        try:
            os.rmdir(dirpath)
        except OSError:
            pass
    try:
        os.rmdir(staging)
    except OSError:
        pass
    summary = f"完成: {len(entries)} 个文件已迁移到 {dest} 并按日期分类"
    set_state(phase="done", running=False, summary=summary, current="")
    log(summary)


# ---------- 清理任务 ----------

async def job_delete():
    afc = AfcService(await create_using_usbmux())
    entries = json.load(open(MANIFEST))
    deleted = skipped = failed = 0
    set_state(phase="deleting", total_files=len(entries), done_files=0)
    for i, e in enumerate(entries):
        if CANCEL["flag"]:
            set_state(phase="done", running=False, summary=f"清理中止: 已删 {deleted}, 跳过 {skipped}")
            return
        lp = e.get("final", "")
        ok = lp and os.path.exists(lp) and (e["size"] < 0 or os.path.getsize(lp) == e["size"])
        if not ok:
            skipped += 1
            log(f"跳过未验证文件 {e['path']}")
            continue
        try:
            await afc.rm_single(e["path"])
            deleted += 1
        except Exception as ex:
            if "OBJECT_NOT_FOUND" in str(ex) or "status: 8" in str(ex):
                deleted += 1  # 已不在设备上, 视为已清理
            else:
                failed += 1
                log(f"删除失败 {e['path']}: {str(ex)[:100]}")
        set_state(done_files=i + 1, deleted=deleted)
    # 清空的 APPLE 目录
    try:
        for name in await afc.listdir("/DCIM"):
            p = "/DCIM/" + name
            try:
                if (await afc.stat(p)).get("st_ifmt") == "S_IFDIR" and len(await afc.listdir(p)) == 0:
                    await afc.rm_single(p)
            except Exception:
                pass
    except Exception:
        pass
    summary = f"清理完成: iPhone 已删除 {deleted} 个文件" + (f", {skipped} 个未验证已跳过" if skipped else "")
    set_state(phase="deleted", running=False, summary=summary)
    log(summary)


def run_async(coro):
    try:
        asyncio.run(coro)
    except Exception as ex:
        set_state(phase="error", running=False, summary=f"出错: {ex}")
        log(f"ERROR: {ex}")


# ---------- HTTP API ----------

@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "index.html"))


@app.get("/api/status")
async def api_status():
    dev = None
    try:
        ld = await create_using_usbmux()
        vals = ld.all_values or {}
        free = await ld.get_value("com.apple.disk_usage", "AmountDataAvailable")
        dev = {
            "name": vals.get("DeviceName", "?"),
            "model": vals.get("ProductType", "?"),
            "ios": vals.get("ProductVersion", "?"),
            "free_gb": round((free or 0) / 1e9, 1),
        }
    except Exception:
        pass
    dest = STATE["dest"] or default_dest()
    disk = None
    if dest and os.path.isdir(dest):
        try:
            st = os.statvfs(dest)
            disk = {"path": dest, "free_gb": round(st.f_bavail * st.f_frsize / 1e9, 1)}
        except Exception:
            pass
    with LOCK:
        job = {k: STATE[k] for k in ("phase", "running", "summary")}
    return {"iphone": dev, "disk": disk, "job": job, "dest": dest}


@app.get("/api/job")
def api_job():
    with LOCK:
        s = dict(STATE)
        s.pop("log", None)
        return s


@app.get("/api/log")
def api_log():
    with LOCK:
        return {"log": STATE["log"]}


@app.post("/api/start")
def api_start(body: dict = Body(default={})):
    if STATE["running"]:
        return JSONResponse({"ok": False, "msg": "任务进行中"}, status_code=409)
    dest = (body.get("dest") or "").strip() or default_dest()
    if not dest or not os.path.isdir(dest):
        return JSONResponse({"ok": False, "msg": f"目标目录不存在: {dest}"}, status_code=400)
    CANCEL["flag"] = False
    with LOCK:
        STATE.update({"phase": "starting", "running": True, "log": [],
                      "done_files": 0, "total_files": 0, "bytes_done": 0,
                      "total_bytes": 0, "verify_ok": 0, "deleted": 0,
                      "summary": "", "dest": dest,
                      "split_cuts": bool(body.get("split_cuts", True))})
    log(f"目标: {dest}")
    threading.Thread(target=run_async, args=(job_pull(dest, STATE["split_cuts"]),), daemon=True).start()
    return {"ok": True}


@app.post("/api/delete")
def api_delete(body: dict = Body(default={})):
    if STATE["running"]:
        return JSONResponse({"ok": False, "msg": "任务进行中"}, status_code=409)
    if not body.get("confirm"):
        return JSONResponse({"ok": False, "msg": "未确认"}, status_code=400)
    if not os.path.exists(MANIFEST):
        return JSONResponse({"ok": False, "msg": "没有可清理的迁移记录, 请先完成迁移"}, status_code=400)
    CANCEL["flag"] = False
    with LOCK:
        STATE.update({"phase": "deleting", "running": True, "deleted": 0, "done_files": 0})
    log("开始清理 iPhone ...")
    threading.Thread(target=run_async, args=(job_delete(),), daemon=True).start()
    return {"ok": True}


@app.post("/api/cancel")
def api_cancel():
    CANCEL["flag"] = True
    log("收到取消指令")
    return {"ok": True}


if __name__ == "__main__":
    import webbrowser
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8787")).start()
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")
