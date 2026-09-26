"""BCI 四分类冷启动模型服务。

权重只从仓库内受信任目录加载；用户上传的 NPZ 永远不会被反序列化为 Python 对象。
冷启动 EA 使用请求内整批 trial 计算参考协方差，因此预测具有批次耦合性。
"""

from __future__ import annotations

import hashlib
import logging
import pickle
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import mne
import scipy
from scipy.linalg import inv, sqrtm
from scipy.signal import butter, filtfilt
import sklearn

LOGGER = logging.getLogger(__name__)

SFREQ: Final = 250
WINDOW_SAMPLES: Final = 501
BANDS: Final = ((4, 12), (8, 16), (12, 24), (20, 36))
CLASS_LABELS: Final = ("left", "right", "forward", "stop")
CLASS_NAMES_ZH: Final = ("左转", "右转", "直行", "停止")
CHANNEL_NAMES: Final = {
    3: ("C3", "Cz", "C4"),
    22: (
        "Fz", "FC3", "FC1", "FCz", "FC2", "FC4", "C5", "C3", "C1",
        "Cz", "C2", "C4", "C6", "CP3", "CP1", "CPz", "CP2", "CP4",
        "P1", "Pz", "P2", "POz",
    ),
}
EXPECTED_CHECKSUMS: Final = {
    3: "7def0b2bd7bf626b0cec43e8f1007d5c90535e2bb334392fde995c2e57bd305d",
    22: "461813eac3cc80fe863ecf7703185fb570c89ec92df5fb84451e318b4a3f554e",
}


def _repo_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bandpass(x: np.ndarray, low: float, high: float) -> np.ndarray:
    b, a = butter(4, [low, high], btype="band", fs=SFREQ)
    return filtfilt(b, a, x, axis=-1)


def _euclidean_alignment(x: np.ndarray) -> np.ndarray:
    n_trials, n_channels = x.shape[:2]
    reference = np.mean([x[i] @ x[i].T for i in range(n_trials)], axis=0)
    reference += (
        1e-6 * np.trace(reference) / n_channels * np.eye(n_channels)
    )
    inverse_sqrt = inv(sqrtm(reference))
    aligned = np.asarray([inverse_sqrt @ trial for trial in x])
    # sqrtm can return complex values because of floating-point noise.
    return np.real_if_close(aligned, tol=1000).astype(np.float64)


@dataclass(frozen=True)
class RuntimeModel:
    csps: list[object]
    classifier: object
    n_channels: int
    checksum: str

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        aligned = _euclidean_alignment(x)
        features = np.hstack(
            [
                csp.transform(_bandpass(aligned, low, high))
                for csp, (low, high) in zip(self.csps, BANDS)
            ]
        )
        probabilities = np.asarray(
            self.classifier.predict_proba(features), dtype=np.float64
        )
        classes = np.asarray(self.classifier.classes_, dtype=int)
        ordered = np.zeros((len(x), 4), dtype=np.float64)
        ordered[:, classes] = probabilities
        return ordered


class Bci4ClassService:
    """一次加载两种通道布局的只读模型，并提供批量冷启动推理。"""

    def __init__(self, asset_dir: Path | None = None, self_test: bool = True) -> None:
        self.asset_dir = asset_dir or (_repo_dir() / "algorithms" / "bci_4class")
        self.models: dict[int, RuntimeModel] = {}
        self.error: str | None = None
        self.loaded_at_seconds: float | None = None
        started = time.perf_counter()
        try:
            for channels in (3, 22):
                self.models[channels] = self._load_model(channels)
            if self_test:
                self._self_test()
            self.loaded_at_seconds = round(time.perf_counter() - started, 4)
            LOGGER.info(
                "BCI models ready layouts=%s load_seconds=%.4f",
                sorted(self.models),
                self.loaded_at_seconds,
            )
        except Exception as exc:  # 服务仍可启动，让 health 暴露失败原因
            self.models.clear()
            self.error = f"{type(exc).__name__}: {exc}"
            LOGGER.exception("BCI model initialization failed")

    @property
    def ready(self) -> bool:
        return set(self.models) == {3, 22} and self.error is None

    @property
    def versions(self) -> dict[str, str]:
        return {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "mne": mne.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        }

    @property
    def checksums(self) -> dict[str, str]:
        return {f"{ch}ch": model.checksum for ch, model in self.models.items()}

    def _load_model(self, channels: int) -> RuntimeModel:
        path = self.asset_dir / "models" / f"coldstart_{channels}ch.pkl"
        actual_checksum = _sha256(path)
        expected_checksum = EXPECTED_CHECKSUMS[channels]
        if actual_checksum != expected_checksum:
            raise RuntimeError(
                f"{path.name} SHA-256 不匹配：期望 {expected_checksum}，实际 {actual_checksum}"
            )
        # 此处只读取镜像内、已校验 checksum 的受信任模型文件。
        with path.open("rb") as stream:
            payload = pickle.load(stream)  # noqa: S301
        if set(payload) != {"csps", "clf", "n_channels"}:
            raise RuntimeError(f"{path.name} 模型结构不符合预期")
        if int(payload["n_channels"]) != channels:
            raise RuntimeError(f"{path.name} 通道布局与文件名不一致")
        return RuntimeModel(
            csps=list(payload["csps"]),
            classifier=payload["clf"],
            n_channels=channels,
            checksum=actual_checksum,
        )

    def _self_test(self) -> None:
        for channels in (3, 22):
            path = self.asset_dir / "data" / f"S3_{channels}ch.npz"
            with np.load(path, allow_pickle=False) as payload:
                sample = np.asarray(payload["X"][:4], dtype=np.float64)
            probabilities = self.models[channels].predict_proba(sample)
            self._validate_probabilities(probabilities, len(sample))

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if not self.ready:
            raise RuntimeError(self.error or "BCI 模型尚未就绪")
        channels = int(x.shape[1])
        model = self.models.get(channels)
        if model is None:
            raise ValueError(f"不支持 {channels} 通道输入")
        started = time.perf_counter()
        probabilities = model.predict_proba(np.asarray(x, dtype=np.float64))
        self._validate_probabilities(probabilities, len(x))
        LOGGER.info(
            "BCI batch inferred trials=%d channels=%d elapsed_ms=%.2f",
            len(x),
            channels,
            (time.perf_counter() - started) * 1000,
        )
        return probabilities

    @staticmethod
    def _validate_probabilities(probabilities: np.ndarray, trials: int) -> None:
        if probabilities.shape != (trials, 4):
            raise RuntimeError(f"模型概率形状异常：{probabilities.shape}")
        if not np.isfinite(probabilities).all():
            raise RuntimeError("模型输出包含 NaN 或 Inf")
        if not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-6):
            raise RuntimeError("模型概率之和不为 1")

    def demo_batch(self, trial_count: int) -> tuple[np.ndarray, np.ndarray]:
        path = self.asset_dir / "data" / "S3_3ch.npz"
        with np.load(path, allow_pickle=False) as payload:
            x = np.asarray(payload["X"])
            y = np.asarray(payload["y"])
        per_class = max(1, trial_count // 4)
        indices: list[int] = []
        for class_id in range(4):
            indices.extend(np.flatnonzero(y == class_id)[:per_class].tolist())
        if len(indices) < trial_count:
            selected = set(indices)
            indices.extend(i for i in range(len(y)) if i not in selected)
        indices = indices[:trial_count]
        return x[indices], y[indices]
