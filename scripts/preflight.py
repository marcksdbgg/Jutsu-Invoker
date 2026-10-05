"""Inspect requirements without installing packages or starting a camera."""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def command(args: list[str]) -> dict:
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=10)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"returncode": None, "error": str(error)}


def package(module: str, distribution: str) -> dict:
    present = importlib.util.find_spec(module) is not None
    try:
        version = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {"present_in_current_python": present, "version": version}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save JSON report; relative to project root")
    args = parser.parse_args()
    config = tomllib.loads((ROOT / "config/desarrollo-gpu.toml").read_text())
    packages = {
        module: package(module, distribution)
        for module, distribution in [
            ("torch", "torch"),
            ("onnxruntime", "onnxruntime-gpu"),
            ("tensorrt", "tensorrt-cu12"),
            ("PyNvVideoCodec", "PyNvVideoCodec"),
            ("cupy", "cupy-cuda12x"),
            ("onnx", "onnx"),
        ]
    }
    binaries = {name: shutil.which(name) for name in ["nvidia-smi", "ffmpeg", "scrcpy"]}
    adb = Path(config["capture"]["adb_path"])
    binaries["adb"] = str(adb) if adb.is_file() else shutil.which("adb")
    gpu = command([
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader",
    ]) if binaries["nvidia-smi"] else {"error": "nvidia-smi not found"}
    hwaccels = command(["ffmpeg", "-hide_banner", "-hwaccels"]) if binaries["ffmpeg"] else {"error": "ffmpeg not found"}
    decoders = command(["ffmpeg", "-hide_banner", "-decoders"]) if binaries["ffmpeg"] else {"error": "ffmpeg not found"}
    ffmpeg_decoder_names = [
        line.strip() for line in decoders.get("stdout", "").splitlines()
        if "h264_cuvid" in line or "hevc_cuvid" in line
    ]
    required_modules = ["onnxruntime", "cupy", "tensorrt", "PyNvVideoCodec"]
    pending = [f"Install/verify {module} in isolated environment" for module in required_modules if not packages[module]["present_in_current_python"]]
    server = ROOT / "runtime/tools/scrcpy-server-v4.1"
    binaries["scrcpy_server"] = str(server) if server.is_file() else None
    if not server.is_file():
        pending.append("Run scripts/download_scrcpy.py for the pinned official server")
    pending.extend([
        "Evaluate pretrained Naruto RGB on independent personal sessions before deciding to train",
        "Measure ten-minute thermal stability and concurrent Dota performance",
    ])
    report = {
        "status": "inspection_only_runtime_not_validated",
        "project_root": str(ROOT),
        "python": {"version": sys.version.split()[0], "executable": sys.executable},
        "binaries": binaries,
        "gpu_query": gpu,
        "ffmpeg_hwaccels": hwaccels.get("stdout", ""),
        "ffmpeg_decoder_entries": ffmpeg_decoder_names,
        "packages": packages,
        "gpu_policy": config["compute"],
        "pending": pending,
        "camera_started": False,
        "gpu_inference_tested": False,
        "hardware_video_decode_tested": False,
        "dota_modified": False,
        "existing_evidence_reports": {
            name: str(ROOT / "runtime" / name)
            for name in ["smoke-naruto-cuda.json", "paridad-naruto.json", "smoke-nvdec.json", "smoke-tensorrt.json", "paridad-tensorrt.json", "live-validation.json"]
            if (ROOT / "runtime" / name).exists()
        },
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized)
    print(serialized, end="")


if __name__ == "__main__":
    main()
