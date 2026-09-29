"""Inspect array headers before NumPy can allocate attacker-declared shapes."""

import io
import math
import zipfile
import zlib

import numpy as np
from fastapi import HTTPException


def _header(stream, size, max_bytes):
    version = np.lib.format.read_magic(stream)
    shape, _, dtype = np.lib.format._read_array_header(stream, version, max_header_size=10000)
    if dtype.hasobject or dtype.kind not in 'fiu' or len(shape) > 3 or any(n <= 0 for n in shape):
        raise ValueError('Only nonempty numeric arrays are accepted')
    count = math.prod(shape)
    if count*dtype.itemsize > max_bytes or count*8 > max_bytes:
        raise HTTPException(413, '数组尺寸超过解压或转换后的大小限制')
    if stream.tell()+count*dtype.itemsize != size:
        raise ValueError('Array header and payload size do not match')
    return count*8


def read_numeric_npz(content, max_bytes, allowed=('X', 'y')):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if not members or len(members) > len(allowed) or len(set(names)) != len(names) or 'X.npy' not in names:
                raise ValueError('Missing or duplicate arrays')
            if any(name not in {key+'.npy' for key in allowed} for name in names):
                raise ValueError('Unexpected archive member')
            if any(member.flag_bits & 1 for member in members):
                raise ValueError('Encrypted archives are not accepted')
            if sum(member.file_size for member in members) > max_bytes:
                raise HTTPException(413, 'NPZ 解压后超过大小限制')
            normalized = 0
            for member in members:
                with archive.open(member) as stream:
                    normalized += _header(stream, member.file_size, max_bytes)
            if normalized > max_bytes:
                raise HTTPException(413, 'NPZ 数组转换后超过大小限制')
        with np.load(io.BytesIO(content), allow_pickle=False, max_header_size=10000) as payload:
            return {key: payload[key] for key in payload.files}
    except HTTPException:
        raise
    except (ValueError, TypeError, OSError, EOFError, KeyError, OverflowError, zipfile.BadZipFile, zlib.error, NotImplementedError) as exc:
        raise HTTPException(422, 'NPZ 数组格式无效、文件损坏或包含不允许的内容') from exc


def read_numeric_npy(content, max_bytes):
    try:
        stream = io.BytesIO(content)
        _header(stream, len(content), max_bytes)
        return np.load(io.BytesIO(content), allow_pickle=False, max_header_size=10000)
    except HTTPException:
        raise
    except (ValueError, TypeError, OSError, EOFError, OverflowError) as exc:
        raise HTTPException(422, 'NPY 数组格式无效') from exc
