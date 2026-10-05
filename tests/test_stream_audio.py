import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('stream_audio', Path(__file__).resolve().parents[1] / 'scripts/stream_audio_router.py')
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


class StreamAudioTests(unittest.TestCase):
    def test_string_and_integer_client_ids_resolve_real_dota(self):
        clients = {'7': {'application.process.binary': 'dota2', 'application.process.id': '123'}}
        with patch.object(router.Path, 'resolve', return_value=Path('/game/dota2')):
            for client in ['7', 7]:
                self.assertTrue(router.is_dota({'client': client}, clients))

    def test_other_app_and_missing_client_are_not_routed(self):
        clients = {'7': {'application.process.binary': 'Discord'}}
        with patch.object(router.Path, 'resolve') as resolve:
            self.assertFalse(router.is_dota({'client': 7}, clients))
            self.assertFalse(router.is_dota({'client': None}, clients))
            resolve.assert_not_called()

    def test_claimed_dota_must_match_running_executable(self):
        clients = {'7': {'application.process.binary': 'dota2', 'application.process.id': '123'}}
        with patch.object(router.Path, 'resolve', return_value=Path('/usr/bin/other')):
            self.assertFalse(router.is_dota({'client': 7}, clients))
        with patch.object(router.Path, 'resolve', side_effect=FileNotFoundError):
            self.assertFalse(router.is_dota({'client': 7}, clients))

    def test_invalid_process_ids_are_rejected(self):
        for pid in [None, '', 'abc', '-1', '0']:
            with self.subTest(pid=pid):
                clients = {'7': {'application.process.binary': 'dota2', 'application.process.id': pid}}
                self.assertFalse(router.is_dota({'client': 7}, clients))
