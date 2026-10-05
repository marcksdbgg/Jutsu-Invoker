"""NVDEC decoding of complete H264 packets, retaining images on CUDA."""
from __future__ import annotations

import time
import numpy as np

from .camera import CameraFrame, Packet


class PtsMapper:
    """Relative PTS alignment: measures queue growth, not absolute camera delay."""
    def __init__(self):
        self.offset_ms = None
        self.last_pts = None

    def map(self, pts_us: int, received_ms: float) -> float:
        if pts_us < 0 or (self.last_pts is not None and pts_us <= self.last_pts):
            raise ValueError("El reloj de cámara retrocedió; reinicia la sesión")
        self.last_pts = pts_us
        observed_offset = received_ms - pts_us / 1000
        self.offset_ms = observed_offset if self.offset_ms is None else min(self.offset_ms, observed_offset)
        return pts_us / 1000 + self.offset_ms


class NvDecoder:
    def __init__(self, generation: int):
        import onnxruntime as ort
        ort.preload_dlls(directory="")
        import cupy as cp
        import PyNvVideoCodec as nvc
        self.cp, self.nvc = cp, nvc
        self.stream = cp.cuda.Stream(non_blocking=True)
        self.decoder = nvc.CreateDecoder(
            gpuid=0, codec=nvc.cudaVideoCodec.H264, usedevicememory=True,
            cudastream=self.stream.ptr, outputColorType=nvc.OutputColorType.RGB,
            latency=nvc.DisplayDecodeLatencyType.LOW,
        )
        self.generation = generation
        self.mapper = PtsMapper()
        self.metadata = {}

    def decode(self, packet: Packet) -> list[CameraFrame]:
        nvc, cp = self.nvc, self.cp
        compressed = np.frombuffer(packet.data, dtype=np.uint8)
        data = nvc.PacketData()
        data.bsl_data = compressed.ctypes.data
        data.bsl = compressed.size
        data.pts = packet.pts_us
        data.key = int(packet.keyframe)
        data.decode_flag = 0 if packet.config else int(nvc.VideoPacketFlag.TIMESTAMP) | int(nvc.VideoPacketFlag.ENDOFPICTURE)
        if not packet.config:
            self.metadata[packet.pts_us] = (self.mapper.map(packet.pts_us, packet.received_ms), packet.received_ms)
            if len(self.metadata) > 16:
                raise RuntimeError("NVDEC acumula demasiados frames; reinicia la cámara")
        frames = self.decoder.Decode(data)
        self.decoder.SyncOnCUStream()
        result = []
        for frame in frames:
            pts = frame.getPTS()
            if pts not in self.metadata:
                raise RuntimeError("NVDEC devolvió una imagen sin timestamp válido")
            stamp, received = self.metadata.pop(pts)
            if frame.__dlpack_device__() != (2, 0):
                raise RuntimeError("NVDEC no entregó memoria CUDA:0; no hay fallback CPU")
            with self.stream:
                rgb = cp.from_dlpack(frame)
                if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != cp.uint8:
                    raise RuntimeError("Formato RGB inesperado de NVDEC")
                # Owned GPU copy: the decoder may recycle its original surface on the next packet.
                image = cp.ascontiguousarray(rgb[:, :, ::-1])
                self.stream.synchronize()
            result.append(CameraFrame(image, pts, stamp, received, time.monotonic() * 1000, self.generation))
        return result
