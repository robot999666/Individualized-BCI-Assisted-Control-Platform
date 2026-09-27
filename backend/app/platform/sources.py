"""Server-owned catalog and provenance checks shared by replay and evaluation."""
import hashlib
import json
from fastapi import HTTPException

from app.core.config import get_settings
from app.services.npz_reader import read_bci_npz

PRESETS = {
    'a01-3ch': ('A01 · 3通道 · 双眨眼闭环演示', ''),
    'a01-22ch': ('A01 · 22通道 · 完整EEG模型', 'a01-22ch'),
    'a02-3ch': ('A02 · 3通道 · 同步EEG/EOG', 'a02-3ch'),
    'a02-22ch': ('A02 · 22通道 · 同步EEG/EOG', 'a02-22ch'),
}


def directory(source_id):
    if source_id not in PRESETS:
        raise HTTPException(422, '请选择有效的内置数据来源')
    return get_settings().demo_data_dir / PRESETS[source_id][1]


def load_source(source_id, split):
    root = directory(source_id)
    path = root / f'{split}.npz'
    try:
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != manifest[split]['npz_sha256']:
            raise HTTPException(503, '内置数据校验失败')
        batch = read_bci_npz(path.name, content, 250, 'uV')
    except (OSError, KeyError, ValueError) as exc:
        raise HTTPException(503, '此来源尚未准备，请运行 scripts/prepare_sources.py') from exc
    return batch.x, {'dataset': 'BCI IV 2a', 'source_id': source_id,
                     'subject': manifest['subject'], 'split': split,
                     'protocol': manifest['protocol'], **manifest[split]}


def source_key(source, subject_id, channels):
    if source.get('dataset') == 'BCI IV 2a':
        return source.get('source_id', f"{source.get('subject', 'A01').lower()}-{channels}ch")
    # Legacy uploads belonged to this participant; newly declared collection IDs must match.
    return source.get('source_id', f'upload:{subject_id}:default')


def check_pair(profile, experiment):
    if profile.status != 'READY' or profile.user_id != experiment.subject_id:
        raise HTTPException(422, '校准档案不可用或用户不匹配')
    channels = len(profile.channel_layout)
    if channels != experiment.source.get('channels'):
        raise HTTPException(422, '校准与回放通道布局不一致')
    if source_key(profile.source, profile.user_id, channels) != source_key(experiment.source, experiment.subject_id, channels):
        raise HTTPException(422, '校准与回放必须使用同一数据来源，请重新选择实验')
