"""
core.py - 脑电+眼电多模态意图识别系统核心模块

整合两个模态：
  1. EEG脑电四分类：左转/右转/直行/停止（FBCSP+LDA）
  2. EOG眼电：眨眼=指令确认，闭眼=紧急求助

系统状态机流程（对应项目图2）：
  - 持续输入EEG+EOG信号
  - 安全监测：信号丢失>5s / 长时间闭眼≥1.5s → 紧急求助
  - EEG每2秒输出一个候选指令
  - 指令变化时需要连续两次眨眼确认
  - 停止指令可立即执行
  - 闭眼检测：EOG持续正向偏移>25uV超过1.5s = 长时间闭眼
"""
import os
import pickle
import numpy as np
from scipy.signal import butter, filtfilt
from mne.decoding import CSP
from scipy.linalg import sqrtm, inv
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "models")

SFREQ = 250
EEG_WINDOW = 501       # 2秒脑电窗
EOG_WINDOW = 250       # 1秒眼电窗

# 四分类标签
CLASS_NAMES = ["左转", "右转", "直行", "停止"]
CLASS_LEFT, CLASS_RIGHT, CLASS_GO, CLASS_STOP = 0, 1, 2, 3


# ============================================================
#  EEG 脑电四分类模型（FBCSP + EA）
# ============================================================

BANDS = [(4, 12), (8, 16), (12, 24), (20, 36)]
EEG_LOW = 4.0    # 全局预处理带通下限
EEG_HIGH = 36.0  # 全局预处理带通上限


def _bandpass_eeg(X, low, high, sfreq=SFREQ, order=4):
    b, a = butter(order, [low, high], btype="band", fs=sfreq)
    return filtfilt(b, a, X, axis=-1)


def _preprocess(X):
    """图1第一步：全局带通滤波 4~36Hz（维度不变）。"""
    return _bandpass_eeg(X, EEG_LOW, EEG_HIGH)


def _euclidean_alignment(X):
    """欧氏对齐：用trial自己的平均空间协方差白化。"""
    X = np.asarray(X, dtype=np.float64)
    n, ch = X.shape[0], X.shape[1]
    R = np.mean([X[i] @ X[i].T for i in range(n)], axis=0)
    R = R + 1e-6 * np.trace(R) / ch * np.eye(ch)
    R_inv_sqrt = inv(sqrtm(R))
    return np.array([R_inv_sqrt @ X[i] for i in range(n)])


class EEGClassifier:
    """脑电四分类器，支持两种模式：

    模式1 - 冷启动（无校准数据）：
        clf = EEGClassifier(calibrated=False, n_channels=22)
        pred = clf.predict(X)  # X: (trials, channels, 501)

    模式2 - 校准后（有用户本人校准数据）：
        clf = EEGClassifier(calibrated=True, n_channels=22)
        clf.calibrate(X_cal, y_cal)  # 用用户数据训练
        pred = clf.predict(X_new)

    输入：(n_trials, n_channels, n_times)，μV，250Hz，n_times=501
    输出：0=左转, 1=右转, 2=直行, 3=停止
    """

    def __init__(self, calibrated=False, n_channels=22):
        self.n_channels = n_channels
        self.calibrated = calibrated
        self._csps = None
        self._clf = None
        self._coldstart_model = None

        if not calibrated:
            # 冷启动：加载预训练模型
            fname = f"coldstart_{n_channels}ch.pkl"
            with open(os.path.join(MODEL_DIR, fname), "rb") as f:
                d = pickle.load(f)
            self._coldstart_csps = d["csps"]
            self._coldstart_clf = d["clf"]

    def calibrate(self, X, y):
        """用用户本人的校准数据训练个性化模型。

        Args:
            X: (n_trials, n_channels, 501)，μV
            y: (n_trials,)，0=左转/1=右转/2=直行/3=停止
        """
        X = np.asarray(X, dtype=np.float64)
        X = _preprocess(X)  # Match prediction-time global filtering.
        n_comp = min(6, X.shape[1])
        feats, self._csps = [], []
        for low, high in BANDS:
            Xf = _bandpass_eeg(X, low, high)
            csp = CSP(n_components=n_comp, norm_trace=False, log=True)
            feats.append(csp.fit_transform(Xf, y))
            self._csps.append(csp)
        self._clf = LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto")
        self._clf.fit(np.hstack(feats), y)
        self.calibrated = True

    def _features(self, X):
        X = np.asarray(X, dtype=np.float64)
        X = _preprocess(X)  # 图1：全局带通4-36Hz
        return np.hstack([
            csp.transform(_bandpass_eeg(X, lo, hi))
            for csp, (lo, hi) in zip(self._csps, BANDS)
        ])

    def predict(self, X):
        """输入 (n_trials, n_channels, 501)，输出类别数组。"""
        if self.calibrated:
            return self._clf.predict(self._features(X)).astype(int)
        else:
            # 冷启动：先全局带通 → EA对齐 → FBCSP
            X = _preprocess(np.asarray(X, dtype=np.float64))
            X_aligned = _euclidean_alignment(X)
            feats = np.hstack([
                csp.transform(_bandpass_eeg(X_aligned, lo, hi))
                for csp, (lo, hi) in zip(self._coldstart_csps, BANDS)
            ])
            return self._coldstart_clf.predict(feats).astype(int)

    def predict_proba(self, X):
        if self.calibrated:
            return self._clf.predict_proba(self._features(X))
        else:
            X = _preprocess(np.asarray(X, dtype=np.float64))
            X_aligned = _euclidean_alignment(X)
            feats = np.hstack([
                csp.transform(_bandpass_eeg(X_aligned, lo, hi))
                for csp, (lo, hi) in zip(self._coldstart_csps, BANDS)
            ])
            return self._coldstart_clf.predict_proba(feats)


