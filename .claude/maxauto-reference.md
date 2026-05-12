# MaxAuto 参考资料

> https://github.com/Maxch3306/openclaw-maxauto
> Stars: 11 | Type: Tauri (Rust + React/TypeScript)
> 用途: OpenClaw 桌面封装，双击安装，polished GUI

## 核心参考价值

### 1. Rust 安装命令 (setup.rs)

MaxAuto 的安装核心逻辑用 Rust 写，参考点：

```rust
// Windows PATH 从注册表刷新，避免重启检测新安装的程序
#[cfg(windows)]
pub fn refresh_path_from_registry() {
    use winreg::enums::*;
    use winreg::RegKey;
    // 从 HKEY_LOCAL_MACHINE 和 HKEY_CURRENT_USER 读 PATH
}

// Git 默认路径检测
pub fn find_git_in_default_paths() -> Option<PathBuf> {
    let candidates = [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
    ];
}

// Node.js 直接从 nodejs.org 下载 zip，而不是用 installer
let version = "24.14.0";
let url = format!("https://nodejs.org/dist/v{}/{}", version, filename);
// reqwest 下载，zip crate 解压
```

### 2. Docker 命令 (docker.rs)

```rust
// 检查 Docker CLI + Daemon 状态
#[tauri::command]
pub async fn check_docker() -> Result<DockerStatus, String> {
    let docker_bin = if cfg!(windows) { "docker.exe" } else { "docker" };
    // docker version --format "{{.Server.Version}}"
    // 同时检查 CLI 和 daemon
}

// 拉取 OpenClaw 镜像
#[tauri::command]
pub async fn pull_openclaw_image(app: AppHandle, tag: Option<String>) -> Result<String, String> {
    let image = format!("ghcr.io/openclaw/openclaw:{}", tag.unwrap_or("latest"));
    // tokio::process::Command::new("docker").args(["pull", &image])
}

// Docker 启动 OpenClaw
#[tauri::command]
pub async fn start_docker_gateway(port: Option<u16>) -> Result<GatewayStatus, String> {
    let port = port.unwrap_or(51789);
    // docker run -d --name openclaw -p {port}:18789 ...
}
```

### 3. 进度事件系统

```rust
use tauri::Emitter;

let _ = app.emit("setup-progress", SetupProgress {
    step: "node".into(),
    message: "Downloading Node.js...".into(),
    progress: Some(0.0),
    error: None,
});
```

### 4. 可借鉴功能

| 功能 | MaxAuto 方案 | 我们可借鉴 |
|------|-------------|-----------|
| Node.js 安装 | 直接下载 zip 解压 | ✅ 可用相同逻辑 |
| PATH 刷新 | 读注册表 | ✅ |
| Docker 检测 | CLI + Daemon 分开检查 | ✅ |
| Git 检测 | 默认路径 + CLI | ✅ |
| 进度回调 | Tauri emit | 我们的 Tkinter 可用 threading.Event |
| OpenClaw 端口 | 默认 51789 | 我们的用 18789（标准） |

### 5. 其余亮点

- **Skills 管理**: winget install 支持（Windows）
- **多 LLM provider**: 自带多种 AI 模型配置界面
- **系统托盘**: 最小化到托盘，关机保持运行
- **自动更新**: GitHub Releases 检测并安装

## IROTECHLAB/openclaw-web-installer

> https://github.com/IROTECHLAB/openclaw-web-installer
> Stars: 0 | Type: Python Flask
> 用途: Web 界面安装向导（Flask + 模板）

纯 Python Flask 实现，1497 行，有完整 Windows 安装逻辑，可参考。

### 可借鉴
- Flask web 界面（比我们 Tkinter 更专业）
- 步骤状态管理（'step', 'message', 'progress', 'errors', 'logs'）
- psutil 系统信息采集
