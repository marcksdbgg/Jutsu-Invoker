import unittest
from jutsu_invoker.tiger_refinement import agreed_tiger


def detection(label,sign,score=.9):
    return [{'source_label':label,'sign':sign,'score':score,'margin':.8,'class_id':2 if sign=='tiger' else 7}]


class TigerRefinementTests(unittest.TestCase):
    def test_original_ram_is_not_remapped_without_both_views(self):
        ram=detection('Hitsuji(Ram)','unknown');tiger=detection('Tora(Tiger)','tiger')
        for mirror,context in [(tiger,ram),(ram,tiger),([],tiger),(tiger,[])]:
            e,accepted=agreed_tiger(ram,mirror,context)
            self.assertFalse(accepted);self.assertEqual(e['sign'],'unknown')
    def test_requires_confidence_and_margin_in_each_view(self):
        ram=detection('Hitsuji(Ram)','unknown');tiger=detection('Tora(Tiger)','tiger')
        weak=detection('Tora(Tiger)','tiger',.84)
        self.assertFalse(agreed_tiger(ram,tiger,weak)[1])
        weak=detection('Tora(Tiger)','tiger');weak[0]['margin']=.14
        self.assertFalse(agreed_tiger(ram,weak,tiger)[1])
    def test_preserves_original_supported_and_other_unsupported_classes(self):
        tiger=detection('Tora(Tiger)','tiger')
        for label,sign in [('Saru(Monkey)','monkey'),('Uma(Horse)','horse'),('Mi(Snake)','snake'),('Ne(Rat)','unknown')]:
            e,accepted=agreed_tiger(detection(label,sign),tiger,tiger)
            self.assertEqual(e['sign'],sign);self.assertFalse(accepted)
    def test_agreement_retains_conservative_response_and_raw_metadata(self):
        ram=detection('Hitsuji(Ram)','unknown');a=detection('Tora(Tiger)','tiger',.89);b=detection('Tora(Tiger)','tiger',.87)
        e,accepted=agreed_tiger(ram,a,b)
        self.assertTrue(accepted);self.assertEqual(e['score'],.87)
        self.assertEqual(ram[0]['sign'],'unknown')
