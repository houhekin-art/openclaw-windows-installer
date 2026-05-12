# OpenClaw Windows 一键安装程序

双击即用，自动安装 WSL2 + Docker Desktop + Ollama + OpenClaw。

## 下载

**👉 下载 `.exe` 安装程序：**
https://github.com/houhekin-art/openclaw-windows-installer/releases

## 功能

- ✅ WSL2 自动安装
- ✅ Docker Desktop 自动安装
- ✅ Ollama 本地 AI 自动安装
- ✅ Llama 3.2 / Qwen 2.5 / DeepSeek R1 模型下载
- ✅ OpenClaw 容器自动部署
- ✅ 中文 UI 向导界面
- ✅ 每步验证，失败自动停止

## 系统要求

- Windows 10 21H2+ 或 Windows 11
- 16GB+ 内存（建议 32GB）
- 50GB+ 可用磁盘空间
- 网络连接（下载约 10GB）

## 快速开始

1. 下载 `OpenClaw-Setup.exe`
2. 右键 → **以管理员身份运行**
3. 选择 AI 模型
4. 等待 30-60 分钟自动完成

## 安装后

访问：http://localhost:18789

首次使用需要创建账号并配置 Ollama 连接。

## 源码编译

```bash
pip install pyinstaller pillow
pyinstaller --onefile --windowed --icon=icon.ico openclaw_setup.py
```
