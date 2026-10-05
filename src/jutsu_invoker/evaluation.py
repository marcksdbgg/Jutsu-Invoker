"""Prompted trials with independent expected labels and retained observations."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import threading
import time

SIGNS = ('monkey', 'tiger', 'horse', 'snake', 'unknown')


class Evaluation:
    def __init__(self, root: Path, thresholds, fps=30):
        self.root, self.thresholds, self.fps = root, thresholds, fps
        self.lock = threading.RLock()
        self.status = 'idle'
        self.trials = []
        self.stream = None
        self.report_path = None
        self.index = None
        self.report = None
        self.confirmed = False
        self.restored = False
        for path in sorted((root/'datos/evaluaciones').glob('*/report.json'), reverse=True):
            try:
                report = json.loads(path.read_text())
                if report.get('status') not in {'finished','aborted'} or not all(k in report for k in ('mode','trials','provisional')):
                    continue
                self.report, self.report_path = report, path
                self.status, self.mode = report['status'], report['mode']
                self.confirmed = report.get('user_confirmed_execution', False)
                self.restored = True
                break
            except (OSError, ValueError):
                continue

    def start(self, mode='signs', rounds=2, now_ms=None):
        if mode not in {'signs', 'recipes'} or type(rounds) is not int or not 1 <= rounds <= 5:
            raise ValueError('Protocolo inválido')
        with self.lock:
            if self.status == 'running':
                raise ValueError('Ya hay una evaluación en curso')
            self.restored = False
            self.mode = mode
            self.start_ms = now_ms if now_ms is not None else time.monotonic()*1000
            self.status, self.index, self.report, self.confirmed = 'running', None, None, False
            self._last_phase = None
            self.abort_reason = None
            self.video_clip = None
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            self.folder = self.root/'datos/evaluaciones'/stamp
            self.folder.mkdir(parents=True)
            self.report_path = self.folder/'report.json'
            self.stream = (self.folder/'observations.jsonl').open('w')
            rng = random.Random(570)
            if mode == 'signs':
                targets = []
                for _ in range(rounds):
                    row = list(SIGNS);rng.shuffle(row);targets.extend(row)
                self.measure_ms, self.rest_ms = 3000, 1500
            else:
                spec = json.loads((self.root/'diseno/mapa-recetas.json').read_text())
                targets = spec['spells'][:];rng.shuffle(targets)
                self.measure_ms, self.rest_ms = 9000, 2000
            self.prepare_ms = 3500
            self.trial_ms = self.prepare_ms+self.measure_ms+self.rest_ms
            self.trials = [{'target': target, 'invalid': False, 'counts': Counter(), 'samples': 0,
                            'stale': 0, 'recipes': [], 'events': [], 'scores': []} for target in targets]
            return self.snapshot(self.start_ms)

    def locate(self, timestamp_ms):
        elapsed = timestamp_ms-self.start_ms
        if elapsed < 0 or elapsed >= len(self.trials)*self.trial_ms:
            return None, 'outside', 0
        index = int(elapsed//self.trial_ms)
        local = elapsed-index*self.trial_ms
        if local < self.prepare_ms:
            return index, 'prepare', self.prepare_ms-local
        if local < self.prepare_ms+self.measure_ms:
            return index, 'measure', self.prepare_ms+self.measure_ms-local
        return index, 'rest', self.trial_ms-local

    def tick(self, now_ms=None):
        now = now_ms if now_ms is not None else time.monotonic()*1000
        with self.lock:
            if self.status != 'running':
                return False
            index, phase, _ = self.locate(now)
            changed = (index, phase) != getattr(self, '_last_phase', None)
            self._last_phase = (index, phase)
            self.index = index
            if index is None:
                self.status = 'finished';self._save()
            return changed

    def observe(self, timestamp_ms, evidence, events, stale=False, frame_meta=None):
        with self.lock:
            if self.status != 'running':
                return
            index, phase, _ = self.locate(timestamp_ms)
            if index is None:
                return
            reliable = (not stale and evidence['sign'] in SIGNS[:-1] and
                        evidence['score'] >= self.thresholds.score_for(evidence['sign']) and
                        evidence['margin'] >= self.thresholds.class_margin)
            decision = evidence['sign'] if reliable else 'unknown'
            trial = self.trials[index]
            if phase == 'measure':
                trial['samples'] += 1;trial['counts'][decision] += 1
                trial['stale'] += int(stale)
                trial['scores'].append(evidence['score'])
                trial['recipes'].extend(e for e in events if e['type'] == 'recipe')
                trial['events'].extend(events)
            self.stream.write(json.dumps({'timestamp_ms': timestamp_ms, 'trial': index+1, 'phase': phase,
                                          'expected': trial['target'], 'decision': decision,
                                          'evidence': evidence, 'stale': stale, 'events': events,
                                          'frame_meta': frame_meta}, ensure_ascii=False)+'\n')

    def exclude_current(self, now_ms=None):
        with self.lock:
            if self.status != 'running':
                raise ValueError('No hay intento activo')
            index, _, _ = self.locate(now_ms if now_ms is not None else time.monotonic()*1000)
            if index is not None:
                self.trials[index]['invalid'] = True

    def abort(self, reason='manual'):
        with self.lock:
            if self.status == 'running':
                self.status = 'aborted';self.abort_reason = reason;self._save()

    def confirm(self):
        with self.lock:
            if self.status != 'finished':
                raise ValueError('Termina el protocolo antes de confirmar las etiquetas')
            self.confirmed = True
            if self.restored:
                self.report.update(user_confirmed_execution=True, provisional=False)
                self.report_path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2)+'\n')
            else:
                self._save()

    def _save(self):
        if self.stream and not self.stream.closed:
            self.stream.flush();self.stream.close()
        results = []
        matrix = {sign: {p: 0 for p in SIGNS} for sign in SIGNS}
        correct = valid = frame_correct = frame_total = 0
        for i, trial in enumerate(self.trials):
            enough = trial['samples'] >= self.fps*self.measure_ms/1000*.75 and trial['stale'] <= trial['samples']*.05
            included = enough and not trial['invalid']
            prediction, fraction = 'inconclusive', 0
            if trial['samples']:
                prediction, votes = trial['counts'].most_common(1)[0]
                fraction = votes/trial['samples']
                if fraction < .8:
                    prediction = 'inconclusive'
            if self.mode == 'signs':
                passed = included and prediction == trial['target']
                if included:
                    for decision, count in trial['counts'].items():
                        matrix[trial['target']][decision] += count
                    frame_correct += trial['counts'][trial['target']];frame_total += trial['samples']
            else:
                recipe_events = trial['recipes']
                passed = included and len(recipe_events) == 1 and recipe_events[0]['spell'] == trial['target']['name']
            valid += included;correct += passed
            results.append({'trial': i+1, 'expected': trial['target'], 'included': included,
                            'excluded_by_user': trial['invalid'], 'capture_complete': enough,
                            'samples': trial['samples'], 'stale_samples': trial['stale'],
                            'decision_counts': dict(trial['counts']), 'events': trial['events'], 'majority': prediction,
                            'majority_fraction': fraction, 'correct': bool(passed), 'recipe_events': trial['recipes']})
        self.report = {'schema_version': 1, 'status': self.status, 'mode': self.mode,
                       'start_monotonic_ms': self.start_ms,
                       'ground_truth': 'prompted_user_labels', 'user_confirmed_execution': self.confirmed,
                       'video_independently_reviewed': False, 'provisional': not self.confirmed,
                       'abort_reason': getattr(self, 'abort_reason', None), 'total_trials': len(results),
                       'included_trials': valid, 'correct_trials': correct,
                       'trial_accuracy': correct/valid if valid else None,
                       'frame_decision_accuracy': frame_correct/frame_total if frame_total else None,
                       'confusion_matrix': matrix if self.mode == 'signs' else None, 'trials': results,
                       'video_clip': getattr(self, 'video_clip', None),
                       'protocol': {'prepare_ms': self.prepare_ms, 'measure_ms': self.measure_ms,
                                    'rest_ms': self.rest_ms, 'target_fps': self.fps,
                                    'minimum_capture_fraction': .75, 'maximum_stale_fraction': .05,
                                    'minimum_majority_fraction': .8,
                                    'guided_next_sign': self.mode == 'recipes'},
                       'note': 'Frames consecutivos están correlacionados. Piloto de esta sesión; no demuestra generalización.',
                       'thresholds': self.thresholds.__dict__, 'game_input_sent': False}
        self.report_path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2)+'\n')

    def snapshot(self, now_ms=None):
        now = now_ms if now_ms is not None else time.monotonic()*1000
        with self.lock:
            result = {'status': self.status, 'mode': getattr(self, 'mode', 'signs'), 'report': self.report,
                      'report_path': str(self.report_path.relative_to(self.root)) if self.report_path else None}
            if self.status == 'running':
                index, phase, remaining = self.locate(now)
                if index is not None:
                    trial = self.trials[index]
                    result.update(trial=index+1, total=len(self.trials), target=trial['target'], phase=phase,
                                  remaining_ms=max(0,remaining), excluded=trial['invalid'], recipe_events=list(trial['recipes']))
            return result
