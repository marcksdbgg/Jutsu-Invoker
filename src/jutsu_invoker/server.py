"""Loopback-only trainer UI and compressed H264 preview; no video transcoding."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit, parse_qs

from .live import LiveTrainer


class TrainerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root: Path, port: int = 32147, **options):
        self.root = root
        self.token = secrets.token_hex(24)
        self.control_lock = threading.Lock()
        super().__init__(("127.0.0.1", port), Handler)
        try:self.app = LiveTrainer(root, **options)
        except BaseException:
            super().server_close()
            raise

    def server_close(self):
        try:
            self.app.close()
        finally:
            super().server_close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def valid_host(self):
        port = self.server.server_address[1]
        return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def body(self, data: bytes, content_type="application/json", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def json(self, value, status=200):
        self.body(json.dumps(value, ensure_ascii=False).encode(), status=status)

    def do_GET(self):
        if not self.valid_host():
            self.json({"error": "Host inválido"}, 403)
            return
        path = urlsplit(self.path).path
        if path == "/api/state":
            self.json(self.server.app.snapshot())
        elif path == "/api/seals":
            self.seals()
        elif path == "/api/recipes":
            self.json(json.loads((self.server.root / "diseno/mapa-recetas.json").read_text()))
        elif path == "/video":
            self.video()
        elif path == "/sellos-naruto.png":
            self.body((self.server.root / "referencias/sellos-naruto.png").read_bytes(), "image/png")
        elif path in {'/audio/naruto-monkey.wav','/audio/naruto-tiger.wav','/audio/naruto-horse.wav','/audio/naruto-snake.wav','/audio/naruto-confirm.wav'}:
            self.body((Path(__file__).parent/'web'/path[1:]).read_bytes(),'audio/wav')
        elif path in {"/", "/app.js", "/preview.js", "/sound.js", "/style.css"}:
            name = "index.html" if path == "/" else path[1:]
            data = (Path(__file__).parent / "web" / name).read_bytes()
            if name == "index.html":
                data = data.replace(b"__CSRF_TOKEN__", self.server.token.encode())
            content_type = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
                            "preview.js": "text/javascript; charset=utf-8", "sound.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}[name]
            self.body(data, content_type)
        else:
            self.json({"error": "No encontrado"}, 404)

    def do_POST(self):
        if not self.valid_host() or self.headers.get("X-Jutsu-Token") != self.server.token:
            self.json({"error": "Solicitud sin token local válido"}, 403)
            return
        port = self.server.server_address[1]
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
            self.json({"error": "Origen inválido"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 4096:
                raise ValueError("Solicitud demasiado grande")
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("Solicitud inválida")
            path = urlsplit(self.path).path
            app = self.server.app
            with self.server.control_lock:
                if path == "/api/start":
                    app.start()
                elif path == "/api/stop":
                    app.stop()
                elif path == "/api/reconnect":
                    app.reconnect(payload.get("facing"))
                elif path == "/api/settings":
                    app.update_settings(payload)
                elif path == "/api/settings/reset":
                    app.update_settings(reset=True)
                elif path == "/api/cancel":
                    app.cancel_event.set()
                elif path == "/api/record/start":
                    app.record(payload.get("label"))
                elif path == "/api/record/stop":
                    if app.evaluation.status == "running":raise ValueError("Detén la evaluación con su propio control")
                    app.finish_recording()
                elif path == '/api/evaluation/start':
                    app.start_evaluation(payload.get('mode','signs'), payload.get('rounds',2))
                elif path == '/api/evaluation/abort':
                    app.abort_evaluation()
                elif path == '/api/evaluation/exclude':
                    app.evaluation.exclude_current()
                elif path == '/api/evaluation/confirm':
                    app.evaluation.confirm()
                elif path == '/api/dota/arm':
                    if app.evaluation.status == 'running':
                        raise ValueError('Termina la evaluación antes de activar Dota')
                    app.dota.arm()
                    app.arm_reset_event.set()
                elif path == '/api/dota/disarm':
                    app.dota.disarm()
                else:
                    self.json({"error": "No encontrado"}, 404)
                    return
            self.json(app.snapshot())
        except (ValueError, RuntimeError, OSError) as error:
            self.json({"error": str(error)}, 400)

    def seals(self):
        # Network events continue while Chrome is behind Dota, without relying
        # on background setTimeout polling. No old cues on reconnect.
        cursor, _, closed = self.server.app.wait_seals()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        self.connection.settimeout(2)
        try:
            self.wfile.write(b'event: ready\ndata: {}\n\n');self.wfile.flush()
            while not closed:
                cursor, events, closed = self.server.app.wait_seals(cursor)
                now = time.monotonic()*1000
                events = [event for event in events if 0<=now-event['received_ms']<=700]
                data = json.dumps({'events':events,'server_monotonic_ms':now,'dota_armed':self.server.app.dota.armed},ensure_ascii=False).encode()
                self.wfile.write(b'event: seals\ndata: '+data+b'\n\n');self.wfile.flush()
        except OSError:
            pass

    def video(self):
        try:
            params = parse_qs(urlsplit(self.path).query)
            cursor = int(params.get("cursor", ["0"])[0])
            generation = int(params.get("generation", ["-1"])[0])
            if cursor < 0:
                raise ValueError("Cursor inválido")
        except ValueError:
            self.json({"error": "Cursor inválido"}, 400)
            return
        data, cursor, generation = self.server.app.hub.batch(cursor, generation)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Video-Cursor", str(cursor))
        self.send_header("X-Video-Generation", str(generation))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except OSError:
            pass
