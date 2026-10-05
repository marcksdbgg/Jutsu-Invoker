import json
from pathlib import Path
import tempfile
import unittest

from jutsu_invoker.evaluation import Evaluation, SIGNS
from jutsu_invoker.recognition import Thresholds

ROOT = Path(__file__).resolve().parents[1]

class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'diseno').mkdir()
        (self.root/'diseno/mapa-recetas.json').write_bytes((ROOT/'diseno/mapa-recetas.json').read_bytes())
        self.e = Evaluation(self.root, Thresholds())
    def tearDown(self):
        self.e.abort()
        self.temp.cleanup()
    def feed(self, index, sign=None, score=.99, margin=.9, stale=False, events=None, count=90):
        trial = self.e.trials[index]
        for frame in range(count):
            stamp = index*self.e.trial_ms+self.e.prepare_ms+frame*1000/30
            self.e.observe(stamp, {'sign': sign or trial['target'], 'score': score, 'margin': margin}, events if frame == 0 and events else [], stale)
    def finish(self):
        self.e.tick(len(self.e.trials)*self.e.trial_ms)
        return self.e.report
    def test_independent_labels_confusion_and_confirmation(self):
        self.e.start(rounds=1, now_ms=0)
        for i,t in enumerate(self.e.trials):
            self.feed(i, sign='tiger' if t['target']=='horse' else t['target'])
        r = self.finish()
        self.assertEqual(r['included_trials'],5)
        self.assertEqual(r['correct_trials'],4)
        self.assertEqual(r['confusion_matrix']['horse']['tiger'],90)
        self.assertTrue(r['provisional'])
        self.e.confirm()
        self.assertFalse(json.loads(self.e.report_path.read_text())['provisional'])
        self.assertFalse(self.e.report['video_independently_reviewed'])
    def test_capture_failures_are_excluded_not_counted_as_unknown_success(self):
        self.e.start(rounds=1,now_ms=0)
        for i,t in enumerate(self.e.trials):
            self.feed(i,stale=t['target']=='unknown',count=1 if t['target']=='horse' else 90)
        r = self.finish()
        self.assertEqual(r['included_trials'],3)
        self.assertEqual(r['correct_trials'],3)
        excluded = [t['expected'] for t in r['trials'] if not t['included']]
        self.assertEqual(set(excluded),{'horse','unknown'})
    def test_phase_boundaries_rejection_and_user_exclusion(self):
        self.e.start(rounds=1,now_ms=0)
        for i in range(5):self.feed(i,score=.79)
        self.e.exclude_current(now_ms=1)
        self.e.observe(100,{'sign':'snake','score':.99,'margin':.9},[])
        r = self.finish()
        self.assertEqual(r['included_trials'],4)
        self.assertTrue(r['trials'][0]['excluded_by_user'])
        self.assertEqual(r['trials'][0]['samples'],90)
        self.assertEqual(self.e.locate(-1)[1],'outside')
        self.assertEqual(self.e.locate(3500)[1],'measure')
        self.assertEqual(self.e.locate(6500)[1],'rest')
    def test_recipe_correctness_requires_one_expected_event(self):
        self.e.start(mode='recipes',now_ms=0)
        for i,t in enumerate(self.e.trials):
            event={'type':'recipe','spell':t['target']['name']}
            self.feed(i,sign='unknown',count=270,events=[event,event] if i==0 else [event])
        r = self.finish()
        self.assertEqual(r['included_trials'],10)
        self.assertEqual(r['correct_trials'],9)
    def test_restart_restores_report_without_recomputing_or_losing_trials(self):
        self.e.start(rounds=1,now_ms=0)
        for i in range(5):self.feed(i)
        report=self.finish()
        restored=Evaluation(self.root,Thresholds(timeout_ms=3000))
        self.assertEqual(restored.snapshot()['report']['correct_trials'],5)
        restored.confirm()
        saved=json.loads(self.e.report_path.read_text())
        self.assertEqual(len(saved['trials']),5)
        self.assertTrue(saved['user_confirmed_execution'])
        self.assertEqual(saved['thresholds']['timeout_ms'],1200)
        restored.start(rounds=1,now_ms=0)
        self.assertFalse(restored.restored)
        restored.abort()

    def test_abort_is_retained_and_cannot_be_confirmed(self):
        self.e.start(rounds=1,now_ms=0)
        self.feed(0)
        self.e.abort('camera_disconnected')
        r=json.loads(self.e.report_path.read_text())
        self.assertEqual(r['status'],'aborted')
        self.assertEqual(r['included_trials'],1)
        self.assertEqual(r['abort_reason'],'camera_disconnected')
        with self.assertRaises(ValueError):self.e.confirm()
        self.e.start(rounds=1,now_ms=0)
        self.assertFalse(self.e.confirmed)
        self.assertIsNone(self.e.abort_reason)

if __name__=='__main__':unittest.main()
