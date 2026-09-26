# 脑电-眼电多模态意图识别系统 — 后端算法说明

> **面向ALS重度运动障碍人群的模块化便携辅助终端**
> 本目录包含核心算法，供前端同学对接使用。

> 平台集成说明：此文保留交付算法的接口背景。生产接入以根README为准：EEG sklearn1.6.1与EOG sklearn1.9.1分环境，使用后端安全控制层。参考demo.py不是生产验收入口。原稿准确率缺少可复核独立实验记录，已取消数值宣传；持续偏移只是安全规则，不是闭眼诊断。

---

## 一、环境搭建

### 1.1 要求
- Python 3.10+
- 操作系统：Windows / macOS / Linux

### 1.2 安装依赖
```bash
pip install numpy scipy scikit-learn mne joblib
```

### 1.3 验证安装
```bash
cd system_integration
python demo.py
```
能看到"EEG四分类演示""EOG眨眼检测演示""系统状态机演示"三部分输出即成功。

---

## 二、目录结构

```
system_integration/
├── core.py                  # ★ 核心代码：所有模型和状态机都在这里
├── demo.py                  # 演示脚本，直接 python demo.py 可跑
├── README.md                # 本文档
└── models/
    ├── coldstart_22ch.pkl    # EEG冷启动模型（22通道，44KB）
    ├── coldstart_3ch.pkl     # EEG冷启动模型（3通道C3/Cz/C4，6KB）
    ├── blink_detector.pkl    # EOG眨眼检测模型（25KB）
    # S3回归数据统一在 ../bci_4class/data/，不重复保存
```

---

## 三、两个模态分别是什么

### 3.1 EEG脑电四分类（运动想象指令）

| 项目 | 说明 |
|------|------|
| 输入 | 2秒脑电信号，22通道（或3通道），501个采样点 |
| 采样率 | 250 Hz |
| 单位 | μV |
| 输出 | 4个类别之一：`左转` / `右转` / `直行` / `停止` |
| 模型 | FBCSP + LDA |

**两种工作模式：**

| 模式 | 什么时候用 | 初始化方式 | 准确率（跨被试） |
|------|-----------|-----------|-----------------|
| 冷启动 | 新用户第一次用，没有校准数据 | `EEGClassifier(calibrated=False)` | 未独立复核 |
| 校准后 | 用户做了40-80次运动想象后 | 调 `calibrate_eeg(X, y)` | 未独立复核 |

### 3.2 EOG眼电（眨眼 + 闭眼）

| 项目 | 说明 |
|------|------|
| 输入 | 1秒垂直EOG信号，单通道，250个采样点 |
| 采样率 | 250 Hz |
| 单位 | μV |
| 眨眼检测输出 | `(是否眨眼: bool, 概率: 0~1)` |
| 闭眼检测输出 | 持续闭眼≥1.5s自动触发紧急求助 |
| 模型 | SVM（眨眼）+ 阈值判断（闭眼） |
| 眨眼准确率 | 无可复核独立评测；数据为自动标签且参与最终训练 |

---

## 四、系统状态机（主流程）

这是前端对接的核心。系统每0.5秒调用一次 `update()`，传入最新信号，返回事件。

### 4.1 紧急求助触发条件（2条，均为安全监测）

| 触发条件 | 说明 |
|----------|------|
| 长时间闭眼 ≥ 1.5s | EOG持续正向偏移>25μV，可能异常 |
| 脑电信号丢失 > 5s | 设备脱落或未佩戴 |

> 注意：连续两次眨眼**不是**紧急求助，它只是用来确认新指令的。紧急求助只来自上述两条安全监测。

### 4.2 正常指令流程

```
EEG检测到候选指令（左转/右转/直行/停止）
  │
  ├─ 指令 = 当前正在执行的 → 维持，不做事
  │
  ├─ 指令 = 停止 → 立即执行停止（安全优先）
  │
  └─ 指令 ≠ 当前且 ≠ 停止
       → 进入"待确认"状态
       → 用户连续两次眨眼确认
       → 执行新指令
```

### 4.3 事件类型

`update()` 返回一个事件列表（或None）：

