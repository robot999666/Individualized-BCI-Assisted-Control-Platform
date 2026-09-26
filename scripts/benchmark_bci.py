"""记录两种通道布局的完整 S3 软件回归基线。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

REPO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_DIR / "backend"))

from app.services.bci_model_service import Bci4ClassService  # noqa: E402


def main() -> None:
    service = Bci4ClassService(self_test=False)
    if not service.ready:
        raise RuntimeError(service.error)
    print("layout,trials,accuracy,seconds,deterministic,max_probability_sum_error")
    for channels in (3, 22):
        with np.load(
            REPO_DIR / "algorithms" / "bci_4class" / "data" / f"S3_{channels}ch.npz",
            allow_pickle=False,
        ) as payload:
            x, y = payload["X"], payload["y"]
        started = time.perf_counter()
        probabilities = service.predict_proba(x)
        elapsed = time.perf_counter() - started
        repeated = service.predict_proba(x)
        print(
            f"{channels}ch,{len(x)},"
            f"{np.mean(np.argmax(probabilities, axis=1) == y):.6f},"
            f"{elapsed:.4f},{np.array_equal(probabilities, repeated)},"
            f"{np.max(np.abs(probabilities.sum(axis=1) - 1.0)):.3e}"
        )


if __name__ == "__main__":
    main()
