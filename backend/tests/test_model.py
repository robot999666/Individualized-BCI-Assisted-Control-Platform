from pathlib import Path

import numpy as np

from app.services.bci_model_service import Bci4ClassService


ASSET_DIR = Path(__file__).resolve().parents[2] / "algorithms" / "bci_4class"


def test_models_load_and_are_ready() -> None:
    service = Bci4ClassService(ASSET_DIR)
    assert service.ready, service.error
    assert set(service.models) == {3, 22}
    assert set(service.checksums) == {"3ch", "22ch"}


def test_inference_is_deterministic_and_probabilities_are_valid() -> None:
    service = Bci4ClassService(ASSET_DIR, self_test=False)
    with np.load(ASSET_DIR / "data" / "S3_3ch.npz", allow_pickle=False) as data:
        x = data["X"][:8]
    first = service.predict_proba(x)
    second = service.predict_proba(x)
    np.testing.assert_array_equal(first, second)
    assert first.shape == (8, 4)
    assert np.isfinite(first).all()
    np.testing.assert_allclose(first.sum(axis=1), 1.0, atol=1e-6)
