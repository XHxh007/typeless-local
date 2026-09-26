# -*- coding: utf-8 -*-
"""
Typeless 本地版 —— 按一下右 Alt 开始说话，再按一下结束，文字直接落在光标处。

链路：右 Alt（底层钩子）→ 录音 → SenseVoice 转写 → Ollama 润色 → 上屏
全程本地，不联网（Ollama 走 localhost）。

依赖：pip install -r requirements.txt
      模型放 models/sense-voice/，怎么下见 README「准备模型」一节。

运行：python typeless_local.py
      python typeless_local.py --file your.wav   离线验证，不录音不上屏
      python typeless_local.py --selftest        麦克风 / 转写 / 输出 三步自测
      python typeless_local.py --keys            按键诊断（带时间戳）

Windows 下建议在管理员权限的终端里跑，否则无法向高权限窗口输入。
"""

import json
import os
import socket
import sys
import threading
import time
import wave

import ctypes

import numpy as np
import sounddevice as sd
import keyboard
import pyperclip

from asr import get_engine
from polish import polish, warmup
from ui import Pill

SAMPLE_RATE = 16000
# 所有路径都基于脚本所在目录，不依赖"当前工作目录"——
# 开机自启时（vbs + pythonw）工作目录是系统目录，相对路径会全部失效，进程直接崩。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 触发键：只用右侧 Alt（右 Alt，即 AltGr 位置那颗）。其他任何键都不触发。
#
# 为什么不用 keyboard 库的 scan_code 判定：
#   keyboard 库只提供基础扫描码，不做左右区分。实测这台机器上
#   `keyboard.key_to_scan_codes('right alt')` 和 `('left alt')` 都返回 56，
#   右 Ctrl / 左 Ctrl 同样都是 29。也就是说靠 scan_code 根本分不出左右。
#
# 精确区分左右靠底层键盘钩子（WH_KEYBOARD_LL）里的扩展位标志：
#   右 Alt / 右 Ctrl 的扫描码会带 0x100 位（对应 E0 前缀），左键没有。
#   所以判据是 `flags & LLKHF_EXTENDED`。
HOTKEY_IS_RIGHT_ALT = True     # 开关：True = 只认右 Alt
LLKHF_EXTENDED = 0x01          # KBDLLHOOKSTRUCT.flags 的扩展位
VK_RMENU = 0xA5                # 右 Alt 的虚拟键码（左 Alt 是 0xA4）
HOTKEY_NAME = "Right Alt（右 Alt）"
# 宽限期：改用"完整按键"判定后已经不需要了，设 0 最跟手。
# 真遇到重复事件误触发，把它调回 2.0 就会多一层保险。
END_GRACE = 0.0
# 按下后等多久没收到 keyup 就强制放行（防 keyup 丢失导致热键卡死）
KEYUP_TIMEOUT = 3.0
CONFIG_FILE = os.path.join(BASE_DIR, "hotkey.json")
DEBOUNCE = 0.35                # 按住会连续触发 keydown，350ms 内的重复事件忽略
# 日常高频键，选它们当热键会疯狂误触
BUSY_SCAN_CODES = {42, 54, 29, 56, 15, 28, 58, 57}
# 输出方式：type=逐字模拟键盘输入（Typeless 默认，直接落在光标处，不动剪贴板）
#           paste=复制后模拟 Ctrl+V（更快，但在终端/部分编辑器会失效）
OUTPUT_MODE = "type"
PASTE_THRESHOLD = 50        # type 模式下超过这么多字自动改用 Ctrl+V
ASR_ENGINE = "sensevoice"      # 或 "whisper"
OLLAMA_MODEL = "qwen2.5:7b"
MIN_SECONDS = 0.35             # 短于此视为误触
MAX_SECONDS = 120
INSTANCE_PORT = 8765           # 单实例锁：端口被占说明已在运行
LOG_FILE = os.path.join(BASE_DIR, "typeless.log")   # 无窗口运行（pythonw）时的日志
# None = 自动选（跳过 PICO 等虚拟设备）。自动选错时，填你耳机/麦克风的名字关键词，
# 例如 "Realtek"、"漫步者"、"智音"。
MIC_DEVICE = None
MIN_RMS = 0.0025               # 低于此音量视为没录到人声

# 这些是虚拟/非人声设备，录音时自动避开
VIRTUAL_DEVICES = ("pico", "声音映射器", "立体声混音", "主声音捕获")

