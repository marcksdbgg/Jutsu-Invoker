"""Exercise scrcpy → NVDEC → owned CUDA tensor on the connected Android."""
import json
from pathlib import Path
import time
import tomllib

from jutsu_invoker.camera import ScrcpyCamera, Session
from jutsu_invoker.nvdec import NvDecoder

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = tomllib.loads((ROOT / 'config/desarrollo-gpu.toml').read_text())
    camera = ScrcpyCamera(ROOT, config['capture']['adb_path'], fps=30)
    decoder = None
    frames, packets, first_pts, last_pts = 0, 0, None, None
    times = []
    try:
        camera.start()
        start = time.monotonic()
        for item in camera.messages():
            if isinstance(item, Session):
                decoder = NvDecoder(1)
                dimensions = [item.width, item.height]
                continue
            packets += 1
            tick = time.perf_counter()
            for frame in decoder.decode(item):
                frames += 1
                last_pts = frame.pts_us
                if first_pts is None:
                    first_pts = last_pts
                assert frame.image.device.id == 0
                assert frame.image.flags.c_contiguous
            times.append((time.perf_counter() - tick) * 1000)
            if time.monotonic() - start >= 10:
                break
    finally:
        camera.close()
    if frames < 100:
        raise RuntimeError(f"Insufficient decoded frames: {frames}")
    import numpy as np
    report = {"status": "passed", "frames": frames, "packets": packets, "dimensions": dimensions,
              "fps_measured": (frames - 1) * 1e6 / (last_pts - first_pts), "decoder": "NVDEC PyNvVideoCodec 2.2.3",
              "output": "owned contiguous BGR uint8 CUDA:0", "decode_and_color_p95_ms": float(np.percentile(times, 95)),
              "absolute_camera_latency_measured": False, "images_copied_to_host": False}
    (ROOT / "runtime/smoke-nvdec.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
