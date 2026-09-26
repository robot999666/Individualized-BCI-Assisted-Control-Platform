"""CSP 空间模式可视化：画出每个指令（左转/右转/直行/停止）的脑地形图。

用法：
    python visualize.py <数据文件.npz>

    数据文件 npz 需含 X（n, 22, t）和 y（n,），若为 3 通道需含 X3（n, 3, t）。
    也支持直接传入 22 通道数据的路径。
"""
import sys
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 中文字体
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "sans-serif"]
matplotlib.rcParams["axes.unicode_minus"] = False

from mne.channels import make_standard_montage
from mne.decoding import CSP
import mne

CH_NAMES = [
    "Fz", "FC3", "FC1", "FCz", "FC2", "FC4", "C5", "C3", "C1", "Cz", "C2",
    "C4", "C6", "CP3", "CP1", "CPz", "CP2", "CP4", "P1", "Pz", "P2", "POz",
]
CMD_NAMES = ["左转（左手）", "右转（右手）", "直行（双脚）", "停止（舌头）"]

from model import bandpass


def plot_csp(X, y, out_path, title="CSP 空间模式"):
    """X: (n, 22, t), y: (n,) 0..3。画四类 one-vs-rest CSP 地形图。"""
    Xf = bandpass(X, 8, 30)
    patterns = []
    for c in range(4):
        yb = (y == c).astype(int)
        csp = CSP(n_components=1, log=False, norm_trace=False).fit(Xf, yb)
        patterns.append(csp.patterns_[0])
    patterns = np.array(patterns)

    info = mne.create_info(CH_NAMES, sfreq=250, ch_types="eeg")
    info.set_montage(make_standard_montage("standard_1005"))

    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    for i, ax in enumerate(axes.flat):
        p = patterns[i] / np.abs(patterns[i]).max()
        mne.viz.plot_topomap(p, info, axes=ax, show=False, cmap="RdBu_r",
                             vlim=(-1, 1), contours=0)
        ax.set_title(CMD_NAMES[i], fontsize=13)
    fig.suptitle(title + "\n红=能量上升(ERS) 蓝=能量下降(ERD)", fontsize=14)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print("已保存:", out_path)


def main():
    if len(sys.argv) < 2:
        print("用法: python visualize.py <数据文件.npz>")
        return
    d = np.load(sys.argv[1])
    X, y = d["X"], d["y"]
    out = sys.argv[1].replace(".npz", "_csp.png")
    plot_csp(X, y, out)


if __name__ == "__main__":
    main()
