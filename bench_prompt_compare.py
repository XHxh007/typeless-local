# -*- coding: utf-8 -*-
"""【历史实验脚本 —— 不测试生产代码】

早期用来对比"清洁模式 vs 条理模式"两版 prompt 的实验：它内嵌了自己的
CLEAN_SYSTEM / STRUCT_SYSTEM，直接调 Ollama，**没有 import polish.py**。
所以它的输出与当前实现无关，别拿它当回归测试跑（会被误导）。

真正的回归测试： python test_regression.py
"""

import json
import time
import urllib.request

OLLAMA = "http://localhost:11434/api/generate"

CLEAN_SYSTEM = """你是一个语音转写后处理工具。输入是语音识别的原始文本，含大量口语冗余。
任务：
1. 删除无意义的填充词和语气词（嗯、啊、呃、那个、就是说、然后呢、对吧、这个这个、就是）
2. 修正语音识别的错字和断句
3. 补充完整的标点符号
严格约束：
- 绝对不得添加原文没有的信息
- 绝对不得改变说话人的原意、结论和语气
- 绝对不要把陈述句改成建议句
- 只输出处理后的文本，不要任何解释、引号或前缀"""

STRUCT_SYSTEM = """你是一个语音转写后处理工具。输入是语音识别的原始文本，含大量口语冗余。
任务：
1. 删除无意义的填充词（嗯、啊、呃、那个、就是说、然后呢、对吧、这个这个、就是）
2. 修正语音识别的错字
3. 把内容整理成 markdown 无序列表，每行一条，条数由原文信息点的数量决定
严格约束（违反任何一条即为失败）：
- 原文的每个信息点都必须出现在输出里，一个都不许丢
- 不许添加任何原文没有的信息、理由、例子或建议
- 保留第一人称和主观限定（"我觉得"、"我建议"、"可能"、"有点"）。这些是说话人的置信度标记，不是废话，删掉会让不确定的说法变成确定结论
- 不许替换连接词（"然后"不能改成"之后"，"所以"不能改成"因此"）
- 只输出列表本身，不要标题、不要解释、不要任何前后缀"""

SAMPLES = [
    ("短句", "嗯 那个 明天下午三点 我们开个会吧 就是讨论一下 那个 新的设计方案"),
    ("中英混合", "那个 我们把这个 feature 部署到 production environment 里面去 呃 然后 记得 嗯 跑一下那个 regression test"),
    ("长段", "嗯 我觉得吧 这个事情 就是说 我们得 呃 分几步来做 首先那个 就是 数据这块 需要先 嗯 把用户行为的数据采集上来 然后呢 再做那个 就是 留存分析 还有就是 嗯 时间上可能有点紧 所以 我建议 先把范围缩小 就是 只看新用户 最后呢 得 那个 输出一份报告给老板"),
]


def call(model, system, user, temperature=0.1):
    payload = {
        "model": model,
        "system": system,
        "prompt": user,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": 400},
        "keep_alive": "10m",
    }
    req = urllib.request.Request(
        OLLAMA,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read().decode("utf-8"))
    elapsed = time.time() - t0
    return out.get("response", "").strip(), elapsed


def run(model, system, label):
    print("=" * 60)
    print(f"模型: {model}   模式: {label}")
    print("=" * 60)
    for name, text in SAMPLES:
        out, sec = call(model, system, text)
        print(f"\n[{name}] {sec:.2f}s")
        print(f"  输入: {text}")
        print(f"  输出: {out}")
    print()


if __name__ == "__main__":
    import sys
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:7b"
    # 预热（把模型加载进显存）
    call(model, CLEAN_SYSTEM, "你好")
    run(model, CLEAN_SYSTEM, "清洁模式 - 只去口水词和补标点")
    run(model, STRUCT_SYSTEM, "条理模式 - 分条结构化")
