"""Derive CUDA-friendly graphs from official OpenMMLab exports (no weight changes)."""
import hashlib,json
from pathlib import Path
import onnx
root=Path(__file__).resolve().parents[1]; directory=root/'modelos/pesos/rtmpose'
onnx.utils.extract_model(str(directory/'det-end2end.onnx'),str(directory/'det-cuda.onnx'),['input'],['1442','1415'])
m=onnx.load(directory/'pose-end2end.onnx')
for v in [*m.graph.input,*m.graph.output]:
 v.type.tensor_type.shape.dim[0].dim_value=1
m=onnx.shape_inference.infer_shapes(m);onnx.checker.check_model(m);onnx.save(m,directory/'pose-cuda.onnx')
p=root/'modelos/manifiesto-articulaciones.json';manifest=json.loads(p.read_text())
manifest['derivation']='det: outputs decoded boxes1442/scores1415 before CPU NMS; pose: fixed batch1; weights unchanged'
manifest['preprocessing']={'det':'BGR top-left320 pad114, mean[103.53,116.28,123.675], std[57.375,57.12,58.395]','pose':'RGB affine square padding1.25 256; mean[123.675,116.28,103.53], std[58.395,57.12,57.375]; SimCC /2'}
manifest['metadata_note']='pose pipeline legacy transform says192x256; actual graph and SimCC input_size agree256x256'
manifest['artifacts']=[a for a in manifest['artifacts'] if not a['file'].endswith('-cuda.onnx')]
for f in ['det-cuda.onnx','pose-cuda.onnx']:
 q=directory/f;manifest['artifacts'].append({'file':str(q.relative_to(root)),'sha256':hashlib.sha256(q.read_bytes()).hexdigest()})
p.write_text(json.dumps(manifest,indent=2)+'\n')
