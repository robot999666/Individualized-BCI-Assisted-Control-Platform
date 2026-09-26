"""Build a disclosed paired replay from genuine, already filtered 2b EOG windows.
This is a software scenario, not synchronous 2a/2b acquisition or independent validation.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np

parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,default=Path('algorithms/eog_blink/eog_dataset.npz'))
parser.add_argument('--output',type=Path,default=Path('sample_data/demo_processed'))
args=parser.parse_args()
with np.load(args.source,allow_pickle=False) as payload:
    x=payload['X'];y=payload['y'];subjects=payload['subj_ids'];sfreq=int(payload['sfreq'])
if sfreq!=250 or x.ndim!=2 or x.shape[1]!=250 or not np.isfinite(x).all():
    raise ValueError('Invalid source dataset')
manifest_path=args.output/'manifest.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
n=len(manifest['evaluation']['trials'])*2
neg=np.flatnonzero(y==0);pos=np.flatnonzero(y==1)
indices=neg[:n].tolist()
# Explicit scenario: true blink-window examples at replay seconds6-8, after EEG stabilization.
indices[6:8]=pos[:2].tolist()
np.savez_compressed(args.output/'eog_demo.npz',X=x[indices])
manifest['eog_pairing']={'dataset':'BCI IV 2b EOG','file':args.source.name,
    'source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),
    'sha256':hashlib.sha256((args.output/'eog_demo.npz').read_bytes()).hexdigest(),
    'source_rows':indices,'subject_ids':subjects[indices].tolist(),'pseudo_labels':y[indices].astype(int).tolist(),
    'sampling_rate':250,'unit':'uV','prefiltered':True,'filter':'1-15Hz applied by source dataset builder',
    'label_origin':'Automatic peak/threshold pseudo-labels; not independent human annotations',
    'training_overlap':'save_model.py fits all supplied EOG windows; development replay only',
    'protocol':'2a EEG + 2b EOG真实片段离线配对场景；不是同一受试者同步采集。EOG窗口按演示时间轴排列，非原始连续记录。',
    'accuracy':None}
manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
print('Prepared',n,'real EOG windows; explicit paired replay; no independent accuracy claim')
