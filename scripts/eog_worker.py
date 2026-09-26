"""Version-isolated real EOG worker. Newline JSON input/output; never logs signal content."""
import hashlib,json,sys,time
from pathlib import Path
import numpy as np
import sklearn
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from algorithms.system_integration.core import EOGBlinkDetector
CHECKSUM='b1280ed3ce7c94361fb666843e7bf515ae2d471a74d1bcb17aeccb9f91e5878f'
if sklearn.__version__!='1.9.1' or hashlib.sha256((root/'algorithms/system_integration/models/blink_detector.pkl').read_bytes()).hexdigest()!=CHECKSUM:
    raise RuntimeError('EOG version/checksum mismatch')
model=EOGBlinkDetector()

def execute(request):
    windows=request['windows'] if isinstance(request,dict) else request
    prefiltered=request.get('prefiltered',False) if isinstance(request,dict) else False
    data=np.asarray(windows,dtype=np.float64)
    if data.ndim!=2 or data.shape[1]!=250 or not 1<=len(data)<=100 or not np.isfinite(data).all():
        raise ValueError('Invalid EOG shape or values')
    results=[]
    for x in data:
        if np.std(x)<1e-8:raise ValueError('Constant EOG signal')
        started=time.perf_counter();blink,probability=model.detect(x,prefiltered=prefiltered);elapsed=(time.perf_counter()-started)*1000
        if not np.isfinite(probability):raise ValueError('Nonfinite output')
        results.append({'blink':bool(blink),'probability':float(probability),'inference_ms':elapsed,
            'mode':'REAL_MODEL','model_sha256':CHECKSUM,'sklearn_version':sklearn.__version__,
            'independent_accuracy':None,'mean_uv':float(np.mean(x)),
            'prefiltered':prefiltered,'peak_index':int(np.argmax(x if prefiltered else model._bandpass(x)))})
    return results

if '--stream' in sys.argv:
    print(json.dumps({'ready':True,'model_sha256':CHECKSUM}),flush=True)
    for line in sys.stdin:
        try:output={'results':execute(json.loads(line))}
        except Exception:output={'error':'Invalid EOG input or model failure'}
        print(json.dumps(output),flush=True)
else:
    json.dump(execute(json.load(sys.stdin)),sys.stdout)
