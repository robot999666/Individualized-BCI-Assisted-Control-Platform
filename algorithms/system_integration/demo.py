"""
demo.py - 多模态系统完整流程演示

演示内容：
  1. 冷启动模式：加载预训练模型，直接对新用户EEG分类
  2. 校准模式：用用户本人数据训练个性化模型
  3. EOG眨眼检测
  4. 系统状态机：EEG指令 + 两次眨眼确认
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (BCISystem, EEGClassifier, EOGBlinkDetector,
                  CLASS_NAMES, SFREQ, EEG_WINDOW, EOG_WINDOW)

HERE = os.path.dirname(os.path.abspath(__file__))


def demo_eeg():
    """演示EEG四分类的两种模式。"""
    print("=" * 60)
    print("1. EEG脑电四分类演示")
    print("=" * 60)

    # 加载测试数据
    d = np.load(os.path.join(HERE, "..", "bci_4class", "data", "S3_22ch.npz"))
    X, y = d["X"], d["y"]
    print(f"测试数据: {X.shape[0]}个trial, {X.shape[1]}通道, {X.shape[2]}点")

    # 模式1：冷启动（无校准）
    print("\n--- 冷启动模式（无用户校准数据）---")
    clf_cold = EEGClassifier(calibrated=False, n_channels=22)
    pred_cold = clf_cold.predict(X)
    acc_cold = np.mean(pred_cold == y)
    print(f"  准确率: {acc_cold*100:.1f}%")
    print(f"  示例预测:")
    for i in range(5):
        print(f"    trial{i}: 真实={CLASS_NAMES[y[i]]}, 预测={CLASS_NAMES[pred_cold[i]]}")

    # 模式2：校准后（用用户本人数据训练）
    print("\n--- 校准模式（用用户本人数据训练）---")
    from sklearn.model_selection import train_test_split
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42)
    clf_cal = EEGClassifier(calibrated=False, n_channels=22)
    clf_cal.calibrate(X_tr, y_tr)
    pred_cal = clf_cal.predict(X_te)
    acc_cal = np.mean(pred_cal == y_te)
    print(f"  训练: {len(X_tr)}个trial, 测试: {len(X_te)}个trial")
    print(f"  准确率: {acc_cal*100:.1f}%")


def demo_eog():
    """演示EOG眨眼检测。"""
    print("\n" + "=" * 60)
    print("2. EOG眼电眨眼检测演示")
    print("=" * 60)

    det = EOGBlinkDetector()
    data = np.load(os.path.join(HERE, "..", "eog_blink", "eog_dataset.npz"))
    X_eog, y_eog = data['X'], data['y']

    # 测几个样本
    blink_idx = np.where(y_eog == 1)[0][:3]
    nonblink_idx = np.where(y_eog == 0)[0][:3]

    print("眨眼样本:")
    for i in blink_idx:
        is_b, prob = det.detect(X_eog[i])
        print(f"  预测={'眨眼' if is_b else '不眨眼'}, 概率={prob:.4f}")

    print("不眨眼样本:")
    for i in nonblink_idx:
        is_b, prob = det.detect(X_eog[i])
        print(f"  预测={'眨眼' if is_b else '不眨眼'}, 概率={prob:.4f}")


def demo_system():
    """演示系统状态机完整流程。"""
    print("\n" + "=" * 60)
    print("3. 系统状态机演示（EEG+EOG整合）")
    print("=" * 60)

    system = BCISystem(n_channels=22)

    # 加载EEG测试数据
    d = np.load(os.path.join(HERE, "..", "bci_4class", "data", "S3_22ch.npz"))
    X, y = d["X"], d["y"]

    # 加载EOG数据
    eog_data = np.load(os.path.join(HERE, "..", "eog_blink", "eog_dataset.npz"))
    X_eog, y_eog = eog_data['X'], eog_data['y']

    # 模拟实时流程
    print("\n模拟实时系统（每0.5秒一个周期）:")
    print("-" * 60)

    # 取几个不同类别的trial
    demo_trials = []
    for c in range(4):
        idx = np.where(y == c)[0][0]
        demo_trials.append((c, X[idx]))

    eog_flat = X_eog[y_eog == 0][0]  # 不眨眼EOG
    eog_blink = X_eog[y_eog == 1][0]  # 眨眼EOG

    # 周期1：收到左转EEG，无眨眼 → 待确认
    print("\n[t=0.5s] 收到EEG(左转)，EOG平稳:")
    events = system.update(eeg_trial=demo_trials[0][1], eog_window=eog_flat)
    for e in (events or []):
        print(f"  → {e}")

    # 周期2：第一次眨眼（计数=1，还不确认）
    print("\n[t=1.0s] 用户第一次眨眼:")
    events = system.update(eeg_trial=None, eog_window=eog_blink)
    for e in (events or []):
        print(f"  → {e}")

    # 周期3：第二次眨眼 → 确认执行左转
    print("\n[t=1.5s] 用户第二次眨眼 → 确认:")
    events = system.update(eeg_trial=None, eog_window=eog_blink)
    for e in (events or []):
        print(f"  → {e}")

    # 周期4：执行左转中，收到右转EEG → 新的待确认
    print("\n[t=2.0s] 执行左转中，收到EEG(右转)，EOG平稳:")
    events = system.update(eeg_trial=demo_trials[1][1], eog_window=eog_flat)
    for e in (events or []):
        print(f"  → {e}")

    # 周期5：连续两次眨眼确认右转
    print("\n[t=2.5s] 用户第一次眨眼:")
    events = system.update(eeg_trial=None, eog_window=eog_blink)
    for e in (events or []):
        print(f"  → {e}")
    print("\n[t=3.0s] 用户第二次眨眼 → 确认执行:")
    events = system.update(eeg_trial=None, eog_window=eog_blink)
    for e in (events or []):
        print(f"  → {e}")

    print("\n" + "-" * 60)
    print("系统状态机流程演示完毕。")
    print("实际部署时由硬件设备持续推送EEG/EOG数据即可。")


if __name__ == "__main__":
    demo_eeg()
    demo_eog()
    demo_system()