recording = False
chunks = []
lock = threading.Lock()
engine = None
pill = Pill()                  # 悬浮状态胶囊（创建失败会自动降级为空操作）
input_sr = SAMPLE_RATE         # 实际录音采样率（蓝牙麦可能只有 8k/16k）
hotkey_scan = None             # 运行时确定的热键 scan_code
last_toggle_at = 0.0           # 上次切换时刻，用来过滤按住产生的重复 keydown
rec_started_at = 0.0           # 本次录音开始时刻，用来算宽限期
armed = True                   # True = 上次按键已松开，新的按下可以生效
last_press_at = 0.0            # 上次按下的时刻，配合 KEYUP_TIMEOUT 防卡死
_lock_socket = None


def pick_input_device():
    """返回 (device_id, 设备名)。默认设备是虚拟麦时自动换第一个真实麦。

    优先切到 WASAPI：MME 后端在这台机器上开阵列麦克风会报
    `MME error 1`（开机自启、音频服务还没就绪时必崩），整个进程直接没。
    """
    devs = sd.query_devices()

    def pick_from(indices):
        """在给定设备索引里挑第一个真实（非虚拟）麦克风。"""
        for i in indices:
            d = devs[i]
            n = d["name"].lower()
            if d["max_input_channels"] <= 0:
                continue
            if any(p in n for p in VIRTUAL_DEVICES):
                continue
            if not MIC_DEVICE or MIC_DEVICE.lower() in n:
                return i, d["name"]
        return None

    # 先在 WASAPI 下找：MME 后端在这台机器上开阵列麦克风会报 MME error 1
    wasapi = [i for i, h in enumerate(sd.query_hostapis())
              if "WASAPI" in h["name"]]
    for api in wasapi:
        hit = pick_from([i for i, d in enumerate(devs) if d["hostapi"] == api])
        if hit:
            return hit
    hit = pick_from(range(len(devs)))
    if hit:
        return hit
    di = sd.default.device[0]
    return di, devs[di]["name"] if 0 <= di < len(devs) else ""


def resample_to_16k(audio, sr):
    """线性插值重采样到 16k。蓝牙耳机麦常是 8k/44.1k，直接喂模型会出错。"""
    if sr == SAMPLE_RATE:
        return audio
    n = int(len(audio) * SAMPLE_RATE / sr)
    return np.interp(
        np.linspace(0.0, len(audio) - 1, n),
        np.arange(len(audio)),
        audio,
    ).astype(np.float32)


def audio_callback(indata, frames, time_info, status):
    if recording:
        with lock:
            chunks.append(indata.copy())
        pill.set_level(float(np.sqrt(np.mean(indata ** 2))))


def paste_text(text, dry=False):
    """把文字送到当前光标处。

    短句逐字敲（不碰剪贴板）；超过 PASTE_THRESHOLD 字就自动改用 Ctrl+V，
    否则几百字要一个字一个字蹦好几秒。
    """
    if dry:
        return
    mode = OUTPUT_MODE
    if mode == "type" and len(text) > PASTE_THRESHOLD:
        mode = "paste"
    print(f"  上屏方式: {mode}（{len(text)} 字）")
    if mode == "type":
        # 逐字模拟键盘输入：不碰剪贴板，跟自己敲键盘一样落在光标处
        keyboard.write(text, delay=0)
        return
    old = None
    try:
        old = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(text)
    keyboard.send("ctrl+v")
    if old is not None:
        threading.Timer(1.0, lambda: pyperclip.copy(old)).start()


CAPS_VK = 0x14
suppress_hotkey = False        # 抑制我们自己模拟的 CapsLock，避免再次触发录音


def caps_lock_on():
    return bool(ctypes.windll.user32.GetKeyState(CAPS_VK) & 1)


def restore_caps_lock():
    """历史遗留：曾用 CapsLock 当热键时需要还原大小写。

    现在热键固定为右 Alt（不会翻转任何锁定状态），这个函数已不再被调用，
    保留是为了以后真要用 CapsLock 时不至于重新造一遍。
    """
    global suppress_hotkey
    if not caps_lock_on():
        return
    suppress_hotkey = True
    try:
        keyboard.press_and_release("caps lock")
    except Exception:
        pass
    threading.Timer(0.6, _clear_suppress).start()


def _clear_suppress():
    global suppress_hotkey
    suppress_hotkey = False


