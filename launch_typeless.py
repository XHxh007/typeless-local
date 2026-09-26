# -*- coding: utf-8 -*-
"""
脱离启动器 —— 用 DETACHED_PROCESS 拉起 typeless_local.py。

为什么需要它：

  `start /b` 会让子进程**共享父进程的控制台**。父 cmd 一退出、控制台关闭，
  子进程就会收到 CTRL_CLOSE_EVENT 被直接杀掉。表现是：

      日志显示启动成功（有 HOOK_STATUS=right_alt_ok）
      → 过一会儿进程悄悄消失
      → 按热键完全没反应

  同理，`pythonw xxx.py &`（shell 后台）也会随会话结束被回收。

  DETACHED_PROCESS 让子进程不依附任何控制台，关掉启动窗口不影响它。

用法（一般由 start_typeless.bat 调用）：

    python launch_typeless.py
    python launch_typeless.py --python "D:\\Python311\\python.exe"   # 手动指定解释器
"""

import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(BASE, "typeless_local.py")

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

# 常见的 Python 安装位置。找不到 pythonw.exe 时挨个探一遍。
COMMON_DIRS = [
    r"C:\Python312", r"C:\Python311", r"C:\Python310", r"C:\Python39",
    r"C:\ProgramData\anaconda3", r"C:\ProgramData\miniconda3",
    os.path.expanduser(r"~\anaconda3"),
    os.path.expanduser(r"~\miniconda3"),
    os.path.expanduser(r"~\AppData\Local\Programs\Python"),
    r"C:\Program Files\Python312", r"C:\Program Files\Python311",
]


def find_pythonw(explicit=None):
    """找一个能用的 pythonw.exe，返回绝对路径或 None。

    顺序：显式指定 → 当前解释器同目录 → PATH → 常见安装位置 → py 启动器。

    为什么优先 pythonw 而不是 python：pythonw 是无窗口版本，不会弹出黑色
    控制台窗口。日常常驻工具必须用它，否则每次开机都挂一个黑框。

    为什么"当前解释器同目录"排在 PATH 前面：调用方（start_typeless.bat）
    已经按 "找得到 tkinter" 的顺序挑好了一个 Python，跟着它更可靠。PATH 里
    第一个 pythonw 未必带 tkinter —— 精简版/嵌入式发行版就没有，UI 会静默
    降级成不显示（实测踩过）。
    """
    if explicit:
        return explicit if os.path.isfile(explicit) else None

    # 1) 当前跑这个脚本的解释器旁边（最常见：bat 用的就是它）
    here = os.path.dirname(os.path.abspath(sys.executable))
    cand = os.path.join(here, "pythonw.exe")
    if os.path.isfile(cand):
        return cand

    # 2) PATH
    hit = shutil.which("pythonw")
    if hit:
        return hit

    # 3) 常见安装目录（含 envs / 子版本目录）
    for d in COMMON_DIRS:
        cand = os.path.join(d, "pythonw.exe")
        if os.path.isfile(cand):
            return cand
        if os.path.isdir(d):
            try:
                for sub in sorted(os.listdir(d), reverse=True):
                    cand = os.path.join(d, sub, "pythonw.exe")
                    if os.path.isfile(cand):
                        return cand
            except OSError:
                pass

    # 4) 最后试 py 启动器（pyw.exe 是它的无窗口版）
    for name in ("pyw", "py"):
        hit = shutil.which(name)
        if hit:
            return hit
    return None


def already_running():
    """单实例探测。

    主程序自己用端口 8765 做锁（见 typeless_local.py 的 ensure_single_instance）。
    但这里**不能只看端口** —— 8765 是常见端口，可能被别的程序占着，那样
    会让启动器误判"已经在跑"而拒绝启动（实测踩过）。

    所以两个条件同时满足才算已经在跑：
      1) 8765 端口被占
      2) 确实有 pythonw.exe 进程
    """
    import socket
    port_busy = False
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 8765))
    except OSError:
        port_busy = True
    finally:
        s.close()
    if not port_busy:
        return False

    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq pythonw.exe"],
            text=True, stderr=subprocess.DEVNULL,
            creationflags=0x08000000,   # CREATE_NO_WINDOW，避免闪黑框
        )
        return "pythonw" in out.lower()
    except Exception:
        # 查不到进程就保守认为没在跑，让用户自己按热键验证
        return False


def main():
    argv = sys.argv[1:]
    explicit = None
    if "--python" in argv:
        i = argv.index("--python")
        explicit = argv[i + 1] if len(argv) > i + 1 else None

    if not os.path.isfile(SCRIPT):
        print(f"找不到 {SCRIPT}")
        return 1

    pyw = find_pythonw(explicit)
    if not pyw:
        print("找不到 pythonw.exe。")
        print("请手动指定：python launch_typeless.py --python \"你的\\pythonw.exe 完整路径\"")
        print("或者把 Python 加进 PATH 后重试。")
        return 1
    print(f"解释器: {pyw}")

    if already_running():
        print("TypelessLocal 已经在运行（端口 8765 被占），不再启动第二个。")
        return 0

    # py 启动器要用 `pyw -3` 的形式；直接给 exe 路径则不用额外参数
    cmd = [pyw, SCRIPT]
    if os.path.basename(pyw).lower().startswith("py"):
        cmd = [pyw, "-3", SCRIPT]

    proc = subprocess.Popen(
        cmd,
        cwd=BASE,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    print(f"已拉起 PID={proc.pid}（已脱离当前会话，关掉本窗口不影响它）")

    import time
    time.sleep(4)
    code = proc.poll()
    if code is None:
        print("[OK] 进程存活。")
        return 0
    print(f"[FAIL] 进程已退出，code={code}。看 typeless.log 找原因。")
    return 2


if __name__ == "__main__":
    sys.exit(main())
