"""Download only pinned official OpenMMLab SDK files; verify archives before extraction."""
from pathlib import Path
import hashlib,json,urllib.request,zipfile
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'modelos/manifiesto-articulaciones.json').read_text())
d=root/'modelos/pesos/rtmpose';d.mkdir(parents=True,exist_ok=True)
for a in manifest['archives']:
 data=urllib.request.urlopen(a['url'],timeout=120).read()
 if hashlib.sha256(data).hexdigest()!=a['sha256']:raise RuntimeError('Archive hash mismatch')
 import io
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  for name in ['end2end.onnx','pipeline.json','deploy.json','detail.json']:
   matches=[f for f in z.namelist() if Path(f).name==name]
   if len(matches)!=1:raise RuntimeError('Unexpected archive structure')
   (d/f"{a['kind']}-{name}").write_bytes(z.read(matches[0]))
print('Pinned official hand exports downloaded; run scripts/prepare_hand_models.py')
