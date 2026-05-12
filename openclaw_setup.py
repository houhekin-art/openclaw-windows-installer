#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 环境检查与安装助手
思路：检查 → 安装缺失组件 → 启动 OpenClaw 向导

依赖: Python 3.8+, tkinter (内置)
打包: pyinstaller --onefile --windowed openclaw_setup.py
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

# ============================================================
# 系统检测
# ============================================================
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def get_ram_gb():
    try:
        class MEM(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong)]
        mem = MEM()
        mem.dwLength = ctypes.sizeof(MEM)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        return mem.ullTotalPhys / (1024**3)
    except Exception:
        return 0

def get_disk_free_gb(drive='C'):
    try:
        free = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(drive+':\\'), None, None, ctypes.pointer(free))
        return free.value / (1024**3)
    except Exception:
        return 0

def get_win_version():
    try:
        v = sys.getwindowsversion()
        return f"Windows {v.major}.{v.minor} (Build {v.build})"
    except Exception:
        return "Unknown"

# ============================================================
# PowerShell 执行
# ============================================================
def run_ps(script, capture=True, timeout=120):
    """运行 PowerShell，返回 (returncode, stdout, stderr)"""
    cmd = ['powershell', '-ExecutionPolicy', 'Bypass', '-Command', script]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, '', 'Command timed out'
    except Exception as e:
        return -1, '', str(e)

def run_ps_bg(script):
    """后台运行（不等待结果）"""
    subprocess.Popen(['powershell', '-ExecutionPolicy', 'Bypass', '-Command', script],
                    creation=subprocess.CREATE_NO_WINDOW)

# ============================================================
# 环境检查器
# ============================================================
class EnvChecker:
    """检查各项依赖是否满足"""

    def check_wsl2(self):
        """检查 WSL2"""
        code, out, _ = run_ps('wsl --status 2>&1')
        if code == 0 and ('默认发行版' in out or 'default distribution' in out.lower()):
            return True, "WSL2 已安装"
        code2, out2, _ = run_ps('wsl --list --verbose 2>&1')
        if code2 == 0 and 'Ubuntu' in out2:
            return True, "WSL2 + Ubuntu 已安装"
        return False, "WSL2 未安装"

    def check_docker(self):
        """检查 Docker Desktop"""
        code, out, _ = run_ps('docker --version 2>&1')
        if code == 0:
            # Docker 已安装，检查 daemon 是否运行
            code2, out2, _ = run_ps('docker info 2>&1')
            if code2 == 0:
                return True, f"Docker 已安装: {out}"
            else:
                return False, f"Docker CLI 已安装，但 daemon 未运行，请启动 Docker Desktop"
        return False, "Docker 未安装"

    def check_ollama(self):
        """检查 Ollama"""
        code, out, _ = run_ps('where ollama 2>&1')
        if code == 0:
            code2, out2, _ = run_ps('curl -s http://localhost:11434 2>&1')
            if code2 == 0 and ('Ollama' in out2 or out2):
                return True, "Ollama 服务运行正常"
            return False, "Ollama 已安装，但服务未运行（请重启或手动启动）"
        return False, "Ollama 未安装"

    def check_openclaw(self):
        """检查 OpenClaw 容器"""
        code, out, _ = run_ps('docker ps --filter "name=openclaw" --format "{{.Names}}" 2>&1')
        if code == 0 and 'openclaw' in out:
            return True, "OpenClaw 容器运行中"
        return False, "OpenClaw 容器未运行"

    def get_status_all(self):
        """获取所有组件状态"""
        wsl2_ok, wsl2_msg = self.check_wsl2()
        docker_ok, docker_msg = self.check_docker()
        ollama_ok, ollama_msg = self.check_ollama()
        openclaw_ok, openclaw_msg = self.check_openclaw()

        return {
            'wsl2':   {'ok': wsl2_ok,   'msg': wsl2_msg,   'name': 'WSL2'},
            'docker': {'ok': docker_ok, 'msg': docker_msg,  'name': 'Docker'},
            'ollama': {'ok': ollama_ok, 'msg': ollama_msg,  'name': 'Ollama'},
            'openclaw': {'ok': openclaw_ok, 'msg': openclaw_msg, 'name': 'OpenClaw'},
        }

