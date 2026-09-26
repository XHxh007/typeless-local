# -*- coding: utf-8 -*-
"""干净的长文本基准：每次测前先卸载模型，避免 GPU/CPU 两份同时常驻互相污染。"""
import json
import subprocess
import time
import urllib.request

from polish import SYSTEM, polish, strip_fillers

MODEL = "qwen2.5:7b"
OLLAMA = "http://localhost:11434/api/generate"

LONG = ("嗯 那个 我跟你说一下 就是 这个 项目 的 进度 吧 首先 那个 数据 采集 这一块 "
        "已经 做完了 大概 采集了 三千 多条 然后 呢 就是 模型 训练 这一块 遇到 一点 问题 "
        "就是 显存 不够 我 觉得 可能 需要 换 一个 更 小 的 batch size 还有 就是 那个 "
        "前端 的 页面 我 建议 我们 先 用 一个 简单 的 版本 上线 后面 再 慢慢 优化 "
        "最后 呢 就是 下 周 三 之前 我 想 把 这个 报告 先 发 给 你 看看")


def stop():
    subprocess.run(["ollama", "stop", MODEL], capture_output=True)
    time.sleep(2)


def where():
    r = subprocess.run(["ollama", "ps"], capture_output=True, text=True)
    for line in r.stdout.splitlines()[1:]:
        if MODEL.split(":")[0] in line:
            return line.split()[3] + " " + line.split()[4]
    return "未驻留"


def call(prompt, num_gpu=None):
    opt = {"temperature": 0, "num_predict": 600}
    if num_gpu is not None:
        opt["num_gpu"] = num_gpu
    payload = {"model": MODEL, "system": SYSTEM,
               "prompt": f"[模式: struct]\n{prompt}", "stream": False,
               "options": opt, "keep_alive": -1}
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("response", "").strip(), time.time() - t0


src = strip_fillers(LONG)
print(f"输入 {len(src)} 字\n")

print("--- GPU ---")
stop()
_, t_load = call(src)                    # 含加载，不计
print(f"  加载+首跑: {t_load:.2f}s  (驻留位置: {where()})")
_, t1 = call(src)
print(f"  稳定耗时 : {t1:.2f}s")

print("--- 纯 CPU ---")
stop()
_, t_load2 = call(src, num_gpu=0)        # 含 CPU 加载，不计
print(f"  加载+首跑: {t_load2:.2f}s  (驻留位置: {where()})")
out_cpu, t2 = call(src, num_gpu=0)
print(f"  稳定耗时 : {t2:.2f}s")

print("\n=== 结论 ===")
print(f"长文本({len(src)}字→润色输出)  GPU {t1:.2f}s   纯CPU {t2:.2f}s   "
      f"差 {t2 / t1:.1f} 倍")
print(f"首次冷启动加载               GPU {t_load:.2f}s   纯CPU {t_load2:.2f}s")

stop()
print("\n恢复 GPU 常驻...")
call("你好")
print("  现在:", where())
