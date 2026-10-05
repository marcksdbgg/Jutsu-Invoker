"""Offline CUDA preprocessing parity against OpenCV affine/resize; profile both networks."""
from pathlib import Path
import json,time
import cv2,numpy as np,cupy as cp
from jutsu_invoker.landmarks import HandLandmarks
root=Path(__file__).resolve().parents[1];m=HandLandmarks(root,profile=True)
p=root/'runtime/revision-piloto/serpiente-1354.png'
im=cv2.imread(str(p))
if im is None:raise RuntimeError('Local calibration image missing')
a=cp.asarray(im);cp.cuda.get_current_stream().synchronize();hands=m.infer(a)
h,w=im.shape[:2];ratio=min(320/h,320/w)
x=cv2.resize(im,(int(w*ratio),int(h*ratio)));ref=np.full((320,320,3),114,dtype=np.uint8);ref[:x.shape[0],:x.shape[1]]=x
ref=((ref.astype(np.float32)-[103.53,116.28,123.675])/[57.375,57.12,58.395]).transpose(2,0,1)[None]
det_error=float(np.max(np.abs(ref-m.det.input.get())))
assert det_error<.019,det_error
if not hands:raise RuntimeError('No hands for pose validation')
x1,y1,x2,y2=hands[-1]['box'];size=max(x2-x1,y2-y1)*1.25;cx,cy=(x1+x2)/2,(y1+y2)/2
matrix=np.asarray([[256/size,0,128-cx*256/size],[0,256/size,128-cy*256/size]],np.float32)
x=cv2.warpAffine(im,matrix,(256,256),flags=cv2.INTER_LINEAR)[:,:,::-1]
ref=((x.astype(np.float32)-[123.675,116.28,103.53])/[58.395,57.12,57.375]).transpose(2,0,1)[None]
err=np.abs(ref-m.pose.input.get());mean=float(err.mean());maximum=float(err.max())
assert mean<.015 and maximum<.16,(mean,maximum)
times=[]
for _ in range(20):
 t=time.perf_counter();m.infer(a);times.append((time.perf_counter()-t)*1000)
report={'test':'offline_local_image_preprocessing_parity_and_gpu_providers','det_max_normalized_error':det_error,'pose_mean_normalized_error':mean,'pose_max_normalized_error':maximum,'pose_difference':'CUDA exact bilinear versus OpenCV quantized interpolation tables','providers':m.finish_profile(),'median_ms':float(np.median(times)),'p95_ms':float(np.percentile(times,95)),'hands':len(hands),'joint_accuracy_measured':False}
(root/'runtime/articulaciones-validacion.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