def process(audio, dry=False):
    t0 = time.time()
    audio = resample_to_16k(audio.flatten().astype(np.float32), input_sr)
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < MIN_RMS:
        print(f"  ⚠ 录音音量过低 (RMS {rms:.4f})，像是没录到人声，不上屏")
        print("    → 改 typeless_local.py 里 MIC_DEVICE 指定你的耳机/麦克风名")
        pill.show("warn", "no audio")
        return
    raw, t_asr = engine.transcribe(audio, SAMPLE_RATE)
    if not raw:
        print("  (没听清)")
        return
    print(f"  原始: {raw}")

    try:
        out, mode, t_pol = polish(raw, model=OLLAMA_MODEL, verbose=True)
    except Exception as e:
        # Ollama 没起来（502 / 拒绝连接）时不能让整段话消失 —— 降级为原文上屏
        print(f"  ⚠ 润色调用失败: {type(e).__name__}: {e}")
        print("    → Ollama 没在运行？先原样上屏，不润色")
        out, mode, t_pol = raw, "raw(no-llm)", 0.0
    print(f"  模式: {mode} | 转写 {t_asr:.2f}s + 润色 {t_pol:.2f}s = "
          f"{time.time() - t0:.2f}s")
    if mode == "skip":
        print(f"  ⚠ 只识别到「{raw}」，内容太短不上屏（喂给模型会编造）")
        pill.show("warn", "too short")
        return
    if mode == "blocked":
        print("  ⚠ 模型输出疑似幻觉，已拦截，不上屏")
        pill.show("warn", "blocked")
        return
    print(f"  输出:\n{out}\n")
    paste_text(out, dry)
    if not dry:
        pill.show("done")


def start_recording():
    global recording, chunks, rec_started_at
    if recording:
        return
    with lock:
        chunks = []
    recording = True
    rec_started_at = time.time()
    pill.show("recording")
    print(f"\n● 录音中... (再按一次 {HOTKEY_NAME} 结束)")


def stop_and_process():
    global recording
    if not recording:
        return
    recording = False
    with lock:
        if not chunks:
            print("  ⚠ 录音流没送来任何数据（麦克风没工作），已放弃本次")
            pill.show("warn", "no audio")
            return
        audio = np.concatenate(chunks, axis=0)
    dur = len(audio) / SAMPLE_RATE
    if dur < MIN_SECONDS:
        print(f"  ({dur:.2f}s 太短，忽略)")
        pill.show("warn", "too short")
        return
    if dur > MAX_SECONDS:
        print(f"  ({dur:.0f}s 超长，截断)")
        audio = audio[: int(MAX_SECONDS * SAMPLE_RATE)]
    print(f"○ 结束，{dur:.1f}s 音频")
    pill.show("processing")
    threading.Thread(target=process, args=(audio,), daemon=True).start()


def toggle_recording():
    if recording:
        stop_and_process()
    else:
        start_recording()


def load_hotkey_scan():
    """兼容旧配置：读 hotkey.json 里记的 scan_code（仅兜底路径会用）。"""
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f).get("scan_code")
        except Exception:
            pass
    return None


def capture_hotkey():
    print("\n还没设置触发键 —— 请按一次你想用来录音的键")
    print("（建议选平时不用的：右 Ctrl、右 Alt、F13~F24 之类）...", flush=True)
    while True:
        ev = keyboard.read_event()
        if ev.event_type == keyboard.KEY_DOWN:
            break
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"scan_code": ev.scan_code, "name": ev.name}, f)
    print(f"已记住: scan_code={ev.scan_code}  name={ev.name!r}", flush=True)
    if ev.scan_code in BUSY_SCAN_CODES:
        print("⚠ 这个键日常用得很多，容易误触录音。"
              "想换就删掉 hotkey.json 重新运行。", flush=True)
    print(flush=True)
    return ev.scan_code


def is_hotkey(e):
    """兜底路径的判定：只认 scan_code，且必须是右 Alt 的那颗。

    注意 keyboard 库分不出左右 Alt（都是 56），所以这条路径下左 Alt
    也会触发 —— 只有底层钩子才能做到严格区分。正常流程不走这里。
    """
    sc = getattr(e, "scan_code", None)
    return sc == hotkey_scan