# ============================================================
#  EOG 眼电眨眼检测器
# ============================================================

class EOGBlinkDetector:
    """眼电眨眼检测：输入1秒EOG信号，判断是否眨眼。

    用法：
        det = EOGBlinkDetector()
        is_blink, prob = det.detect(eog_1sec)  # eog_1sec: (250,) uV
    """

    def __init__(self, threshold=0.5):
        import joblib
        self.model = joblib.load(os.path.join(MODEL_DIR, "blink_detector.pkl"))
        self.threshold = threshold

    def _bandpass(self, data, low=1.0, high=15.0, order=4):
        nyq = SFREQ / 2.0
        b, a = butter(order, [low / nyq, high / nyq], btype='band')
        return filtfilt(b, a, data)

    def _extract_features(self, window):
        from scipy.stats import skew, kurtosis
        feats = [
            np.max(window), np.min(window),
            np.max(window) - np.min(window), np.mean(window),
            np.var(window), np.sqrt(np.mean(window**2)),
            np.sum(np.abs(np.diff(window))),
            np.argmax(window) / len(window),
        ]
        center = len(window) // 2
        pre = window[center-25:center]
        feats.append((window[center] - pre[0]) / 0.1)
        post = window[center:center+25]
        feats.append((post[-1] - window[center]) / 0.1)
        center_e = np.sum(window[center-25:center+25]**2)
        feats.append(center_e / (np.sum(window**2) + 1e-10))
        feats.append(np.sum(np.diff(np.sign(window)) != 0))
        feats.append(skew(window))
        feats.append(kurtosis(window))
        return np.array(feats).reshape(1, -1)

    def detect(self, eog_window_uv, prefiltered=False):
        """检测1秒EOG窗是否包含眨眼。

        Args:
            eog_window_uv: (250,) array，垂直EOG信号，单位uV
        Returns:
            (is_blink: bool, probability: float)
        """
        data = np.asarray(eog_window_uv, dtype=np.float64)
        filtered = data if prefiltered else self._bandpass(data)
        feat = self._extract_features(filtered)
        prob = self.model.predict_proba(feat)[0, 1]
        return prob > self.threshold, prob


# ============================================================
#  系统状态机（对应项目图2）
# ============================================================

class SystemState:
    IDLE = "idle"               # 等待指令
    MOVING = "moving"           # 正在执行运动
    STOPPED = "stopped"         # 已停止
    EMERGENCY = "emergency"     # 紧急求助


