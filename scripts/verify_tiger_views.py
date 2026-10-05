"""Retrospective held-pose and failed-tiger diagnostics, no camera accuracy claim."""
from pathlib import Path
import json,cv2,cupy as cp,time
from collections import Counter
from jutsu_invoker.gpu import NarutoCuda,choose_evidence
from jutsu_invoker.tiger_refinement import refine_tiger
root=Path(__file__).resolve().parents[1];model=NarutoCuda(root,backend='tensorrt');records=[]
folder=root/'datos/evaluaciones/20261004T132245725408Z'
report=json.loads((folder/'report.json').read_text());clip=root/report['video_clip'];meta=json.loads(clip.with_suffix('.json').read_text())
rows=[json.loads(x) for x in (folder/'observations.jsonl').read_text().splitlines()]
measured=[r for r in rows if r['phase']=='measure'][::3];indices={p['pts_us']:i for i,p in enumerate(meta['packets'])}
selected={indices[r['frame_meta']['pts_us']]:r for r in measured}
cap=cv2.VideoCapture(str(clip))
for i in range(max(selected)+1):
 ok,host=cap.read()
 if not ok:break
 if i not in selected:continue
 a=cp.asarray(host);cp.cuda.get_current_stream().synchronize();ds=model.infer(a);before=choose_evidence(ds);after,refine=refine_tiger(model,a,ds);r=selected[i]
 records.append({'expected':r['expected'],'before':before,'after':after,'refinement':refine,'frame':i})
 time.sleep(.01)
cap.release()
examples=[]
for idx in [1000,4145]:
 host=cv2.imread(str(root/f'runtime/revision-piloto/tiger-{idx}.png'));a=cp.asarray(host);cp.cuda.get_current_stream().synchronize();ds=model.infer(a);after,refine=refine_tiger(model,a,ds)
 examples.append({'frame':idx,'raw':ds,'after':after,'refinement':refine})
def decision(e):return e['sign'] if e['score']>=.8 and e['margin']>=.15 else 'unknown'
result={'kind':'retrospective_sampled_frames_not_new_accuracy','source':str(folder.relative_to(root)),'samples':len(records),'baseline_correct':sum(decision(r['before'])==r['expected'] for r in records),'refined_correct':sum(decision(r['after'])==r['expected'] for r in records),'changed_frames':sum(r['after']!=r['before'] for r in records),'false_tiger_outside_tiger':sum(decision(r['after'])=='tiger' and r['expected']!='tiger' for r in records),'per_expected':dict(Counter(r['expected'] for r in records)),'examples':examples,'records':records,'real_ram_negative_trials':0}
(root/'runtime/tiger-refinement-validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['records','examples']},indent=2));print([(e['frame'],e['after'],e['refinement']['accepted'] if e['refinement'] else None) for e in examples])
