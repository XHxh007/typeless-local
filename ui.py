# -*- coding: utf-8 -*-
"""
录音状态胶囊 —— 屏幕底部居中的无边框置顶小窗。

用 tkinter（标准库）实现，零额外依赖。UI 跑在独立线程，
主线程通过队列发指令，避免和键盘钩子互相阻塞。

状态：recording / processing / done / warn / hide
录音中还会画实时音量条 —— 用来一眼确认麦克风到底有没有在收音。

视觉约定（想改外观时只看这一段）：
  1. 顶部一对粉色猫耳（平滑曲线，占顶部猫耳区），胶囊本体全圆角
  2. 音量条 30 根、每根 7.4px 宽 —— 细、密、圆头，静音时缩成一个小圆点
  3. 钟形包络：中心条最高、向两侧递减，整排读起来像一道声波弧
  4. 三档亮度表达电平：中心最亮、两侧渐暗
  5. 音量做指数平滑，避免逐帧硬切造成的抖动
  6. 壳体靠透明色抠图，**没有 alpha 通道** —— 不要用半透明/发光

樱花粉配色（深底 + 高饱和粉），浅色壁纸上也能看清。
"""

import queue
import threading

try:
    import tkinter as tk
except Exception:
    tk = None

# ---- 外壳 ----
W, H = 210, 52          # 总高含顶部猫耳区
EAR_H = 10              # 猫耳伸出的高度
BODY_TOP = EAR_H        # 胶囊本体从这条线开始
BODY_H = H - EAR_H      # 本体高度 = 42
PAD_BOTTOM = 120
BG_COLOR = "#3a2536"        # 本体面
BORDER = "#ff7ab8"          # 本体描边（主粉）
CAVITY = "#2b1c2a"          # 更深的内层（抠图底色）
FG_COLOR = "#ffe3ef"
ACCENT = "#ff7ab8"
OK = "#7ee0b0"
WARN = "#ff8fa8"

# ---- 猫耳 ----
EAR_FILL = "#ff7ab8"        # 耳外廓
EAR_INNER = "#ffd9e8"       # 耳内浅色
EAR_W = 14                  # 单耳宽度（随胶囊缩窄同比收小）
EAR_GAP = 20                # 两耳间距（左耳左边缘 -> 右耳左边缘）
# 两耳合起来的中心线对齐胶囊正中：总跨度 = EAR_GAP + EAR_W
EAR_LEFT_X = (W - (EAR_GAP + EAR_W)) / 2

# ---- 音量条 ----
# 宽度账：可用条区 = W - BAR_X0 - 右侧 REC 保留位(40)
#         210 - 42 - 40 = 128px
#         12 根 × 7px + 11 × 3px = 117px，落在 128px 内留余量
BARS = 12
BAR_W = 7                   # 条宽（圆头直径）—— 细，≥4px 才保得住圆头
BAR_GAP = 3
BAR_X0 = 42                 # 条区左边界
BAR_MIN = float(BAR_W)      # 最短视觉高度 = 一个圆点
BAR_MAX = 28.0              # 最长视觉高度
BAR_HI = "#ffd9e8"          # 中心最亮
BAR_MID = "#ff9ecb"
BAR_LO = "#ff7ab8"          # 两侧
SMOOTH_KEEP = 0.65          # 平滑系数：越大越稳、越迟钝

STATE_STYLE = {
    "recording": (ACCENT, "recording"),
    "processing": (ACCENT, "processing"),
    "done": (OK, "done"),
    "warn": (WARN, "warn"),
}


