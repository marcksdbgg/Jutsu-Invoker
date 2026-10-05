"""Explicit offline CPU reference vs CUDA diagnostics; never a runtime fallback."""
import json
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from jutsu_invoker.gpu import NarutoCuda

ROOT = Path(__file__).resolve().parents[1]


def cpu_nms(raw, ratio, image_shape):
    grids, strides = [], []
    for stride in [8, 16, 32]:
        xx, yy = np.meshgrid(np.arange(416 // stride), np.arange(416 // stride))
        grids.append(np.stack([xx, yy], axis=-1).reshape(-1, 2))
        strides.append(np.full((xx.size, 1), stride, dtype=np.float32))
    center = (raw[:, :2] + np.concatenate(grids)) * np.concatenate(strides)
    size = np.exp(raw[:, 2:4]) * np.concatenate(strides)
    boxes = np.concatenate([center - size / 2, center + size / 2], axis=1) / ratio
    scores = raw[:, 4:5] * raw[:, 5:]
    classes = scores.argmax(axis=1)
    best = scores.max(axis=1)
    order = np.argsort(best)[::-1]
    order = order[best[order] >= .3]
    keep = []
    while len(order) and len(keep) < 64:
        index = order[0]
        keep.append(index)
        other = order[1:]
        intersection = np.maximum(0, np.minimum(boxes[index, 2:], boxes[other, 2:]) -
                                  np.maximum(boxes[index, :2], boxes[other, :2]) + 1).prod(axis=1)
        area = (boxes[index, 2:] - boxes[index, :2] + 1).prod()
        other_area = (boxes[other, 2:] - boxes[other, :2] + 1).prod(axis=1)
        iou = intersection / np.maximum(area + other_area - intersection, 1e-6)
        order = other[iou <= .45]
    boxes = boxes[keep].copy()
    h, w = image_shape[:2]
    boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, w)
    boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, h)
    return classes[keep], best[keep], boxes


def main():
    model = NarutoCuda(ROOT)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    reference = ort.InferenceSession(str(ROOT / "modelos/pesos/naruto-yolox/yolox_nano.onnx"),
                                    sess_options=options, providers=["CPUExecutionProvider"])
    checks = []
    for label, image in [
        ("synthetic_720p", np.random.default_rng(42).integers(0, 256, (720, 1280, 3), dtype=np.uint8)),
        ("reference_sheet_not_accuracy_dataset", cv2.imread(str(ROOT / "referencias/sellos-naruto.png"))),
    ]:
        if image is None:
            raise RuntimeError("Missing diagnostic image")
        device_image = model.cp.asarray(image)
        model.cp.cuda.get_current_stream().synchronize()
        detections = model.infer(device_image)
        model.stream.synchronize()
        actual = model.cp.asnumpy(model.output)
        # Exact same preprocessed tensor: isolates network arithmetic from resize differences.
        expected = reference.run(None, {reference.get_inputs()[0].name: model.cp.asnumpy(model.input)})[0]
        np.testing.assert_allclose(actual, expected, atol=2e-4, rtol=2e-4)
        ratio = min(416 / image.shape[0], 416 / image.shape[1])
        ids, scores, boxes = cpu_nms(actual[0], ratio, image.shape)
        np.testing.assert_array_equal([d["class_id"] for d in detections], ids)
        if len(ids):
            np.testing.assert_allclose([d["score"] for d in detections], scores, atol=1e-6)
            np.testing.assert_allclose([d["box"] for d in detections], boxes, atol=1e-3)
        checks.append({"input": label, "raw_max_abs_error": float(np.abs(actual - expected).max()),
                       "detections": len(detections), "nms_class_and_box_parity": True})
    # The source CSV is missing the last channel. It must remain an unknown class.
    assert len(model.labels) == 16 and "15" not in model.mapping
    report = {"status": "passed", "checks": checks, "network_atol": 2e-4, "network_rtol": 2e-4,
              "nms_box_atol": 1e-3, "purpose": "offline_reference_only", "accuracy_measured": False}
    output = ROOT / "runtime/paridad-naruto.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
