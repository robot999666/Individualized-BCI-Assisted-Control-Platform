"""Package committed source and the verified static build; keep secrets/data separate."""
import io
import json
from pathlib import Path
import subprocess
import tarfile


root = Path(__file__).resolve().parents[1]
destination = root / 'temp' / 'deploy'
destination.mkdir(parents=True, exist_ok=True)
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
if subprocess.check_output(['git', 'diff', 'HEAD', '--name-only'], cwd=root, text=True).strip():
    raise SystemExit('Commit tracked changes before packaging')
if not (root / 'frontend/out/lab/index.html').is_file():
    raise SystemExit('Build the static frontend before packaging')
source = subprocess.check_output(['git', 'archive', '--format=tar', 'HEAD'], cwd=root)
with tarfile.open(fileobj=io.BytesIO(source)) as archive, tarfile.open(destination/'release.tar.gz', 'w:gz') as release:
    for member in archive.getmembers():
        if not member.isfile():
            continue
        path = Path(member.name)
        if any(part in {'temp','runtime','.venv','node_modules','BCICIV_2a_gdf'} for part in path.parts):
            raise SystemExit('Private directory in release: ' + member.name)
        if path.name in {'.env','eog_dataset.npz'} or path.suffix in {'.pem','.key','.zip'}:
            raise SystemExit('Private file in release: ' + member.name)
        release.addfile(member, archive.extractfile(member))
    for path in (root/'frontend/out').rglob('*'):
        if path.is_file():
            release.add(path, arcname=path.relative_to(root).as_posix())
    data = (commit+'\n').encode()
    entry = tarfile.TarInfo('RELEASE_COMMIT')
    entry.size = len(data)
    release.addfile(entry, io.BytesIO(data))
with tarfile.open(destination/'demo.tar.gz', 'w:gz') as demo:
    for folder in ('','a01-22ch','a02-3ch','a02-22ch'):
        for name in ('calibration.npz','evaluation.npz','eog_demo.npz','manifest.json'):
            relative = Path(folder)/name
            demo.add(root/'sample_data/demo_processed'/relative, arcname=relative.as_posix())
    demo.add(root/'sample_data/demo_processed/eog_evaluation.npz', arcname='eog_evaluation.npz')
print(json.dumps({'commit':commit,'release_bytes':(destination/'release.tar.gz').stat().st_size,
                  'demo_bytes':(destination/'demo.tar.gz').stat().st_size}))
