# -*- coding: utf-8 -*-
"""
验证 faster-whisper 在真实运行路径下的表现：numpy 数组输入（录音走的就是这条路，不经过 ffmpeg）。
同时测：模型缓存后的二次加载时间、麦克风可否按 16kHz 打开。
"""

import subprocess
import time

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

# 1. 把 flac 转成 16kHz mono raw，numpy 直接读 —— 绕开文件解码
subprocess.run(
    ["ffmpeg", "-y", "-i", "jfk.flac", "-ar", "16000", "-ac", "1",
     "-f", "s16le", "-acodec", "pcm_s16le", "jfk.raw"],
    capture_output=True,
)
audio = np.fromfile("jfk.raw", dtype=np.int16).astype(np.float32) / 32768.0
print(f"音频: {len(audio) / 16000:.1f}s  ({len(audio)} samples)")

# 2. 二次加载（模型已缓存，这才是日常启动的真实耗时）
t0 = time.time()
model = WhisperModel("small", device="cpu", compute_type="int8")
print(f"模型加载(已缓存): {time.time() - t0:.2f}s")

# 3. 转写 numpy 数组
t1 = time.time()
segments, info = model.transcribe(audio, language="en", vad_filter=True)
text = "".join(s.text for s in segments).strip()
el = time.time() - t1
dur = len(audio) / 16000
print(f"转写: {el:.2f}s  (实时倍数 {dur / el:.1f}x)")
print(f"结果: {text}")

# 4. 再跑一次，看第二次推理是否更快（避免首次预热干扰）
t2 = time.time()
segments, _ = model.transcribe(audio, language="en", vad_filter=True)
print(f"第二次转写: {time.time() - t2:.2f}s")

# 5. 麦克风能否按 16kHz 打开
print("\n麦克风 16kHz 打开测试:")
try:
    with sd.InputStream(samplerate=16000, channels=1, dtype="float32"):
        print("  OK — 可以 16kHz 单声道录音")
except Exception as e:
    print(f"  失败: {e}")
    print("  -> 需要把 SAMPLE_RATE 改成 44100 并在转写前重采样")
