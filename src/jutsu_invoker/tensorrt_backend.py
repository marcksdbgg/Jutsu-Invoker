"""Direct TensorRT inference. Engines are keyed to model, GPU and runtime."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace


def identity(model: Path, precision: str = "fp32") -> dict:
    import cupy as cp
    import tensorrt as trt
    props = cp.cuda.runtime.getDeviceProperties(0)
    return {"model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(), "precision": precision,
            "tensorrt": trt.__version__, "gpu": props["name"].decode(),
            "compute_capability": [props["major"], props["minor"]],
            "input_shape": [1, 3, 416, 416], "output_shape": [1, 3549, 21]}


def engine_paths(root: Path, precision: str = "fp32"):
    model = root / "modelos/pesos/naruto-yolox/yolox_nano.onnx"
    spec = identity(model, precision)
    key = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:20]
    path = root / "runtime/engines" / f"naruto-{precision}-{key}.engine"
    return model, spec, path


def build_engine(root: Path, precision: str = "fp32") -> dict:
    import onnxruntime as ort
    ort.preload_dlls(directory="")
    import tensorrt as trt
    model, spec, path = engine_paths(root, precision)
    if path.exists() and path.with_suffix(".json").exists():
        meta = json.loads(path.with_suffix(".json").read_text())
        if meta.get("identity") == spec and hashlib.sha256(path.read_bytes()).hexdigest() == meta.get("engine_sha256"):
            return meta
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.STRONGLY_TYPED))
    parser = trt.OnnxParser(network, logger)
    if precision != "fp32":
        raise ValueError("Only validated FP32 engines are currently supported")
    if not parser.parse(model.read_bytes()):
        raise RuntimeError("TensorRT ONNX parser: " + "; ".join(str(parser.get_error(i)) for i in range(parser.num_errors)))
    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 256 * 1024 * 1024)
    config.clear_flag(trt.BuilderFlag.TF32)
    config.profiling_verbosity = trt.ProfilingVerbosity.DETAILED
    config.builder_optimization_level = 3
    serialized = builder.build_serialized_network(network, config)
    if serialized is None:
        raise RuntimeError("TensorRT could not build engine; no runtime fallback is selected")
    data = bytes(serialized)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)
    meta = {"identity": spec, "engine_sha256": hashlib.sha256(data).hexdigest(),
            "engine": str(path.relative_to(root)), "bytes": len(data), "parity_verified": False}
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


class Binding:
    def __init__(self, session):
        self.session = session

    def bind_input(self, name, device, device_id, dtype, shape, pointer):
        self._bind(name, device, device_id, shape, pointer)

    bind_output = bind_input

    def _bind(self, name, device, device_id, shape, pointer):
        if device != "cuda" or device_id != 0 or tuple(self.session.engine.get_tensor_shape(name)) != tuple(shape):
            raise ValueError("TensorRT binding must use the expected CUDA:0 tensor")
        if not self.session.context.set_tensor_address(name, pointer):
            raise RuntimeError(f"Failed to bind TensorRT tensor {name}")


class TensorRTSession:
    def __init__(self, root: Path, stream, precision: str = "fp32"):
        import tensorrt as trt
        model, spec, path = engine_paths(root, precision)
        if not path.exists() or not path.with_suffix(".json").exists():
            raise RuntimeError("Engine absent: run jutsu-invoker build-engine before starting the camera")
        self.meta = json.loads(path.with_suffix(".json").read_text())
        if self.meta.get("identity") != spec or hashlib.sha256(path.read_bytes()).hexdigest() != self.meta.get("engine_sha256"):
            raise RuntimeError("TensorRT engine identity or hash mismatch; rebuild it")
        self.stream = stream
        self.logger = trt.Logger(trt.Logger.WARNING)
        self.runtime = trt.Runtime(self.logger)
        self.engine = self.runtime.deserialize_cuda_engine(path.read_bytes())
        if self.engine is None:
            raise RuntimeError("TensorRT engine could not be loaded")
        self.context = self.engine.create_execution_context()
        if self.context is None:
            raise RuntimeError("TensorRT execution context could not be created")
        inputs, outputs = [], []
        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            tensor = SimpleNamespace(name=name, shape=list(self.engine.get_tensor_shape(name)))
            if self.engine.get_tensor_dtype(name) != trt.float32:
                raise RuntimeError("Expected FP32 external I/O")
            (inputs if self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT else outputs).append(tensor)
        self.inputs, self.outputs = inputs, outputs

    def get_inputs(self):
        return self.inputs

    def get_outputs(self):
        return self.outputs

    def disable_fallback(self):
        pass  # Direct TensorRT has no CPU execution provider.

    def io_binding(self):
        return Binding(self)

    def run_with_iobinding(self, binding):
        if not self.context.execute_async_v3(stream_handle=self.stream.ptr):
            raise RuntimeError("TensorRT GPU execution failed")

    def profile_information(self):
        return {"providers": ["TensorRT_GPU"], "engine": self.meta["engine"],
                "engine_sha256": self.meta["engine_sha256"], "precision": "fp32"}
