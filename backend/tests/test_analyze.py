import io
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from app.api.deps import bci_service
from app.main import app

client = TestClient(app)
ASSET_DIR = Path(__file__).resolve().parents[2] / "algorithms" / "bci_4class"


def _fixture(channels: int = 3, trials: int = 8) -> tuple[np.ndarray, np.ndarray]:
    with np.load(
        ASSET_DIR / "data" / f"S3_{channels}ch.npz", allow_pickle=False
    ) as data:
        return data["X"][:trials], data["y"][:trials]


def _npz_bytes(x: np.ndarray | None, y: np.ndarray | None = None, **extra: object) -> bytes:
    stream = io.BytesIO()
    payload: dict[str, object] = dict(extra)
    if x is not None:
        payload["X"] = x
    if y is not None:
        payload["y"] = y
    np.savez_compressed(stream, **payload)
    return stream.getvalue()


def _post(content: bytes, filename: str = "batch.npz", **fields: str):
    data = {"sampling_rate_hz": "250", "unit": "uV", **fields}
    return client.post(
        "/api/v1/analyze",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        data=data,
    )


def test_analyze_valid_labeled_batch() -> None:
    x, y = _fixture()
    response = _post(_npz_bytes(x, y))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["source"] == "upload"
    assert data["model_mode"] == "cold_start"
    assert data["trial_count"] == 8
    assert data["channel_layout"] == "3ch"
    assert data["validation"]["labeled_trials"] == 8
    assert len(data["predictions"]) == 8
    assert data["signal"]["channels"] == ["C3", "Cz", "C4"]
    assert len(data["signal"]["timestamps"]) == 501


def test_analyze_accepts_22_channels_without_labels() -> None:
    x, _ = _fixture(22, 4)
    response = _post(_npz_bytes(x))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["channel_layout"] == "22ch"
    assert data["validation"] is None
    assert all(item["expected_class_id"] is None for item in data["predictions"])


def test_rejects_single_trial() -> None:
    x, y = _fixture(trials=1)
    response = _post(_npz_bytes(x, y))
    assert response.status_code == 422
    assert "至少需要 2 个 trial" in response.json()["detail"]


def test_rejects_wrong_channels_and_window_size() -> None:
    assert _post(_npz_bytes(np.zeros((2, 4, 501)))).status_code == 422
    assert _post(_npz_bytes(np.zeros((2, 3, 500)))).status_code == 422


def test_rejects_sampling_rate_unit_and_non_finite_values() -> None:
    x, _ = _fixture(trials=2)
    assert _post(_npz_bytes(x), sampling_rate_hz="256").status_code == 422
    assert _post(_npz_bytes(x), unit="V").status_code == 422
    x = x.copy()
    x[0, 0, 0] = np.nan
    assert _post(_npz_bytes(x)).status_code == 422


def test_rejects_missing_x_object_array_and_extra_arrays() -> None:
    assert _post(_npz_bytes(None, y=np.array([0, 1]))).status_code == 422
    objects = np.empty((2, 3, 501), dtype=object)
    objects.fill(1.0)
    assert _post(_npz_bytes(objects)).status_code == 422
    x, _ = _fixture(trials=2)
    assert _post(_npz_bytes(x, metadata=np.array([1]))).status_code == 422


def test_rejects_wrong_extension_and_invalid_zip() -> None:
    x, _ = _fixture(trials=2)
    assert _post(_npz_bytes(x), filename="batch.csv").status_code == 422
    assert _post(b"not a zip").status_code == 422


def test_health_remains_responsive_while_inference_runs(monkeypatch) -> None:
    """CPU 推理在线程池等待时，健康接口不应被事件循环阻塞。"""
    x, _ = _fixture(trials=4)
    content = _npz_bytes(x)
    started = threading.Event()
    release = threading.Event()
    original = bci_service.predict_proba

    def delayed_predict(batch: np.ndarray) -> np.ndarray:
        started.set()
        if not release.wait(timeout=3):
            raise TimeoutError("测试未释放推理线程")
        return original(batch)

    monkeypatch.setattr(bci_service, "predict_proba", delayed_predict)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(_post, content)
        assert started.wait(timeout=2)
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["model_ready"] is True
        release.set()
        assert pending.result(timeout=3).status_code == 200
