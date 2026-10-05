"""Compare TensorRT to the CUDA reference before enabling a new engine."""
import json
from pathlib import Path
import cv2
import numpy as np
from jutsu_invoker.gpu import NarutoCuda, choose_evidence
from jutsu_invoker.tensorrt_backend import engine_paths

root = Path(__file__).resolve().parents[1]
reference = NarutoCuda(root, backend='onnxruntime')
actual = NarutoCuda(root, backend='tensorrt')
checks = []
for label, host in [
    ('synthetic_720p', np.random.default_rng(42).integers(0,256,(720,1280,3),dtype=np.uint8)),
    ('reference_sheet_not_accuracy_dataset', cv2.imread(str(root/'referencias/sellos-naruto.png'))),
    ('neutral_720p', np.full((720,1280,3),114,np.uint8)),
]:
    if host is None:
        raise RuntimeError('Missing reference image')
    image = actual.cp.asarray(host)
    actual.cp.cuda.get_current_stream().synchronize()
    ref_detections = reference.infer(image)
    detections = actual.infer(image)
    expected = reference.cp.asnumpy(reference.output)
    output = actual.cp.asnumpy(actual.output)
    np.testing.assert_allclose(actual.cp.asnumpy(actual.input), reference.cp.asnumpy(reference.input), atol=0,rtol=0)
    np.testing.assert_allclose(output, expected, atol=2e-4, rtol=2e-4)
    assert [d['class_id'] for d in detections] == [d['class_id'] for d in ref_detections]
    if detections:
        np.testing.assert_allclose([d['score'] for d in detections], [d['score'] for d in ref_detections], atol=2e-4, rtol=2e-4)
        np.testing.assert_allclose([d['box'] for d in detections], [d['box'] for d in ref_detections], atol=.05, rtol=2e-4)
    assert choose_evidence(detections)['sign'] == choose_evidence(ref_detections)['sign']
    checks.append({'input':label,'raw_max_abs_error':float(np.abs(output-expected).max()),'detections':len(detections),'evidence_sign_parity':True,'nms_parity':True})
report={'status':'passed','checks':checks,'atol':2e-4,'rtol':2e-4,'personal_sign_accuracy_measured':False}
(root/'runtime/paridad-tensorrt.json').write_text(json.dumps(report,indent=2)+'\n')
_,_,path=engine_paths(root)
metadata=path.with_suffix('.json')
meta=json.loads(metadata.read_text());meta.update(parity_verified=True,parity_report='runtime/paridad-tensorrt.json')
metadata.write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps(report,indent=2))
