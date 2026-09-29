"""安全读取 BCI 批量 NPZ 上传。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from fastapi import HTTPException

from app.core.config import get_settings
from app.services.array_uploads import read_numeric_npz


@dataclass(frozen=True)
class BciBatch:
    x: np.ndarray
    y: np.ndarray | None


def _reject(detail: str, status_code: int = 422) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


def read_bci_npz(
    filename: str,
    content: bytes,
    sampling_rate_hz: int,
    unit: str,
) -> BciBatch:
    settings = get_settings()
    if not filename.lower().endswith(".npz"):
        _reject("仅支持 NPZ 文件上传（.npz 扩展名）")
    if not content:
        _reject("文件内容为空")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        _reject(f"压缩文件超过大小限制（{settings.max_upload_mb}MB）", 413)
    if sampling_rate_hz != settings.bci_sampling_rate_hz:
        _reject(f"采样率必须为 {settings.bci_sampling_rate_hz} Hz")
    if unit.strip().lower().replace("μ", "u").replace("µ", "u") != "uv":
        _reject("输入单位必须为 μV（表单字段 unit=uV）")

    max_decompressed = settings.bci_max_decompressed_mb * 1024 * 1024
    arrays = read_numeric_npz(content, max_decompressed)
    x, y = arrays['X'], arrays.get('y')

    if x.dtype.kind not in "fiu":
        _reject("X 必须是数值数组，禁止对象数组")
    if x.ndim != 3:
        _reject("X 形状必须为 (n_trials, n_channels, 501)")
    n_trials, n_channels, n_times = x.shape
    if n_trials < 2:
        _reject("冷启动 EA 至少需要 2 个 trial，不能进行单 trial 推理")
    if n_channels not in (3, 22):
        _reject("通道数必须为 3 或 22")
    if n_times != settings.bci_window_samples:
        _reject(f"每个 trial 必须为 {settings.bci_window_samples} 个采样点")
    if x.nbytes > max_decompressed:
        _reject(
            f"X 数组超过解压后大小限制（{settings.bci_max_decompressed_mb}MB）",
            413,
        )
    x = np.asarray(x, dtype=np.float64)
    if not np.isfinite(x).all():
        _reject("X 包含 NaN 或 Inf")

    if y is not None:
        if y.dtype.kind not in "iu" or y.shape != (n_trials,):
            _reject("y 必须是一维整数数组，长度与 trial 数一致")
        if not np.isin(y, [0, 1, 2, 3]).all():
            _reject("y 标签只能取 0、1、2、3")
        y = np.asarray(y, dtype=np.int64)
    return BciBatch(x=x, y=y)
