# Typeless 本地版

按一下右 Alt 说话，再按一下，整理好的文字直接落在光标处。

**全本地运行，不联网。** 语音识别在你的 CPU 上跑，文字润色走本机 Ollama，没有任何数据出机器。

> 定位：一个能自己掌控的语音输入工具。不用注册、不用订阅、不用担心你对着麦克风说的话被传到哪去。
<img width="367" height="91" alt="image" src="https://github.com/user-attachments/assets/0cd7274e-0e1e-4ded-8f6b-fde7b7dd7c13" />

---

## 它解决什么问题

用系统自带或云端语音输入时，最难忍的三件事：

1. **口述出来的是一坨**——"嗯那个今天下午三点我们要不开个会吧"，直接上屏没法用
2. **隐私**——你说的话要经别人的服务器
3. **专名识别**——中文里人名、公司名、专业术语错得离谱

这个项目针对这三点：

| 问题 | 做法 |
|---|---|
| 口述是散的 | 规则层删语气词 + 模型层断句分条 + 校验层防改原意，四层管线 |
| 隐私 | ASR 和润色都在本机，`localhost` 都不出 |
| 专名错字 | SenseVoice（中文比 Whisper 准得多）+ 可维护的热词表 |

**端到端延迟约 0.75 秒**（短句，GPU 润色）。这不是个玩具延迟，是能日常用的量级。

---

## 准备环境

需要三样东西：**Python 3.9+**、**Ollama**、**SenseVoice 模型**。

### 1. Python