# ---- 精确识别右 Alt：底层键盘钩子 ----
# keyboard 库的 scan_code 分不出左右（左右 Alt 都是 56），
# 所以右 Alt 单独走 WH_KEYBOARD_LL 钩子，读 flags 的扩展位。
_hook_handle = None
_hook_proc = None          # 必须全局持有，否则回调被 GC 回收会直接崩
_hook_ready = threading.Event()
_hook_ok = False


def _install_right_alt_hook():
    """装底层钩子，只在「右侧 Alt」的按下/松开时切换录音。

    返回 True 表示装好了。装不上（非 Windows / 权限不足）返回 False，
    此时退化成 keyboard 库的 scan_code 判定，会左右 Alt 都触发。
    """
    global _hook_handle, _hook_proc
    if os.name != "nt":
        return False

    import ctypes
    from ctypes import wintypes

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

    user32 = ctypes.windll.user32
    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM)

    # 必须先声明原型。ctypes 对未声明的外部函数按 32 位 C int 处理参数，
    # 而 64 位下 WPARAM/LPARAM 是 8 字节指针宽度 —— 值一大就抛
    # "OverflowError: int too long to convert"。后果不只是刷屏报错：
    # CallNextHookEx 拿不到正确返回值会打断钩子链，影响系统里其他程序的热键。
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                         wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL

    def _proc(n_code, w_param, l_param):
        # 整个回调体包在 try 里：钩子回调抛异常会被 ctypes 打到 stderr，
        # 而且返回值不可靠。宁可静默失败，也不能影响按键的正常传递。
        try:
            if n_code >= 0:
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                # 右 Alt = 扩展位 + 右 Alt 虚拟键码，两个条件都满足才算
                if kb.vkCode == VK_RMENU and (kb.flags & LLKHF_EXTENDED):
                    if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        fire_hotkey()
                    elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                        global armed
                        armed = True
        except Exception:
            pass
        try:
            return user32.CallNextHookEx(None, n_code, w_param, l_param)
        except Exception:
            return 0

    _hook_proc = HOOKPROC(_proc)     # 全局持有，防止被 GC

    def _body():
        """装钩子 + 泵消息，**必须在同一个线程里**完成。

        为什么不能拆开：WH_KEYBOARD_LL 的回调是在安装钩子的那个线程里被调用
        的（系统往该线程的消息队列投递消息来触发）。最初写成"主线程装钩子、
        另开线程泵消息"，结果钩子能装上（SetWindowsHookExW 返回非 0）但按键
        完全没反应 —— 因为主线程在 sleep 循环里从不处理消息，回调永远不触发。
        千万别改回去。
        """
        global _hook_handle, _hook_ok
        _hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _hook_proc,
                                                None, 0)
        _hook_ok = bool(_hook_handle)
        _hook_ready.set()
        if not _hook_handle:
            return
        class MSG(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                        ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                        ("time", wintypes.DWORD), ("pt_x", wintypes.LONG),
                        ("pt_y", wintypes.LONG)]

        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    _hook_ready.clear()
    threading.Thread(target=_body, daemon=True).start()
    _hook_ready.wait(5)      # 等安装结果，装不上要走降级分支
    if not _hook_ok:
        print("  ⚠ 右 Alt 专用钩子装不上，退化为左右 Alt 都会触发")
    return _hook_ok


def _uninstall_hook():
    global _hook_handle
    if _hook_handle:
        try:
            import ctypes
            ctypes.windll.user32.UnhookWindowsHookEx(_hook_handle)
        except Exception:
            pass
        _hook_handle = None


def fire_hotkey():
    """右 Alt 按下 → 开始录音；再按一次 → 结束并上屏。

    和 on_any_press 共用同一套 armed / 去抖逻辑，保证"一次物理按键
    只算一次触发"。
    """
    global last_toggle_at, armed, last_press_at
    if suppress_hotkey:
        return
    now = time.time()
    if not armed:
        if now - last_press_at < KEYUP_TIMEOUT:
            return
        armed = True
    if now - last_toggle_at < DEBOUNCE:
        return
    last_toggle_at = now
    last_press_at = now
    armed = False
    if recording:
        stop_and_process()
    else:
        start_recording()


