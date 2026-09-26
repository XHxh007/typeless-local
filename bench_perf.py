# -*- coding: utf-8 -*-
"""性能实测：分别测 ASR 和润色在 GPU / 纯 CPU 下的耗时。"""
import json
import time
import urllib.request
import wave

import numpy as np

from asr import get_engine
from polish import SYSTEM, polish

OLLAMA = "http://localhost:11434/api/generate"


def load_wav(path):
    with wave.open(path, "rb") as w:
        ch, sr = w.getnchannels(), w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()),
                             dtype=np.int16).astype(np.float32) / 32768.0
    if ch == 2:
        data = data.reshape(-1, 2).mean(axis=1)
    if sr != 16000:
        n = int(len(data) * 16000 / sr)
        data = np.interp(np.linspace(0, len(data) - 1, n),
                         np.arange(len(data)), data).astype(np.float32)
    return data


def call_cpu(model, prompt):
    """强制 num_gpu=0，模拟没有独显的机器。"""
    payload = {
        "model": model, "system": SYSTEM,
        "prompt": f"[模式: clean]\n{prompt}",
        "stream": False,
        "options": {"temperature": 0, "num_predict": 600, "num_gpu": 0},
        "keep_alive": -1,
    }
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("response", "").strip(), time.time() - t0


if __name__ == "__main__":
    # 必须有这层保护：否则任何人 import 这个模块都会把整套基准重跑一遍
    # （之前踩过 —— 从别的脚本 import bench_perf 时把 GPU 基准污染了）
    print("=== 1) ASR（SenseVoice int8，CPU）===")
    audio = load_wav("test_zh.wav")
    print(f"音频 {len(audio) / 16000:.1f}s")
    eng = get_engine("sensevoice")
    t0 = time.time()
    text, t_asr = eng.transcribe(audio, 16000)
    print(f"耗时 {t_asr:.2f}s   识别: {text}")

    print("\n=== 2) 润色（qwen2.5:7b，GPU）===")
    out, mode, t_gpu = polish(text, verbose=True)
    print(f"耗时 {t_gpu:.2f}s   输出: {out[:80]}")

    print("\n=== 3) 润色（qwen2.5:7b，强制纯 CPU）===")
    _, t_cpu1 = call_cpu("qwen2.5:7b", text)      # 第一次含加载，不计
    print(f"  (首次含 CPU 加载: {t_cpu1:.2f}s，不计入)")
    out2, t_cpu = call_cpu("qwen2.5:7b", text)
    print(f"耗时 {t_cpu:.2f}s   输出: {out2[:80]}")

    print("\n=== 汇总 ===")
    print(f"ASR          : {t_asr:.2f}s  (CPU)")
    print(f"润色 GPU     : {t_gpu:.2f}s")
    print(f"润色 纯CPU   : {t_cpu:.2f}s")
    print(f"端到端 GPU   : {t_asr + t_gpu:.2f}s")
    print(f"端到端 纯CPU : {t_asr + t_cpu:.2f}s")
    print("\n提示：长短文本差距很大，配置评估用 bench_long.py（含模型卸载，数据更干净）")