从 [python.org](https://www.python.org/downloads/) 装，安装时勾选 **Add Python to PATH**。

> **必须有 tkinter**（标准安装自带）。屏幕底部那个状态胶囊是 Tk 画的，精简版 / 嵌入式（embeddable zip）发行版没有 tkinter，UI 会自动降级成不显示——程序还能跑，但你不知道它在录音。

### 2. Ollama + 模型

从 [ollama.com](https://ollama.com) 下载安装，然后：

```bash
ollama pull qwen2.5:7b
```

> 显存不够（<6GB）就换 `qwen2.5:3b`，然后改 `typeless_local.py` 里的 `OLLAMA_MODEL`。
> 不装 Ollama 也能跑——会跳过硬，直接上屏原始转写结果。

### 3. SenseVoice 模型

下载 int8 版并在项目下建 `models/sense-voice/`：

```bash
# 从 HuggingFace 镜像下（国内直连 HF 会 502，必须走镜像）
export HF_ENDPOINT=https://hf-mirror.com
```

需要放进 `models/sense-voice/` 的文件：

```
models/sense-voice/
├── model.int8.onnx
└── tokens.txt
```

来源：`csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`（见 [sherpa-onnx 文档](https://k2-fsa.github.io/sherpa/onnx/sense-voice/index.html)）。

> 为什么不用 Whisper：实测中文专名会错（"达摩院"→"打磨院"）、不加标点，且慢一个数量级。详见下面「为什么用 SenseVoice」。

### 4. Python 依赖

```bash
pip install -r requirements.txt
```

---

## 跑起来

```bash
python typeless_local.py
```

看到 `就绪：只有【Right Alt（右 Alt）】能触发` 就可以用了。按一下右 Alt 开始，再按一下结束。

**Windows 用户可以直接双击 `start_typeless.bat`** —— 它会自动找 Python、自动起 Ollama、启动后把最近日志打出来。停止用 `kill_typeless.bat`。

其他用法：

```bash
python typeless_local.py --file your.wav    # 离线验证：跑一段 wav，不录音不上屏
python typeless_local.py --selftest         # 三步自测：麦克风 → 转写 → 输出
python typeless_local.py --keys             # 按键诊断（带时间戳）
```

---

## 状态胶囊

按下触发键后，屏幕底部居中浮出一个小胶囊：

| 状态 | 显示 |
|---|---|
| 录音中 | 粉色圆点 + **实时音量条** + REC |
| 处理中 | 粉色 processing... |
| 已上屏 | 绿色 done，1.4 秒后自动消失 |
| 异常 | 浅红（no audio / too short / blocked） |

**音量条是关键**：它一动就说明麦克风真在收你的声音。之前有过"录到了虚拟麦克风"的坑——对着麦克风说话，音量条纹丝不动，一眼就看出问题。

只调外观不用跑整条链路：

```bash
python ui_preview.py      # 轮播四种状态 + 假音量动画
```

### 外观约定

改外观之前先看这几条（`ui.py` 顶部注释里也有一份）：

| 约定 | 具体做法 | 为什么 |
|---|---|---|
| 顶部一对猫耳 | 平滑三角 + 浅粉内耳，坐落在本体顶边上 | 高辨识度小面积点缀，不加在做工细节上 |
| 只有圆，没有方 | 本体全圆角 + 音量条圆头（`capstyle="round"`） | 圆角壳配直角条是"廉价感"的主要来源 |
| 条要细而密 | **12 根 × 7px 宽**，间隙 3px | 单根 <4px 时圆头就失效退化成直角，7px 是"细"的底线 |
| 钟形包络 | 中心条最高、向两侧递减到 30% | 整排读起来像一道声波弧，而不是一排等高柱子 |
| 用亮度表达电平 | 中心 `#ffd9e8` → 中间 `#ff9ecb` → 两侧 `#ff7ab8` | 单色平涂没有层次 |
| 高度不许硬切 | 指数平滑 `smooth = smooth*0.65 + level*0.35` | 每 40ms 直接跳高度会抖得像老式 LED 电平表 |

静音时音量条收缩成一个**小圆点**（最短视觉高度 = 条宽 7px），而不是缩成牙签。

尺寸是 **210×52**（本体 42px + 猫耳 10px）。宽度账：可用条区 = `210 - 42 - 40 = 128px`，`12 根 × 7px + 11 × 3px = 117px`，正好落在里面。**想加根数就必须先加宽胶囊，三者是绑死的。**

配色是**樱花粉**（深底 + 高饱和粉），浅色壁纸上也能看清：底 `#3a2536` / 描边 `#ff7ab8` / 耳内 `#ffd9e8`。

### 两个改 UI 时会踩的坑

1. **窗口没有 alpha 通道**。壳体靠 `-transparentcolor` 只抠纯黑，所以做不出半透明/发光效果，猫耳只能是实心色块。
2. **猫耳尖要留 2px 余量**。`width=1` 的描边会以路径为中心向两侧各伸 0.5px，且 tkinter 算 `bbox` 时会保守地再向外取整一格——耳尖放 y=1.5 时 `bbox` 仍是 -1，放到 2.0 才干净。

---

## 交互方式

**按一下开始录音，再按一下结束**，文字自动润色后落在光标处。

一次物理按键 = `keydown` + `keyup` 两个事件。程序只在**这次按键松开之后**才接受下一次按下，所以按住不放刷的一串重复 keydown 会被全部无视——不会变成"按一下就结束"。

**触发键固定为右 Alt，其他任何键都不触发。** 为什么非要右 Alt 而不是 CapsLock 或别的键——因为要的是"一个你永远不用、但一定会顺手按到"的键。右 Alt 在日常输入里几乎不被使用，同时又在拇指的自然落点上。

### 为什么必须用底层钩子，而不是 keyboard 库

这是这个项目最核心的一个技术决定，也是踩坑最多的地方。

`keyboard` 库只提供基础扫描码，**不做左右区分**。实测：

| 查询 | 返回 |
|---|---|
| `key_to_scan_codes('right alt')` | `(56, 57400)` |
| `key_to_scan_codes('left alt')` | `56` |
| `key_to_scan_codes('right ctrl')` | `(29, 57400, 57629…)` → 实际都是 29 |

左右 Alt 都是 56、左右 Ctrl 都是 29。**靠扫描码根本分不出左右**——早期版本用 Right Ctrl 时，左 Ctrl 同样会误触发，就是这个原因。

精确区分靠底层键盘钩子（`WH_KEYBOARD_LL`）里的**扩展位标志**：

- 右 Alt / 右 Ctrl 的扫描码会带 `0x100` 位（对应 E0 前缀），左键没有
- 判据：`KBDLLHOOKSTRUCT.flags & 0x01 (LLKHF_EXTENDED)`，且 `vkCode == 0xA5 (VK_RMENU)`
- 两个条件都满足才触发 → **左 Alt 物理上不可能触发**

装不上钩子时（非 Windows / 权限不足）自动退化为 `keyboard` 库路径，此时左右 Alt 都会触发，启动日志会打印警告。

### 两个必踩的坑（都踩过了，写下来省你几小时）

**坑 1：钩子的安装线程和消息循环必须是同一个线程。**

`WH_KEYBOARD_LL` 的回调**在安装钩子的那个线程里被调用**——系统靠往该线程的消息队列投递消息来触发它。最初写成"主线程 `SetWindowsHookExW` + 另开线程 `GetMessageW`"，结果：

- `SetWindowsHookExW` 返回非 0，`HOOK_STATUS=right_alt_ok`，**看起来一切正常**
- 但按键**完全没反应**，因为主线程在 `while True: sleep(1)` 里从不处理消息，回调永远不执行

正确写法是把装钩子和 `GetMessageW` 循环放在**同一个线程函数**里（见 `_body()`）。**别改回去。**

> 这个坑最阴的地方是它在架构层面看着"很合理"——"一个装钩子、一个泵消息，职责分离"——而报错信息是**没有报错**。

**坑 2：Win32 函数必须先声明原型。**

```python
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
```

不声明的话 ctypes 按 32 位 C int 处理参数，而 64 位下 `WPARAM/LPARAM` 是 8 字节指针宽度，值一大就抛 `OverflowError: int too long to convert`。后果不只是刷屏：

- 返回值不可靠会**打断钩子链**，可能影响系统里其他程序的热键
- 回调里抛的异常被 ctypes 静默打到 stderr，`pythonw` 下根本看不见

所以 `_proc` 的整个函数体（含 `CallNextHookEx`）都包在 try 里，异常一律吞掉——宁可静默失败，也不能影响按键的正常传递。

### 验证触发键

**自动验证（推荐，不需要人按键）**：

```bash
python test_hook_auto.py
```

用 `keybd_event` 模拟左右 Alt，拦截真正的触发动作，直接给结论：

```
[1] 模拟按下【左 Alt】...  触发 0 次（期望 0）
[2] 模拟按下【右 Alt】...  触发 1 次（期望 1）
[3] 再模拟一次【右 Alt】... 触发 1 次（期望 1）
✔ 通过：只有右 Alt 触发，左 Alt 被正确忽略
```

**人工验证**：`python test_right_alt.py`，按左右 Alt 各几次，看哪一行带 `✔ TRIGGER`。

---

## 为什么不做「按住说话」

一开始想做成"按住右 Alt 说话、松开输出"，更接近对讲机的手感。放弃了，因为**按住不放会重复触发**，而 `keyup` 在部分键盘/驱动下会丢——丢了就永远等不到松开，热键直接卡死。

现在改成点击式切换：按下开始、再按结束。它同时免疫这两个问题。"keyup 超时兜底"也留着（超过 `KEYUP_TIMEOUT` 3 秒没等到松开也会放行）。

---

## 输出方式（文字落在哪）

文字出现在**松手那一刻光标所在的地方**——所以说完之前别切窗口，否则会跑到新窗口去。

| `OUTPUT_MODE` | 做法 | 适用 |
|---|---|---|
| `type`（默认，Typeless 同款） | 逐字模拟键盘输入，直接落在光标处 | 不碰剪贴板，最通用 |
| `paste` | 复制后模拟 Ctrl+V | 更快，但在终端、部分编辑器里会失效 |

`type` 模式下**超过 `PASTE_THRESHOLD`（默认 50 字）会自动改用粘贴**：逐字输入的速度跟字数成正比，几百字要一个一个蹦好几秒。短句继续走 `type`，不动你的剪贴板。

---

## 润色是怎么做的

四层管线，核心判断一句话：**把"删除"交给规则，把"重组"交给模型**。

| 层 | 干什么 | 谁来做 | 为什么 |
|---|---|---|---|
| 规则层 | 删硬填充词（嗯/啊/呃/就是说/然后呢） | 字符串替换 | 确定性、零延迟、零失真 |
| 模型层 | 断句、补标点、分条、修识别错字 | qwen2.5:7b | 这些只有模型做得来 |
| 校验层 | 置信度词、英文 token 丢了就回退 | 断言 | 不信任模型的自述 |
| 格式层 | 列表标记、引导句、序号词去重 | 程序 | 见下面的"7b 不稳定" |

### 为什么不让 LLM 删口水词

实测把"删除"交给模型，它会**系统性出错**——它根本不是在删除，是在重写，而重写必然注入它的先验。三条实际发生的：

1. 删掉"我觉得" → 你的不确定说法变成确定结论
2. 把"然后"改成"之后" → 偷偷换了连接词
3. 直接丢掉信息点

解法是把不可改的东西做成**白名单**（`must_keep`），在 prompt 里显式声明"这些必须原样保留"。打个比方：相当于给变量加 `volatile`，禁止优化器动它。

### 两道防幻觉闸

| 闸 | 规则 | 拦的是什么 |
|---|---|---|
| 输入太短不入模 | 核心字符 < 3 直接 skip | 实测输入"二."被编成一大段话 |
| 输出异常长 | 输出 > 输入×3 + 15 则拦截 | 模型无中生有 |

### 分流：什么时候分条

`route()` 按两个条件判断：**≥2 个枚举信号**（第一/第二、一是/二是、首先/最后）或**去空格后 > 30 字**，走分条；否则只清洁。短句硬套列表会很怪，所以默认不分。

### 7b 不稳定，所以格式由程序决定

实测同一个 prompt 调两次，**结果会不一样**：列表标记时而 `-` 时而 `1.`、引导句时而被编进第一项时而被整个吞掉。

这不是 prompt 写得不好，是 7B 模型在多规则密集 prompt 下的能力上限——**别试图靠改 prompt 修它**。所以三件事收回到程序里做：

- `normalize_list_marks()` —— 是枚举就给 `1. 2. 3.`，不是就给 `-`，输出永远一致
- `ensure_lead_in()` —— 引导句（"今天开会讨论了三件事"）被编号了就提出来、被吞了就补回去
- `tidy_output()` —— 清掉空标记、清理 `1. 第一是X` 这种编号与序号词重复

### 防注入

转写文本用 `<transcription>` 标签包起来，并在 system prompt 里声明这是**不可信输入**：里面出现"忽略上面的要求""帮我总结"之类，只当作要清洗的内容，不当作命令执行。

> `<transcription>` 防注入与枚举编号规则的设计参考 [OpenTypeless](https://github.com/tover0314-w/opentypeless)（MIT License）。

**残留问题**：模型偶尔会把"忽略上面的要求"这句**内容本身**当垃圾删掉（不是执行了，是清理掉了）。安全目标达成，保真度不完美。

---

## 为什么用 SenseVoice 而不是 Whisper

同一段中文音频的对比（参考答案：欢迎大家来体验**达摩院**推出的语音识别模型）：

| 引擎 | 推理 | 结果 |
|---|---|---|
| **SenseVoice** | **0.30s** | 欢迎大家来体验**达摩院**推出的语音识别模型**。** ✅ |
| whisper-small | 3.49s | 欢迎大家来体验**打磨院**…… ❌ |

SenseVoice 全对、自带句号和数字规整（"十五六个"→"15~16个"）、**快 11.6 倍**。Whisper 中文的弱项是专名错字和不加标点，这正是"难用"的来源。

---

## 性能

参考数据（i9-14900HX / RTX 4060 Laptop 8GB / Ollama 0.34.2 / qwen2.5:7b）：

| 环节 | 耗时 |
|---|---|
| SenseVoice 转写（5.5s 音频） | **0.25s** |
| Ollama 润色（短句，模型常驻后） | **0.50s** |
| **端到端（短句）** | **0.75s** |
| 启动预热（一次） | 数秒，启动时自动做 |

长短文本差距很大，长段（224 字）实测 GPU vs 纯 CPU：

| 场景 | GPU | 纯 CPU | 差距 |
|---|---|---|---|
| 长段润色 | **2.20s** | **12.02s** | 5.5× |
| 首次加载模型 | 7.26s | **32.17s** | 4.4× |

复现：`python bench_long.py`（每次测前自动卸载模型，避免 GPU/CPU 两份同时常驻互相污染）。

**配置要求**（关键：**识别吃 CPU，润色吃 GPU**。本项目的 onnxruntime 只有 CPU 执行器，显卡再好也不影响识别速度）：

| 配置 | 能不能跑 |
|---|---|
| ≥6GB 显存独显 | qwen2.5:7b 直接跑，显存占约 4.7GB |
| 4GB 显存 / 核显 | 换 `qwen2.5:3b`（约 2GB），稍慢但可用 |
| 纯 CPU | 能跑，但长段要等 12 秒、冷启动 32 秒（设了常驻，只有开机第一次） |

---

## 装成日常工具（Windows）

| 文件 | 作用 |
|---|---|
| `start_typeless.bat` | **双击启动**。自动找 Python、自动起 Ollama、窗口停住显示结果 |
| `kill_typeless.bat` | **双击停止**。改了代码后先停再起 |

**开机自启**：把 `start_typeless.bat` 的快捷方式丢进 `shell:startup` 文件夹即可。

> **注意**：开机自启是普通权限，在**管理员权限的窗口**里无法输入。想要全场景可用，就用管理员身份运行 `start_typeless.bat`。

### 为什么必须双击启动，不能让别的程序代启动

主程序是常驻进程，必须活过启动它的那个终端。以下方式都**活不下来**（实测）：

| 启动方式 | 结果 |
|---|---|
| `pythonw xxx.py &`（shell 后台） | 随会话结束被回收 |
| `cmd /c start /b ...` | 同上，且 `/b` 共享控制台更脆弱 |
| `subprocess.Popen(..., DETACHED_PROCESS)` | 仍被上层进程树回收 |
| 计划任务服务（schtasks） | 被安全策略拦截 |
| **双击 `start_typeless.bat`** | ✅ 唯一可靠方式 |

原因是调用方的进程树可能按 **Job Object** 管理，会话结束时整个 job 关闭、所有子进程被杀，`DETACHED_PROCESS` 也逃不出 job。

所以 `launch_typeless.py` 的作用是：让 pythonw **不依附 bat 的 cmd 窗口**，这样你读完输出按任意键关窗时，程序不会被一起关掉。

### 进程死没死，怎么查

`pythonw` 无窗口运行时，进程死了**看不出任何迹象**——只有按热键没反应才知道，但那时分不清是"进程没了"还是"热键坏了"。三个判断手段：

1. **心跳**：日志里每 5 分钟一条 `[心跳] 存活 HH:MM:SS`。没有新心跳 = 进程死了。
2. **启动状态**：日志搜 `HOOK_STATUS=`，`right_alt_ok` 是正常，`keyboard_fallback` 说明钩子没装上（左右 Alt 都会触发）。
3. **进程列表**：`tasklist /FI "IMAGENAME eq pythonw.exe"`

### 改了代码之后必须重启进程

`pythonw.exe` 常驻内存，**改完代码不重启，跑的还是旧代码**。这是最容易踩的坑：改了热键逻辑，按新键没反应，其实是因为老进程还在响应老键。

判断"跑的是不是新代码"：日志里搜 `触发键:` 和 `HOOK_STATUS=`。

| 日志内容 | 含义 |
|---|---|
| `触发键: Right Alt（右 Alt）` + `HOOK_STATUS=right_alt_ok` | ✅ 新代码，钩子正常 |
| `HOOK_STATUS=keyboard_fallback` | ⚠️ 钩子没装上，左右 Alt 都会触发 |

**标准流程**：双击 `kill_typeless.bat` → 双击 `start_typeless.bat`。

### bat 里中文为什么乱码

日志是 **UTF-8**，而 cmd 默认按 **GBK(936)** 解码 → `[心跳] 存活` 显示成 `[寒泠烦] 瀛橹椿`。

修法两处配合，缺一不可：

1. bat 开头 `chcp 65001 >nul` —— 把控制台切到 UTF-8
2. 日志输出改用 Python 读（`sys.stdout.reconfigure(encoding='utf-8')`）

**为什么不用 PowerShell 的 `Get-Content`**：它默认按 ANSI 解码文件，中文必糊。加 `-Encoding UTF8` 能读对，但输出端还受 `[Console]::OutputEncoding` 影响，不如直接用 Python 可控。

记这条的通用价值：**处理中文日志，写端和读端编码必须一起管**。只改一边永远修不干净。

---

## 可调的旋钮

| 参数 | 位置 | 怎么选 |
|---|---|---|
| `ASR_ENGINE` | typeless_local.py | `sensevoice`（默认）或 `whisper` |
| `OLLAMA_MODEL` | typeless_local.py | qwen2.5:7b 是「不改原意」的底线，别往下调 |
| `OUTPUT_MODE` / `PASTE_THRESHOLD` | typeless_local.py | type 为默认；超过 50 字自动切粘贴，嫌慢就调小 |
| `MIC_DEVICE` | typeless_local.py | `None` = 自动选（跳过虚拟设备）。选错了填设备名关键词 |
| `MIN_RMS` | typeless_local.py | 静音判定阈值。环境吵就调高，声音小就调低 |
| `route()` 阈值 30 字 | polish.py | 短句走清洁、长段走分条。想让更多话变列表就调小 |
| `HARD_FILLERS` | polish.py | 规则层直接删的词。**有歧义的别加**（"那个方案"是实指，"他的话不算数"删"的话"会变意） |
| `HOTWORDS` | asr.py | **唯一需要你手动维护的**。遇到识别错的专有名词就往里加一条 |

---

## 已知边界

- **模型常驻显存**：qwen2.5:7b 占约 4.7GB。别再同时开别的大模型，会挤到共享内存。
- **长段分条偶尔丢小修饰语**（实测丢过"时间上"）。校验层只拦置信度词和英文/数字，拦不住这类。介意就把 `mode` 固定成 `clean`。
- **"那个""就是"偶尔残留**：模型怕误删实义用法会偏保守。
- **剪贴板只在长文本时被占用**：≤50 字走逐字输入，完全不碰剪贴板；超过则复制 + 模拟 Ctrl+V，1 秒后自动还原。终端等少数地方 Ctrl+V 不生效。
- **超过 120 秒的录音会被截断**（`MAX_SECONDS`），且没有 VAD 自动分段——一口气说太久会丢后半段。
- **首次说话前会自动预热**，启动后等终端打印「就绪」再说。

---

## 文件

| 文件 | 作用 |
|---|---|
| `typeless_local.py` | 主程序。右 Alt 单击切换录音、转写、上屏、离线验证 |
| `asr.py` | ASR 引擎适配层（SenseVoice / Whisper 统一接口）+ 热词表 |
| `polish.py` | 润色模块。规则层删语气词 + 模型层断句分条 + 校验层保真 + 格式层兜底 |
| `ui.py` | 悬浮状态胶囊：粉色猫耳 + 12 根圆头音量条（tkinter，无额外依赖；创建失败会自动降级不崩） |
| `ui_preview.py` | 胶囊外观预览：轮播四种状态 + 假音量动画，调 UI 时用 |
| `launch_typeless.py` | 脱离启动器：自动找 pythonw，用 `DETACHED_PROCESS` 拉起主程序 |
| `start_typeless.bat` | **双击启动**（Windows） |
| `kill_typeless.bat` | **双击停止**（Windows） |
| `models/sense-voice/` | SenseVoice int8 模型（约 228MB，需自行下载，未随仓库提供） |

### 测试与基准

| 脚本 | 作用 | 什么时候跑 |
|---|---|---|
| `test_regression.py` | **主回归**。A 段纯函数单测（不调模型）+ B 段端到端性质断言 | 改 `polish.py` 后必跑 |
| `test_toggle.py` | 按键切换逻辑单测（按住不放/完整点击/keyup 丢失等 5 个场景） | 改热键逻辑后跑 |
| `test_hook_auto.py` | 右 Alt 钩子验证（**自动**）：模拟按键，不需要人操作 | 改钩子代码后跑 |
| `test_right_alt.py` | 右 Alt 钩子验证（人工按键）：按左右 Alt 各几次 | 换键盘后跑 |
| `test_zh_asr.py` | ASR 引擎对比 | 换引擎时 |
| `test_asr.py` | ASR 基础可用性检查 | 换模型时 |
| `bench_long.py` | 长文本润色耗时（GPU vs 纯 CPU） | 评估配置要求时 |
| `bench_perf.py` | 短文本基准：ASR 耗时 + 润色 GPU/CPU 对比 | 快速看单句延迟 |
| `bench_prompt_compare.py` | 历史实验脚本，不测生产代码 | 一般不用 |

---

## License

MIT —— 见 [LICENSE](LICENSE)。

`polish.py` 的 prompt 设计（防注入标签与枚举编号规则）参考 [OpenTypeless](https://github.com/tover0314-w/opentypeless)，同为 MIT License，版权声明保留在源码与 LICENSE 中。
