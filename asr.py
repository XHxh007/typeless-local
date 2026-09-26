# -*- coding: utf-8 -*-
"""
ASR 引擎适配层：把 SenseVoice 和 faster-whisper 封装成同一套接口。

为什么默认用 SenseVoice：
- Whisper 对中文不加标点、专名容易错（实测"达摩院"→"打磨院"）
- SenseVoice 原生输出中文标点和数字规整（"十五六个"→"15~16个"），CPU 上快一个量级

用法：
    from asr import get_engine
    engine = get_engine("sensevoice")   # 或 "whisper"
    text = engine.transcribe(audio_float32, sample_rate)
"""

import os
import time

# 热词表：ASR 常错的专有名词，转写后按字面替换。
# 这是唯一需要你手动维护的东西 —— 遇到识别错的词就往这里加。
HOTWORDS = {
    # "打磨院": "达摩院",
    # "同计大学": "同济大学",
}


def apply_hotwords(text):
    for wrong, right in HOTWORDS.items():
        text = text.replace(wrong, right)
    return text


# 模型路径基于本文件所在目录，不依赖当前工作目录（开机自启时工作目录是系统目录）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class SenseVoiceASR:
    name = "sensevoice"

    def __init__(self, model_dir=None, num_threads=8):
        import sherpa_onnx
        model_dir = model_dir or os.path.join(BASE_DIR, "models", "sense-voice")
        model = os.path.join(model_dir, "model.int8.onnx")
        if not os.path.isfile(model):
            raise FileNotFoundError(f"模型缺失: {model}")
        t0 = time.time()
        self.rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model,
            tokens=os.path.join(model_dir, "tokens.txt"),
            num_threads=num_threads,
            use_itn=True,     # 数字规整：十五六个 -> 15~16个
            debug=False,
        )
        self.load_time = time.time() - t0

    def transcribe(self, audio, sample_rate):
        t0 = time.time()
        stream = self.rec.create_stream()
        stream.accept_waveform(sample_rate, audio)
        self.rec.decode_stream(stream)
        text = stream.result.text.strip()
        return apply_hotwords(text), time.time() - t0


class WhisperASR:
    name = "whisper"

    def __init__(self, size="small", device="cpu", compute_type="int8"):
        from faster_whisper import WhisperModel
        t0 = time.time()
        self.model = WhisperModel(size, device=device, compute_type=compute_type)
        self.load_time = time.time() - t0

    def transcribe(self, audio, sample_rate):
        t0 = time.time()
        segs, _ = self.model.transcribe(audio, language="zh", vad_filter=True)
        text = "".join(s.text for s in segs).strip()
        return apply_hotwords(text), time.time() - t0


def get_engine(kind="sensevoice", **kw):
    if kind == "sensevoice":
        return SenseVoiceASR(**kw)
    if kind == "whisper":
        return WhisperASR(**kw)
    raise ValueError(f"未知引擎: {kind}")
