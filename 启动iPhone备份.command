#!/bin/bash
# iPhone 备份工具启动器 —— 双击运行
# 自动检测并安装依赖(Python venv),启动后自动打开网页
cd "$(dirname "$0")"

echo "======================================"
echo "  iPhone 备份到移动硬盘 - 启动器"
echo "======================================"

# 1) 检查 python3
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
    echo ""
    echo "未检测到 Python3。将尝试调用 Xcode 命令行工具安装器..."
    xcode-select --install 2>/dev/null
    echo ""
    echo "请在弹出的系统窗口中点击「安装」,装完后重新双击本启动器即可。"
    read -r -p "按回车退出..."
    exit 1
fi
echo "Python: $("$PY" --version 2>&1)"

# 2) 创建虚拟环境(仅首次)
if [ ! -d .venv ]; then
    echo "首次运行,正在创建虚拟环境..."
    "$PY" -m venv .venv
    if [ ! -f .venv/bin/python3 ]; then
        echo "虚拟环境创建失败,尝试 ensurepip..."
        "$PY" -m ensurepip --default-pip >/dev/null 2>&1
        "$PY" -m venv .venv || { echo "仍失败,请把错误截图发给我"; read -r -p "按回车退出..."; exit 1; }
    fi
fi
PY=".venv/bin/python3"

# 3) 检测依赖,缺则安装
if ! "$PY" -c "import pymobiledevice3, fastapi, uvicorn" 2>/dev/null; then
    echo "正在安装依赖(仅首次,需要联网)..."
    "$PY" -m pip install -q --upgrade pip
    "$PY" -m pip install -q "pymobiledevice3==11.43.1"
    if ! "$PY" -c "import pymobiledevice3, fastapi, uvicorn" 2>/dev/null; then
        echo "依赖安装失败,请检查网络后重试"
        read -r -p "按回车退出..."
        exit 1
    fi
    echo "依赖安装完成"
fi

# 4) 启动(自动打开 http://127.0.0.1:8787)
echo ""
echo "启动中,浏览器即将打开 http://127.0.0.1:8787 ..."
echo "(此窗口保持开着即为运行中,关闭窗口即停止)"
exec "$PY" app.py