class BCISystem:
    """多模态意图识别系统主控制器。

    流程（图2）：
      1. 持续接收EEG+EOG信号
      2. 安全监测：信号丢失>5s / 长时间闭眼≥1.5s → 紧急求助
      3. EEG每2秒给出候选指令
      4. 指令与当前状态不同时，需连续两次眨眼确认
      5. 停止指令立即执行

    使用方式：
        system = BCISystem(n_channels=22)
        # 实时循环：
        while True:
            eeg_trial = read_eeg_2s()      # (22, 501)
            eog_window = read_eog_1s()     # (250,)
            result = system.update(eeg_trial, eog_window)
            if result:
                print(result)
    """

    def __init__(self, n_channels=22):
        self.eeg = EEGClassifier(calibrated=False, n_channels=n_channels)
        self.eog = EOGBlinkDetector()

        # 状态机
        self.state = SystemState.IDLE
        self.current_command = None       # 当前执行的指令
        self.pending_command = None       # 待确认的候选指令
        self.blink_count = 0              # 连续眨眼计数
        self.last_blink_time = -999       # 上次眨眼时间（秒）
        self.time = 0.0                   # 内部计时器

        # 安全监测
        self.last_eeg_time = 0.0
        self.last_eog_time = 0.0
        self.was_blink = False
        self.eye_closed_time = None       # 闭眼起始时间

        # 参数
        self.BLINK_CONFIRM_WINDOW = 2.0   # 两次眨眼确认窗口（秒）
        self.SIGNAL_LOSS_TIMEOUT = 5.0   # 信号丢失超时（秒）
        self.LONG_CLOSURE_TIME = 1.5     # 长时间闭眼阈值（秒）
        self.EYE_CLOSE_THRESH = 25.0     # 闭眼EOG平均幅度阈值（uV）

    def calibrate_eeg(self, X_cal, y_cal):
        """用户校准时调用。

        Args:
            X_cal: (n_trials, n_channels, 501)，μV
            y_cal: labels，0=左转/1=右转/2=直行/3=停止
        """
        self.eeg = EEGClassifier(calibrated=True, n_channels=X_cal.shape[1])
        self.eeg.calibrate(X_cal, y_cal)
        print(f"[系统] EEG个性化校准完成，{len(X_cal)}个校准样本")

    def update(self, eeg_trial=None, eog_window=None, dt=0.5):
        """
        每0.5秒调用一次，传入最新信号。

        Args:
            eeg_trial: (n_channels, 501) 或 None（无新EEG数据时）
            eog_window: (250,) 或 None
            dt: 距上次调用的时间间隔（秒）

        Returns:
            dict 或 None: 系统事件，如
              {"type": "command", "command": "左转"}
              {"type": "emergency", "reason": "长时间闭眼≥1.5s"}
              {"type": "pending", "command": "右转", "msg": "请眨眼确认"}
              {"type": "state", "state": "stopped"}
        """
        self.time += dt
        events = []

        # ---- 1. 安全监测：信号丢失 ----
        if eeg_trial is not None:
            self.last_eeg_time = self.time
        if eog_window is not None:
            self.last_eog_time = self.time

        if self.time - self.last_eeg_time > self.SIGNAL_LOSS_TIMEOUT:
            events.append({"type": "emergency", "reason": "脑电信号丢失>5s"})
            self.state = SystemState.EMERGENCY
            self.current_command = "停止"
            self.pending_command = None

        # Emergency is latched. No later blink may override it.
        if self.state == SystemState.EMERGENCY:
            return events if events else None

        # ---- 2. EOG眨眼检测 + 闭眼检测 ----
        if eog_window is not None:
            eog_raw = np.asarray(eog_window, dtype=np.float64)

            # 2a. 眨眼检测：连续两次眨眼 = 确认待执行指令
            #     （紧急求助只来自安全监测：信号丢失/长时间闭眼）
            is_blink, prob = self.eog.detect(eog_raw)
            if is_blink and not self.was_blink:
                if self.time - self.last_blink_time < self.BLINK_CONFIRM_WINDOW:
                    self.blink_count += 1
                else:
                    self.blink_count = 1
                self.last_blink_time = self.time

                # 连续两次眨眼 → 确认待执行指令
                if self.blink_count >= 2:
                    if self.pending_command is not None:
                        events.append({"type": "command",
                                       "command": self.pending_command,
                                       "msg": f"连续两次眨眼确认，执行[{self.pending_command}]"})
                        self.current_command = self.pending_command
                        self.pending_command = None
                        self.state = SystemState.MOVING
                    # 无待确认指令时，眨眼忽略
                    self.blink_count = 0
            else:
                # 非眨眼，重置计数（如果超出窗口）
                if self.time - self.last_blink_time > self.BLINK_CONFIRM_WINDOW:
                    self.blink_count = 0
            self.was_blink = bool(is_blink)

            # 2b. 闭眼检测：用原始信号的平均幅度
            # 闭眼时眼球上转，垂直EOG持续正向偏移（>25uV），区别于眨眼的短尖峰
            eog_mean = np.mean(eog_raw)
            if eog_mean > self.EYE_CLOSE_THRESH:
                # EOG持续正向偏高，可能在闭眼
                if self.eye_closed_time is None:
                    self.eye_closed_time = self.time
                # 持续闭眼超过阈值 → 紧急求助
                elif self.time - self.eye_closed_time >= self.LONG_CLOSURE_TIME:
                    events.append({"type": "emergency",
                                   "reason": f"长时间闭眼≥{self.LONG_CLOSURE_TIME}s（紧急求助）"})
                    self.state = SystemState.EMERGENCY
                    self.current_command = "停止"
                    self.pending_command = None
                    self.eye_closed_time = None
                    return [event for event in events if event['type'] == 'emergency']
            else:
                # EOG回到基线，闭眼结束
                self.eye_closed_time = None

        # ---- 3. EEG四分类（图1输出候选指令）----
        if eeg_trial is not None and self.state != SystemState.EMERGENCY:
            trial = eeg_trial[np.newaxis, :, :]  # (1, ch, 501)
            pred = int(self.eeg.predict(trial)[0])
            cmd = CLASS_NAMES[pred]

            if pred == CLASS_STOP:
                # 停止指令立即执行（安全优先，不需眨眼确认）
                if self.current_command != "停止":
                    events.append({"type": "command", "command": "停止",
                                   "msg": "立即执行停止"})
                    self.current_command = "停止"
                    self.state = SystemState.STOPPED
                    self.pending_command = None
            elif cmd != self.current_command:
                # 新指令与当前不同 → 设为待确认，等待连续两次眨眼
                if self.pending_command != cmd:
                    self.pending_command = cmd
                    self.blink_count = 0
                    events.append({"type": "pending", "command": cmd,
                                   "msg": f"候选指令[{cmd}]，请连续两次眨眼确认"})
            else:
                # 指令不变，维持当前状态，清除待确认
                self.pending_command = None

        return events if events else None
