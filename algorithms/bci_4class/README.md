# BCI 四分类意图识别模型交付包

面向 ALS 重度运动障碍人群的脑电四分类模型，用于识别四类离散意图指令：

| 类别 | 运动想象 | 指令 |
|------|---------|------|
| 0 | 左手 | **左转** |
| 1 | 右手 | **右转** |
| 2 | 双脚 | **直行** |
| 3 | 舌头 | **停止** |

## 目录结构

```
bci_4class/
├── model.py          # FBCSP 四分类 + EA 冷启动（自包含，核心）
├── demo.py           # 演示（校准 / 冷启动两种方式）
├── realtime.py       # 滑动窗口实时分类（连续脑电流 → 逐段分类）
├── visualize.py      # CSP 空间模式可视化（脑地形图）
├── plot_wave.py      # 脑电波波形图（电压-时间曲线）
├── requirements.txt
├── README.md
├── data/
│   ├── S3_22ch.npz   # S3 真实数据（288 trial × 22 通道 × 501 时间点）
│   └── S3_3ch.npz    # S3 真实数据（3 通道 C3/Cz/C4 版）
└── models/
    ├── coldstart_22ch.pkl   # 预训练冷启动模型（22 通道）
    └── coldstart_3ch.pkl    # 预训练冷启动模型（3 通道）
```

## 环境安装

```bash
pip install -r requirements.txt
```

依赖：numpy、scipy、scikit-learn、mne、matplotlib。

## 输入数据格式（重要）

模型输入为**已经切好的 trial**（一段运动想象信号，一个 trial 对应一个样本）：

| 项目 | 要求 |
|------|------|
| 类型 | `np.ndarray`，float32 或 float64 |
| 形状 | `(n_trials, n_channels, n_times)` |
| 通道 | **22 通道**（BCI 2a 标准布局）或 **3 通道**（顺序固定 [C3, Cz, C4]）|
| 采样率 | 250 Hz |
| 单位 | **μV（微伏）** |
| 时间点 | 建议 501（2 秒窗口），训练和推理须一致 |
| 标签 | `(n_trials,)`，取值 0/1/2/3（仅校准模式需要）|

> 若你的采集窗口不是 2 秒，可自行裁剪/重采样到与训练一致的长度。

## 使用方式

### 方式一：校准模式（有校准数据）

独立Python接口可用有标签数据训练分类器；Web平台保存EA参考，不重新训练分类器。准确率需独立验证：

```python
from model import FBCSPModel, CLASS_NAMES

# X_calib: (n, 22, 501) 或 (n, 3, 501)，μV
# y_calib: (n,)，0/1/2/3
m = FBCSPModel().fit(X_calib, y_calib)

pred = m.predict(X_new)               # (n,) 0/1/2/3
proba = m.predict_proba(X_new)        # (n, 4) 各类概率
name = [CLASS_NAMES[p] for p in pred] # 转成中文指令名
```

### 方式二：冷启动模式（无校准数据）

直接加载预训练模型，对目标数据做 EA 对齐后分类：

```python
from model import ColdStartModel

# 22 通道
m = ColdStartModel.load("models/coldstart_22ch.pkl")
pred = m.predict(X_new)               # X_new: (n, 22, 501) μV

# 3 通道（C3/Cz/C4）
m3 = ColdStartModel.load("models/coldstart_3ch.pkl")
pred3 = m3.predict(X_new_3ch)         # X_new_3ch: (n, 3, 501) μV
```

> 历史交付文档称预训练使用全部9人，但缺少完整训练会话清单。历史准确率缺少可复核实验记录，不作为平台宣传或独立验证结果。S3已知参与训练。

## 可视化

提供两种可视化，注意区分：

1. **脑电波波形图**（电压-时间曲线）—— 展示原始信号长什么样：

```bash
python plot_wave.py data/S3_22ch.npz
```

生成 `data/S3_22ch_wave.png`，画四个指令各一个样本的波形（22 通道中高亮 C3/Cz/C4）。

2. **脑地形图**（头皮空间分布）—— 展示模型学到的空间模式：

```bash
python visualize.py data/S3_22ch.npz
```

生成 `data/S3_22ch_csp.png`，展示四个指令各自激活的脑区。

## 连续流实时分类（滑动窗口）

设备输出的是**连续脑电流**，不是切好的 trial。用 `realtime.py` 里的 `sliding_predict`
对连续流做滑动窗口分类：

```python
from realtime import sliding_predict
from model import ColdStartModel

m = ColdStartModel.load("models/coldstart_22ch.pkl")

# X_stream: (n_channels, n_total_samples) 连续脑电，μV，250Hz
results = sliding_predict(m, X_stream, window=501, step=125)
# results = [(起始时间秒, 预测类别 0~3), ...]
```

要点：
- 窗口固定 **501 点（2 秒）**，须与训练一致；步长默认 **0.5 秒**，可调。
- 窗口跨两个类别时会有一段歧义区，工程上可用"连续多帧一致"来平滑。
- 运行 `python realtime.py` 查看完整演示。

## 完整流程示例

```bash
python demo.py
```

演示两种模式（校准 / 冷启动）× 两种通道（22 / 3 通道）的完整流程，并报告准确率。

## 模型说明

- **FBCSP（滤波组共空间模式）+ LDA**：对脑电做 mu/beta 多频带分解，逐频带做 CSP
  空间滤波（提取对侧运动皮层 C3/C4 的能量变化），再经 LDA 分类。小样本鲁棒、可解释、
  计算量小、适合端侧部署。
- **EA（欧氏对齐）**：冷启动模式的预处理，用目标数据自己的协方差做白化，消除个体间
  空间分布差异。
- **3 通道 vs 22 通道**：3 通道（C3/Cz/C4）与22通道使用不同CSP/LDA权重；精度需在清晰、独立的实验协议下比较。模型自动识别通道数。

## 注意事项

1. 本包为科研原型，不构成医疗器械宣称。
2. 输入单位必须是 μV（微伏）；若数据是伏特需先 ×1e6。
3. 推理时时间点数须与训练一致（本包模型为 501 点，即 2 秒 @ 250Hz）。
4. 3 通道输入的通道顺序必须固定为 [C3, Cz, C4]。
