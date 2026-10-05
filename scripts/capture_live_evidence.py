"""Local bounded diagnostic sampling. Frames are deduplicated; labels stay unassigned."""
import argparse,json,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=90);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
args.output.parent.mkdir(parents=True,exist_ok=True);end=time.monotonic()+args.seconds;last=None;count=0
with args.output.open('w') as f:
 while time.monotonic()<end:
  s=json.loads(urllib.request.urlopen('http://127.0.0.1:32147/api/state',timeout=3).read());key=(s.get('started_ms'),s.get('frames'))
  if key!=last:
   last=key;count+=1
   row={k:s.get(k) for k in ['server_monotonic_ms','status','frames','sign','score','margin','detections','pending','rejection','capture_orientation_degrees','queue_age_ms','processing_ms','last_recipe']}
   row['pose']=s.get('poses',[])[-1:] ;f.write(json.dumps(row)+'\n');f.flush()
  time.sleep(.025)
print(json.dumps({'file':str(args.output),'samples':count,'target_labels_assigned':False}))