def on_any_press(e):
    """keyboard 库的兜底路径（只在底层钩子装不上时启用）。

    正常流程走 fire_hotkey()（右 Alt 专用钩子）。这个函数保留是为了
    非 Windows 环境或钩子失败时程序不至于完全没热键可用。
    """
    global last_toggle_at, armed, last_press_at
    if suppress_hotkey or not is_hotkey(e):
        return
    now = time.time()
    if not armed:
        # keyup 偶尔会丢（少数键盘/驱动），等不到就放行，免得热键彻底卡死
        if now - last_press_at < KEYUP_TIMEOUT:
            return
        armed = True
    if now - last_toggle_at < DEBOUNCE:
        return
    last_toggle_at = now
    last_press_at = now
    armed = False               # 等这次按键松开后才允许下一次
    if recording:
        stop_and_process()
    else:
        start_recording()


def on_any_release(e):
    """松开 → 这次按键结束，允许下一次按下生效。"""
    global armed
    if is_hotkey(e):
        armed = True


def run_selftest():
    """三步自测：麦克风有没有数据 → 转写能不能出字 → 输出能不能落到光标处。"""
    global input_sr, engine
    print("=== 1/3 麦克风 ===", flush=True)
    dev_id, dev_name = pick_input_device()
    input_sr = int(sd.query_devices(dev_id)["default_samplerate"])
    print(f"设备: {dev_name}  ({input_sr}Hz)", flush=True)
    print("请对着麦克风说 3 秒话...", flush=True)
    data = sd.rec(int(3 * input_sr), samplerate=input_sr, channels=1,
                  dtype="float32", device=dev_id)
    sd.wait()
    audio = data.flatten()
    rms = float(np.sqrt(np.mean(audio ** 2)))
    print(f"收到 {len(audio)} 个样本, RMS={rms:.4f}", flush=True)
    print("判定:", "麦克风正常 ✓" if rms >= MIN_RMS else
          f"没收到声音 ✗ → 改 MIC_DEVICE 换设备（当前阈值 {MIN_RMS}）", flush=True)

    print("\n=== 2/3 转写 ===", flush=True)
    text, t = get_engine(ASR_ENGINE).transcribe(
        resample_to_16k(audio, input_sr), SAMPLE_RATE)
    print(f"耗时 {t:.2f}s   识别结果: {text!r}", flush=True)
    print("判定:", "转写正常 ✓" if text else "没识别出字 ✗", flush=True)

    print("\n=== 3/3 输出 ===", flush=True)
    print("把光标点到一个能打字的地方（记事本、微信输入框都行），3 秒后写入测试文字...",
          flush=True)
    time.sleep(3)
    try:
        keyboard.write(f"[输出测试] {text or 'hello'}", delay=0)
        print(f"已用 OUTPUT_MODE={OUTPUT_MODE} 写入。看看光标处有没有出现。", flush=True)
    except Exception as e:
        print(f"写入失败: {type(e).__name__}: {e}", flush=True)
        print("→ 把 OUTPUT_MODE 改成 'paste' 再试", flush=True)


def run_key_diagnose():
    """按键诊断（带时间戳）。

    判定标准：按住一个键 2 秒再松手——
      · 『松开』出现在 ~2.0s   → 正常键，能当热键
      · 『松开』出现在 ~0.00s  → 切换键（CapsLock 就是这种），按下瞬间系统就补发了
    """
    hk = load_hotkey_scan()
    print(f"当前热键: scan_code={hk}", flush=True)
    print("按键诊断 —— 按下/松开任意键查看事件，Esc 退出。", flush=True)
    print("请这样测：把你想当热键的那个键【按住 2 秒，再松手】，看时间戳。\n", flush=True)
    t0 = time.time()
    def cb(e):
        down = e.event_type == keyboard.KEY_DOWN
        dt = time.time() - t0
        mark = "   <<< 这就是当前热键" if (
            hk is not None and getattr(e, "scan_code", None) == hk) else ""
        print(f"  [{dt:5.2f}s] {'按下' if down else '松开'}: "
              f"name={e.name!r} scan={e.scan_code}{mark}", flush=True)
        if down and (e.name or "") == "esc":
                keyboard.unhook(cb)
                print("\n退出诊断。")
                raise SystemExit(0)
    keyboard.hook(cb)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n退出诊断。")


def run_file(path):
    with wave.open(path, "rb") as w:
        ch, sr = w.getnchannels(), w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()),
                             dtype=np.int16).astype(np.float32) / 32768.0
    if ch == 2:
        data = data.reshape(-1, 2).mean(axis=1)
    print(f"[离线验证] {path}  {len(data) / sr:.1f}s")
    process(data, dry=True)


