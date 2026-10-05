import unittest

from jutsu_invoker.gpu import choose_evidence


class EvidenceTests(unittest.TestCase):
    def test_no_detection_is_unknown(self):
        self.assertEqual(choose_evidence([])["sign"], "unknown")

    def test_competing_boxes_reduce_margin(self):
        detections = [
            {"sign": "snake", "class_id": 5, "score": .95, "margin": .7},
            {"sign": "horse", "class_id": 6, "score": .9, "margin": .7},
        ]
        self.assertLess(choose_evidence(detections)["margin"], .15)

    def test_other_seals_are_not_remapped(self):
        detection = {"sign": "unknown", "class_id": 7, "score": .99, "margin": .7}
        self.assertEqual(choose_evidence([detection])["sign"], "unknown")
