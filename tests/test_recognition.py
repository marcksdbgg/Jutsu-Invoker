import itertools
from pathlib import Path
import unittest

from jutsu_invoker.recognition import Observation, Trainer, Thresholds

ROOT = Path(__file__).resolve().parents[1]
SIGNS = {"Q": "monkey", "W": "tiger", "E": "horse", "R": "snake"}


class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.trainer = Trainer(ROOT / "diseno/mapa-recetas.json")
        self.time = 0.0

    def frame(self, sign, dt=25, score=.95, margin=.5, **kwargs):
        self.time += dt
        observation = Observation(self.time, SIGNS.get(sign, sign), score, margin, **kwargs)
        return self.trainer.update(observation, self.time)

    def hold(self, sign, frames=4):
        return [event for _ in range(frames) for event in self.frame(sign)]

    def test_all_ten_recipes_and_all_orders_of_three_distinct(self):
        sequences = [(s, s * 3) for s in "QWE"]
        sequences += [(a + b, a * 2 + b) for a, b in itertools.permutations("QWE", 2)]
        sequences += [("".join(p), "QWE") for p in itertools.permutations("QWE", 3)]
        names = set()
        for sequence, expected in sequences:
            with self.subTest(sequence=sequence):
                self.setUp()
                for token in sequence:
                    self.hold(token)
                recipes = [e for e in self.hold("R") if e["type"] == "recipe"]
                self.assertEqual(len(recipes), 1)
                self.assertEqual(recipes[0]["orbs"], expected)
                self.assertEqual(self.trainer.pending, [])
                names.add(recipes[0]["spell"])
        self.assertEqual(len(names), 10)

    def test_held_sign_not_repeated_and_snake_only_once(self):
        self.assertEqual(len([e for e in self.hold("Q", 30) if e["type"] == "accepted"]), 1)
        self.assertEqual(len([e for e in self.hold("R", 30) if e["type"] == "recipe"]), 1)

    def test_transient_snake_cannot_confirm(self):
        self.hold("E")
        events = self.hold("R", 2) + self.hold("transition", 3)
        self.assertFalse(any(e["type"] == "recipe" for e in events))
        self.assertEqual(self.trainer.pending, ["E"])

    def test_confirmation_requires_recipe(self):
        events = self.hold("R")
        self.assertEqual(events[-1]["reason"], "confirmation_without_recipe")

    def test_stale_or_nonvisual_preserves_recipe_without_pose_evidence(self):
        for visual in [True, False]:
            self.setUp()
            self.hold("Q")
            observation = Observation(self.time + 25, "snake", .95, .5, visual)
            events = self.trainer.update(observation, self.time + 200 if visual else self.time + 25)
            self.assertEqual(events[0]["reason"], "stale_or_nonvisual")
            self.assertEqual(events[0]['type'], 'rejected')
            self.assertEqual(self.trainer.pending, ['Q'])
            self.assertEqual(self.trainer.candidate_count, 0)

    def test_duplicate_frames_not_evidence_or_release(self):
        self.frame("Q")
        observation = Observation(self.time, "monkey", .95, .5)
        for _ in range(20):
            events = self.trainer.update(observation, self.time)
            self.assertEqual(events[0]["reason"], "non_increasing_timestamp")
        self.assertEqual(self.trainer.candidate_count, 1)

    def test_low_margin_and_low_score_break_stability(self):
        self.frame("Q")
        self.frame("Q", margin=.01)
        self.frame("Q")
        self.frame("Q", score=.5)
        self.assertEqual(self.trainer.pending, [])
        self.assertEqual(self.trainer.candidate_count, 0)

    def test_short_noise_does_not_release_latch(self):
        self.hold("Q")
        self.frame("unknown")
        self.assertFalse(any(e["type"] == "accepted" for e in self.hold("Q")))
        self.assertEqual(self.trainer.pending, ["Q"])

    def test_return_to_selected_pose_preserves_recipe(self):
        self.hold("Q")
        self.hold("unknown", 3)
        events = self.hold("Q", 20)
        self.assertTrue(any(e.get("reason") == "selector_already_selected" for e in events))
        self.assertEqual(self.trainer.pending, ["Q"])

    def test_missing_frames_restart_stability_but_preserve_recipe(self):
        self.hold("Q")
        events = self.frame("R", dt=101)
        self.assertEqual(events[0]["reason"], "observation_gap")
        self.assertEqual(self.trainer.pending, ['Q'])
        self.assertFalse(any(e['type']=='recipe' for e in events))
        events=self.hold('R',3)
        self.assertEqual([e['spell'] for e in events if e['type']=='recipe'],['Cold Snap'])

    def test_horse_tiger_camera_jitter_then_snake_keeps_both_selectors(self):
        self.trainer=Trainer(ROOT/'diseno/mapa-recetas.json',Thresholds(timeout_ms=1600,element_stable_ms=150,element_observations=5,confirmation_stable_ms=200,confirmation_observations=7))
        self.hold('E',8);self.hold('W',8)
        events=self.frame('R',dt=180)+self.hold('R',3)
        self.assertEqual(self.trainer.pending,['E','W'])
        self.assertFalse(any(e['type']=='recipe' for e in events))
        # A late snake frame cannot complete stability or renew inactivity.
        events=self.trainer.update(Observation(self.time,'snake',.99,.5),self.time+150)
        self.assertEqual(self.trainer.pending,['E','W'])
        self.assertEqual(self.trainer.candidate_count,0)
        self.time+=150
        events=self.hold('R',10)
        self.assertEqual([e['spell'] for e in events if e['type']=='recipe'],['Chaos Meteor'])

    def test_missing_stale_and_duplicate_images_expire_at_real_inactivity_deadline(self):
        for reason in ['observation_gap','stale_or_nonvisual','non_increasing_timestamp']:
            self.setUp();self.trainer=Trainer(ROOT/'diseno/mapa-recetas.json',Thresholds(timeout_ms=1600));self.hold('Q')
            before=self.trainer.last_activity_ms
            events=self.trainer.miss(self.time+1599,reason)
            self.assertEqual(self.trainer.pending,['Q']);self.assertEqual(self.trainer.last_activity_ms,before)
            events=self.trainer.miss(self.time+1601,reason)
            self.assertEqual(events[0]['reason'],'recipe_timeout');self.assertEqual(self.trainer.pending,[])

    def test_held_selector_keeps_recipe_alive_without_repeating(self):
        events = self.hold("Q", 70)
        self.assertEqual(len([e for e in events if e["type"] == "accepted"]), 1)
        self.assertFalse(any(e.get("reason") == "recipe_timeout" for e in events))
        self.assertEqual(self.trainer.pending, ["Q"])

    def test_personal_timing_allows_slow_sequence_but_still_rejects_camera_gaps(self):
        self.trainer = Trainer(ROOT / "diseno/mapa-recetas.json", Thresholds(timeout_ms=3000))
        events=self.hold("Q",100)+self.hold("W")+self.hold("R")
        self.assertEqual([e['spell'] for e in events if e['type']=='recipe'],['Ghost Walk'])
        self.hold('unknown',3)
        self.hold('E')
        events=self.frame('R',dt=101)
        self.assertEqual(events[0]['reason'],'observation_gap')
        self.assertFalse(any(e['type']=='recipe' for e in events))

    def test_neutral_transition_after_long_hold_can_confirm(self):
        events=self.hold('Q',200)+self.hold('unknown',25)+self.hold('R')
        self.assertEqual([e['spell'] for e in events if e['type']=='recipe'],['Cold Snap'])

    def test_inactivity_expires_and_unknown_cannot_renew(self):
        self.hold('Q',200)
        events=self.hold('unknown',50)+self.hold('R')
        self.assertTrue(any(e.get('reason')=='recipe_timeout' for e in events))
        self.assertFalse(any(e['type']=='recipe' for e in events))

    def test_personal_stability_rejects_brief_intermediate_pose(self):
        self.trainer=Trainer(ROOT/'diseno/mapa-recetas.json',Thresholds(element_stable_ms=150,confirmation_stable_ms=200,element_observations=5,confirmation_observations=7,timeout_ms=3000))
        events=self.hold('Q',40)+self.hold('W',4)+self.hold('unknown',15)+self.hold('R',10)
        self.assertEqual([e['spell'] for e in events if e['type']=='recipe'],['Cold Snap'])
        self.assertFalse(any(e.get('token')=='W' for e in events))

    def test_unknown_seals_cannot_be_forced_to_supported_class(self):
        events = self.hold("ram", 30)
        self.assertFalse(any(e["type"] == "accepted" for e in events))

    def test_invalid_numbers_and_future_timestamp(self):
        self.hold("Q")
        events = self.trainer.update(Observation(float("nan"), "snake", .95, .5), self.time)
        self.assertEqual(events[0]["reason"], "invalid_observation")
        events = self.trainer.update(Observation(self.time + 50, "snake", .95, .5), self.time)
        self.assertEqual(events[0]["reason"], "stale_or_nonvisual")

    def test_non_boolean_visual_marker_is_invalid(self):
        events = self.trainer.update(Observation(0, "snake", .95, .5, "false"), 0)
        self.assertEqual(events[0]["reason"], "invalid_observation")


if __name__ == "__main__":
    unittest.main()
