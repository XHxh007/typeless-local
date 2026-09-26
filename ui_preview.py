# -*- coding: utf-8 -*-
"""
胶囊外观预览 —— 不启录音、不加载模型，只在屏幕上轮播四种状态。
调 UI 的时候用它看效果，比跑整条链路快得多。

    python ui_preview.py
"""

import math
import time

import ui


def main():
    p = ui.Pill()
    if not p.ok:
        print("tkinter 不可用，跳过预览")
        return
    print("预览：recording(带假音量) -> processing -> done -> warn，共 2 轮")
    print("看屏幕底部居中位置。Ctrl+C 退出。")
    try:
        for _ in range(2):
            p.show("recording")
            t0 = time.time()
            while time.time() - t0 < 3.0:
                e = time.time() - t0
                # 模拟说话的包络：快抖动 + 慢起伏
                env = 0.30 + 0.60 * abs(math.sin(e * 3.4))
                env *= 0.75 + 0.25 * math.sin(e * 0.9)
                p.set_level(env * 0.08)
                time.sleep(0.033)
            p.show("processing")
            time.sleep(1.6)
            p.show("done")
            time.sleep(1.6)
            p.show("warn", "no audio")
            time.sleep(1.6)
            p.hide()
            time.sleep(0.4)
    except KeyboardInterrupt:
        pass
    p.hide()
    time.sleep(0.3)


if __name__ == "__main__":
    main()
