"""FBCSP 四分类模型 + EA 冷启动（自包含，无内部依赖）。

四分类：0=左转(左手), 1=右转(右手), 2=直行(双脚), 3=停止(舌头)
支持 22 通道（完整电极）和 3 通道（C3/Cz/C4）两种输入。

两种使用方式：
  1. 校准模式（有校准数据）：用 FBCSPModel.fit(X, y) 在用户校准数据上训练。
  2. 冷启动模式（无校准数据）：加载预训练模型（models/coldstart_*.pkl），
     用 ColdStartModel 对目标数据做 EA 对齐后分类。

输入格式：np.ndarray，float32/float64，形状 (n_trials, n_channels, n_times)，
    单位 μV，采样率 250Hz，n_times 建议 501（2 秒窗口）。

依赖：numpy, scipy, scikit-learn, mne
"""
import pickle

import numpy as np
from mne.decoding import CSP
from scipy.linalg import sqrtm, inv
from scipy.signal import butter, filtfilt
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis

SFREQ = 250
BANDS = [(4, 12), (8, 16), (12, 24), (20, 36)]
C3CZ_C4 = [7, 9, 11]          # 22 通道中 C3/Cz/C4 的索引
CLASS_NAMES = ["左转", "右转", "直行", "停止"]


def bandpass(X, low, high, sfreq=SFREQ, order=4):
    b, a = butter(order, [low, high], btype="band", fs=sfreq)
    return filtfilt(b, a, X, axis=-1)


def euclidean_alignment(X, return_ref=False):
    """欧氏对齐（EA）：用一组 trial 自己的平均空间协方差做白化。

    用于跨受试者/冷启动：消除个体间空间分布差异。
    X: (n_trials, n_channels, n_times)
    """
    X = np.asarray(X, dtype=np.float64)
    n, ch = X.shape[0], X.shape[1]
    R = np.mean([X[i] @ X[i].T for i in range(n)], axis=0)
    R = R + 1e-6 * np.trace(R) / ch * np.eye(ch)
    R_inv_sqrt = inv(sqrtm(R))
    Xa = np.array([R_inv_sqrt @ X[i] for i in range(n)])
    if return_ref:
        return Xa, R_inv_sqrt
    return Xa


class FBCSPModel:
    """FBCSP（滤波组共空间模式）+ LDA 四分类。"""

    def __init__(self, sfreq=SFREQ, bands=BANDS):
        self.sfreq = sfreq
        self.bands = bands
        self.csps = None
        self.clf = None
        self.n_channels = None

    def _n_comp(self, n_ch):
        return min(6, n_ch)          # 22通道用6，3通道用3

    def fit(self, X, y):
        X = np.asarray(X, dtype=np.float64)
        self.n_channels = X.shape[1]
        n_comp = self._n_comp(X.shape[1])
        feats, self.csps = [], []
        for low, high in self.bands:
            Xf = bandpass(X, low, high, self.sfreq)
            csp = CSP(n_components=n_comp, norm_trace=False, log=True)
            feats.append(csp.fit_transform(Xf, y))
            self.csps.append(csp)
        self.clf = LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto")
        self.clf.fit(np.hstack(feats), y)
        return self

    def _features(self, X):
        X = np.asarray(X, dtype=np.float64)
        return np.hstack([csp.transform(bandpass(X, lo, hi, self.sfreq))
                          for csp, (lo, hi) in zip(self.csps, self.bands)])

    def predict(self, X):
        return self.clf.predict(self._features(X))

    def predict_proba(self, X):
        return self.clf.predict_proba(self._features(X))

    def save(self, path):
        with open(path, "wb") as f:
            pickle.dump({"csps": self.csps, "clf": self.clf,
                         "n_channels": self.n_channels}, f)

    @classmethod
    def load(cls, path):
        obj = cls()
        d = pickle.load(open(path, "rb"))
        obj.csps, obj.clf, obj.n_channels = d["csps"], d["clf"], d["n_channels"]
        return obj


class ColdStartModel:
    """冷启动（无校准）模型：对目标数据做 EA 对齐，再用预训练 FBCSP 分类。

    用法：
        m = ColdStartModel.load("models/coldstart_22ch.pkl")
        pred = m.predict(X_new)        # X_new 为新用户的无标签数据
    """

    def __init__(self, fbcsp):
        self.fbcsp = fbcsp

    def predict(self, X):
        return self.fbcsp.predict(euclidean_alignment(X))

    def predict_proba(self, X):
        return self.fbcsp.predict_proba(euclidean_alignment(X))

    @classmethod
    def load(cls, fbcsp_path):
        return cls(FBCSPModel.load(fbcsp_path))
