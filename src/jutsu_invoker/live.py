"""Live camera controller, bounded video preview fanout and local trainer state."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import threading
import time
import tomllib

from .camera import LatestFrame, Packet, ScrcpyCamera, Session
from .recognition import Observation, Thresholds, Trainer
from .evaluation import Evaluation
from .dota import DotaIntegration
from .settings import UserSettings


def thresholds_from_config(config: dict) -> Thresholds:
    a = config["acceptance"]
    return Thresholds(enter_score=a["enter_score"], class_margin=a["class_margin"],
                      element_stable_ms=a["element_min_stable_ms"], confirmation_stable_ms=a["confirmation_min_stable_ms"],
                      element_observations=a["element_min_fresh_observations"], confirmation_observations=a["confirmation_min_fresh_observations"],
                      timeout_ms=a["inter_sign_timeout_ms"], max_age_ms=a["max_observation_age_ms"],
                      max_gap_ms=a["max_observation_gap_ms"], release_ms=a["release_min_ms"],
                      monkey_enter_score=a.get("monkey_enter_score"), monkey_stable_ms=a.get("monkey_min_stable_ms"),
                      monkey_observations=a.get("monkey_min_fresh_observations"),
                      tiger_enter_score=a.get("tiger_enter_score"), tiger_stable_ms=a.get("tiger_min_stable_ms"),
                      tiger_observations=a.get("tiger_min_fresh_observations"))


class VideoHub:
    def __init__(self):
        self.lock = threading.Lock()
        self.config = None
        self.history = deque(maxlen=64)
        self.cursor = 0
        self.generation = 0

    def reset(self):
        with self.lock:
            self.config = None
            self.history.clear()
            self.generation += 1

    @staticmethod
    def wire(packet):
        flags = packet.pts_us | (int(packet.config) << 62) | (int(packet.keyframe) << 61)
        return struct.pack(">QI", flags, len(packet.data)) + packet.data

    def publish(self, packet):
        with self.lock:
            if packet.config:
                self.config = self.wire(packet)
                return
            self.cursor += 1
            self.history.append((self.cursor, packet.keyframe, self.wire(packet)))

    def batch(self, cursor=0, generation=-1):
        """Finite Annex-B batches; lagging clients restart at a complete GOP."""
        with self.lock:
            if not self.config or not self.history:
                return b"", cursor, self.generation
            rows = list(self.history)
            restart = cursor == 0 or cursor > self.cursor or generation != self.generation or cursor < rows[0][0] - 1
            if restart:
                keys = [i for i, row in enumerate(rows) if row[1]]
                if not keys:
                    return b"", cursor, self.generation
                rows = rows[keys[-1]:]
            else:
                rows = [r for r in rows if r[0] > cursor]
            data = (self.config if restart and rows else b"") + b"".join(r[2] for r in rows)
            return data, rows[-1][0] if rows else cursor, self.generation


class Recorder:
    def __init__(self, root: Path, label: str, facing: str, fps: int, config: bytes | None, orientation: int = 0):
        if label not in {"monkey", "tiger", "horse", "snake", "transition", "unknown", "evaluation"}:
            raise ValueError("Etiqueta de captura inválida")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.path = root / "datos/clips" / f"{stamp}-{label}.h264"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("wb")
        self.config = config
        self.meta = {"schema_version": 1, "label": label, "session": stamp, "camera_facing": facing,
                     "target_fps": fps, "capture_orientation_degrees": orientation, "codec": "h264", "first_pts_us": None, "packets": []}
        self.waiting_keyframe = True

    def packet(self, packet):
        if packet.config:
            self.config = packet.data
            if not self.waiting_keyframe:
                self.stream.write(packet.data)
            return
        if self.waiting_keyframe:
            if not packet.keyframe or self.config is None:
                return
            self.waiting_keyframe = False
            self.meta["first_pts_us"] = packet.pts_us
            self.stream.write(self.config)
        offset = self.stream.tell()
        self.stream.write(packet.data)
        self.meta["packets"].append({"pts_us": packet.pts_us, "offset_bytes": offset,
                                     "bytes": len(packet.data), "keyframe": packet.keyframe})

    def close(self, reason="manual"):
        if self.stream.closed:
            return str(self.path)
        self.stream.close()
        self.meta["closed_reason"] = reason
        self.meta["frames"] = len(self.meta["packets"])
        self.path.with_suffix(".json").write_text(json.dumps(self.meta, ensure_ascii=False, indent=2) + "\n")
        return str(self.path)


class LiveTrainer:
    def __init__(self, root: Path, backend=None, facing=None, serial=None, dota_enabled=False):
        self.root = root
        self.user_settings = UserSettings(root, tomllib.loads((root / "config/desarrollo-gpu.toml").read_text()))
        self.config = self.user_settings.config()
        self.backend = backend or self.config["compute"]["inference_backend"]
        if self.backend == "onnxruntime_cuda_fp32":
            self.backend = "onnxruntime"
        self.facing = facing or self.config["capture"]["camera_facing"]
        self.serial = serial
        self.thresholds = thresholds_from_config(self.config)
        self.evaluation = Evaluation(root, self.thresholds, self.config['capture']['target_fps'])
        self.dota = DotaIntegration(root, enabled=dota_enabled)
        self.hub = VideoHub()
        self.lock = threading.RLock()
        self.record_lock = threading.Lock()
        self.recorder = None
        self.last_config = None
        self.command_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.cancel_event = threading.Event()
        self.arm_reset_event = threading.Event()
        self.settings_event = threading.Event()
        self.thread = None
        self.camera = None
        self.events = deque(maxlen=30)
        self.seal_condition = threading.Condition()
        self.seal_sequence = 0
        self.seal_events = deque(maxlen=32)
        self.seal_closed = False
        self.dota.on_cast = self.publish_seal
        self.timings = deque(maxlen=300)
        self.poses = deque(maxlen=12)
        self.trainer = None
        self.state = {"status": "stopped", "message": "Cámara detenida", "pending": [], "sign": "unknown",
                      "score": 0, "margin": 0, "fps": 0, "frames": 0, "backend": self.backend,
                      "facing": self.facing, "capture_orientation_degrees": self.config["capture"].get("capture_orientation_degrees",0), "recording": None, "last_recipe": None, "game_input_sent": False}

    def snapshot(self):
        with self.lock:
            state = self.state.copy()
            state["events"] = list(self.events)
            state["poses"] = list(self.poses) if state["status"] == "running" and self.config["vision"]["pose_diagnostic_hz"] else []
            state["thresholds"] = asdict(self.thresholds)
            state["settings"] = self.user_settings.values.copy()
            state["settings_pending"] = self.settings_event.is_set()
            state["settings_defaults"] = self.user_settings.defaults.copy()
            state["server_monotonic_ms"] = time.monotonic() * 1000
            state["preview_transport"] = "finite_h264_batches"
            state['evaluation'] = self.evaluation.snapshot()
            state['dota'] = self.dota.snapshot()
            state['game_input_sent'] = state['dota']['game_input_sent']
            return state

    def apply_settings(self):
        with self.lock:
            self.config = self.user_settings.config()
            self.thresholds = thresholds_from_config(self.config)
            self.evaluation.thresholds = self.thresholds
            if self.trainer:
                self.trainer.thresholds = self.thresholds
                self.emit([self.trainer.cancel('settings_changed')])
            self.poses.clear()
            self.state['capture_orientation_degrees'] = self.config['capture']['capture_orientation_degrees']
            self.settings_event.clear()

    def update_settings(self, changes=None, reset=False):
        if self.evaluation.status == 'running':
            raise ValueError('Termina la prueba antes de cambiar ajustes; sus resultados conservarán los valores originales')
        previous_orientation = self.config['capture']['capture_orientation_degrees']
        self.user_settings.save(changes, reset)
        self.dota.disarm('Ajustes cambiados')
        running = self.thread and self.thread.is_alive()
        if self.user_settings.values['orientation'] != previous_orientation and running:
            self.stop()
            self.apply_settings()
            self.start()
        elif running:
            self.settings_event.set()
        else:
            self.apply_settings()

    def set_state(self, **values):
        with self.lock:
            self.state.update(values)

    def emit(self, events):
        with self.lock:
            for event in events:
                if event["type"] == "rejected":
                    self.state["rejection"] = event["reason"]
                else:
                    recorded = {**event, "received_ms": time.monotonic() * 1000}
                    self.events.append(recorded)
                if event["type"] == "recipe":
                    self.state["last_recipe"] = event
                if event['type'] in {'accepted','recipe'} and self.evaluation.status != 'running':
                    self.dota.submit(event)
                if event['type'] in {'accepted','recipe'}:
                    self.publish_seal(recorded)
                if event['type'] == 'cancelled' and event['reason'] not in {'dota_armed','dota_context_changed'}:
                    self.dota.cancel_pending(event['reason'])
            self.state["pending"] = self.trainer.pending.copy() if self.trainer else []

    def publish_seal(self,event):
        # No inference/UI lock here: GSI confirms while holding the Dota lock.
        with self.seal_condition:
            self.seal_sequence += 1
            self.seal_events.append((self.seal_sequence,event))
            self.seal_condition.notify_all()

    def wait_seals(self, after=None, timeout=15):
        """Bounded push channel: a new/reconnected listener starts after history."""
        with self.seal_condition:
            if after is None:return self.seal_sequence, [], self.seal_closed
            self.seal_condition.wait_for(lambda:self.seal_sequence>after or self.seal_closed, timeout)
            return self.seal_sequence, [event for seq,event in self.seal_events if seq>after], self.seal_closed

    def start(self):
        with self.command_lock:
            if self.thread and self.thread.is_alive():
                return
            self.stop_event.clear()
            self.cancel_event.clear()
            self.last_config = None
            self.timings.clear()
            self.set_state(status="starting", message="Preparando reconocedor y cámara…", error=None,
                           facing=self.facing, pending=[], frames=0, fps=0, sign="unknown", score=0,
                           margin=0, last_recipe=None, rejection=None)
            self.thread = threading.Thread(target=self._run, name="jutsu-inference", daemon=True)
            self.thread.start()

    def stop(self):
        self.evaluation.abort('camera_stopped')
        self.dota.camera_live = False
        self.dota.camera_timestamp_ms = None
        self.dota.disarm('Cámara detenida')
        with self.command_lock:
            self.stop_event.set()
            self.hub.reset()
            camera = self.camera
            if camera and camera.stream:
                try:
                    camera.stream.shutdown(2)
                except OSError:
                    pass
            if self.thread:
                self.thread.join(timeout=12)
                if self.thread.is_alive():
                    raise RuntimeError("La cámara sigue cerrándose; espera antes de reiniciar")
            self.set_state(status="stopped", message="Cámara detenida", pending=[], fps=0, sign="unknown", score=0, margin=0, error=None)

    def reconnect(self, facing=None):
        if facing is not None and facing not in {"back", "front"}:
            raise ValueError("Cámara inválida")
        self.stop()
        if facing:
            self.facing = facing
        self.start()

    def record(self, label):
        with self.record_lock:
            if self.recorder:
                raise ValueError("Detén la toma actual antes de iniciar otra")
            if self.state["status"] != "running":
                raise ValueError("Inicia la cámara antes de grabar")
            self.recorder = Recorder(self.root, label, self.facing, self.config["capture"]["target_fps"], self.last_config, self.config["capture"].get("capture_orientation_degrees",0))
            self.set_state(recording={"label": label, "path": str(self.recorder.path.relative_to(self.root))})

    def start_evaluation(self, mode='signs', rounds=2):
        if self.settings_event.is_set():
            raise ValueError('Espera a que se apliquen los ajustes antes de empezar la prueba')
        if self.state['status'] != 'running' or self.state['frames'] < 1:
            raise ValueError('Espera imágenes de cámara antes de evaluar')
        with self.record_lock:
            if self.recorder or self.evaluation.status == 'running':
                raise ValueError('Termina la toma o evaluación actual')
            self.dota.disarm('Evaluación en curso')
            self.evaluation.start(mode, rounds)
            try:
                self.recorder = Recorder(self.root, 'evaluation', self.facing, self.config['capture']['target_fps'], self.last_config, self.config['capture'].get('capture_orientation_degrees',0))
            except OSError:
                self.evaluation.abort('recording_failed')
                raise
            self.evaluation.video_clip = str(self.recorder.path.relative_to(self.root))
            self.recorder.meta['evaluation_report'] = str(self.evaluation.report_path.relative_to(self.root))
            self.set_state(recording={'label': 'evaluation', 'path': str(self.recorder.path.relative_to(self.root))})
            self.set_state(last_recipe=None, pending=[])
            self.cancel_event.set()

    def abort_evaluation(self):
        if self.evaluation.status != 'running':
            raise ValueError('No hay evaluación activa')
        self.evaluation.abort()
        self.finish_recording('evaluation_aborted')
        self.cancel_event.set()

    def close(self):
        try:
            self.stop()
        finally:
            with self.seal_condition:
                self.seal_closed = True
                self.seal_condition.notify_all()
            self.dota.close()

    def finish_recording(self, reason="manual"):
        with self.record_lock:
            path = self.recorder.close(reason) if self.recorder else None
            self.recorder = None
            self.set_state(recording=None, last_recording=path)
            return path

    def _capture(self, latest, failures):
        from .nvdec import NvDecoder
        decoder = None
        generation = 0
        try:
            for item in self.camera.messages():
                if self.stop_event.is_set():
                    break
                if isinstance(item, Session):
                    generation += 1
                    if generation > 1:self.evaluation.abort('camera_session_changed')
                    self.finish_recording("camera_session_changed")
                    self.last_config = None
                    latest.clear()
                    self.hub.reset()
                    decoder = NvDecoder(generation)
                    self.set_state(dimensions=[item.width, item.height])
                    continue
                self.hub.publish(item)
                with self.record_lock:
                    if item.config:
                        self.last_config = item.data
                    if self.recorder:
                        self.recorder.packet(item)
                if decoder is None:
                    raise RuntimeError("Paquete sin sesión scrcpy")
                for frame in decoder.decode(item):
                    latest.put(frame)
        except Exception as error:
            if not self.stop_event.is_set():
                failures.append(str(error))
        finally:
            self.hub.reset()

    def _run(self):
        from .gpu import NarutoCuda, choose_evidence
        latest = LatestFrame()
        failures = []
        producer = None
        self.trainer = Trainer(self.root / self.config["recipe_spec"], self.thresholds)
        try:
            model = NarutoCuda(self.root, backend=self.backend)
            from .landmarks import HandLandmarks
            hands_model = HandLandmarks(self.root) if self.config["vision"]["pose_branch_enabled"] else None
            last_pose_ms = -float("inf")
            self.poses.clear()
            if self.backend == "tensorrt" and not model.session.meta.get("parity_verified"):
                raise RuntimeError("Valida el engine con scripts/verify_tensorrt_parity.py antes de abrir la cámara")
            model.cp.cuda.Device(0).use()
            # Compile GPU kernels and warm up inference before opening the phone camera.
            dummy = model.cp.full((720, 1280, 3), 114, dtype=model.cp.uint8)
            model.cp.cuda.get_current_stream().synchronize()
            for _ in range(3):
                model.infer(dummy)
            if hands_model:
                hands_model.warmup(dummy)
            c = self.config["capture"]
            self.camera = ScrcpyCamera(self.root, c["adb_path"], self.serial, self.facing,
                                       c["target_fps"], f'{c["width"]}x{c["height"]}',
                                       orientation=c.get("capture_orientation_degrees",0))
            self.camera.start()
            producer = threading.Thread(target=self._capture, args=(latest, failures), name="jutsu-nvdec", daemon=True)
            producer.start()
            start = time.monotonic()
            cpu_start = time.process_time()
            window_start, window_frames = start, 0
            generation = None
            dota_generation = self.dota.context_generation
            gap_reported = False
            last_frame_ms = time.monotonic() * 1000
            self.set_state(status="running", message="Forma un sello frente a la cámara", started_ms=last_frame_ms,
                           freshness_note="Edad relativa de cola; no latencia absoluta del sensor")
            while not self.stop_event.is_set():
                if self.dota.context_generation != dota_generation:
                    dota_generation = self.dota.context_generation
                    self.emit([self.trainer.cancel('dota_context_changed')])
                    dota_generation = self.dota.context_generation
                if self.settings_event.is_set():
                    self.apply_settings()
                if failures:
                    raise RuntimeError(failures[0])
                frame = latest.take(.1)
                if self.stop_event.is_set():
                    break
                now = time.monotonic() * 1000
                evaluating = self.evaluation.status == 'running'
                phase_changed = self.evaluation.tick(now)
                if evaluating and self.evaluation.status != 'running':
                    self.finish_recording('evaluation_finished')
                    self.emit([self.trainer.cancel('evaluation_finished')])
                elif evaluating and phase_changed:
                    self.emit([self.trainer.cancel('evaluation_phase_changed')])
                    # Preparation/rest intentionally omit grammar updates; begin a new segment.
                    self.trainer.last_timestamp_ms = None
                if self.arm_reset_event.is_set():
                    self.emit([self.trainer.cancel('dota_armed')])
                    self.arm_reset_event.clear()
                if self.cancel_event.is_set():
                    self.emit([self.trainer.cancel()])
                    self.cancel_event.clear()
                if frame is None:
                    if generation is not None and now - last_frame_ms > self.thresholds.max_gap_ms:
                        self.emit(self.trainer.miss(now, "observation_gap"))
                        self.set_state(sign="unknown", score=0, margin=0, fps=0, rejection="observation_gap")
                        self.dota.camera_live = False
                        gap_reported = True
                    if now - last_frame_ms > 3000:
                        raise RuntimeError("La cámara no entrega imágenes; pulsa Reconectar")
                    if not producer.is_alive():
                        raise RuntimeError("El stream de cámara terminó; pulsa Reconectar")
                    continue
                last_frame_ms = now
                gap_reported = False
                if generation != frame.generation:
                    self.emit([self.trainer.cancel("camera_session_changed")])
                    generation = frame.generation
                age = now - frame.timestamp_ms
                if age > self.thresholds.max_age_ms:
                    self.emit(self.trainer.miss(now, "stale_or_nonvisual"))
                    self.set_state(rejection="stale_or_nonvisual", queue_age_ms=age, sign="unknown", score=0, margin=0)
                    self.dota.camera_live = False
                    self.evaluation.observe(frame.timestamp_ms, {'sign':'unknown','score':0,'margin':0}, [], stale=True)
                    continue
                tick = time.perf_counter()
                detections = model.infer(frame.image)
                evidence = choose_evidence(detections)
                refinement = None
                if self.config["vision"].get("tiger_refinement_enabled",False):
                    from .tiger_refinement import refine_tiger
                    evidence, refinement = refine_tiger(model, frame.image, detections,
                                                        minimum_score=self.config["vision"].get("tiger_refinement_min_score",.85))
                pose_ms = None
                if hands_model and self.config["vision"]["pose_diagnostic_hz"] > 0 and frame.timestamp_ms - last_pose_ms >= 1000/self.config["vision"]["pose_diagnostic_hz"]:
                    pose_tick = time.perf_counter()
                    hands = hands_model.infer(frame.image)
                    pose_ms = (time.perf_counter()-pose_tick)*1000
                    with self.lock:
                        self.poses.append({"pts_us":frame.pts_us,"timestamp_ms":frame.timestamp_ms,
                                           "hands":hands,"dimensions":[frame.image.shape[1],frame.image.shape[0]],
                                           "session":frame.generation})
                    last_pose_ms = frame.timestamp_ms
                processing = (time.perf_counter() - tick) * 1000
                now = time.monotonic() * 1000
                self.dota.camera_timestamp_ms = frame.timestamp_ms
                self.dota.camera_max_age_ms = self.thresholds.max_age_ms
                self.dota.camera_context_timeout_ms = self.thresholds.timeout_ms
                self.dota.camera_live = now-frame.timestamp_ms <= self.thresholds.max_age_ms
                measurement_phase = self.evaluation.locate(frame.timestamp_ms)[1] if self.evaluation.status == 'running' else None
                events = self.trainer.update(Observation(frame.timestamp_ms, **evidence), now) if self.evaluation.status != 'running' or measurement_phase == 'measure' else []
                self.evaluation.observe(frame.timestamp_ms, evidence, events, stale=now-frame.timestamp_ms > self.thresholds.max_age_ms,
                                        frame_meta={'pts_us': frame.pts_us, 'received_ms': frame.received_ms,
                                                    'processing_ms': processing, 'queue_age_ms': now-frame.timestamp_ms,
                                                    'detections': detections, 'tiger_refinement': refinement, 'capture_orientation_degrees': self.camera.orientation})
                if self.dota.context_generation != dota_generation:
                    events=[self.trainer.cancel('dota_context_changed')]
                    dota_generation=self.dota.context_generation
                for event in events:
                    if event['type'] in {'accepted','recipe'}:event['dota_context_generation']=dota_generation
                self.emit(events)
                self.timings.append(processing)
                window_frames += 1
                elapsed = time.monotonic() - start
                with self.lock:
                    self.state["frames"] += 1
                    self.state.update(evidence, accepted_sign=self.trainer.latched if self.trainer.latched==evidence['sign'] else None,
                                      detections=detections, tiger_refinement=refinement, processing_ms=processing, pose_processing_ms=pose_ms,
                                      transition_remaining_ms=max(0, self.thresholds.timeout_ms-(frame.timestamp_ms-self.trainer.last_activity_ms)) if self.trainer.last_activity_ms is not None else 0,
                                      queue_age_ms=now-frame.timestamp_ms, received_to_event_ms=now-frame.received_ms,
                                      last_frame_ms=now, dropped_decoded_frames=latest.dropped,
                                      cpu_logical_threads=(time.process_time()-cpu_start)/max(elapsed,.001),
                                      pending=self.trainer.pending.copy(), rejection=None if events and events[-1]["type"] in {"accepted","recipe"} else self.state.get("rejection"))
                if time.monotonic()-window_start >= 1:
                    import numpy as np
                    self.set_state(fps=window_frames/(time.monotonic()-window_start),
                                   processing_p95_ms=float(np.percentile(self.timings,95)))
                    window_start, window_frames = time.monotonic(), 0
                    (self.root / "runtime/live-state.json").write_text(json.dumps(self.snapshot(),ensure_ascii=False,indent=2)+"\n")
        except Exception as error:
            self.emit([self.trainer.cancel("camera_or_gpu_error")])
            self.set_state(status="error", message="No se pudo continuar", error=str(error), fps=0, pending=[])
        finally:
            self.evaluation.abort('camera_stopped')
            self.dota.camera_live = False
            self.dota.camera_timestamp_ms = None
            self.dota.disarm('Cámara detenida')
            self.stop_event.set()
            if self.camera:
                self.camera.close()
                self.camera = None
            if producer:
                producer.join(timeout=5)
            self.hub.reset()
            self.finish_recording("camera_stopped")
            self.emit([self.trainer.cancel("camera_stopped")])
            if self.state["status"] != "error":
                self.set_state(status="stopped", message="Cámara detenida", fps=0, pending=[], sign="unknown", score=0, margin=0)
            report = self.snapshot()
            report["absolute_camera_latency_measured"] = False
            report["personal_sign_accuracy_measured"] = False
            (self.root / "runtime/live-last-run.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
