"""脑电波波形图绘制（展示原始脑电电压随时间的变化）。

用法：
    python plot_wave.py                    # 默认用 S3 数据，画四类各一个样本的波形
    python plot_wave.py <data.npz>         # 用指定数据
    python plot_wave.py <data.npz> <trial> # 画指定 trial

说明：
    这是「脑电波图」（电压-时间曲线），与 visualize.py 的「脑地形图」
    （头皮空间分布）是两种不同的可视化。
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "sans-serif"]
matplotlib.rcParams["axes.unicode_minus"] = False

SFREQ = 250
CH22 = ["Fz", "FC3", "FC1", "FCz", "FC2", "FC4", "C5", "C3", "C1", "Cz", "C2",
        "C4", "C6", "CP3", "CP1", "CPz", "CP2", "CP4", "P1", "Pz", "P2", "POz"]
CH3 = ["C3", "Cz", "C4"]
C3CZ_C4 = [7, 9, 11]          # 22 通道中 C3/Cz/C4 的索引
CMD = ["左转（左手）", "右转（右手）", "直行（双脚）", "停止（舌头）"]


def plot_trial(ax, X_trial, ch_names, title, highlight=None):
    """画单个 trial 的波形。

    X_trial: (n_channels, n_times)，μV
    highlight: 需要高亮显示的通道索引列表（可选）
    """
    n_ch, n_t = X_trial.shape
    t = np.arange(n_t) / SFREQ
    hl = set(highlight or [])
    for i in range(n_ch):
        if i in hl:
            ax.plot(t, X_trial[i], lw=1.4, label=ch_names[i])
        else:
            ax.plot(t, X_trial[i], lw=0.5, color="lightgray")
    ax.set_xlabel("时间 (s)")
    ax.set_ylabel("电压 (μV)")
    ax.set_title(title)
    if highlight:
        ax.legend(loc="upper right", fontsize=8)
    ax.axhline(0, color="gray", lw=0.5, linestyle="--")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    data_path = args[0] if args else os.path.join(here, "data", "S3_22ch.npz")
    d = np.load(data_path)
    X, y = d["X"], d["y"]
    n_ch = X.shape[1]
    ch_names = CH22 if n_ch == 22 else (CH3 if n_ch == 3 else
                                         [f"ch{i+1}" for i in range(n_ch)])
    highlight = C3CZ_C4 if n_ch == 22 else list(range(n_ch))

    if len(args) >= 2:
        # 画指定 trial
        idx = int(args[1])
        fig, ax = plt.subplots(figsize=(10, 5))
        title = f"{CMD[y[idx]]}（trial {idx}，通道数={n_ch}）"
        plot_trial(ax, X[idx], ch_names, title, highlight)
    else:
        # 画四类各一个样本
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        for c in range(4):
            idx = np.where(y == c)[0][0]
            plot_trial(axes.flat[c], X[idx], ch_names,
                       f"{CMD[c]}（通道数={n_ch}）", highlight)
        fig.suptitle("脑电波波形图（S3 示例，每类一个样本）", fontsize=14)

    fig.tight_layout()
    out = data_path.replace(".npz", "_wave.png")
    fig.savefig(out, dpi=120)
    print("已保存:", out)


if __name__ == "__main__":
    main()
