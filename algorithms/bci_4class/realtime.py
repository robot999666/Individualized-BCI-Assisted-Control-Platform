"""滑动窗口实时分类示例。

设备输出的是**连续脑电流**（不是切好的 trial），需要先用滑动窗口把连续流
切成 2 秒一段，逐段喂给模型分类。

核心函数：
    sliding_predict(model, X_continuous, window, step)
        model: 有 predict(X) 方法的模型（FBCSPModel 或 ColdStartModel）
        X_continuous: (n_channels, n_total_samples) 连续脑电，μV，250Hz
        返回 [(起始时间秒, 预测类别), ...]

用法：
    python realtime.py
"""
import os

import numpy as np

from model import FBCSPModel, ColdStartModel, CLASS_NAMES
from sklearn.model_selection import train_test_split

HERE = os.path.dirname(os.path.abspath(__file__))
SFREQ = 250
WINDOW = 501       # 2 秒窗口（须与训练一致）
STEP = 125         # 每 0.5 秒判一次（可调，越小越实时但计算越多）


def sliding_predict(model, X_continuous, window=WINDOW, step=STEP):
    """对连续脑电流做滑动窗口分类。

    Args:
        model: FBCSPModel / ColdStartModel
        X_continuous: (n_channels, n_total_samples)，μV，250Hz
        window: 窗口采样点数（默认 501 = 2 秒）
        step: 滑动步长（采样点，默认 125 = 0.5 秒）

    Returns:
        list[(起始时间秒, 预测类别 0~3)]
    """
    X = np.asarray(X_continuous, dtype=np.float64)
    assert X.ndim == 2, "X_continuous 应为 (n_channels, n_total_samples)"
    results = []
    for start in range(0, X.shape[1] - window + 1, step):
        seg = X[:, start:start + window][None, :, :]   # (1, ch, window)
        pred = int(model.predict(seg)[0])
        results.append((start / SFREQ, pred))
    return results


def demo():
    print("=" * 64)
    print("滑动窗口实时分类演示（连续脑电流 → 逐段分类）")
    print("=" * 64)

    # 1. 用 S3 数据做校准
    d = np.load(os.path.join(HERE, "data", "S3_22ch.npz"))
    X, y = d["X"], d["y"]                       # (288, 22, 501) 已切好的 trial
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42)
    m = FBCSPModel().fit(X_tr, y_tr)
    print(f"\n[校准] 用 S3 数据训练 FBCSP 完成（测试集 {len(y_te)} 个 trial）")

    # 2. 取 6 个测试 trial，首尾拼接模拟连续流
    n_show = 6
    stream = X_te[:n_show].transpose(1, 0, 2).reshape(22, -1)   # (22, n_show*501)
    true_seq = np.repeat(y_te[:n_show], WINDOW)                 # 每个时间点真实类别

    # 3. 滑动窗口分类
    print(f"\n[滑动窗口] 窗口=2秒，步长=0.5秒，对 {n_show*2} 秒连续流分类：")
    print(f"{'起始时间':>8s}  {'预测':>6s}  {'真实':>6s}  {'结果'}")
    for t, pred in sliding_predict(m, stream):
        # 取窗口中心时间点的真实类别作参考（窗口边界处会有跨类歧义）
        center = int((t + WINDOW / 2 / SFREQ) * SFREQ)
        true = int(true_seq[min(center, len(true_seq) - 1)])
        ok = "OK" if pred == true else ""
        print(f"{t:7.2f}s  {CLASS_NAMES[pred]:>6s}  {CLASS_NAMES[true]:>6s}  {ok}")

    print("\n" + "=" * 64)
    print("说明：")
    print("  1. 连续流按 (n_channels, n_total_samples) 传入，μV、250Hz。")
    print("  2. 窗口固定 2 秒(501点)与训练一致，步长按需调（0.25~0.5秒）。")
    print("  3. 窗口跨两个类别时会有一段歧义区，工程上可用连续多帧一致来平滑。")
    print("=" * 64)


if __name__ == "__main__":
    demo()
