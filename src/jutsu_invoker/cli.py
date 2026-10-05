"""Entrenador Android en vivo, diagnósticos CUDA y replay de observaciones."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
import signal
import threading

from .recognition import Observation, Thresholds, Trainer

ROOT = Path(__file__).resolve().parents[2]


def write_report(report: dict, output: Path | None) -> None:
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized)
    print(serialized, end="")


def image_or_smoke(args) -> None:
    import cv2
    import numpy as np
    from .gpu import NarutoCuda, choose_evidence
    model = NarutoCuda(ROOT, profile=True, backend=args.backend)
    cp = model.cp
    if args.command == "image":
        host = cv2.imread(str(args.path))
        if host is None:
            raise ValueError(f"Image could not be loaded: {args.path}")
    else:
        host = np.random.default_rng(42).integers(0, 256, (720, 1280, 3), dtype=np.uint8)
    image = cp.asarray(host)  # Explicit diagnostic upload; never used as a live video decoder.
    cp.cuda.get_current_stream().synchronize()
    detections = model.infer(image)
    ratio = min(416 / host.shape[0], 416 / host.shape[1])
    rh, rw = int(host.shape[0] * ratio), int(host.shape[1] * ratio)
    expected = np.full((416, 416, 3), 114, dtype=np.uint8)
    expected[:rh, :rw] = cv2.resize(host, (rw, rh), interpolation=cv2.INTER_LINEAR)
    expected = expected.transpose(2, 0, 1)[None].astype(np.float32)
    model.stream.synchronize()
    difference = np.abs(cp.asnumpy(model.input) - expected)
    preprocessing = {"max_abs_error": float(difference.max()), "mean_abs_error": float(difference.mean()),
                     "tolerance": 1.0, "reference": "OpenCV bilinear uint8 BGR"}
    if preprocessing["max_abs_error"] > 1:
        raise RuntimeError(f"Preprocessing parity failed: {preprocessing}")
    for _ in range(10):
        model.infer(image)
    samples = []
    for _ in range(args.iterations):
        start = time.perf_counter()
        model.infer(image)
        samples.append((time.perf_counter() - start) * 1000)
    profile = model.finish_profile()
    props = cp.cuda.runtime.getDeviceProperties(0)
    report = {
        "status": "gpu_reference_smoke_passed", "backend": args.backend + "_cuda_fp32",
        "gpu": props["name"].decode(), "input_shape": model.input_meta.shape,
        "output_shape": model.output_meta.shape, "preprocessing": preprocessing,
        "profile": profile, "iterations": args.iterations,
        "latency_ms": {f"p{p}": float(np.percentile(samples, p)) for p in [50, 95, 99]},
        "measurement": "same diagnostic image; preprocessing+network+NMS+small host metadata; " + ("ORT profiling enabled" if args.backend == "onnxruntime" else "direct TensorRT FP32"),
        "detections": detections, "evidence": choose_evidence(detections),
        "accuracy_measured": False, "camera_tested": False, "nvdec_tested": False,
        "tensorrt_tested": args.backend == "tensorrt", "dota_running_benchmark": False, "game_input_sent": False,
    }
    write_report(report, args.output)


def replay(args) -> None:
    import tomllib
    from .live import thresholds_from_config
    thresholds = thresholds_from_config(tomllib.loads((ROOT/'config/desarrollo-gpu.toml').read_text()))
    trainer = Trainer(ROOT / "diseno/mapa-recetas.json", thresholds)
    confirmed = 0
    with args.path.open() as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                now = row.pop("now_ms", row.get("timestamp_ms"))
                if row.pop("cancel", False):
                    events = [trainer.cancel()]
                else:
                    events = trainer.update(Observation(**row), now)
            except (ValueError, TypeError) as error:
                raise ValueError(f"Invalid replay row {number}: {error}") from error
            for event in events:
                print(json.dumps(event, ensure_ascii=False))
                confirmed += event["type"] == "recipe"
    print(json.dumps({"type": "summary", "recipes": confirmed, "pending": trainer.pending,
                      "thresholds": asdict(thresholds), "source": "replay_not_camera",
                      "game_input_sent": False}, ensure_ascii=False))


def live(args) -> None:
    from .live import LiveTrainer
    from .server import TrainerServer
    options = dict(backend=args.backend, facing=args.camera, serial=args.serial, dota_enabled=args.dota and not args.headless)
    stopped = threading.Event()
    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, lambda *_: stopped.set())
    server = None
    if args.headless:
        app = LiveTrainer(ROOT, **options)
    else:
        server = TrainerServer(ROOT, port=args.port, **options)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"Entrenador: http://127.0.0.1:{server.server_address[1]} · Ctrl+C para cerrar", flush=True)
        app = server.app
    try:
        app.start()
        start = time.monotonic()
        while not stopped.wait(.2):
            state = app.snapshot()
            if args.headless and state["status"] == "error":
                raise RuntimeError(state["error"])
            if args.duration and time.monotonic() - start >= args.duration:
                break
    finally:
        app.stop()
        if server:
            server.shutdown()
            server.server_close()
        else:
            app.dota.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    if args.headless or args.duration:
        write_report(app.snapshot(), args.output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["smoke", "image"]:
        p = sub.add_parser(name)
        if name == "image":
            p.add_argument("path", type=Path)
        p.add_argument("--iterations", type=int, default=30)
        p.add_argument("--output", type=Path)
        p.add_argument("--backend", choices=["onnxruntime", "tensorrt"], default="onnxruntime")
    sub.add_parser("build-engine")
    p = sub.add_parser('install-dota')
    p.add_argument('--game-dir', type=Path, required=True)
    p.add_argument('--bindings', type=Path, required=True)
    p = sub.add_parser("cameras")
    p.add_argument("--serial")
    p = sub.add_parser("live")
    p.add_argument("--port", type=int, default=32147)
    p.add_argument("--backend", choices=["onnxruntime", "tensorrt"])
    p.add_argument("--camera", choices=["front", "back"])
    p.add_argument("--serial")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--dota", action="store_true", help="Enable local GSI and incremental orb/Invoke integration")
    p.add_argument("--duration", type=float)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("replay")
    p.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command in {"smoke", "image"} and args.iterations < 1:
        parser.error("--iterations must be positive")
    if args.command == "live" and (args.duration is not None and args.duration <= 0 or not 0 <= args.port <= 65535):
        parser.error("--duration debe ser positivo y --port válido")
    try:
        if args.command == 'install-dota':
            from .dota import install_gsi
            write_report(install_gsi(ROOT,args.game_dir,args.bindings),None)
        elif args.command == "live":
            live(args)
        elif args.command == "cameras":
            import tomllib
            from .camera import ScrcpyCamera
            config = tomllib.loads((ROOT / "config/desarrollo-gpu.toml").read_text())
            print(ScrcpyCamera(ROOT, config["capture"]["adb_path"], args.serial).list_modes())
        elif args.command == "build-engine":
            from .tensorrt_backend import build_engine
            write_report(build_engine(ROOT), None)
        elif args.command == "replay":
            replay(args)
        else:
            image_or_smoke(args)
    except (RuntimeError, ValueError, ImportError, OSError) as error:
        print(f"Jutsu Invoker: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
