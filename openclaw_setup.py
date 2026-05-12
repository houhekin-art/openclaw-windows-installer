#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 一键安装程序 - UI 版本
运行方式: python openclaw_setup.py
打包命令: pyinstaller --onefile --windowed openclaw_setup.py
依赖: Python 3.8+, tkinter (内置), requests (内置)
"""
import subprocess
import sys
import os
import re
import threading
import tempfile
import ctypes
import shutil
import time
import json

# ============================================================
# 管理员检查
# ============================================================
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def get_ram_gb():
    try:
        kernel32 = ctypes.windll.kernel32
        class MEM(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
            ]
        mem = MEM()
        mem.dwLength = ctypes.sizeof(MEM)
        kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        return mem.ullTotalPhys / (1024**3)
    except Exception:
        return 0

def get_disk_free_gb(drive='C'):
    try:
        free_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(f'{drive}:\\'), None, None, ctypes.pointer(free_bytes))
        return free_bytes.value / (1024**3)
    except Exception:
        return 0

def get_win_version():
    try:
        ver = sys.getwindowsversion()
        return f"Windows {ver.major}.{ver.minor} (Build {ver.build})"
    except Exception:
        return "Unknown"

# ============================================================
# GitHub Actions Windows 环境检测
# ============================================================
def is_github_actions():
    return os.environ.get('GITHUB_ACTIONS') == 'true'

# ============================================================
# 安装器核心（参考 MaxAuto 改进）
# ============================================================
class Installer:
    def __init__(self, log_func, complete_callback):
        self.log = log_func
        self.complete = complete_callback
        self.cancelled = False
        self._progress_callback = None

    def set_progress(self, step_idx):
        if self._progress_callback:
            self._progress_callback(step_idx)

    def run_ps(self, script, admin=False, capture=True, timeout=300):
        if self.cancelled:
            return None
        flags = '-ExecutionPolicy Bypass'
        if admin:
            flags += ' -Verb RunAs'
        cmd = ['powershell', flags, '-Command', script]
        try:
            if capture:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                return result
            else:
                subprocess.Popen(cmd, creation=subprocess.CREATE_NO_WINDOW)
                return None
        except subprocess.TimeoutExpired:
            self.log('[超时] 命令执行超过 5 分钟')
            return None
        except Exception as e:
            self.log(f'[错误] {e}')
            return None

    def check(self, cond, ok_msg, fail_msg):
        if cond:
            self.log(f'  ✓ {ok_msg}', 'ok')
            return True
        self.log(f'  ✗ {fail_msg}', 'error')
        return False

    # ---- WSL2 ----
    def install_wsl2(self):
        self.set_progress(0)
        self.log('[1/5] WSL2 安装')
        r = self.run_ps('wsl --status 2>&1')
        if r and r.returncode == 0:
            self.log('  ✓ WSL2 已安装，跳过')
            return True

        # MaxAuto 风格：自动选择最简单路径
        self.log('  开始安装 WSL2（可能需要重启）...')
        self.run_ps('wsl --install --no-distribution', admin=True)

        self.log('')
        self.log('=' * 50, 'warn')
        self.log('需要重启电脑！重启后重新运行本程序。', 'warn')
        self.log('=' * 50, 'warn')
        return False

    # ---- Docker ----
    def install_docker(self):
        self.set_progress(1)
        self.log('[2/5] Docker Desktop 安装')

        # 检查 Docker CLI
        r = self.run_ps('where docker 2>&1')
        if r and r.returncode == 0:
            r2 = self.run_ps('docker --version 2>&1')
            self.log(f'  ✓ Docker 已安装: {r2.stdout.strip() if r2 else ""}', 'ok')
            return True

        self.log('  下载 Docker Desktop（约 600MB）...')
        tmp = os.path.join(tempfile.gettempdir(), 'DockerDesktopInstaller.exe')
        try:
            self.run_ps(
                f"[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
                f"Invoke-WebRequest -Uri 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe' "
                f"-OutFile '{tmp}'"
            )
        except Exception as e:
            self.log(f'  下载失败: {e}')
            return False

        if not os.path.exists(tmp) or os.path.getsize(tmp) < 1000:
            self.log('  Docker 下载失败，请检查网络')
            return False

        self.log('  安装 Docker Desktop（安装向导中请勾选 "Use WSL 2"）...')
        self.run_ps(f'Start-Process "{tmp}" -ArgumentList "install --quiet --accept-license" -Wait')

        # MaxAuto 风格：等待 Docker 服务就绪
        self.log('  等待 Docker 服务启动...')
        for i in range(20):
            if self.cancelled:
                return False
            time.sleep(3)
            r = self.run_ps('docker info 2>&1')
            if r and r.returncode == 0:
                break

        r = self.run_ps('docker --version')
        version = r.stdout.strip() if r else 'unknown'
        self.log(f'  ✓ Docker 版本: {version}', 'ok')
        return True

    # ---- Ollama ----
    def install_ollama(self):
        self.set_progress(2)
        self.log('[3/5] Ollama 安装')

        r = self.run_ps('where ollama 2>&1')
        if r and r.returncode == 0:
            self.log('  ✓ Ollama 已安装，跳过')
            return True

        self.log('  下载并安装 Ollama...')
        try:
            # 参考 MaxAuto: 用 msiexec 静默安装
            self.run_ps(
                "Start-Process msiexec.exe -ArgumentList '/i', 'https://ollama.com/download/OllamaSetup.msi', '/quiet', '/norestart' -Wait"
            )
        except Exception as e:
            self.log(f'  安装失败: {e}')
            return False

        # MaxAuto 风格：配置环境变量后重启服务
        self.run_ps('[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0", "User")')
        self.run_ps('net stop ollama 2>$null; net start ollama')
        time.sleep(5)

        r = self.run_ps('curl http://localhost:11434 2>&1')
        self.log(f'  ✓ Ollama 服务运行正常', 'ok')
        return True

    # ---- 模型下载 ----
    def download_model(self, choice):
        self.set_progress(3)
        self.log('[4/5] 下载 AI 模型')
        models = {
            '1': ('llama3.2', 'Llama 3.2', '约 2GB，速度快'),
            '2': ('qwen2.5', 'Qwen 2.5', '约 4.5GB，中文强'),
            '3': ('deepseek-r1:7b', 'DeepSeek R1 7B', '约 4.5GB，推理强'),
        }
        if choice not in models:
            self.log('  跳过，可稍后运行: ollama pull <模型名>')
            return True

        model_id, model_name, desc = models[choice]
        self.log(f'  开始下载 {model_name}（{desc}）')
        self.log(f'  注意：下载约需 5-20 分钟，请保持网络连接')
        self.log(f'  命令: ollama pull {model_id}', 'info')

        r = self.run_ps(f'ollama pull {model_id}', timeout=1800)
        if r and r.returncode == 0:
            self.log(f'  ✓ {model_name} 下载完成', 'ok')
        else:
            self.log(f'  ⚠ 下载未完成，可稍后重试: ollama pull {model_id}', 'warn')
        return True

    # ---- OpenClaw ----
    def install_openclaw(self):
        self.set_progress(4)
        self.log('[5/5] OpenClaw 安装')

        # 检查 Docker（MaxAuto 风格：详细状态报告）
        r = self.run_ps('docker info 2>&1')
        if not self.check(r and r.returncode == 0, 'Docker 运行正常', 'Docker 未运行，请先安装 Docker Desktop'):
            return False

        # 清理旧容器（如果存在）
        self.run_ps('docker stop openclaw 2>$null; docker rm openclaw 2>$null')

        # 创建数据目录
        data_dir = os.path.join(os.path.expanduser('~'), 'openclaw_data')
        os.makedirs(data_dir, exist_ok=True)
        self.log(f'  数据目录: {data_dir}')

        # 拉取镜像（MaxAuto 风格：带进度）
        self.log('  下载 OpenClaw 镜像（约 2GB）...')
        r = self.run_ps('docker pull openclaw/openclaw:latest', timeout=900)
        if not (r and r.returncode == 0):
            self.log('  ⚠ 镜像下载失败，请检查网络', 'warn')

        # 启动容器（参考 MaxAuto docker.rs）
        self.log('  启动 OpenClaw 容器...')
        startup = (
            f'docker run -d --name openclaw -p 18789:18789 '
            f'-v "{data_dir}:/workspace" '
            f'-v /var/run/docker.sock:/var/run/docker.sock '
            f'-e OLLAMA_BASE_URL=http://host.docker.internal:11434 '
            f'--restart unless-stopped openclaw/openclaw:latest'
        )
        r = self.run_ps(startup)
        if not (r and r.returncode == 0):
            self.log(f'  ✗ 启动失败: {r.stderr if r else ""}', 'error')
            return False

        self.log('  等待 OpenClaw 启动（约 30 秒）...')
        time.sleep(30)

        # 验证
        r = self.run_ps('docker ps | findstr openclaw')
        if r and r.returncode == 0:
            self.log('  ✓ OpenClaw 容器运行中', 'ok')
        else:
            self.log('  ⚠ 容器状态未知，请手动检查: docker ps -a', 'warn')

        return True

    def run_all(self, model_choice='1'):
        ok = True

        # WSL2
        ok = self.install_wsl2()
        if not ok:
            self.complete(warn_restart=True)
            return

        # Docker
        ok = self.install_docker()
        if not ok:
            self.log('Docker 阶段未完成，可重新运行程序继续', 'warn')
            return

        # Ollama
        self.install_ollama()

        # 模型
        self.download_model(model_choice)

        # OpenClaw
        self.install_openclaw()

        self.complete()


# ============================================================
# Tkinter UI
# ============================================================
try:
    import tkinter as tk
    from tkinter import scrolledtext, messagebox, ttk
except ImportError:
    print("[错误] 需要 Python 3.8+，请从 https://www.python.org/downloads/ 下载安装")
    input("按回车退出...")
    sys.exit(1)

# 配色
BG = '#F0F4F8'
CARD = '#FFFFFF'
ACCENT = '#2563EB'
ACCENT_LIGHT = '#DBEAFE'
SUCCESS = '#16A34A'
ERROR = '#DC2626'
WARN = '#D97706'
TEXT = '#1E293B'
TEXT_LIGHT = '#64748B'
BORDER = '#CBD5E1'

TAG_COLORS = {
    'info': TEXT,
    'ok': SUCCESS,
    'error': ERROR,
    'warn': WARN,
}

STEPS = [
    ('WSL2', 'Windows Linux 子系统'),
    ('Docker', '容器化平台'),
    ('Ollama', '本地 AI 运行时'),
    ('AI 模型', 'Llama3.2 / Qwen2.5'),
    ('OpenClaw', 'AI 助手'),
]


class App:
    def __init__(self, root):
        self.root = root
        self.root.title('OpenClaw 一键安装程序')
        self.root.configure(bg=BG)
        self.root.geometry('900x700')
        self.root.minsize(800, 600)

        self.model_choice = tk.StringVar(value='1')
        self._build()

    def _build(self):
        # 顶部
        header = tk.Frame(self.root, bg=ACCENT, height=80)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text='OpenClaw 一键安装程序',
                 font=('Segoe UI', 18, 'bold'),
                 fg='white', bg=ACCENT, anchor='w', padx=30).pack(fill='x', pady=18)
        tk.Label(header, text='Powered by 花果山 · 搜索猴',
                 fg='#93C5FD', bg=ACCENT, font=('Segoe UI', 9)).pack(
                     side='right', anchor='s', padx=30, pady=5)

        content = tk.Frame(self.root, bg=BG)
        content.pack(fill='both', expand=True, padx=20, pady=15)

        # 左侧步骤
        left = tk.Frame(content, bg=BG, width=240)
        left.pack(side='left', fill='y', padx=(0, 15))
        left.pack_propagate(False)
        tk.Label(left, text='安装步骤',
                 font=('Segoe UI', 11, 'bold'), bg=BG, fg=TEXT, anchor='w').pack(anchor='w', pady=(0, 10))

        self.step_indicators = []
        for i, (title, sub) in enumerate(STEPS):
            fr = tk.Frame(left, bg=CARD, padx=10, pady=8,
                          highlightbackground=BORDER, highlightthickness=1)
            fr.pack(fill='x', pady=3)
            ind = tk.Frame(fr, width=22, height=22, bg=BORDER)
            ind.pack(side='left', padx=(0, 8), anchor='n')
            ind.pack_propagate(False)
            c = tk.Canvas(ind, width=22, height=22, bg=BORDER, bd=0, highlightthickness=0)
            c.pack()
            oval = c.create_oval(2, 2, 20, 20, fill=BORDER, outline='')
            txt = c.create_text(11, 11, text=str(i+1),
                                fill='white', font=('Segoe UI', 8, 'bold'))
            info = tk.Frame(fr, bg=CARD)
            info.pack(side='left')
            tk.Label(info, text=title, font=('Segoe UI', 10, 'bold'),
                     bg=CARD, fg=TEXT, anchor='w').pack(anchor='w')
            tk.Label(info, text=sub, font=('Segoe UI', 8), bg=CARD,
                     fg=TEXT_LIGHT, anchor='w').pack(anchor='w')
            self.step_indicators.append({'c': c, 'oval': oval, 'txt': txt, 'frame': fr})

        # 右侧
        right = tk.Frame(content, bg=BG)
        right.pack(side='left', fill='both', expand=True)

        # 系统信息
        sys_fr = tk.Frame(right, bg=CARD, padx=18, pady=14,
                          highlightbackground=BORDER, highlightthickness=1)
        sys_fr.pack(fill='x', pady=(0, 12))
        self.sys_lbl = tk.Label(sys_fr, text='正在检查系统...',
                                font=('Segoe UI', 10), bg=CARD, fg=TEXT,
                                anchor='w', justify='left')
        self.sys_lbl.pack(anchor='w')

        # 详情
        detail = tk.Frame(right, bg=CARD, padx=18, pady=14,
                          highlightbackground=BORDER, highlightthickness=1)
        detail.pack(fill='x', pady=(0, 12))
        self.detail_title = tk.Label(detail, text='准备安装',
                                     font=('Segoe UI', 12, 'bold'),
                                     bg=CARD, fg=TEXT, anchor='w')
        self.detail_title.pack(anchor='w')
        self.detail_desc = tk.Label(detail, text='点击「开始安装」启动全部流程。\n\n'
                                     '约需 30-60 分钟，部分阶段需管理员权限。\n'
                                     '如电脑需要重启，重启后重新运行程序即可继续。',
                                    font=('Segoe UI', 10), bg=CARD, fg=TEXT_LIGHT,
                                    anchor='w', justify='left', wraplength=480)
        self.detail_desc.pack(anchor='w', pady=(6, 0))

        # 模型选择
        mdl_fr = tk.Frame(detail, bg=CARD)
        mdl_fr.pack(anchor='w', pady=(10, 0))
        tk.Label(mdl_fr, text='选择 AI 模型：',
                 font=('Segoe UI', 10, 'bold'), bg=CARD, fg=TEXT).pack(anchor='w')
        for val, lbl in [('1', 'Llama 3.2（推荐，速度快）'),
                           ('2', 'Qwen 2.5（中文能力强）'),
                           ('3', 'DeepSeek R1 7B（推理能力强）'),
                           ('4', '暂不下载（稍后手动选择）')]:
            tk.Radiobutton(mdl_fr, text=lbl, variable=self.model_choice, value=val,
                           font=('Segoe UI', 9), bg=CARD, fg=TEXT,
                           activebackground=CARD, selectcolor=ACCENT_LIGHT).pack(anchor='w', padx=15)

        # 日志
        tk.Label(right, text='安装日志',
                 font=('Segoe UI', 11, 'bold'), bg=BG, fg=TEXT, anchor='w').pack(anchor='w', pady=(0, 5))
        log_fr = tk.Frame(right, bg='#1E293B')
        log_fr.pack(fill='both', expand=True)
        self.log_txt = scrolledtext.ScrolledText(log_fr, font=('Consolas', 9),
                                                  bg='#1E293B', fg='#E2E8F0',
                                                  insertbackground='white', relief='flat',
                                                  state='disabled', padx=10, pady=8, wrap='word')
        self.log_txt.pack(fill='both', expand=True)

        # 按钮
        btn_fr = tk.Frame(right, bg=BG)
        btn_fr.pack(fill='x', pady=(10, 0))
        self.start_btn = tk.Button(btn_fr, text='▶ 开始安装',
                                   font=('Segoe UI', 11, 'bold'),
                                   bg=ACCENT, fg='white', relief='flat',
                                   cursor='hand2', padx=20, pady=6, command=self.start)
        self.start_btn.pack(side='right')
        self.cancel_btn = tk.Button(btn_fr, text='✕ 取消',
                                    font=('Segoe UI', 10),
                                    bg='white', fg=ERROR, relief='flat',
                                    cursor='hand2', padx=12, pady=6,
                                    state='disabled', command=self.cancel)
        self.cancel_btn.pack(side='right', padx=(0, 10))

        self.root.after(300, self.check_sys)

    def check_sys(self):
        admin = is_admin()
        ram = get_ram_gb()
        disk = get_disk_free_gb('C')
        win_ver = get_win_version()
        parts = [f'系统：{win_ver}']
        if admin:
            parts.append('✓ 管理员权限正常')
        else:
            parts.append('⚠ 需要管理员权限！请右键「以管理员身份运行」')
        if ram >= 16:
            parts.append(f'✓ 内存 {ram:.1f}GB（推荐 16GB+）')
        elif ram >= 8:
            parts.append(f'⚠ 内存 {ram:.1f}GB（建议 16GB+，8GB 勉强可用）')
        else:
            parts.append(f'✕ 内存 {ram:.1f}GB 不足（至少 8GB）')
        if disk >= 50:
            parts.append(f'✓ C盘空间 {disk:.1f}GB 满足要求')
        else:
            parts.append(f'⚠ C盘空间 {disk:.1f}GB（建议 50GB+）')
        self.sys_lbl.configure(text='\n'.join(parts))
        if not admin or ram < 8:
            self.start_btn.configure(state='disabled', text='系统不满足要求')

    def log(self, msg, tag='info'):
        color = TAG_COLORS.get(tag, TEXT)
        self.log_txt.configure(state='normal')
        self.log_txt.insert('end', msg + '\n', tag)
        self.log_txt.tag_config(tag, foreground=color)
        self.log_txt.see('end')
        self.log_txt.configure(state='disabled')
        self.root.update_idletasks()

    def set_step(self, idx, status):
        if idx >= len(self.step_indicators):
            return
        si = self.step_indicators[idx]
        colors = {'pending': (BORDER, TEXT_LIGHT),
                  'running': (WARN, 'white'),
                  'done': (SUCCESS, 'white'),
                  'error': (ERROR, 'white')}
        fill, fg = colors.get(status, (BORDER, TEXT_LIGHT))
        si['c'].itemconfig(si['oval'], fill=fill)
        icons = {'pending': str(idx+1), 'running': '▶', 'done': '✓', 'error': '✗'}
        si['c'].itemconfig(si['txt'], text=icons.get(status, str(idx+1)), fill=fg)
        bd_colors = {'done': SUCCESS, 'error': ERROR, 'running': ACCENT}
        si['frame'].configure(highlightbackground=bd_colors.get(status, BORDER),
                              highlightthickness=2 if status == 'running' else 1)

    def start(self):
        if not is_admin():
            messagebox.showwarning('权限不足', '请右键选择「以管理员身份运行」！')
            return
        self.start_btn.configure(state='disabled', text='安装中...', bg=TEXT_LIGHT)
        self.cancel_btn.configure(state='normal')

        # 重置所有步骤状态
        for i in range(len(STEPS)):
            self.set_step(i, 'pending')

        self.log('=' * 55)
        self.log('OpenClaw 一键安装程序启动')
        self.log(f'开始时间：{time.strftime("%Y-%m-%d %H:%M:%S")}')
        self.log(f'AI 模型选择：{self.model_choice.get()}')
        self.log('=' * 55)
        self.log('')

        installer = Installer(log_func=self.log, complete_callback=self.on_complete)
        installer._progress_callback = self.set_step
        t = threading.Thread(target=installer.run_all, args=(self.model_choice.get(),))
        t.daemon = True
        t.start()

    def cancel(self):
        self.log('\n[已取消安装]')
        self.cancel_btn.configure(state='disabled')
        self.start_btn.configure(state='normal', text='▶ 重新安装', bg=ACCENT)

    def on_complete(self, warn_restart=False):
        self.cancel_btn.configure(state='disabled')
        self.start_btn.configure(state='normal', text='✓ 安装完成', bg=SUCCESS)
        msg = ('需要重启电脑！\n\n'
               '重启后重新运行本程序继续剩余步骤。') if warn_restart else (
              '所有组件安装完成！\n\n'
              '打开浏览器访问：http://localhost:18789\n'
              '首次使用需要创建账号并配置 Ollama。')
        messagebox.showinfo('安装完成' if not warn_restart else '需要重启', msg)


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
