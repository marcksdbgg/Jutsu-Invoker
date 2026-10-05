import http.client
import json
from pathlib import Path
import tempfile
import tomllib
from jutsu_invoker.settings import UserSettings
import threading
import unittest
from jutsu_invoker.server import TrainerServer

ROOT=Path(__file__).resolve().parents[1]

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.server=TrainerServer(ROOT,port=0,dota_enabled=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_address[1]
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,method='GET',body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        c.request(method,path,body=body,headers=headers or {})
        r=c.getresponse();status=r.status;data=r.read();c.close();return status,data
    def test_local_ui_and_bounded_empty_preview(self):
        status,html=self.request('/')
        self.assertEqual(status,200);self.assertIn(self.server.token.encode(),html)
        status,data=self.request('/api/state');self.assertEqual(json.loads(data)['status'],'stopped')
        self.assertEqual(self.request('/video'),(200,b''))
        self.assertEqual(self.request('/video?cursor=broken')[0],400)
        self.assertEqual(self.request('/sound.js')[0],200)
        for name in ['naruto-monkey','naruto-tiger','naruto-horse','naruto-snake','naruto-confirm']:
            status,data=self.request('/audio/'+name+'.wav')
            self.assertEqual(status,200);self.assertEqual(data[:4],b'RIFF');self.assertLess(len(data),60000)
        self.assertEqual(self.request('/audio/../../config/usuario.json')[0],404)
        self.assertEqual(self.request('/audio/naruto-seal.wav')[0],404)

    def test_seal_push_has_no_history_replay_and_only_new_accepted_events(self):
        app=self.server.app
        app.emit([{'type':'accepted','token':'Q','sign':'monkey','pending':['Q'],'timestamp_ms':1}])
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        try:
            c.request('GET','/api/seals');r=c.getresponse()
            self.assertEqual(r.status,200);self.assertEqual(r.getheader('Content-Type'),'text/event-stream; charset=utf-8')
            self.assertEqual(r.fp.readline(),b'event: ready\n')
            self.assertEqual(r.fp.readline(),b'data: {}\n');self.assertEqual(r.fp.readline(),b'\n')
            app.emit([{'type':'rejected','reason':'unsupported_or_transition'}, {'type':'accepted','token':'W','sign':'tiger','pending':['Q','W'],'timestamp_ms':2}])
            self.assertEqual(r.fp.readline(),b'event: seals\n')
            data=json.loads(r.fp.readline().removeprefix(b'data: '))
            self.assertEqual([e['token'] for e in data['events']],['W'])
            cursor,old,_=app.wait_seals();self.assertEqual(old,[])
            app.emit([{'type':'cancelled','reason':'manual_cancel'}])
            self.assertEqual(app.wait_seals(cursor,timeout=0)[1],[])
        finally:c.close()
    def test_settings_http_persistence_validation_and_reset(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'config').mkdir()
            app=self.server.app
            app.user_settings=UserSettings(root,tomllib.loads((ROOT/'config/desarrollo-gpu.toml').read_text()))
            app.apply_settings()
            headers={'X-Jutsu-Token':self.server.token,'Content-Type':'application/json'}
            self.assertEqual(self.request('/preview.js')[0],200)
            self.assertEqual(self.request('/api/settings','POST',b'{"timeout_ms":1800}')[0],403)
            status,data=self.request('/api/settings','POST',b'{"timeout_ms":1800}',headers)
            self.assertEqual(status,200);self.assertEqual(json.loads(data)['thresholds']['timeout_ms'],1800)
            self.assertEqual(json.loads(app.user_settings.path.read_text())['timeout_ms'],1800)
            before=app.user_settings.path.read_bytes()
            self.assertEqual(self.request('/api/settings','POST',b'{"orientation":45}',headers)[0],400)
            self.assertEqual(before,app.user_settings.path.read_bytes())
            status,data=self.request('/api/settings/reset','POST',b'{}',headers)
            self.assertEqual(status,200);self.assertEqual(json.loads(data)['settings']['timeout_ms'],1600)
            self.assertEqual(json.loads(data)['settings']['orientation'],180)
    def test_camera_mode_does_not_enable_dota_or_keyboard(self):
        app=self.server.app
        self.assertIsNone(app.dota.receiver)
        self.assertIsNone(app.dota.keyboard)
        self.assertFalse(app.snapshot()['game_input_sent'])
        headers={'X-Jutsu-Token':self.server.token}
        self.assertEqual(self.request('/api/dota/arm','POST',b'{}',headers)[0],400)
        self.assertIsNone(app.dota.keyboard)
        self.assertFalse(app.snapshot()['dota']['armed'])
        self.assertEqual(self.request('/api/evaluation/start','POST',b'{}',headers)[0],400)

    def test_controls_require_local_host_token_and_origin(self):
        self.assertEqual(self.request('/api/cancel','POST',b'{}')[0],403)
        headers={'X-Jutsu-Token':self.server.token,'Origin':'https://external.example'}
        self.assertEqual(self.request('/api/cancel','POST',b'{}',headers)[0],403)
        headers['Origin']=f'http://127.0.0.1:{self.port}'
        self.assertEqual(self.request('/api/cancel','POST',b'{}',headers)[0],200)
        self.assertTrue(self.server.app.cancel_event.is_set())
        self.assertEqual(self.request('/api/state',headers={'Host':'external.example'})[0],403)
        self.assertEqual(self.request('/api/cancel','POST',b'[]',headers)[0],400)

if __name__=='__main__':unittest.main()
