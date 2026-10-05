"""Download pinned public ONNX weights; verify Git blob identity before saving."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = "Kazuhito00/NARUTO-HandSignDetection"
REVISION = "07f4d3231f43f97cbd37653c793825f1dbc94d0e"
FILES = {
    "model/yolox/yolox_nano.onnx": (3610160, "41ba540d4281d07182dc10dff264efc90a13266d"),
    "setting/labels.csv": (237, "1a4e1747e1bc42e90615d4ec6cecd61f19ff8f3c"),
    "LICENSE": (1074, "26a63bd74038f12bd6e3af1eb46057faaa55c347"),
}


def main() -> None:
    destination = ROOT / "modelos/pesos/naruto-yolox"
    destination.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for path, (size, blob_sha1) in FILES.items():
        url = f"https://raw.githubusercontent.com/{REPO}/{REVISION}/{path}"
        target = destination / Path(path).name
        data = target.read_bytes() if target.exists() else urllib.request.urlopen(url, timeout=60).read()
        actual_blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        if len(data) != size or actual_blob != blob_sha1:
            raise RuntimeError(f"Integrity check failed: {path}; remove corrupt file before retrying")
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
        artifacts.append({"file": str(target.relative_to(ROOT)), "url": url,
                          "bytes": len(data), "git_blob_sha1": actual_blob,
                          "sha256": hashlib.sha256(data).hexdigest()})
    rows = list(csv.reader(io.StringIO((destination / "labels.csv").read_text(encoding="utf-8-sig"))))
    labels = [row[0] for row in rows[1:]]  # Upstream demo explicitly uses class_id + 1.
    manifest = {
        "schema_version": 1, "repository": f"https://github.com/{REPO}",
        "revision": REVISION, "repository_license": "MIT", "artifacts": artifacts,
        "input": {"shape": [1, 3, 416, 416], "dtype": "float32", "color": "BGR",
                  "range": [0, 255], "padding": 114, "padding_anchor": "top_left",
                  "resize": "bilinear_uint8", "normalization": "none"},
        # Actual graph has 16 score channels; upstream CSV names only the first 15.
        # Never alias the unnamed channel to a target seal.
        "output": {"shape": [1, 3549, 21], "format": "raw_yolox", "classes": labels + ["unmapped_15"],
                   "unmapped_class_ids": [15]},
        "label_csv_offset": 1,
        "class_mapping": {"2": "tiger", "5": "snake", "6": "horse", "8": "monkey"},
        "preprocessing_source": f"https://github.com/{REPO}/blob/{REVISION}/model/yolox/yolox_onnx.py",
        "label_offset_source": f"https://github.com/{REPO}/blob/{REVISION}/simple_demo.py",
        "dataset": "private; public weights; no personal accuracy measured",
    }
    output = ROOT / "modelos/manifiesto-naruto.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Verified {len(artifacts)} artifacts; manifest: {output}")


if __name__ == "__main__":
    main()
