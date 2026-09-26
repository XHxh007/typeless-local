# -*- coding: utf-8 -*-
"""
右 Alt 钩子验证 —— 确认「只有右边那颗 Alt 能触发」。

跑起来后：
  1. 按几次【左 Alt】
  2. 按几次【右 Alt】
  3. 按几个别的键（Ctrl / Shift / 空格）

输出里应该只有「右 Alt」行带 ✔ TRIGGER，其余全是「忽略」。
按 Ctrl+C 看统计。

    python test_right_alt.py
"""

import ctypes
import time
from ctypes import wintypes

LLKHF_EXTENDED = 0x01
VK_RMENU = 0xA5
VK_LMENU = 0xA4

ULONG_PTR = ctypes.c_size_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
WM_KEYUP, WM_SYSKEYUP = 0x0101, 0x0105

stats = {"left": 0, "right": 0, "other": 0}
t0 = time.time()


def main():
    user32 = ctypes.windll.user32
    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM)

    # 必须先声明原型：否则 ctypes 按 32 位 C int 处理 WPARAM/LPARAM，
    # 64 位下值一大就抛 OverflowError，CallNextHookEx 返回值也不可靠。
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                         wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t

    def proc(n_code, w_param, l_param):
        if n_code >= 0:
            try:
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                up = w_param in (WM_KEYUP, WM_SYSKEYUP)
                if not (down or up):
                    return user32.CallNextHookEx(None, n_code, w_param, l_param)

                ext = bool(kb.flags & LLKHF_EXTENDED)
                el = time.time() - t0
                tag = f"[{el:6.2f}s]"

                if kb.vkCode == VK_RMENU and ext:
                    # 这正是我们要的：右 Alt
                    if down:
                        stats["right"] += 1
                    kind = "按下" if down else "松开"
                    mark = "✔ TRIGGER" if down else "  (release)"
                    print(f"{tag} 右 Alt  {kind}  vk={kb.vkCode:#x} "
                          f"scan={kb.scanCode} flags={kb.flags:#x}  {mark}",
                          flush=True)
                elif kb.vkCode == VK_LMENU or (kb.vkCode == VK_RMENU and not ext):
                    # 左 Alt；或者是没带扩展位的 Alt（= 左 Alt）
                    if down:
                        stats["left"] += 1
                    kind = "按下" if down else "松开"
                    print(f"{tag} 左 Alt  {kind}  vk={kb.vkCode:#x} "
                          f"scan={kb.scanCode} flags={kb.flags:#x}  "
                          f"← 忽略（不该触发）", flush=True)
                elif down and up is False and ext:
                    # 右键盘上的其他扩展键（右 Ctrl 等），打出来供参考
                    stats["other"] += 1
                    print(f"{tag} 其他键  按下  vk={kb.vkCode:#x} "
                          f"scan={kb.scanCode} flags={kb.flags:#x}  ← 忽略",
                          flush=True)
            except Exception as e:
                print(f"  (回调异常: {e})", flush=True)
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    hproc = HOOKPROC(proc)
    hhook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, hproc, None, 0)
    print("钩子句柄 =", hhook)
    if not hhook:
        print("钩子装不上，测不了。")
        return

    print("请按：先按几次【左 Alt】，再按几次【右 Alt】，然后按 Ctrl/Shift/空格")
    print("观察哪一行带 ✔ TRIGGER。Ctrl+C 结束看统计。\n", flush=True)

    class MSG(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD), ("pt_x", wintypes.LONG),
                    ("pt_y", wintypes.LONG)]

    msg = MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except KeyboardInterrupt:
        pass
    finally:
        user32.UnhookWindowsHookEx(hhook)
        print(f"\n统计：左 Alt {stats['left']} 次 / 右 Alt {stats['right']} 次 "
              f"/ 其他扩展键 {stats['other']} 次")
        if stats["right"] > 0 and stats["left"] > 0:
            print("✔ 左右区分正常：右 Alt 触发，左 Alt 被忽略")
        elif stats["right"] > 0:
            print("✔ 右 Alt 能触发（左 Alt 没测到，再按几次左 Alt 确认）")
        else:
            print("✘ 没检测到右 Alt，检查是不是按了右边那颗 Alt")


if __name__ == "__main__":
    main()
