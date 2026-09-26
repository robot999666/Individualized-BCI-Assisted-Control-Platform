"""Reproducible T/E demo extraction. Never use E data to fit the EA profile."""
import argparse
import hashlib
import json
from pathlib import Path
import mne
import numpy as np


def extract(path, count):
    raw = mne.io.read_raw_gdf(path, preload=True, verbose='ERROR')
    if raw.info['sfreq'] != 250 or len(raw.ch_names) != 25:
        raise ValueError('Expected 250Hz, 22 EEG + 3 EOG')
    events, codes = mne.events_from_annotations(raw, verbose='ERROR')
    reverse = {v: int(k) for k, v in codes.items() if k.isdigit()}
    starts = [int(e[0]) for e in events if reverse.get(e[2]) == 768]
    rejects = [int(e[0]) for e in events if reverse.get(e[2]) == 1023]
    trials, metadata = [], []
    data = raw.get_data()[:22] * 1e6
    for e in events:
        code = reverse.get(e[2])
        if code not in [769, 770, 771, 772, 783]:
            continue
        cue = int(e[0])
        trial_id = max((i for i, s in enumerate(starts) if s <= cue), default=-1)
        if trial_id < 0:
            continue
        start = starts[trial_id]
        stop = starts[trial_id+1] if trial_id+1 < len(starts) else raw.n_times
        if any(start <= r < stop for r in rejects):
            continue
        a, b = cue + 125, cue + 626
        x = data[[7, 9, 11], a:b]
        if x.shape != (3, 501) or not np.isfinite(x).all():
            continue
        trials.append(x)
        metadata.append({'trial_index_zero_based': trial_id, 'cue_sample': cue,
                         'sample_start': a, 'sample_stop_exclusive': b, 'event': code})
        if len(trials) == count:
            break
    if len(trials) != count:
        raise ValueError('Insufficient clean trials')
    return np.asarray(trials), {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                               'trials': metadata, 'channels': ['C3','Cz','C4'], 'sampling_rate': 250,
                               'unit': 'uV', 'epoch': 'cue+0.5s through cue+2.5s inclusive'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path('sample_data/BCICIV_2a_gdf'))
    parser.add_argument('--output', type=Path, default=Path('sample_data/demo_processed'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'subject': 'A01', 'protocol': 'T session calibration / E session replay; not independent model evaluation',
                'training_overlap': 'Unknown at session level; model documentation says all 9 subjects used',
                'accuracy': None, 'eog': 'Excluded from EEG; real EOG model drives confirmation', 'license': 'Research dataset; not bundled in Git; see original provider terms'}
    for split, session, count in [('calibration','T',40), ('evaluation','E',24)]:
        x, info = extract(args.source / f'A01{session}.gdf', count)
        np.savez_compressed(args.output / f'{split}.npz', X=x)
        info['npz_sha256'] = hashlib.sha256((args.output / f'{split}.npz').read_bytes()).hexdigest()
        manifest[split] = info
    # Separate real EOG traces for diagnostic model execution only; never EEG labels.
    raw = mne.io.read_raw_gdf(args.source / 'A01E.gdf', preload=True, verbose='ERROR')
    ocular = raw.get_data()[23] * 1e6
    windows = np.asarray([ocular[t['sample_start']:t['sample_start']+501]
                          for t in manifest['evaluation']['trials']])
    if not np.isfinite(windows).all():
        raise ValueError('Nonfinite EOG data')
    np.savez_compressed(args.output / 'eog_evaluation.npz', X=windows)
    manifest['eog_diagnostic'] = {'source': 'A01E.gdf', 'channel_index': 23,
        'channel_name': raw.ch_names[23], 'sampling_rate': 250, 'unit': 'uV',
        'labels': None, 'sha256': hashlib.sha256((args.output/'eog_evaluation.npz').read_bytes()).hexdigest(),
        'purpose': 'Offline model execution; electrode orientation and blink labels not independently verified'}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({k: len(manifest[k]['trials']) for k in ['calibration','evaluation']}))

if __name__ == '__main__':
    main()
