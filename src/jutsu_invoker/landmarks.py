"""Diagnostic 21-joint hands: RTMDet + RTMPose, images and networks on CUDA.

Independent of seal decisions. No extrapolation, CPU inference, or fabricated joints.
"""
from pathlib import Path
import hashlib,json
import numpy as np
from .gpu import RESIZE_KERNEL, NMS_KERNEL

AFFINE = r'''
extern "C" __global__ void crop(const unsigned char* im,float* out,int h,int w,
 float cx,float cy,float size) {
 int i=blockDim.x*blockIdx.x+threadIdx.x;if(i>=3*256*256)return;
 int c=i/(256*256),x=i%256,y=(i/256)%256;
 float fx=cx-size*.5f+x*size/256.f,fy=cy-size*.5f+y*size/256.f;
 int x0=(int)floorf(fx),y0=(int)floorf(fy);float ax=fx-x0,ay=fy-y0;
 float v=0;for(int dy=0;dy<2;dy++)for(int dx=0;dx<2;dx++){
 int xx=x0+dx,yy=y0+dy;
 if(xx>=0&&xx<w&&yy>=0&&yy<h)v+=im[(yy*w+xx)*3+2-c]*(dx?ax:1-ax)*(dy?ay:1-ay);
 }
 float mean[3]={123.675f,116.28f,103.53f},std[3]={58.395f,57.12f,57.375f};
 out[i]=(v-mean[c])/std[c];
}
'''

class CudaGraph:
 def __init__(self,path,shapes,stream,cp,profile=False):
  import onnxruntime as ort
  options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
  options.add_session_config_entry('session.disable_cpu_ep_fallback','1')
  options.enable_profiling=profile;options.profile_file_prefix=str(path.parent/'profile')
  self.session=ort.InferenceSession(str(path),sess_options=options,providers=[('CUDAExecutionProvider',{'user_compute_stream':str(stream.ptr),'cudnn_conv_algo_search':'HEURISTIC','cudnn_conv_use_max_workspace':'0','use_tf32':'0'})])
  self.session.disable_fallback();self.binding=self.session.io_binding()
  self.input=cp.empty(shapes[0],dtype=cp.float32)
  self.binding.bind_input('input','cuda',0,np.float32,self.input.shape,self.input.data.ptr)
  self.outputs=[]
  for meta,shape in zip(self.session.get_outputs(),shapes[1:]):
   out=cp.empty(shape,dtype=cp.float32);self.outputs.append(out)
   self.binding.bind_output(meta.name,'cuda',0,np.float32,shape,out.data.ptr)
 def run(self):self.session.run_with_iobinding(self.binding)

class HandLandmarks:
 def __init__(self,root:Path,profile=False):
  import onnxruntime as ort
  ort.preload_dlls(directory='')
  import cupy as cp
  self.cp=cp;self.stream=cp.cuda.Stream(non_blocking=True)
  manifest=json.loads((root/'modelos/manifiesto-articulaciones.json').read_text())
  for a in manifest['artifacts']:
   if hashlib.sha256((root/a['file']).read_bytes()).hexdigest()!=a['sha256']:raise RuntimeError('Hand model hash mismatch')
  d=root/'modelos/pesos/rtmpose'
  with self.stream:
   self.det=CudaGraph(d/'det-cuda.onnx',[(1,3,320,320),(1,2100,4),(1,2100,1)],self.stream,cp,profile)
   self.pose=CudaGraph(d/'pose-cuda.onnx',[(1,3,256,256),(1,21,512),(1,21,512)],self.stream,cp,profile)
   self.resize=cp.RawKernel(RESIZE_KERNEL.replace('416','320'),'letterbox')
   self.crop=cp.RawKernel(AFFINE,'crop');self.nms=cp.RawKernel(NMS_KERNEL,'nms')
  self.stream.synchronize()
 def warmup(self,image):
  # Compile the crop and execute pose even if the dummy frame contains no hands.
  self.infer(image)
  h,w=image.shape[:2]
  with self.stream:
   self.crop(((3*256*256+255)//256,),(256,),(image,self.pose.input,h,w,np.float32(w/2),np.float32(h/2),np.float32(256)))
   for _ in range(3):self.pose.run()
  self.stream.synchronize()
 def infer(self,image):
  cp=self.cp
  if not isinstance(image,cp.ndarray) or image.dtype!=cp.uint8 or not image.flags.c_contiguous or image.device.id!=0:raise ValueError('Expected contiguous CUDA BGR uint8')
  h,w=image.shape[:2];ratio=min(320/h,320/w);rh,rw=int(h*ratio),int(w*ratio)
  hands=[]
  with self.stream:
   self.resize(((3*320*320+255)//256,),(256,),(image,self.det.input,h,w,rh,rw))
   self.det.input-=cp.asarray([103.53,116.28,123.675],dtype=cp.float32)[None,:,None,None]
   self.det.input/=cp.asarray([57.375,57.12,58.395],dtype=cp.float32)[None,:,None,None]
   self.det.run();boxes=cp.ascontiguousarray(self.det.outputs[0][0]/ratio);scores=self.det.outputs[1][0,:,0]
   order=cp.ascontiguousarray(cp.argsort(scores)[::-1].astype(cp.int32));count=int(cp.count_nonzero(scores>=.3).item())
   keep=cp.empty(64,dtype=cp.int32);n=cp.zeros(1,dtype=cp.int32)
   self.nms((1,),(1,),(boxes,order,count,np.float32(.6),keep,n))
   indices=keep[:min(2,int(n.item()))]
   meta=cp.concatenate([boxes[indices],scores[indices,None]],axis=1).get(stream=self.stream)
   for row in meta:
    x1,y1,x2,y2=map(float,row[:4]);size=max(x2-x1,y2-y1)*1.25
    if size<12:continue
    cx,cy=(x1+x2)/2,(y1+y2)/2
    self.crop(((3*256*256+255)//256,),(256,),(image,self.pose.input,h,w,np.float32(cx),np.float32(cy),np.float32(size)))
    self.pose.run();xx,yy=self.pose.outputs
    xs,ys=cp.argmax(xx[0],axis=1),cp.argmax(yy[0],axis=1)
    confidence=cp.minimum(cp.max(xx[0],axis=1),cp.max(yy[0],axis=1))
    points=cp.stack([xs/512*size+cx-size/2,ys/512*size+cy-size/2,confidence],axis=1).get(stream=self.stream)
    hands.append({'box':row[:4].tolist(),'score':float(row[4]),'joints':points.tolist()})
  self.stream.synchronize();return hands
 def finish_profile(self):
  result=[]
  for graph in [self.det,self.pose]:
   p=Path(graph.session.end_profiling());entries=json.loads(p.read_text())
   providers=sorted({e['args']['provider'] for e in entries if e.get('cat')=='Node' and e.get('args',{}).get('provider')})
   if providers!=['CUDAExecutionProvider']:raise RuntimeError(f'Unexpected hand providers {providers}')
   result.append({'file':str(p),'providers':providers})
  return result
