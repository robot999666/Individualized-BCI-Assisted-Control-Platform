from pathlib import Path
"""
eog_detect.py - EOG眨眼检测模块
从BCICIV 2b的连续EOG信号中自动检测眨眼事件，并构建二分类数据集。
"""
import os
import glob
import numpy as np
import mne
from scipy.signal import butter, filtfilt, find_peaks


# ============ 配置 ============
DATA_DIR = r"D:\大创\bci_data\bciciv2b"
SFREQ = 250  # BCICIV 2b采样率
EOG_CH = "EOG:ch02"  # 垂直EOG，眨眼最明显

# 眨眼检测参数
BLINK_LOW = 1.0    # Hz，带通下限
BLINK_HIGH = 15.0   # Hz，带通上限
PEAK_THRESH = 80    # uV，峰值阈值
MIN_PEAK_DIST = int(SFREQ * 0.3)  # 两次眨眼最小间隔0.3s
HALF_WIN = int(SFREQ * 0.5)       # 眨眼窗：峰值前后0.5s，共1s

# 非眨眼样本参数
N_NONBLINK_PER_FILE = 50  # 每个文件随机取多少个非眨眼窗


def bandpass(data, low, high, sfreq, order=4):
    """四阶巴特沃斯零相位带通滤波。"""
    nyq = sfreq / 2.0
    b, a = butter(order, [low / nyq, high / nyq], btype='band')
    return filtfilt(b, a, data)


def detect_blinks(eog_data_uv, sfreq=SFREQ,
                  peak_thresh=PEAK_THRESH,
                  min_dist=MIN_PEAK_DIST):
    """
    从垂直EOG信号中检测眨眼峰值位置。

    眨眼波形特征：
    - 快速正向偏转（眨眼时角膜向上，EOG正向）
    - 持续100-400ms
    - 峰值通常>80uV

    参数:
        eog_data_uv: 1D array, EOG信号（uV）
        sfreq: 采样率
        peak_thresh: 峰值阈值(uV)
        min_dist: 最小峰间距（采样点）
    返回:
        peak_indices: 眨眼峰值的采样点位置数组
    """
    # 带通滤波突出眨眼频段
    filtered = bandpass(eog_data_uv, BLINK_LOW, BLINK_HIGH, sfreq)

    # 找正向峰值（眨眼主要表现为正向偏转）
    peaks, props = find_peaks(
        filtered,
        height=peak_thresh,      # 峰值高度阈值
        distance=min_dist,       # 最小峰间距
        prominence=peak_thresh*0.5,  # 突出度阈值（排除噪声毛刺）
        width=(int(sfreq*0.05), int(sfreq*0.5))  # 峰宽50-500ms
    )

    return peaks, filtered


def extract_windows(data_uv, peak_indices, half_win=HALF_WIN):
    """
    以peak_indices为中心截取窗口。
    返回: (n_windows, 2*half_win) 的数组
    """
    n = len(data_uv)
    windows = []
    for p in peak_indices:
        start = p - half_win
        end = p + half_win
        if start >= 0 and end < n:
            windows.append(data_uv[start:end])
    return np.array(windows)


def extract_nonblink_windows(data_uv, blink_peaks, half_win=HALF_WIN,
                              n_samples=N_NONBLINK_PER_FILE,
                              safety_margin=int(SFREQ*1.0)):
    """
    从不含眨眼的平稳段随机截取非眨眼窗口。
    排除眨眼峰值前后safety_margin范围内的区域。
    """
    n = len(data_uv)
    # 标记眨眼附近的禁区
    forbidden = np.zeros(n, dtype=bool)
    for p in blink_peaks:
        lo = max(0, p - safety_margin)
        hi = min(n, p + safety_margin)
        forbidden[lo:hi] = True

    # 找可用区域
    valid_starts = half_win
    valid_ends = n - half_win
    if valid_ends <= valid_starts:
        return np.empty((0, 2*half_win))

    # 随机采样
    windows = []
    attempts = 0
    max_attempts = n_samples * 20
    while len(windows) < n_samples and attempts < max_attempts:
        center = np.random.randint(valid_starts, valid_ends)
        if not forbidden[center]:
            windows.append(data_uv[center-half_win:center+half_win])
        attempts += 1

    return np.array(windows)