# ============================================================
# 环境安装器
# ============================================================
class EnvInstaller:
    def __init__(self, log_callback, progress_callback):
        self.log = log_callback
        self.progress = progress_callback
        self._stop = False

    def stop(self):
        self._stop = True

    def log(self, msg, tag='info'):
        self.log(msg, tag)
        self.root_update()

    def root_update(self):
        try:
            import tkinter as tk
            from tkinter import scrolledtext
            for widget in tk.AllWidgets if hasattr(tk, 'AllWidgets') else []:
                pass
        except:
            pass

    def install_wsl2(self):
        self.log('[安装] WSL2...')
        code, out, err = run_ps('wsl --install --no-distribution', timeout=30)
        # wsl --install 会触发异步安装流程
        self.log('  WSL2 安装命令已执行')
        self.log('  注意：可能需要重启电脑才能完成安装')
        self.log('  重启后请重新运行本程序', 'warn')
        return True  # 标记为需要重启

    def install_docker(self):
        self.log('[安装] Docker Desktop（约 600MB）...')
        tmp = os.path.join(tempfile.gettempdir(), 'DockerDesktopInstaller.exe')
        # 下载
        dl_script = (
            f"[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
            f"Invoke-WebRequest -Uri 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe' "
            f"-OutFile '{tmp}'"
        )
        code, out, err = run_ps(dl_script, timeout=600)
        if code != 0 or not os.path.exists(tmp):
            self.log(f'  下载失败: {err}', 'error')
            return False
        self.log(f'  下载完成，安装中（约需 3-5 分钟）...')
        # 静默安装
        code2, out2, err2 = run_ps(
            f'Start-Process "{tmp}" -ArgumentList "install --quiet --accept-license" -Wait',
            timeout=600
        )
        self.log('  Docker Desktop 安装完成', 'ok')
        self.log('  请启动 Docker Desktop，等待右下角图标变绿', 'warn')
        return True

    def install_ollama(self):
        self.log('[安装] Ollama...')
        code, out, err = run_ps(
            "Start-Process msiexec.exe -ArgumentList '/i', 'https://ollama.com/download/OllamaSetup.msi', '/quiet', '/norestart' -Wait",
            timeout=300
        )
        if code != 0:
            self.log(f'  安装失败: {err}', 'error')
            return False
        # 配置环境变量
        run_ps('[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0", "User")')
        run_ps('net stop ollama 2>$null; net start ollama')
        time.sleep(5)
        self.log('  Ollama 安装完成', 'ok')
        return True

    def install_openclaw(self, ollama_ok=False):
        self.log('[安装] OpenClaw 容器...')
        # 先清理旧容器
        run_ps('docker stop openclaw 2>$null; docker rm openclaw 2>$null')
        data_dir = os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'openclaw_data')
        os.makedirs(data_dir, exist_ok=True)
        self.log(f'  数据目录: {data_dir}')

        # 拉取镜像
        self.log('  拉取 OpenClaw 镜像（约 2GB）...')
        code, out, err = run_ps('docker pull openclaw/openclaw:latest', timeout=900)
        if code != 0:
            self.log(f'  镜像拉取失败: {err}', 'error')

        # 启动
        ollama_url = 'http://host.docker.internal:11434' if ollama_ok else 'http://localhost:11434'
        startup = (
            f'docker run -d --name openclaw -p 18789:18789 '
            f'-v "{data_dir}:/workspace" '
            f'-v /var/run/docker.sock:/var/run/docker.sock '
            f'-e OLLAMA_BASE_URL={ollama_url} '
            f'--restart unless-stopped openclaw/openclaw:latest'
        )
        code2, out2, err2 = run_ps(startup, timeout=30)
        if code2 != 0:
            self.log(f'  容器启动失败: {err2}', 'error')
            return False
        self.log('  OpenClaw 容器启动中（约 30 秒后可用）...')
        time.sleep(30)
        self.log('  OpenClaw 安装完成！', 'ok')
        return True

    def install_all(self, to_install):
        """安装选中的组件"""
        results = {}
        for comp in ['wsl2', 'docker', 'ollama', 'openclaw']:
            if not to_install.get(comp):
                continue
            if self._stop:
                break

            if comp == 'wsl2':
                results['wsl2'] = self.install_wsl2()
            elif comp == 'docker':
                results['docker'] = self.install_docker()
            elif comp == 'ollama':
                results['ollama'] = self.install_ollama()
            elif comp == 'openclaw':
                ollama_ok = results.get('ollama') or EnvChecker().check_ollama()[0]
                results['openclaw'] = self.install_openclaw(ollama_ok)

        return results


