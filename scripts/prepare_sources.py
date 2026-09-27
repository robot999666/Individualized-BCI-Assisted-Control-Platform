"""Prepare selectable real T/E sources; preserve the original demo and its pairing."""
import hashlib
import json
from pathlib import Path

import mne
import numpy as np
from prepare_demo import extract

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = ROOT / 'sample_data/demo_processed'
    original = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    for subject, channels in [('A01', 22), ('A02', 3), ('A02', 22)]:
        target = base / f'{subject.lower()}-{channels}ch'
        target.mkdir(parents=True, exist_ok=True)
        manifest = {key: original[key] for key in ('protocol', 'training_overlap', 'accuracy', 'license')}
        manifest['subject'] = subject
        for split, suffix, count in [('calibration', 'T', 40), ('evaluation', 'E', 24)]:
            x, info = extract(ROOT / f'sample_data/BCICIV_2a_gdf/{subject}{suffix}.gdf', count, channels)
            path = target / f'{split}.npz'
            np.savez_compressed(path, X=x)
            info['npz_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest[split] = info
        if subject == 'A01':
            # Same selected EEG trials; explicitly declared offline cross-dataset EOG pairing.
            (target / 'eog_demo.npz').write_bytes((base / 'eog_demo.npz').read_bytes())
            manifest['eog_pairing'] = original['eog_pairing']
        else:
            raw = mne.io.read_raw_gdf(ROOT / f'sample_data/BCICIV_2a_gdf/{subject}E.gdf', preload=True, verbose='ERROR')
            signal = raw.get_data()[23] * 1e6
            x = np.asarray([signal[t['sample_start']:t['sample_stop_exclusive']] for t in manifest['evaluation']['trials']])
            if not np.isfinite(x).all():
                raise ValueError('Invalid EOG input')
            path = target / 'eog_demo.npz'
            np.savez_compressed(path, X=x)
            manifest['eog_pairing'] = {
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'sequence': False, 'prefiltered': False,
                'sample_starts': [t['sample_start'] for t in manifest['evaluation']['trials']],
                'protocol': f'{subject}E同一GDF中与EEG同步的EOG通道23，250Hz/μV；电极方向和眨眼标签未独立验证，不保证触发确认。',
            }
        (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'{subject} {channels}ch ready')


if __name__ == '__main__':
    main()