def ensure_single_instance():
    """端口锁：防止开机自启和手动启动叠出两个实例，导致双重粘贴。"""
    global _lock_socket
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", INSTANCE_PORT))
    except OSError:
        print("Typeless 已经在运行了，本次退出。")
        sys.exit(0)
    _lock_socket = s


def main():
    global engine
    if "--keys" in sys.argv:
        run_key_diagnose()
        return
    if "--selftest" in sys.argv:
        run_selftest()
        return
    if "--file" in sys.argv:
        idx = sys.argv.index("--file")
        path = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else "test_zh.wav"
        engine = get_engine(ASR_ENGINE)
        run_file(path)
        return

    ensure_single_instance()
    print(f"加载 {ASR_ENGINE} ...")
    t0 = time.time()
    engine = get_engine(ASR_ENGINE)
    dev_id, dev_name = pick_input_device()
    global input_sr, hotkey_scan
    input_sr = int(sd.query_devices(dev_id)["default_samplerate"])
    print(f"录音设备: {dev_name}  ({input_sr}Hz)")
    # 开机自启时 Ollama 服务可能还没起来（502），等它一下，否则第一句话要等冷启动
    for attempt in range(3):
        if warmup(OLLAMA_MODEL):
            break
        print(f"  Ollama 还没就绪（{attempt + 1}/3），3 秒后重试...")
        time.sleep(3)

    hotkey_scan = load_hotkey_scan()
    if hotkey_scan is None and not HOTKEY_IS_RIGHT_ALT:
        hotkey_scan = capture_hotkey()
    print(f"就绪 (共 {time.time() - t0:.1f}s)。触发键: {HOTKEY_NAME}")
    print("按一下开始录音，再按一下结束并上屏。Ctrl+C 退出。")

    # 开机时音频服务常常还没就绪，开流失败会让整个进程崩掉，所以要重试
    stream = None
    for attempt in range(6):
        try:
            stream = sd.InputStream(samplerate=input_sr, channels=1,
                                    dtype="float32", callback=audio_callback,
                                    device=dev_id)
            break
        except Exception as e:
            print(f"  麦克风打不开（{attempt + 1}/6）：{e}")
            time.sleep(5)
    if stream is None:
        print("麦克风始终打不开，退出。请检查是否有别的程序独占麦克风。")
        return

    with stream:
        hook_ok = HOTKEY_IS_RIGHT_ALT and _install_right_alt_hook()
        if hook_ok:
            print(f"就绪：只有【{HOTKEY_NAME}】能触发（已装底层钩子，左右严格区分）",
                  flush=True)
        else:
            keyboard.on_press(on_any_press)
            keyboard.on_release(on_any_release)
            print(f"就绪：触发键 {HOTKEY_NAME}（走 keyboard 库，可能不区分左右）",
                  flush=True)
        print("按一下右 Alt 开始录音，再按一下结束并上屏。Ctrl+C 退出。", flush=True)
        print("HOOK_STATUS=" + ("right_alt_ok" if hook_ok else "keyboard_fallback"),
              flush=True)
        _start_heartbeat()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n退出。", flush=True)
        finally:
            _uninstall_hook()


def _start_heartbeat():
    """每 5 分钟往日志写一条心跳。

    为什么需要：pythonw 无窗口运行时，进程要是死了（被误关、被系统回收、
    崩溃）你完全看不出来 —— 只有按下热键没反应才知道，但那时已经很难判断
    是"进程没了"还是"热键判定坏了"。有心跳就能一眼区分。
    """
    def _beat():
        while True:
            time.sleep(300)
            try:
                print(f"[心跳] 存活 {time.strftime('%H:%M:%S')}", flush=True)
            except Exception:
                pass

    threading.Thread(target=_beat, daemon=True).start()


class _Tee:
    """把输出同时送到控制台和日志文件。

    为什么要无条件写文件：pythonw（无窗口）下 sys.stdout 既不是 None、
    fileno() 也不报错，但写出去的内容直接消失 —— 判断"有没有控制台"的各种
    办法全都不准。所以不管什么启动方式都留一份日志，排查时永远有据。
    """

    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        _log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
        print(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} 启动 ===", file=_log)
        sys.stdout = _Tee(sys.stdout, _log)
        sys.stderr = _Tee(sys.stderr, _log)
    except Exception as e:
        try:
            print(f"(日志不可用: {e})")
        except Exception:
            pass
    main()
