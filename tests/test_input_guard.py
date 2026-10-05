from types import SimpleNamespace
import unittest
from jutsu_invoker.input_guard import InputGuard
from jutsu_invoker.dota import KEY_CODES

class InputGuardTests(unittest.TestCase):
    def test_enter_outside_dota_does_not_latch_chat_block(self):
        guard=InputGuard.__new__(InputGuard)
        guard.virtual_codes=set();guard._epoch=0;guard.expected={}
        guard.text_codes={36};guard.escape_code=9;guard.text_blocked=False;guard.focus_probe=lambda:False
        guard._observe(SimpleNamespace(evtype=13,detail=36))
        self.assertFalse(guard.text_blocked)
        guard.focus_probe=lambda:True
        guard._observe(SimpleNamespace(evtype=13,detail=36))
        self.assertTrue(guard.text_blocked)
        guard.focus_probe=lambda:False
        guard._observe(SimpleNamespace(evtype=13,detail=9))
        self.assertTrue(guard.text_blocked)
    def test_own_evdev_function_keys_are_not_manual_input(self):
        guard=InputGuard.__new__(InputGuard)
        guard.virtual_codes=set(range(191,196));guard._epoch=0
        guard.expected={};guard.text_codes={36,104};guard.escape_code=9;guard.text_blocked=False;guard.focus_probe=lambda:True
        for key in ['f13','f14','f15','f16','f17']:
            guard._observe(SimpleNamespace(evtype=13,detail=KEY_CODES[key]+8))
        self.assertEqual(guard._epoch,0)
        guard._observe(SimpleNamespace(evtype=13,detail=KEY_CODES['q']+8))
        guard._observe(SimpleNamespace(evtype=13,detail=50))  # Shift
        guard._observe(SimpleNamespace(evtype=15,detail=1))  # Selection click
        self.assertEqual(guard._epoch,3)

    def test_direct_keys_ignore_one_own_press_but_preserve_manual_press(self):
        import time
        guard=InputGuard.__new__(InputGuard)
        guard.virtual_codes=set();guard._epoch=0;guard.expected={24:[time.monotonic()+1]}
        guard.text_codes={36};guard.escape_code=9;guard.text_blocked=False;guard.focus_probe=lambda:True
        guard._observe(SimpleNamespace(evtype=13,detail=24));self.assertEqual(guard._epoch,0)
        guard._observe(SimpleNamespace(evtype=13,detail=24));self.assertEqual(guard._epoch,1)
        guard._observe(SimpleNamespace(evtype=13,detail=36));self.assertTrue(guard.text_blocked)
        guard._observe(SimpleNamespace(evtype=13,detail=9));self.assertFalse(guard.text_blocked)
        guard._observe(SimpleNamespace(evtype=15,detail=2))
        guard._observe(SimpleNamespace(evtype=14,detail=24))
        self.assertEqual(guard._epoch,3)
