# -*- coding: utf-8 -*-
"""
右 Alt 钩子自动验证 —— 不需要人按键。

用 keybd_event 模拟按下「左 Alt」和「右 Alt」，检查只有右 Alt 触发。

为什么需要这个：钩子装得上（SetWindowsHookExW 成功）**不代表**回调能收到事件。
底层键盘钩子的回调必须在「安装钩子的那个线程」的消息循环里执行，
拆成两个线程就会静默失效 —— 这个脚本能自动抓出这种情况。

注意：会短暂向系统发送 Alt 按键（每次约 60ms）。

    python test_hook_auto.py
"""

import ctypes
import time

import typeless_local as t

fired = []


def fake_fire():
    fired.append(time.time())


# 拦掉真正的触发动作，避免测试时真的开始录音
t.fire_hotkey = fake_fire

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
VK_LMENU = 0xA4      # 左 Alt
VK_RMENU = 0xA5      # 右 Alt


def press(vk, extended):
    """模拟一次完整按键（按下 → 松开）。extended=True 模拟右侧那颗键。"""
    user32 = ctypes.windll.user32
    down = KEYEVENTF_EXTENDEDKEY if extended else 0
    user32.keybd_event(vk, 0, down, 0)
    time.sleep(0.06)
    user32.keybd_event(vk, 0, down | KEYEVENTF_KEYUP, 0)
    time.sleep(0.30)


def main():
    print("安装钩子 ...", flush=True)
    ok = t._install_right_alt_hook()
    print("安装结果 =", ok, flush=True)
    if not ok:
        print("钩子装不上，无法继续测试", flush=True)
        return 1
    time.sleep(0.6)

    print("\n[1] 模拟按下【左 Alt】...", flush=True)
    press(VK_LMENU, extended=False)
    n_left = len(fired)
    print(f"    触发 {n_left} 次（期望 0）", flush=True)

    print("[2] 模拟按下【右 Alt】...", flush=True)
    before = len(fired)
    press(VK_RMENU, extended=True)
    n_right1 = len(fired) - before
    print(f"    触发 {n_right1} 次（期望 1）", flush=True)

    print("[3] 再模拟一次【右 Alt】...", flush=True)
    before = len(fired)
    press(VK_RMENU, extended=True)
    n_right2 = len(fired) - before
    print(f"    触发 {n_right2} 次（期望 1）", flush=True)

    t._uninstall_hook()

    print("\n===== 结论 =====", flush=True)
    if n_left == 0 and n_right1 == 1 and n_right2 == 1:
        print("✔ 通过：只有右 Alt 触发，左 Alt 被正确忽略", flush=True)
        return 0
    if n_right1 == 0 and n_right2 == 0:
        print("✘ 失败：右 Alt 也没触发 —— 钩子回调没生效"
              "（多半是安装线程与消息循环不在同一个线程）", flush=True)
        return 2
    if n_left > 0:
        print(f"✘ 失败：左 Alt 也触发了 {n_left} 次，左右没区分开", flush=True)
        return 3
    print(f"? 异常：左 {n_left} 次 / 右 {n_right1 + n_right2} 次", flush=True)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