class Pill:
    """悬浮状态胶囊。所有方法都可以从任意线程调用。"""

    def __init__(self):
        self.q = queue.Queue()
        self.level = 0.0
        self.ok = tk is not None
        if not self.ok:
            return
        self.ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self.ready.wait(8)

    # ---- 对外接口（主线程调用） ----
    def show(self, state, text=""):
        if not self.ok:
            return
        self.q.put(("show", state, text))

    def hide(self):
        if self.ok:
            self.q.put(("hide", "", ""))

    def set_level(self, rms):
        """喂入实时音量（0~1 量级）。"""
        if self.ok:
            self.level = min(1.0, rms * 12.0)

    # ---- 内部：只在 UI 线程执行 ----
    def _run(self):
        try:
            self.root = tk.Tk()
        except Exception:
            self.ok = False
            self.ready.set()
            return
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", "black")
        except Exception:
            pass
        self.root.configure(bg="black")
        self.root.geometry(f"{W}x{H}+{(sw - W) // 2}+{sh - PAD_BOTTOM}")
        self.canvas = tk.Canvas(self.root, width=W, height=H,
                                bg="black", highlightthickness=0)
        self.canvas.pack()
        self.root.withdraw()
        self.visible = False
        self.state = "idle"
        self.text = ""
        self.hide_at = None
        self.smooth = 0.0        # 平滑后的音量
        self.ready.set()
        self.root.after(40, self._tick)
        self.root.mainloop()

    def _tick(self):
        try:
            while True:
                cmd, state, text = self.q.get_nowait()
                if cmd == "show":
                    self.state, self.text = state, text
                    if not self.visible:
                        self.visible = True
                        self.root.deiconify()
                    if state == "recording":
                        self.smooth = 0.0
                    delay = 1.4 if state in ("done", "warn") else None
                    self.hide_at = (_now() + delay) if delay else None
                elif cmd == "hide":
                    self.visible = False
                    self.root.withdraw()
        except queue.Empty:
            pass

        if self.visible and self.hide_at and _now() > self.hide_at:
            self.visible = False
            self.root.withdraw()

        if self.visible:
            self._draw()
        self.root.after(40, self._tick)

    def _draw(self):
        c = self.canvas
        c.delete("all")
        color, _label = STATE_STYLE.get(self.state, (ACCENT, "recording"))
        cy = BODY_TOP + BODY_H / 2

        self._draw_ears(c, color)

        # 本体：两层圆角叠出 1px 描边（外层填描边色、内层填面色）
        r = (BODY_H - 2) // 2
        _rounded(c, 1, BODY_TOP + 1, W - 1, H - 1, r, fill=BORDER, outline="")
        _rounded(c, 2, BODY_TOP + 2, W - 2, H - 2, r, fill=BG_COLOR, outline="")

        # 状态圆点：细环 + 实心核
        c.create_oval(11, cy - 8, 27, cy + 8, outline=color, width=1)
        c.create_oval(14, cy - 5, 24, cy + 5, fill=color, outline="")

        if self.state == "recording":
            self._draw_bars(c)
            c.create_text(W - 12, cy, text="REC", anchor="e",
                          fill=color, font=("Segoe UI", 8, "bold"))
        else:
            words = {
                "processing": "processing...",
                "done": "done",
                "warn": self.text or "no audio",
            }.get(self.state, "")
            c.create_text(BAR_X0, cy, text=words, anchor="w",
                          fill=FG_COLOR, font=("Segoe UI", 10))

    def _draw_ears(self, c, color):
        """一对猫耳：外廓用状态色，内耳用浅粉，做出层次。

        直接坐在本体顶边上（bottom = BODY_TOP + 1），靠本体描边盖住接缝。
        内耳三角的顶点必须比耳尖低——否则它那条斜边会顶出画布上边界被裁掉。
        耳尖留 2.0：width=1 的描边向两侧各伸 0.5px，且 tkinter 算 bbox 时会
        再保守地向外取整一格，留 2px 才能保证 bbox 上界不为负。
        """
        top = 2.0
        bottom = BODY_TOP + 1.0
        for x0 in (EAR_LEFT_X, EAR_LEFT_X + EAR_GAP):
            x1 = x0 + EAR_W
            mid = (x0 + x1) / 2
            c.create_polygon(
                mid, top,          # 尖
                x1, bottom,        # 右下
                x0, bottom,        # 左下
                fill=color, outline=EAR_INNER, width=1, smooth=False,
            )
            # 内耳：从耳尖往下挪 4px 起笔，底边收窄，整体含在外廓里
            ix0, ix1 = x0 + 5.0, x1 - 5.0
            imid = (ix0 + ix1) / 2
            c.create_polygon(
                imid, top + 4.0,
                ix1, bottom - 1.0,
                ix0, bottom - 1.0,
                fill=EAR_INNER, outline="", smooth=False,
            )

    def _draw_bars(self, c):
        """实时音量条：一排细密圆头竖条，钟形包络 + 中心亮两侧暗。"""
        # 指数平滑，消掉逐帧硬切
        self.smooth = self.smooth * SMOOTH_KEEP + self.level * (1 - SMOOTH_KEEP)
        if self.smooth < 0.004:
            self.smooth = 0.0
        lv = self.smooth

        cy = BODY_TOP + BODY_H / 2
        mid = (BARS - 1) / 2
        for i in range(BARS):
            d = abs(i - mid) / mid              # 0 = 中心，1 = 两端
            shape = 0.30 + 0.70 * (1 - d)       # 钟形包络，两端仍留 30%
            h = BAR_MIN + shape * lv * (BAR_MAX - BAR_MIN)
            # 圆头会把线两端各撑出 BAR_W/2，所以线长要减掉一个条宽
            ln = max(1.0, h - BAR_W)
            x = BAR_X0 + i * (BAR_W + BAR_GAP) + BAR_W / 2
            col = BAR_HI if d < 0.34 else (BAR_MID if d < 0.67 else BAR_LO)
            c.create_line(x, cy - ln / 2, x, cy + ln / 2,
                          width=BAR_W, fill=col, capstyle="round")


def _rounded(c, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
           x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


def _now():
    import time
    return time.time()
