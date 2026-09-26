from pathlib import Path
"""
blink_inference.py - 眨眼检测推理接口
用法：传入一段1秒的EOG信号（250个采样点），输出是否眨眼。

在实际系统中：
1. 持续读取EOG:ch02信号
2. 每收到250个采样点（1秒），调用 detect_blink()
3. 如果检测到眨眼，触发紧急求助指令
"""
import numpy as np
import joblib
from scipy.signal import butter, filtfilt

# 加载模型
_model = joblib.load(str(Path(__file__).resolve().parent / 'blink_detector.pkl'))
SFREQ = 250
WIN_LEN = 250  # 1秒窗


def _bandpass(data, low=1.0, high=15.0, sfreq=SFREQ, order=4):
    nyq = sfreq / 2.0
    b, a = butter(order, [low / nyq, high / nyq], btype='band')
    return filtfilt(b, a, data)


def _extract_features(window):
    """和训练时一致的14维手工特征。"""
    from scipy.stats import skew, kurtosis
    feats = []
    feats.append(np.max(window))
    feats.append(np.min(window))
    feats.append(np.max(window) - np.min(window))
    feats.append(np.mean(window))
    feats.append(np.var(window))
    feats.append(np.sqrt(np.mean(window**2)))
    feats.append(np.sum(np.abs(np.diff(window))))
    center = len(window) // 2
    feats.append(np.argmax(window) / len(window))
    pre = window[center-25:center]
    feats.append((window[center] - pre[0]) / 0.1)
    post = window[center:center+25]
    feats.append((post[-1] - window[center]) / 0.1)
    center_energy = np.sum(window[center-25:center+25]**2)
    total_energy = np.sum(window**2) + 1e-10
    feats.append(center_energy / total_energy)
    feats.append(np.sum(np.diff(np.sign(window)) != 0))
    feats.append(skew(window))
    feats.append(kurtosis(window))
    return np.array(feats).reshape(1, -1)


def detect_blink(eog_window_uv):
    """
    输入：1秒的EOG信号（250个采样点，单位uV），垂直EOG通道。
    输出：(是否眨眼 bool, 眨眼概率 float)
    """
    assert len(eog_window_uv) == WIN_LEN, f"需要{WIN_LEN}个采样点，收到{len(eog_window_uv)}"
    filtered = _bandpass(eog_window_uv)
    feat = _extract_features(filtered)
    prob = _model.predict_proba(feat)[0, 1]
    return prob > 0.5, prob


# ============ 测试 ============
if __name__ == "__main__":
    # 用数据集里的样本测试
    data = np.load(str(Path(__file__).resolve().parent / 'eog_dataset.npz'))
    X, y = data['X'], data['y']

    # 测5个眨眼样本
    print("=== 眨眼样本测试 ===")
    blink_idx = np.where(y == 1)[0][:5]
    for i, idx in enumerate(blink_idx):
        is_blink, prob = detect_blink(X[idx])
        print(f"  样本{i+1}: 预测={is_blink}, 概率={prob:.4f}, 真实=眨眼")

    # 测5个非眨眼样本
    print("\n=== 非眨眼样本测试 ===")
    nonblink_idx = np.where(y == 0)[0][:5]
    for i, idx in enumerate(nonblink_idx):
        is_blink, prob = detect_blink(X[idx])
        print(f"  样本{i+1}: 预测={is_blink}, 概率={prob:.4f}, 真实=不眨眼")
