"""CUDA reference backend for the pinned Naruto YOLOX, with device I/O binding."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

# Match upstream BGR uint8 resize, top-left padding=114, CHW float32 [0,255].
RESIZE_KERNEL = r'''
extern "C" __global__ void letterbox(const unsigned char* image, float* out,
    int h, int w, int rh, int rw) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i >= 3 * 416 * 416) return;
    int c = i / (416 * 416), y = (i / 416) % 416, x = i % 416;
    if (y >= rh || x >= rw) { out[i] = 114.f; return; }
    float fx = (x + .5f) * w / rw - .5f;
    float fy = (y + .5f) * h / rh - .5f;
    fx = fmaxf(0.f, fx); fy = fmaxf(0.f, fy);
    int x0 = min((int)floorf(fx), w-1), y0 = min((int)floorf(fy), h-1);
    int x1 = min(x0+1, w-1), y1 = min(y0+1, h-1);
    float ax = fx-x0, ay = fy-y0;
    float a = image[(y0*w+x0)*3+c], b = image[(y0*w+x1)*3+c];
    float d = image[(y1*w+x0)*3+c], e = image[(y1*w+x1)*3+c];
    out[i] = floorf((a+(b-a)*ax)*(1-ay)+(d+(e-d)*ax)*ay+.5f);
}
'''

NMS_KERNEL = r'''
extern "C" __global__ void nms(const float* boxes, const int* order,
    int count, float threshold, int* keep, int* n_kept) {
    if (threadIdx.x || blockIdx.x) return;
    int n = 0;
    for (int k = 0; k < count && n < 64; ++k) {
        int i = order[k]; bool rejected = false;
        for (int p = 0; p < n; ++p) {
            int j = keep[p];
            float iw = fmaxf(0.f, fminf(boxes[4*i+2],boxes[4*j+2])-fmaxf(boxes[4*i],boxes[4*j])+1.f);
            float ih = fmaxf(0.f, fminf(boxes[4*i+3],boxes[4*j+3])-fmaxf(boxes[4*i+1],boxes[4*j+1])+1.f);
            float ai = (boxes[4*i+2]-boxes[4*i]+1.f)*(boxes[4*i+3]-boxes[4*i+1]+1.f);
            float aj = (boxes[4*j+2]-boxes[4*j]+1.f)*(boxes[4*j+3]-boxes[4*j+1]+1.f);
            if (iw*ih / fmaxf(ai+aj-iw*ih, 1e-6f) > threshold) { rejected = true; break; }
        }
        if (!rejected) keep[n++] = i;
    }
    *n_kept = n;
}
'''


class NarutoCuda:
    def __init__(self, root: Path, profile: bool = False, backend: str = "onnxruntime"):
        import onnxruntime as ort
        ort.preload_dlls(directory="")
        import cupy as cp
        self.cp = cp
        self.root = root
        self.backend = backend
        self.manifest = json.loads((root / "modelos/manifiesto-naruto.json").read_text())
        for artifact in self.manifest["artifacts"]:
            if hashlib.sha256((root / artifact["file"]).read_bytes()).hexdigest() != artifact["sha256"]:
                raise RuntimeError(f"Artifact hash mismatch: {artifact['file']}")
        self.labels = self.manifest["output"]["classes"]
        self.mapping = self.manifest["class_mapping"]
        if backend == "onnxruntime" and "CUDAExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("CUDAExecutionProvider unavailable; CPU fallback is disabled")
        self.stream = cp.cuda.Stream(non_blocking=True)
        options = ort.SessionOptions()
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.enable_profiling = profile
        options.profile_file_prefix = str(root / "runtime/ort-naruto")
        if backend == "tensorrt":
            from .tensorrt_backend import TensorRTSession
            self.session = TensorRTSession(root, self.stream)
        elif backend == "onnxruntime":
            self.session = ort.InferenceSession(
            str(root / "modelos/pesos/naruto-yolox/yolox_nano.onnx"), sess_options=options,
            providers=[("CUDAExecutionProvider", {
                "device_id": "0", "user_compute_stream": str(self.stream.ptr),
                "gpu_mem_limit": str(256 * 1024 * 1024), "arena_extend_strategy": "kSameAsRequested",
                "cudnn_conv_algo_search": "HEURISTIC", "cudnn_conv_use_max_workspace": "0",
                "use_tf32": "0",
            })],
            )
        else:
            raise ValueError(f"Unknown inference backend: {backend}")
        self.session.disable_fallback()
        self.input_meta = self.session.get_inputs()[0]
        self.output_meta = self.session.get_outputs()[0]
        if self.input_meta.shape != [1, 3, 416, 416] or self.output_meta.shape != [1, 3549, 21]:
            raise RuntimeError(f"Unexpected model shapes: {self.input_meta.shape}, {self.output_meta.shape}")
        self.resize_kernel = cp.RawKernel(RESIZE_KERNEL, "letterbox")
        self.nms_kernel = cp.RawKernel(NMS_KERNEL, "nms")
        with self.stream:
            self.input = cp.empty((1, 3, 416, 416), dtype=cp.float32)
            self.output = cp.empty((1, 3549, 21), dtype=cp.float32)
            grids, strides = [], []
            for stride in [8, 16, 32]:
                yy, xx = cp.meshgrid(cp.arange(416 // stride), cp.arange(416 // stride), indexing="ij")
                grids.append(cp.stack([xx, yy], axis=-1).reshape(-1, 2))
                strides.append(cp.full((xx.size, 1), stride, dtype=cp.float32))
            self.grid = cp.concatenate(grids).astype(cp.float32)
            self.strides = cp.concatenate(strides)
        self.stream.synchronize()
        self.binding = self.session.io_binding()
        self.binding.bind_input(self.input_meta.name, "cuda", 0, np.float32, self.input.shape, self.input.data.ptr)
        self.binding.bind_output(self.output_meta.name, "cuda", 0, np.float32, self.output.shape, self.output.data.ptr)

    def preprocess(self, image):
        cp = self.cp
        if not isinstance(image, cp.ndarray) or image.dtype != cp.uint8 or image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Expected CUDA HWC uint8 BGR frame; host images are diagnostic inputs only")
        if image.device.id != 0 or not image.flags.c_contiguous:
            raise ValueError("Expected contiguous CUDA:0 frame")
        h, w = image.shape[:2]
        if h < 1 or w < 1:
            raise ValueError("Empty frame")
        ratio = min(416 / h, 416 / w)
        rh, rw = int(h * ratio), int(w * ratio)
        if rh < 1 or rw < 1:
            raise ValueError("Unsupported image aspect ratio")
        count = 3 * 416 * 416
        with self.stream:
            self.resize_kernel(((count + 255) // 256,), (256,), (image, self.input, h, w, rh, rw))
        return ratio

    def infer(self, image, score_threshold: float = 0.3) -> list[dict]:
        """Caller must make producer CUDA work visible before passing the frame."""
        cp = self.cp
        ratio = self.preprocess(image)
        with self.stream:
            self.session.run_with_iobinding(self.binding)
            pred = self.output[0]
            scores = pred[:, 4:5] * pred[:, 5:]
            ids = cp.argmax(scores, axis=1)
            best = cp.max(scores, axis=1)
            second = cp.partition(scores, -2, axis=1)[:, -2]
            center = (pred[:, :2] + self.grid) * self.strides
            size = cp.exp(pred[:, 2:4]) * self.strides
            boxes = cp.ascontiguousarray(cp.concatenate([center - size / 2, center + size / 2], axis=1) / ratio)
            # NMS on all anchors: no top-k truncation of possible competitors.
            order = cp.ascontiguousarray(cp.argsort(best)[::-1].astype(cp.int32))
            count = int(cp.count_nonzero(best >= score_threshold).item())
            keep = cp.empty(64, dtype=cp.int32)
            n_kept = cp.zeros(1, dtype=cp.int32)
            self.nms_kernel((1,), (1,), (boxes, order, count, np.float32(.45), keep, n_kept))
            n = int(n_kept.item())
            selected = keep[:n]
            selected_boxes = boxes[selected].copy()
            h, w = image.shape[:2]
            selected_boxes[:, [0, 2]] = cp.clip(selected_boxes[:, [0, 2]], 0, w)
            selected_boxes[:, [1, 3]] = cp.clip(selected_boxes[:, [1, 3]], 0, h)
            meta = cp.concatenate([selected_boxes, best[selected, None], ids[selected, None],
                                   (best - second)[selected, None]], axis=1)
            host = meta.get(stream=self.stream)
        return [{"box": row[:4].tolist(), "score": float(row[4]), "class_id": int(row[5]),
                 "source_label": self.labels[int(row[5])], "sign": self.mapping.get(str(int(row[5])), "unknown"),
                 "margin": float(row[6])} for row in host]

    def finish_profile(self) -> dict:
        if self.backend == "tensorrt":
            return self.session.profile_information()
        path = Path(self.session.end_profiling())
        entries = json.loads(path.read_text())
        nodes = [entry for entry in entries if entry.get("cat") == "Node" and entry.get("args", {}).get("provider")]
        providers = sorted({entry["args"]["provider"] for entry in nodes})
        if not nodes or providers != ["CUDAExecutionProvider"]:
            raise RuntimeError(f"GPU profile verification failed: {providers}")
        return {"file": str(path.relative_to(self.root)), "node_events": len(nodes), "providers": providers}


def choose_evidence(detections: list[dict]) -> dict:
    if not detections:
        return {"sign": "unknown", "score": 0.0, "margin": 0.0}
    best = detections[0]
    # Scores are objectness*class confidence, not calibrated probabilities.
    # A competing box can make a confident local prediction ambiguous globally.
    competing = [d["score"] for d in detections[1:] if d["class_id"] != best["class_id"]]
    margin = min(best["margin"], max(0.0, best["score"] - max(competing, default=0.0)))
    return {"sign": best["sign"], "score": best["score"], "margin": margin}
