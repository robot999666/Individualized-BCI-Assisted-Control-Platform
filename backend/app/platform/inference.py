import hashlib
import time

import numpy as np
from scipy.linalg import inv, sqrtm

from app.api.deps import bci_service
from app.services.bci_model_service import BANDS, _bandpass
from algorithms.system_integration.core import _preprocess

PIPELINE_VERSION = "integration-global4-36-v1"


def calibrate(x):
    x = _preprocess(x)
    reference = np.mean(x @ np.swapaxes(x, 1, 2), axis=0)
    scale = np.trace(reference) / x.shape[1]
    if not np.isfinite(scale) or scale <= 1e-12:
        raise ValueError("校准信号能量不足")
    matrix = np.real_if_close(inv(sqrtm(reference + 1e-6 * scale * np.eye(x.shape[1]))))
    if np.iscomplexobj(matrix) or not np.isfinite(matrix).all():
        raise ValueError("EA reference 无效")
    return matrix.astype(np.float64)


def fingerprint(trial):
    return hashlib.sha256(np.asarray(trial, dtype="<f8").tobytes()).hexdigest()


def predict(x, reference, personalized=None):
    start = time.perf_counter()
    if not bci_service.ready:
        raise ValueError("模型未就绪")
    model = bci_service.models[x.shape[1]]
    prepared = _preprocess(x)
    aligned = reference @ prepared if personalized is None else prepared
    bands = [_bandpass(aligned, low, high) for low, high in BANDS]
    pre = time.perf_counter()
    csps = model.csps if personalized is None else personalized._csps
    classifier = model.classifier if personalized is None else personalized._clf
    features = np.hstack([csp.transform(band) for csp, band in zip(csps, bands)])
    feat = time.perf_counter()
    probability = np.zeros((len(x), 4))
    probability[:, np.asarray(classifier.classes_, dtype=int)] = classifier.predict_proba(features)
    end = time.perf_counter()
    bci_service._validate_probabilities(probability, len(x))
    return probability, {"preprocessing_ms": (pre-start)*1000,
                         "feature_extraction_ms": (feat-pre)*1000,
                         "model_inference_ms": (end-feat)*1000}
