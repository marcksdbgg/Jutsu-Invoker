"""Prepare five verified local audio excerpts; source media is not distributed."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = 'https://www.myinstants.com/media/sounds/ytmp3free_BaQB7oM.mp3'
SOURCE_SHA256 = '48bfb43d5565b4c00786e42af280d769faacca52b80512ec7be8cd1400f41642'
RATE = 48000
SEGMENTS = [
    ('monkey', .474, .730),
    ('tiger', .730, 1.084),
    ('horse', 1.084, 1.292),
    ('snake', 1.292, 1.528),
    ('confirm', 1.528, 2.143125),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Existing MP3; must match the pinned source hash')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'src/jutsu_invoker/web/audio')
    args = parser.parse_args()
    if not shutil.which('ffmpeg'):
        parser.error('Install FFmpeg before preparing audio')
    source = args.source or ROOT / 'referencias/audio/naruto-hand-signs-source.mp3'
    data = source.read_bytes() if source.exists() else urllib.request.urlopen(SOURCE_URL, timeout=60).read()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError('Source hash mismatch; no audio assets were changed')
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(data)
    decoded = subprocess.check_output([
        'ffmpeg', '-v', 'error', '-i', str(source), '-ac', '1', '-ar', str(RATE),
        '-f', 'f32le', 'pipe:1',
    ])
    samples = np.frombuffer(decoded, dtype='<f4')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    # Prepare every excerpt before replacing any existing local asset.
    with tempfile.TemporaryDirectory() as directory:
        for tick, (pose, start, end) in enumerate(SEGMENTS, 1):
            clip = samples[round(start * RATE):round(end * RATE)].copy()
            expected = round(end * RATE) - round(start * RATE)
            if len(clip) != expected or not np.isfinite(clip).all() or np.max(np.abs(clip)) == 0:
                raise ValueError(f'Invalid audio segment: {pose}')
            clip *= .75 / float(np.max(np.abs(clip)))
            fade_in = round(.003 * RATE)
            fade_out = round((.018 if pose == 'confirm' else .006) * RATE)
            clip[:fade_in] *= np.linspace(0, 1, fade_in)
            clip[-fade_out:] *= np.linspace(1, 0, fade_out)
            name = f'naruto-{pose}.wav'
            output = Path(directory) / name
            with wave.open(str(output), 'wb') as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(RATE)
                writer.writeframes(np.rint(clip * 32767).astype('<i2').tobytes())
            records.append({'pose': pose, 'source_tick': tick, 'duration_ms': len(clip) / RATE * 1000,
                            'sha256': hashlib.sha256(output.read_bytes()).hexdigest()})
        for pose, _, _ in SEGMENTS:
            name = f'naruto-{pose}.wav'
            shutil.copyfile(Path(directory) / name, args.output_dir / name)
    default_output = ROOT / 'src/jutsu_invoker/web/audio'
    report = (ROOT / 'runtime/audio-cuts-validation.json' if args.output_dir == default_output
              else args.output_dir / 'audio-cuts-validation.json')
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({'source_sha256': SOURCE_SHA256, 'sample_rate': RATE,
                                 'segments': records}, indent=2) + '\n')
    print(f'Prepared {len(records)} local excerpts in {args.output_dir}')


if __name__ == '__main__':
    main()
