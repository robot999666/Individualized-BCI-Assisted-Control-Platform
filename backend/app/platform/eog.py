"""Persistent, version-isolated real EOG process and model-event provider."""
import asyncio,json,queue,subprocess,threading,time
from pathlib import Path
import numpy as np
from app.core.config import get_settings

CHECKSUM='b1280ed3ce7c94361fb666843e7bf515ae2d471a74d1bcb17aeccb9f91e5878f'
ROOT=Path(__file__).resolve().parents[3]
lock=asyncio.Lock()
_thread_lock=threading.Lock()
_process=None
_output=None


def health():
    ready = _process is not None and _process.poll() is None
    return {'mode':'REAL_MODEL','status':'ok' if ready else 'unavailable',
            'runtime_available':Path(get_settings().eog_python).is_file(),
            'model_sha256':CHECKSUM,'sklearn_version':'1.9.1'}


def shutdown():
    global _process
    if _process is not None:
        _process.terminate()
        try:_process.wait(timeout=3)
        except subprocess.TimeoutExpired:_process.kill()
        _process=None


def _start():
    global _process,_output
    if _process is not None and _process.poll() is None:return
    executable=Path(get_settings().eog_python)
    if not executable.is_file():raise ValueError('EOG runtime unavailable')
    _process=subprocess.Popen([str(executable),str(ROOT/'scripts/eog_worker.py'),'--stream'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1,cwd=ROOT)
    _output=queue.Queue()
    process,out=_process,_output
    def reader():
        for line in process.stdout:out.put(line)
        out.put('{"error":"EOG worker stopped"}')
    threading.Thread(target=reader,daemon=True).start()
    try:
        ready=json.loads(out.get(timeout=30))
        if not ready.get('ready'):raise ValueError('EOG worker failed to load verified model')
    except Exception:
        shutdown();raise ValueError('EOG runtime initialization failed') from None


def warmup():
    with _thread_lock:_start()


def analyze_batch(windows,prefiltered=False):
    data=np.asarray(windows,dtype=np.float64)
    if data.ndim!=2 or data.shape[1]!=250 or not 1<=len(data)<=100 or not np.isfinite(data).all() or np.any(np.std(data,axis=1)<1e-8):
        raise ValueError('EOG requires finite nonconstant 250-sample windows in microvolts')
    with _thread_lock:
        _start()
        try:
            _process.stdin.write(json.dumps({'windows':data.tolist(),'prefiltered':prefiltered})+'\n');_process.stdin.flush()
            result=json.loads(_output.get(timeout=10))
            if 'error' in result:raise ValueError(result['error'])
            return result['results']
        except Exception:
            shutdown();raise ValueError('EOG inference failed; control must STOP') from None


class RealEOGProvider:
    mode='REAL_MODEL'
    def __init__(self):
        self.last_peak=-999.0
        self.blinks=[]
        self.closed_since=None
        self.candidate=None

    def reset_candidate(self,candidate):
        if candidate!=self.candidate:
            self.candidate=candidate;self.blinks=[]

    def consume(self,result,start_sample,signal_time):
        # Distinct peaks prevent a single blink in overlapping windows counting twice.
        peak_time=(start_sample+result['peak_index'])/250
        if not result.get('prefiltered',False) and result['mean_uv']>25:
            if self.closed_since is None:self.closed_since=signal_time
            elif signal_time-self.closed_since>=1.5:
                return 'EMERGENCY'
        else:self.closed_since=None
        self.blinks=[t for t in self.blinks if signal_time-t<=2]
        if result['blink'] and peak_time-self.last_peak>=.25:
            self.last_peak=peak_time
            if self.candidate is not None:self.blinks.append(peak_time)
        if len(self.blinks)>=2:
            self.blinks=[]
            return 'CONFIRM'
        return 'NO_SIGNAL'
