"""Re-score stored visual evidence with the current grammar, never target-assisted."""
from pathlib import Path
from collections import Counter
import json,tomllib
from jutsu_invoker.live import thresholds_from_config
from jutsu_invoker.recognition import Trainer,Observation
root=Path(__file__).resolve().parents[1]
folder=root/'datos/evaluaciones/20261004T132829954661Z'
report=json.loads((folder/'report.json').read_text())
rows=[json.loads(x) for x in (folder/'observations.jsonl').read_text().splitlines()]
th=thresholds_from_config(tomllib.loads((root/'config/desarrollo-gpu.toml').read_text()))
results=[]
for i,trial in enumerate(report['trials'],1):
 trainer=Trainer(root/'diseno/mapa-recetas.json',th);events=[]
 for row in rows:
  if row['trial']!=i or row['phase']!='measure':continue
  t=row['timestamp_ms'];now=t+row['frame_meta']['queue_age_ms']
  events.extend(trainer.update(Observation(t,**row['evidence'],fresh_visual=not row['stale']),now))
 spells=[e['spell'] for e in events if e['type']=='recipe']
 target=next(r['expected']['name'] for r in rows if r['trial']==i)
 results.append({'trial':i,'expected':target,'emitted':spells,'correct':spells==[target],'accepted':[e['token'] for e in events if e['type']=='accepted'],'cancellations':dict(Counter(e['reason'] for e in events if e['type']=='cancelled'))})
output={'source_report':str(folder.relative_to(root)/'report.json'),'kind':'offline_replay_same_evidence_not_new_camera_accuracy','thresholds':th.__dict__,'original_correct':report['correct_trials'],'replayed_correct':sum(r['correct'] for r in results),'total':len(results),'trials':results}
(root/'runtime/recetas-replay-mejora.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output,indent=2))
