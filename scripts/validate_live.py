"""Exercise a running local service with the real phone; never fabricates seal accuracy."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import time
import urllib.request

parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:32147');args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
html=urllib.request.urlopen(args.url).read().decode()
token=re.search(r'name="session-token" content="([^"]+)"',html).group(1)
def get():return json.load(urllib.request.urlopen(args.url+'/api/state',timeout=5))
def post(action,payload=None):
    req=urllib.request.Request(args.url+'/api/'+action,data=json.dumps(payload or {}).encode(),headers={'X-Jutsu-Token':token,'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(req,timeout=20))
def wait_running():
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        state=get()
        if state['status']=='error':raise RuntimeError(state['error'])
        if state['status']=='running' and state['frames']>=30:return state
        time.sleep(.1)
    raise RuntimeError('Camera start timeout')

initial=wait_running();samples=[];cursor=0;generation=-1;decoded_packets=0;configs=0;keyframes=0;preview=bytearray()
post('record/start',{'label':'unknown'})
start=time.monotonic()
while time.monotonic()-start<12:
    state=get()
    if state['status']!='running':raise RuntimeError(state.get('error') or 'Camera stopped')
    with urllib.request.urlopen(args.url+f'/video?cursor={cursor}&generation={generation}',timeout=5) as response:
        batch=response.read()
        if batch:
            cursor=int(response.headers['X-Video-Cursor']);generation=int(response.headers['X-Video-Generation'])
    offset=0
    while offset<len(batch):
        flags,size=struct.unpack('>QI',batch[offset:offset+12]);payload=batch[offset+12:offset+12+size]
        if len(payload)!=size:raise RuntimeError('Truncated preview packet')
        configs+=bool(flags&(1<<62));keyframes+=bool(flags&(1<<61));decoded_packets+=not bool(flags&(1<<62))
        preview.extend(payload);offset+=12+size
    samples.append({k:state.get(k) for k in ['fps','processing_ms','queue_age_ms','received_to_event_ms','cpu_logical_threads','frames']})
    time.sleep(.05)
path=post('record/stop')['last_recording']
meta=json.loads(Path(path).with_suffix('.json').read_text())
assert meta['frames']>100 and len(meta['packets'])==meta['frames']
clip_probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,has_b_frames','-of','json',path]))
(root/'runtime/preview-validation.h264').write_bytes(preview)
preview_probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,has_b_frames','-of','json',str(root/'runtime/preview-validation.h264')]))
assert clip_probe['streams'][0]['has_b_frames']==0 and preview_probe['streams'][0]['width']==1280
stop=post('stop');assert stop['status']=='stopped' and not stop['pending']
post('start');after=wait_running()
import numpy as np
metrics={key:{f'p{p}':float(np.percentile([s[key] for s in samples if s[key] is not None],p)) for p in [50,95]} for key in ['fps','processing_ms','queue_age_ms','received_to_event_ms','cpu_logical_threads']}
report={'status':'passed','camera':initial['facing'],'backend':initial['backend'],'capture_sample_seconds':12,'validation_wall_seconds':time.monotonic()-start,
        'processed_frames':samples[-1]['frames']-initial['frames'],'metrics':metrics,
        'preview':{'finite_batches_verified':True,'packets':decoded_packets,'config_packets':configs,'keyframes':keyframes,'probe':preview_probe,'browser_render_verified':False},
        'recording':{'frames':meta['frames'],'pts_monotonic':all(a['pts_us']<b['pts_us'] for a,b in zip(meta['packets'],meta['packets'][1:])),'probe':clip_probe,'label':'unknown','not_personal_accuracy_dataset':True},
        'stop_restart_verified':True,'running_after_restart':after['status'],'game_input_sent':False,
        'personal_sign_accuracy_measured':False,'absolute_camera_latency_measured':False,'dota_concurrent_benchmark':False}
(root/'runtime/live-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