# ============================================================
# Tkinter UI
# ============================================================
try:
    import tkinter as tk
    from tkinter import scrolledtext, messagebox, ttk
except ImportError:
    print("[错误] 需要 Python 3.8+，请从 https://www.python.org/downloads/ 下载")
    input("按回车退出...")
    sys.exit(1)

# 配色
BG      = '#F0F4F8'
CARD    = '#FFFFFF'
ACCENT  = '#2563EB'
ACCENT2 = '#1D4ED8'
GREEN   = '#16A34A'
RED     = '#DC2626'
ORANGE  = '#D97706'
GRAY    = '#64748B'
BORDER  = '#CBD5E1'
TEXT    = '#1E293B'

TAG_COLORS = {
    'info': TEXT,
    'ok':   GREEN,
    'error': RED,
    'warn': ORANGE,
}


class OpenClawSetupApp:
    def __init__(self, root):
        self.root = root
        self.root.title('OpenClaw 环境安装助手')
        self.root.configure(bg=BG)
        self.root.geometry('820x680')
        self.root.minsize(760, 580)

        self.installer = None
        self.checker = EnvChecker()
        self.components = {}   # {'id': {'ok': bool, 'msg': str, 'name': str}}

        self._build()

    def _build(self):
        # 顶部
        hdr = tk.Frame(self.root, bg=ACCENT, height=72)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text='OpenClaw 环境安装助手',
                 font=('Segoe UI', 17, 'bold'), fg='white', bg=ACCENT,
                 anchor='w', padx=28).pack(fill='x', pady=16)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='both', expand=True, padx=20, pady=15)

        # 左列：状态卡片
        left = tk.Frame(body, bg=BG, width=360)
        left.pack(side='left', fill='y', padx=(0, 15))
        left.pack_propagate(False)

        tk.Label(left, text='环境状态检测',
                 font=('Segoe UI', 12, 'bold'), bg=BG, fg=TEXT, anchor='w').pack(anchor='w', pady=(0, 8))

        self.cards = {}
        comps = [
            ('wsl2',    'WSL2',     'Windows Linux 子系统'),
            ('docker',  'Docker',    '容器化平台'),
            ('ollama',  'Ollama',    '本地 AI 大模型运行时'),
            ('openclaw','OpenClaw',  'AI 助手'),
        ]
        for cid, name, sub in comps:
            fr = tk.Frame(left, bg=CARD, padx=16, pady=12,
                         highlightbackground=BORDER, highlightthickness=1)
            fr.pack(fill='x', pady=4, ipady=6)

            # 状态指示
            ind = tk.Frame(fr, width=16, height=16)
            ind.pack(side='left', padx=(0, 10), anchor='n')
            ind.pack_propagate(False)
            c = tk.Canvas(ind, width=16, height=16, bg=CARD, bd=0, highlightthickness=0)
            c.pack()
            oval = c.create_oval(1, 1, 15, 15, fill=BORDER, outline='')

            info = tk.Frame(fr, bg=CARD)
            info.pack(side='left')
            tk.Label(info, text=name, font=('Segoe UI', 11, 'bold'),
                     bg=CARD, fg=TEXT, anchor='w').pack(anchor='w')
            tk.Label(info, text=sub, font=('Segoe UI', 8), bg=CARD,
                     fg=GRAY, anchor='w').pack(anchor='w')
            self.msg_lbl = tk.Label(fr, text='点击「检测」查看状态',
                                   font=('Segoe UI', 8), bg=CARD, fg=GRAY, anchor='w')
            self.msg_lbl.pack(anchor='w', pady=(3, 0))

            self.cards[cid] = {
                'frame': fr, 'canvas': c, 'oval': oval,
                'ind': ind, 'name': name,
                'msg_lbl': self.msg_lbl,
            }

        # 检测按钮
        tk.Button(left, text='🔄 检测环境', font=('Segoe UI', 10, 'bold'),
                  bg=ACCENT, fg='white', relief='flat', cursor='hand2',
                  padx=16, pady=7, command=self.check_all).pack(pady=(12, 0), ipady=2, fill='x')

        # 右列：操作区
        right = tk.Frame(body, bg=BG)
        right.pack(side='left', fill='both', expand=True)

        # 系统信息
        sys_fr = tk.Frame(right, bg=CARD, padx=16, pady=12,
                         highlightbackground=BORDER, highlightthickness=1)
        sys_fr.pack(fill='x', pady=(0, 12))
        self.sys_lbl = tk.Label(sys_fr, text='正在检测系统...',
                                font=('Segoe UI', 9), bg=CARD, fg=TEXT, anchor='w', justify='left')
        self.sys_lbl.pack(anchor='w')

        # 安装选项
        opt_fr = tk.Frame(right, bg=CARD, padx=16, pady=12,
                         highlightbackground=BORDER, highlightthickness=1)
        opt_fr.pack(fill='x', pady=(0, 12))
        tk.Label(opt_fr, text='选择要安装的组件：',
                 font=('Segoe UI', 11, 'bold'), bg=CARD, fg=TEXT, anchor='w').pack(anchor='w')
        self.opts = {}
        for cid, name, sub in comps:
            var = tk.BooleanVar(value=False)
            cb = tk.Checkbutton(opt_fr, text=f'{name}  — {sub}',
                               variable=var, font=('Segoe UI', 10),
                               bg=CARD, fg=TEXT, anchor='w',
                               activebackground=CARD, selectcolor='#DBEAFE',
                               command=lambda c=cid, v=var: self._toggle_opt(c, v))
            cb.pack(anchor='w', padx=10, pady=2)
            self.opts[cid] = var

        # 按钮行
        btn_fr = tk.Frame(right, bg=BG)
        btn_fr.pack(fill='x', pady=(0, 10))

        self.install_btn = tk.Button(btn_fr, text='▶ 开始安装',
                                    font=('Segoe UI', 11, 'bold'),
                                    bg=ACCENT, fg='white', relief='flat',
                                    cursor='hand2', padx=20, pady=7,
                                    state='disabled', command=self.start_install)
        self.install_btn.pack(side='left')

        self.open_btn = tk.Button(btn_fr, text='🌐 打开 OpenClaw',
                                  font=('Segoe UI', 11, 'bold'),
                                  bg=GREEN, fg='white', relief='flat',
                                  cursor='hand2', padx=20, pady=7,
                                  state='disabled', command=self.open_openclaw)
        self.open_btn.pack(side='left', padx=(10, 0))

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

        self.root.after(300, self.check_all)
        self.root.after(500, self.update_sys_info)

    def update_sys_info(self):
        ram = get_ram_gb()
        disk = get_disk_free_gb('C')
        win = get_win_version()
        parts = [f'系统：{win}',
                 f'内存：{ram:.1f} GB',
                 f'C盘可用：{disk:.1f} GB']
        if ram < 8:
            parts.append(f'⚠ 内存偏低，建议 16GB+')
        if disk < 30:
            parts.append(f'⚠ 空间偏低，建议 50GB+')
        self.sys_lbl.configure(text=' | '.join(parts))

        # Admin check
        if not is_admin():
            self.install_btn.configure(state='disabled', text='⚠ 需管理员权限')
            self.log('[警告] 请右键「以管理员身份运行」程序', 'warn')

    def _toggle_opt(self, cid, var):
        """勾选变化时更新按钮文字"""
        selected = sum(v.get() for v in self.opts.values())
        if selected > 0:
            self.install_btn.configure(state='normal', text=f'▶ 安装 ({selected}项)')

    def update_card(self, cid, ok, msg):
        """更新单个组件卡片状态"""
        if cid not in self.cards:
            return
        c = self.cards[cid]
        color = GREEN if ok else RED
        c['canvas'].itemconfig(c['oval'], fill=color)
        c['msg_lbl'].configure(text=msg,
                               fg=GREEN if ok else ORANGE if '未运行' in msg else RED)

    def check_all(self):
        """检测所有组件"""
        self.log('正在检测环境...')
        results = self.checker.get_status_all()
        self.components = results

        for cid, info in results.items():
            self.update_card(cid, info['ok'], info['msg'])
            self.log(f"  {info['name']}: {info['ok'] and '✓' or '✗'} {info['msg']}")

        # 自动勾选未安装的
        any_missing = False
        for cid, info in results.items():
            self.opts[cid].set(not info['ok'])
            if not info['ok']:
                any_missing = True

        # 开放安装按钮
        if any_missing:
            count = sum(not info['ok'] for info in results.values())
            self.install_btn.configure(state='normal', text=f'▶ 安装 ({count}项)')
        else:
            self.install_btn.configure(state='normal', text='✅ 全部就绪')

        # 如果全部就绪，开启打开按钮
        all_ok = all(info['ok'] for info in results.values())
        if all_ok:
            self.open_btn.configure(state='normal')
            self.log('所有组件已就绪！点击「打开 OpenClaw」继续', 'ok')

    def log(self, msg, tag='info'):
        color = TAG_COLORS.get(tag, TEXT)
        self.log_txt.configure(state='normal')
        self.log_txt.insert('end', msg + '\n', tag)
        self.log_txt.tag_config(tag, foreground=color)
        self.log_txt.see('end')
        self.log_txt.configure(state='disabled')
        self.root.update_idletasks()

    def start_install(self):
        if not is_admin():
            messagebox.showwarning('权限不足', '请右键选择「以管理员身份运行」！')
            return

        to_install = {cid: var.get() for cid, var in self.opts.items()}
        if not any(to_install.values()):
            messagebox.showwarning('未选择', '请至少选择一个要安装的组件')
            return

        # 禁用按钮
        self.install_btn.configure(state='disabled', text='安装中...')
        self.log('=' * 50)
        self.log('开始安装...')
        self.log(f'将安装: {[cid for cid, v in to_install.items() if v]}')
        self.log('=' * 50)

        self.installer = EnvInstaller(log_callback=self.log, progress_callback=None)
        threading.Thread(target=self._do_install, args=(to_install,), daemon=True).start()

    def _do_install(self, to_install):
        results = self.installer.install_all(to_install)
        self.root.after(0, self._install_done, results)

    def _install_done(self, results):
        self.log('')
        self.log('=' * 50, 'ok')
        self.log('安装阶段完成！', 'ok')
        self.log('=' * 50)

        # 检测哪些需要重启
        if results.get('wsl2'):
            self.log('')
            self.log('需要重启电脑！', 'warn')
            self.log('重启后重新运行本程序完成剩余步骤', 'warn')
            messagebox.showwarning('需要重启',
                'WSL2 安装需要重启电脑。\n\n'
                '请保存好工作，重启后重新运行本程序。')
        else:
            self.log('')
            self.log('建议：点击「检测环境」确认安装结果', 'info')
            self.log('确认全部就绪后，点击「打开 OpenClaw」继续配置', 'ok')
            self.check_all()

        self.install_btn.configure(state='normal', text='▶ 重新检测')

    def open_openclaw(self):
        import webbrowser
        self.log('正在打开浏览器...')
        webbrowser.open('http://localhost:18789')


if __name__ == '__main__':
    root = tk.Tk()
    OpenClawSetupApp(root)
    root.mainloop()
