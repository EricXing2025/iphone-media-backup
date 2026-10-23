# iPhone Media Backup / iPhone 照片视频备份工具

A tiny local web tool to offload photos & videos from an iPhone to an external drive over USB — with verification, date-based organization, and optional cleanup of the device.

一个本地小工具：用数据线把 iPhone 的照片/视频迁移到移动硬盘，自动校验、按日期分类，并可选择在确认备份完好后清理手机空间。

---

## English

### Features

- 🔌 **USB transfer, no iTunes** — reads the camera roll (`/DCIM`) directly over the AFC protocol (via [pymobiledevice3](https://github.com/doronz88/pymobiledevice3)). No cloud, no Photos app export, no quality loss.
- 🌐 **Simple web UI** — double-click the launcher, your browser opens `http://127.0.0.1:8787`, click *Start*.
- 🗂 **Auto-organization** — files land in `YYYY-MM-DD/` folders split into `视频/` (videos) and `照片/` (photos). Optionally, videos are further divided into `成片/` (edited/exported clips — detects ffmpeg/Lavf, Insta360, and other non-camera encoders) and `素材/` (camera originals).
- ✅ **Verify before delete** — every file is size-checked after copying; the "Clean iPhone" step only deletes files verified present on the drive.
- ⏯ **Resumable** — interrupted runs skip already-copied files.
- 🧳 **Self-contained** — the launcher bootstraps a Python venv and installs dependencies automatically. Copy the folder to any Mac and it just works.

### Requirements

- macOS (tested on macOS 15/arm64)
- iPhone connected via USB cable, unlocked, and "Trust This Computer" accepted
- An external drive (any filesystem; exFAT works)
- Internet connection **only for first-run dependency install**

### Quick Start

```bash
git clone https://github.com/EricXing2025/iphone-media-backup.git
cd iphone-media-backup
# then double-click start.command (or run it from terminal)
```

1. Double-click **`start.command`** — it creates `.venv`, installs `pymobiledevice3` + `fastapi` + `uvicorn`, and opens the web page.
   - If macOS blocks it: right-click → **Open** → **Open**.
   - If `python3` is missing: it triggers the Xcode Command Line Tools installer — finish that, then re-run.
2. In the web page: check that iPhone and the drive are detected, pick the destination folder, click **开始迁移** (Start migration).
3. Keep the iPhone **unlocked** during transfer (Settings → Display & Brightness → Auto-Lock → Never).
4. After verification passes, confirm the files on the drive, tick the checkbox and click **清理 iPhone** (Clean iPhone).

> The web UI is currently in Chinese — the buttons are self-explanatory and a translation contribution is welcome.

### How it works

| Step | What happens |
|---|---|
| Scan | Walks `/DCIM` via AFC, records every file's size + capture mtime |
| Pull | Streams each file to a hidden staging dir on the drive (`.iPhone迁移暂存`), resumable |
| Verify | Byte-size check per file; failures abort before anything else runs |
| Classify | Moves files into `YYYY-MM-DD/照片\|视频/`; exported clips (Lavf/Insta360/no camera markers, or `.mp4`) go to `视频/成片/`, camera originals to `视频/素材/` |
| Clean | Deletes each file from the device **only if** its verified copy exists on the drive; removes emptied `APPLE` folders |

### Safety notes

- Deletion only ever touches files verified byte-for-byte on the destination — anything unverified is skipped and reported.
- iCloud Photos is untouched; cloud items remain in the cloud (this tool reads only what is physically on the device).
- Deleting via AFC bypasses the Photos database — iOS may take a moment to reconcile the library view.

### Limitations

- **macOS only** (AFC via Apple's usbmuxd).
- Reads only locally-stored camera-roll media. If you use *iCloud Photos → Optimize iPhone Storage*, cloud-only originals are not on the device and cannot be pulled.
- Does not preserve albums/edits — originals only.

### Disclaimer

Use at your own risk. The device-cleanup feature deletes files from your iPhone; while it is guarded by verification, please double-check your backup before cleaning. The author is not responsible for data loss.

---

## 中文

### 功能

- 🔌 **数据线直传，不经过 iTunes**——通过 AFC 协议直接读取相册目录（`/DCIM`)，借助 [pymobiledevice3](https://github.com/doronz88/pymobiledevice3)。不走云端、无压缩，原图原视频。
- 🌐 **网页操作界面**——双击启动器自动打开 `http://127.0.0.1:8787`，点按钮就行。
- 🗂 **自动分类**——按拍摄日期归入 `YYYY-MM-DD/` 文件夹，再分 `视频/`、`照片/`；可选把视频细分为 `成片/`（剪映/Insta360 等 App 导出的，按 Lavf 等编码器标记识别）和 `素材/`（相机原片）。
- ✅ **先校验后删除**——每个文件拷贝后校验大小；"清理手机"只删已确认落在硬盘上的文件。
- ⏯ **断点续传**——中断后重跑会跳过已拷好的文件。
- 🧳 **绿色免配置**——启动器自动建 venv 装依赖，整个文件夹拷到任何 Mac 都能用。

### 环境要求

- macOS（在 macOS 15/arm64 上实测）
- iPhone 数据线连接、解锁并"信任此电脑"
- 一块移动硬盘（exFAT/APFS 均可）
- **仅首次**安装依赖需要联网

### 快速开始

1. 下载或 clone 本仓库，双击 **`启动iPhone备份.command`**
   - 系统拦截时：右键 → 打开 → 打开
   - 没有 Python3 时会自动弹出 Xcode 命令行工具安装，装完重试即可
2. 网页里确认 iPhone 和硬盘都被识别，选择目标目录，点 **开始迁移**
3. 传输期间保持 iPhone **亮屏解锁**（设置→显示与亮度→自动锁定→永不）
4. 校验通过后，确认硬盘文件完好，勾选确认框，点 **清理 iPhone**

### 工作原理

| 步骤 | 动作 |
|---|---|
| 扫描 | 遍历 `/DCIM`，记录每个文件的大小和拍摄时间 |
| 拷贝 | 流式写入硬盘上的隐藏暂存目录（`.iPhone迁移暂存`)，可续传 |
| 校验 | 逐文件比对大小，失败即中止 |
| 分类 | 移入 `YYYY-MM-DD/照片\|视频/`；导出片（`.mp4` 或带 Lavf/Insta360 标记、无相机标记）进 `视频/成片/`，相机原片进 `视频/素材/` |
| 清理 | 只删除**已验证**在硬盘上的文件，并清空的 APPLE 目录 |

### 安全说明

- 删除前逐个校验硬盘文件完好，未通过的一律跳过并提示
- 不影响 iCloud 云端照片（本工具只处理设备本地文件）
- 通过 AFC 删除绕过相册数据库，iOS 需要一点时间刷新相册显示

### 局限

- 仅支持 macOS
- 只迁移设备本地相册原图；开了"iCloud 照片+优化储存空间"的话，云端独有的原图拿不到
- 不保留相册分组和编辑记录，只迁移原始文件

### 免责声明

请自行承担使用风险。"清理手机"会从 iPhone 删除文件，虽然做了完整性校验，仍请确认备份无误后再清理。作者不对数据丢失负责。

---

## Credits / 致谢

- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) — the iOS device protocol implementation (AFC/lockdown)
- [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) — web backend

## License

[MIT](LICENSE)