| type | 什么时候出现 | 含义 |
|------|-------------|------|
| `pending` | EEG检测到新指令但还没确认 | `command`字段是候选指令名，前端提示"请眨眼确认" |
| `command` | 指令已确认执行 | `command`字段是指令名 |
| `emergency` | 紧急求助触发 | `reason`字段是原因 |

---

## 五、前端对接代码

### 5.1 最小调用示例

```python
from core import BCISystem

system = BCISystem(n_channels=22)  # 或 n_channels=3

# 实时循环（每0.5秒一次）
while True:
    eeg_trial = 读取硬件()     # shape: (22, 501) μV
    eog_window = 读取硬件()    # shape: (250,) μV

    events = system.update(
        eeg_trial=eeg_trial,   # 2秒脑电窗
        eog_window=eog_window, # 1秒眼电窗
        dt=0.5
    )

    if events:
        for e in events:
            print(e)
            # 前端根据 e['type'] 更新界面
```

### 5.2 用户校准流程

新用户第一次用时，建议先校准：

```python
system = BCISystem(n_channels=22)

# 用户做运动想象：每类10-20次
# 前端引导用户："想象左手运动，按空格继续..."
X_cal = []  # 收集校准数据，shape (n_trials, 22, 501)
y_cal = []  # 对应标签 0=左转/1=右转/2=直行/3=停止

# 校准完成后：
system.calibrate_eeg(X_cal, y_cal)  # 自动切换到个性化模型
```

### 5.3 包装成Web API（FastAPI示例）

```python
# app.py
from fastapi import FastAPI
from pydantic import BaseModel
import numpy as np
from core import BCISystem

app = FastAPI()
system = BCISystem(n_channels=22)

class SignalInput(BaseModel):
    eeg: list   # 22×501 的二维数组
    eog: list   # 250 的一维数组

@app.post("/api/update")
def update_signal(sig: SignalInput):
    eeg = np.array(sig.eeg, dtype=float).reshape(22, 501)
    eog = np.array(sig.eog, dtype=float)
    events = system.update(eeg_trial=eeg, eog_window=eog, dt=0.5)
    return {"events": events or []}

@app.post("/api/calibrate")
def calibrate(data: dict):
    X = np.array(data['X'])  # (n_trials, 22, 501)
    y = np.array(data['y'])  # (n_trials,)
    system.calibrate_eeg(X, y)
    return {"status": "ok"}
```

启动：`uvicorn app:app --host 0.0.0.0 --port 8000`

---

## 六、数据格式约定

前端从硬件（或模拟器）收到的数据必须是：

### EEG脑电
```python
np.ndarray, shape = (22, 501)
dtype = float, 单位 = μV
采样率 = 250 Hz
时间窗 = cue后0.5~2.5秒（共2秒）
```
如果硬件只有3个电极（C3/Cz/C4），shape就是 `(3, 501)`，初始化时用 `n_channels=3`。

### EOG眼电
```python
np.ndarray, shape = (250,)
dtype = float, 单位 = μV
采样率 = 250 Hz
时间窗 = 1秒
通道 = 垂直EOG（眼睛上下方向的电极）
```

---

## 七、可调参数

在 `core.py` 的 `BCISystem.__init__` 里：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `BLINK_CONFIRM_WINDOW` | 2.0s | 两次眨眼确认的时间窗口 |
| `SIGNAL_LOSS_TIMEOUT` | 5.0s | 信号丢失多久触发求助 |
| `LONG_CLOSURE_TIME` | 1.5s | 闭眼多久触发求助 |
| `EYE_CLOSE_THRESH` | 25.0μV | 判定闭眼的EOG幅度阈值 |

---

## 八、快速验证

```bash
cd system_integration
python demo.py
```

应该看到：
1. EEG冷启动/校准两种模式的准确率
2. EOG眨眼检测正确
3. 状态机：pending → 两次眨眼 → command 完整流程

---

## 九、注意事项

1. **sklearn版本警告**：加载预训练模型时可能有版本警告，不影响功能。
2. **冷启动准确率**：交付数值未独立复核，不作为平台泛化指标；建议使用分离校准与评测协议。
3. **EOG通道**：用垂直EOG（上下方向），眨眼最明显。水平EOG对眨眼不敏感。
4. **三通道模式**：硬件只有3个EEG电极时，`BCISystem(n_channels=3)`。
5. **输入必须是μV**：如果硬件输出是V，需要乘以1e6转成μV。
