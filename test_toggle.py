# -*- coding: utf-8 -*-
"""验证"一次完整按键 = 一次触发"的切换逻辑（不录音、不弹窗）。"""
import time
import ui


class FakePill:
    def show(self, *a, **k):
        pass

    def set_level(self, *a):
        pass

    def hide(self, *a):
        pass


ui.Pill = lambda *a, **k: FakePill()

import typeless_local as T

T.hotkey_scan = 29
T.END_GRACE = 0.0
T.stop_and_process = lambda: (print("   -> 结束录音"),
                              setattr(T, "recording", False))


class Ev:
    def __init__(self, scan):
        self.scan_code = scan
        self.name = "right ctrl" if scan == 29 else "other"


def reset():
    T.recording = False
    T.armed = True
    T.last_toggle_at = 0.0
    T.last_press_at = 0.0


def case(name, fn):
    reset()
    print(f"\n[{name}]")
    fn()


def c1():
    T.on_any_press(Ev(29))
    print("  按下一次后 recording =", T.recording, "| armed =", T.armed)
    assert T.recording and not T.armed


def c2():
    """按住不放：系统刷一串重复 keydown，不能把录音关掉。"""
    T.on_any_press(Ev(29))
    for i in range(8):
        time.sleep(0.05)
        T.on_any_press(Ev(29))
    print("  按住刷 8 次重复事件后 recording =", T.recording)
    assert T.recording


def c3():
    """完整两次点击：开始 → 结束。"""
    T.on_any_press(Ev(29))
    T.on_any_release(Ev(29))
    time.sleep(0.5)
    T.on_any_press(Ev(29))
    print("  第二次完整按下后 recording =", T.recording)
    assert not T.recording


def c4():
    """keyup 丢失：超过 KEYUP_TIMEOUT 后自动放行，不能彻底卡死。"""
    T.on_any_press(Ev(29))          # 开始
    # 假装过了很久（两次按下真实间隔也是秒级），期间没收到任何松开事件
    T.last_press_at -= T.KEYUP_TIMEOUT + 0.1
    T.last_toggle_at -= T.KEYUP_TIMEOUT + 0.1
    T.on_any_press(Ev(29))
    print("  keyup 丢失后仍能切换 recording =", T.recording)
    assert not T.recording


def c5():
    """别的键不触发。"""
    T.on_any_press(Ev(56))
    print("  按 right alt(56) 后 recording =", T.recording)
    assert not T.recording


for n, f in [("1 按一次开始", c1), ("2 按住不放不结束", c2),
             ("3 两次完整点击=开始+结束", c3), ("4 keyup 丢失不卡死", c4),
             ("5 其他键不触发", c5)]:
    try:
        case(n, f)
        print("  ✓ 通过")
    except AssertionError:
        print("  ✗ 失败")

print("\n全部用例跑完。")
