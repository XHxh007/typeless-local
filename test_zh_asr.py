# -*- coding: utf-8 -*-
"""中文 ASR 引擎对比：SenseVoice vs faster-whisper-small。同一段音频，比准确率和速度。"""

import time
import wave

import numpy as np

from asr import get_engine

WAV = "test_zh.wav"
REFERENCE = "欢迎大家来体验达摩院推出的语音识别模型"


def load_wav(path):
    with wave.open(path, "rb") as w:
        ch, sw, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch == 2:
        data = data.reshape(-1, 2).mean(axis=1)
    return data, sr


def main():
    audio, sr = load_wav(WAV)
    print(f"音频 {len(audio) / sr:.1f}s @ {sr}Hz")
    print(f"参考答案: {REFERENCE}\n")

    for kind, kw in (("sensevoice", {}), ("whisper", {"size": "small"})):
        try:
            t0 = time.time()
            eng = get_engine(kind, **kw)
            load_t = time.time() - t0
            text, inf_t = eng.transcribe(audio, sr)
            hit = "命中" if text == REFERENCE else "有差异"
            print(f"[{eng.name}]")
            print(f"  加载 {load_t:.2f}s   推理 {inf_t:.2f}s   ({hit})")
            print(f"  -> {text}")
            if text != REFERENCE:
                diff = [(a, b) for a, b in zip(text, REFERENCE) if a != b]
                print(f"  差异字符: {diff}")
        except Exception as e:
            print(f"[{kind}] 失败: {type(e).__name__}: {e}")
        print()


if __name__ == "__main__":
    main()
