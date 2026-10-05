from pathlib import Path
import json,tempfile,tomllib,unittest
from types import SimpleNamespace
from jutsu_invoker.settings import UserSettings, validate
from jutsu_invoker.live import LiveTrainer,thresholds_from_config
from jutsu_invoker.recognition import Trainer,Observation

ROOT=Path(__file__).resolve().parents[1]
BASE=tomllib.loads((ROOT/'config/desarrollo-gpu.toml').read_text())

class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'config').mkdir();(self.root/'config/desarrollo-gpu.toml').write_text((ROOT/'config/desarrollo-gpu.toml').read_text())
    def tearDown(self):self.temp.cleanup()
    def test_save_reload_reset_and_keep_machine_configuration(self):
        s=UserSettings(self.root,BASE);s.save({'timeout_ms':1800,'monkey_score':.77})
        restored=UserSettings(self.root,BASE)
        self.assertEqual(restored.values['timeout_ms'],1800)
        self.assertEqual(restored.config()['capture']['adb_path'],BASE['capture']['adb_path'])
        restored.save(reset=True);self.assertEqual(restored.values['timeout_ms'],1600)
        self.assertEqual(UserSettings(self.root,BASE).values,restored.defaults)
    def test_invalid_updates_do_not_change_saved_file(self):
        s=UserSettings(self.root,BASE);s.save({'timeout_ms':1700});before=s.path.read_bytes()
        for change in [{'timeout_ms':True},{'timeout_ms':float('nan')},{'timeout_ms':0},{'orientation':45},{'pose_hz':1.5},{'tiger_refinement':1},{'unknown_key':1}]:
            with self.subTest(change=change),self.assertRaises(ValueError):s.save(change)
            self.assertEqual(s.path.read_bytes(),before)
            self.assertEqual(s.values['timeout_ms'],1700)
    def test_runtime_changes_wait_for_frame_boundary_and_clear_old_recipe(self):
        app=LiveTrainer(self.root);app.trainer=Trainer(ROOT/'diseno/mapa-recetas.json',app.thresholds)
        app.trainer.pending=['Q'];app.thread=SimpleNamespace(is_alive=lambda:True)
        app.update_settings({'timeout_ms':1800})
        self.assertEqual(app.thresholds.timeout_ms,1600);self.assertEqual(app.trainer.pending,['Q'])
        self.assertTrue(app.settings_event.is_set());app.apply_settings()
        self.assertEqual(app.trainer.thresholds.timeout_ms,1800);self.assertEqual(app.trainer.pending,[])
        self.assertFalse(app.settings_event.is_set())
    def test_settings_cannot_change_an_active_pilot(self):
        app=LiveTrainer(self.root);app.evaluation.status='running'
        with self.assertRaises(ValueError):app.update_settings({'timeout_ms':1800})
        self.assertFalse(app.user_settings.path.exists())
    def test_pilot_waits_until_pending_settings_are_applied(self):
        app=LiveTrainer(self.root);app.settings_event.set()
        with self.assertRaisesRegex(ValueError,'apliquen los ajustes'):app.start_evaluation()
        self.assertEqual(app.evaluation.status,'idle')
    def test_mono_is_faster_without_weakening_other_elements(self):
        th=thresholds_from_config(BASE)
        for sign in ['monkey','tiger','horse']:
            trainer=Trainer(ROOT/'diseno/mapa-recetas.json',th);events=[]
            for t in [0,33,66,100]:events.extend(trainer.update(Observation(t,sign,.77,.3),t))
            self.assertEqual(bool([e for e in events if e['type']=='accepted']),sign=='monkey')
    def test_requested_timeout_keeps_transitions_until_1600_ms(self):
        trainer=Trainer(ROOT/'diseno/mapa-recetas.json',thresholds_from_config(BASE))
        for t in [0,33,66,100]:trainer.update(Observation(t,'monkey',.9,.3),t)
        for t in range(150,1701,50):
            events=trainer.update(Observation(t,'unknown',0,0),t)
            self.assertFalse(any(e.get('reason')=='recipe_timeout' for e in events))
        self.assertEqual(trainer.pending,['Q'])
        events=trainer.update(Observation(1750,'unknown',0,0),1750)
        self.assertEqual(events[0]['reason'],'recipe_timeout');self.assertEqual(trainer.pending,[])
    def test_tiger_accepts_four_clear_frames_without_shortening_horse_or_snake(self):
        th=thresholds_from_config(BASE)
        for sign in ['tiger','horse','snake']:
            trainer=Trainer(ROOT/'diseno/mapa-recetas.json',th);trainer.pending=['Q'];events=[]
            for t in [0,33,66,99]:events.extend(trainer.update(Observation(t,sign,.9,.3),t))
            self.assertEqual(any(e['type']=='accepted' for e in events),sign=='tiger')
            self.assertFalse(any(e['type']=='recipe' for e in events))
    def test_tiger_still_requires_both_elapsed_time_and_four_distinct_images(self):
        th=thresholds_from_config(BASE)
        for timestamps in [[0,10,20,30,40],[0,45,90]]:
            trainer=Trainer(ROOT/'diseno/mapa-recetas.json',th);events=[]
            for t in timestamps:events.extend(trainer.update(Observation(t,'tiger',.9,.3),t))
            self.assertFalse(any(e['type']=='accepted' for e in events))
        trainer=Trainer(ROOT/'diseno/mapa-recetas.json',th)
        for _ in range(20):trainer.update(Observation(0,'tiger',.9,.3),0)
        self.assertEqual(trainer.pending,[]);self.assertEqual(trainer.candidate_count,1)
    def test_tiger_speedup_does_not_accept_weak_ambiguous_or_interrupted_pose(self):
        th=thresholds_from_config(BASE)
        for score,margin in [(.79,.3),(.9,.14)]:
            trainer=Trainer(ROOT/'diseno/mapa-recetas.json',th);events=[]
            for t in [0,33,66,99,132,165]:events.extend(trainer.update(Observation(t,'tiger',score,margin),t))
            self.assertFalse(any(e['type']=='accepted' for e in events))
        for middle in [Observation(66,'unknown',0,0),Observation(66,'horse',.9,.3),
                       Observation(66,'tiger',.9,.3,False)]:
            trainer=Trainer(ROOT/'diseno/mapa-recetas.json',th)
            for t in [0,33]:trainer.update(Observation(t,'tiger',.9,.3),t)
            trainer.update(middle,66)
            events=[]
            for t in [99,132,165]:events.extend(trainer.update(Observation(t,'tiger',.9,.3),t))
            self.assertFalse(any(e['type']=='accepted' for e in events))
    def test_tiger_specific_settings_persist_without_changing_other_poses(self):
        settings=UserSettings(self.root,BASE)
        settings.save({'tiger_stable_ms':130,'tiger_observations':5,'tiger_enter_score':.82})
        th=thresholds_from_config(UserSettings(self.root,BASE).config())
        self.assertEqual(th.stability_for('tiger'),(130,5));self.assertEqual(th.score_for('tiger'),.82)
        self.assertEqual(th.stability_for('horse'),(150,5));self.assertEqual(th.score_for('horse'),.8)
        with self.assertRaises(ValueError):settings.save({'tiger_observations':2})
    def test_existing_user_preferences_gain_new_tiger_defaults(self):
        (self.root/'config/usuario.json').write_text(json.dumps({'timeout_ms':1900,'monkey_score':.76}))
        settings=UserSettings(self.root,BASE)
        self.assertEqual(settings.values['timeout_ms'],1900)
        self.assertEqual(settings.values['monkey_score'],.76)
        self.assertEqual(settings.values['tiger_stable_ms'],90)
        self.assertEqual(settings.values['tiger_observations'],4)