def load_eog_from_gdf(fpath):
    """读取gdf文件，返回EOG:ch02信号（uV）和被试ID。"""
    raw = mne.io.read_raw_gdf(fpath, preload=True, verbose='ERROR')
    if EOG_CH not in raw.ch_names:
        # 退而求其次找任何EOG通道
        eog_chs = [ch for ch in raw.ch_names if 'EOG' in ch]
        if not eog_chs:
            return None, None, None
        ch = eog_chs[0]
    else:
        ch = EOG_CH

    data = raw[ch][0][0]  # V
    data_uv = data * 1e6  # uV
    sfreq = raw.info['sfreq']

    # 从文件名提取被试ID (B0101T -> subject 1)
    fname = os.path.basename(fpath)
    subj_id = int(fname[1:3])  # B01... -> 1

    return data_uv, sfreq, subj_id


def build_dataset(data_dir=DATA_DIR):
    """
    遍历所有gdf文件，构建眨眼/不眨眼数据集。
    返回:
        X: (n_samples, window_len) 数组
        y: (n_samples,) 标签 1=眨眼, 0=不眨眼
        subj_ids: (n_samples,) 每个样本对应的被试ID
    """
    files = sorted(glob.glob(os.path.join(data_dir, "*.gdf")))
    print(f"找到 {len(files)} 个gdf文件")

    all_blink_windows = []
    all_nonblink_windows = []
    all_blink_subj = []
    all_nonblink_subj = []

    for fpath in files:
        fname = os.path.basename(fpath)
        data_uv, sfreq, subj_id = load_eog_from_gdf(fpath)
        if data_uv is None:
            continue

        # 检测眨眼
        peaks, filtered = detect_blinks(data_uv, sfreq)

        # 截取眨眼窗
        blink_wins = extract_windows(filtered, peaks, HALF_WIN)
        # 截取非眨眼窗
        nonblink_wins = extract_nonblink_windows(
            filtered, peaks, HALF_WIN, N_NONBLINK_PER_FILE
        )

        all_blink_windows.append(blink_wins)
        all_nonblink_windows.append(nonblink_wins)
        all_blink_subj.append(np.full(len(blink_wins), subj_id))
        all_nonblink_subj.append(np.full(len(nonblink_wins), subj_id))

        print(f"  {fname}: {len(blink_wins)} blinks, {len(nonblink_wins)} non-blinks (subj {subj_id})")

    # 合并
    X_blink = np.vstack(all_blink_windows)
    X_nonblink = np.vstack(all_nonblink_windows)
    y_blink = np.ones(len(X_blink))
    y_nonblink = np.zeros(len(X_nonblink))
    subj_blink = np.concatenate(all_blink_subj)
    subj_nonblink = np.concatenate(all_nonblink_subj)

    X = np.vstack([X_blink, X_nonblink])
    y = np.concatenate([y_blink, y_nonblink])
    subj_ids = np.concatenate([subj_blink, subj_nonblink])

    print(f"\n数据集构建完成:")
    print(f"  眨眼样本: {len(X_blink)}")
    print(f"  不眨眼样本: {len(X_nonblink)}")
    print(f"  总样本: {len(X)}")
    print(f"  窗口长度: {X.shape[1]} 点 ({X.shape[1]/sfreq:.1f}s)")

    return X, y, subj_ids


if __name__ == "__main__":
    X, y, subj_ids = build_dataset()
    # 保存
    save_path = str(Path(__file__).resolve().parent / 'eog_dataset.npz')
    np.savez_compressed(save_path, X=X, y=y, subj_ids=subj_ids, sfreq=SFREQ)
    print(f"已保存到 {save_path}")
