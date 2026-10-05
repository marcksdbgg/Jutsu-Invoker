"""Version-pinned scrcpy 4.1 protocol, USB camera transport and NVDEC producer."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import threading
import time

VERSION = "4.1"
SERVER_SHA256 = "deacb991ed2509715160ffdc7907e47b4160eb30d1566217e9047fd5b8850cae"
PTS_MASK = (1 << 61) - 1
MAX_PACKET_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class Session:
    width: int
    height: int


@dataclass(frozen=True)
class Packet:
    pts_us: int
    data: bytes
    config: bool
    keyframe: bool
    received_ms: float


def read_exact(stream, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = stream.recv(length - len(data))
        if not chunk:
            raise EOFError("Cámara desconectada: stream cerrado")
        data.extend(chunk)
    return bytes(data)


def read_message(stream) -> Session | Packet:
    header = read_exact(stream, 12)
    if header[0] & 0x80:
        flags, width, height = struct.unpack(">III", header)
        if flags & 0x7FFFFFFE or not (0 < width <= 8192 and 0 < height <= 8192):
            raise ValueError("Metadatos de sesión scrcpy inválidos")
        return Session(width, height)
    flags, size = struct.unpack(">QI", header)
    if not 0 < size <= MAX_PACKET_BYTES:
        raise ValueError("Tamaño de paquete scrcpy inválido")
    data = read_exact(stream, size)
    return Packet(flags & PTS_MASK, data, bool(flags & (1 << 62)), bool(flags & (1 << 61)),
                  time.monotonic() * 1000)


def authorized_devices(adb: str) -> list[str]:
    result = subprocess.run([adb, "devices"], capture_output=True, text=True, check=True, timeout=10)
    return [line.split()[0] for line in result.stdout.splitlines()[1:]
            if len(line.split()) >= 2 and line.split()[1] == "device"]


class ScrcpyCamera:
    def __init__(self, root: Path, adb: str, serial: str | None = None,
                 facing: str = "back", fps: int = 30, size: str = "1280x720", orientation: int = 0):
        if type(orientation) is not int or orientation not in {0,90,180,270}:
            raise ValueError("Orientación de cámara inválida")
        self.orientation = orientation
        self.root, self.adb = root, adb
        devices = authorized_devices(adb)
        if serial is None:
            if len(devices) != 1:
                raise RuntimeError("Conecta un Android autorizado o selecciona --serial")
            serial = devices[0]
        elif serial not in devices:
            raise RuntimeError("El Android seleccionado no está conectado y autorizado")
        self.serial = serial
        self.facing, self.fps, self.size = facing, fps, size
        self.port = None
        self.process = None
        self.stream = None
        self.log = None
        self.scid = f"{secrets.randbits(31):08x}"

    def adb_command(self, *args, **kwargs):
        return subprocess.run([self.adb, "-s", self.serial, *args], capture_output=True, text=True,
                              check=True, timeout=15, **kwargs)

    def prepare(self):
        server = self.root / "runtime/tools/scrcpy-server-v4.1"
        if not server.exists() or hashlib.sha256(server.read_bytes()).hexdigest() != SERVER_SHA256:
            raise RuntimeError("Ejecuta scripts/download_scrcpy.py para instalar el servidor verificado")
        self.remote = f"/data/local/tmp/jutsu-scrcpy-{self.scid}.jar"
        self.adb_command("push", str(server), self.remote)

    def list_modes(self) -> str:
        self.prepare()
        try:
            result = self.adb_command("shell", f"CLASSPATH={self.remote}", "app_process", "/",
                                      "com.genymobile.scrcpy.Server", VERSION, "list_cameras=true",
                                      "list_camera_sizes=true", "audio=false", "control=false")
            return result.stdout + result.stderr
        finally:
            self.adb_command("shell", "rm", "-f", self.remote)

    def start(self):
        self.prepare()
        try:
            self.port = int(self.adb_command("forward", "tcp:0", f"localabstract:scrcpy_{self.scid}").stdout.strip())
            directory = self.root / "runtime/logs"
            directory.mkdir(parents=True, exist_ok=True)
            self.log_path = directory / f"scrcpy-{self.scid}.log"
            self.log = self.log_path.open("w")
            command = [self.adb, "-s", self.serial, "shell", f"CLASSPATH={self.remote}", "app_process", "/",
                       "com.genymobile.scrcpy.Server", VERSION, f"scid={self.scid}", "log_level=info",
                       "tunnel_forward=true", "audio=false", "control=false", "cleanup=false",
                       "video_source=camera", f"camera_facing={self.facing}", f"camera_size={self.size}",
                       f"camera_fps={self.fps}", f"capture_orientation={self.orientation}", "video_codec=h264", "video_bit_rate=4000000",
                       "video_codec_options=profile:int=1,level:int=512,max-bframes:int=0,i-frame-interval:int=1", "send_device_meta=false"]
            self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(self.log_path.read_text()[-2000:])
                candidate = None
                try:
                    candidate = socket.create_connection(("127.0.0.1", self.port), timeout=1)
                    candidate.settimeout(3)
                    if read_exact(candidate, 1) != b"\0":
                        raise ValueError("Handshake scrcpy inválido")
                    if read_exact(candidate, 4) != b"h264":
                        raise ValueError("El stream no utiliza H264")
                    self.stream = candidate
                    self.stream.settimeout(3)
                    return self
                except (OSError, EOFError):
                    if candidate:
                        candidate.close()
                    time.sleep(.1)
                except ValueError:
                    candidate.close()
                    raise
            raise RuntimeError(f"Timeout de cámara; revisa {self.log_path}")
        except BaseException:
            self.close()
            raise

    def messages(self):
        while True:
            yield read_message(self.stream)

    def close(self):
        if self.stream is not None:
            try:
                self.stream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.stream.close()
            self.stream = None
        if self.process is not None:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process = None
        if self.port is not None:
            try:
                self.adb_command("forward", "--remove", f"tcp:{self.port}")
            except (OSError, subprocess.SubprocessError):
                pass
            self.port = None
        if self.log:
            self.log.close()
            self.log = None
        if hasattr(self, "remote"):
            try:
                self.adb_command("shell", "rm", "-f", self.remote)
            except (OSError, subprocess.SubprocessError):
                pass


@dataclass
class CameraFrame:
    image: object  # An owned, contiguous CuPy BGR tensor.
    pts_us: int
    timestamp_ms: float
    received_ms: float
    decoded_ms: float
    generation: int


class LatestFrame:
    """One pending decoded frame; encoded packets are never skipped."""
    def __init__(self):
        self.condition = threading.Condition()
        self.frame = None
        self.dropped = 0

    def put(self, frame):
        with self.condition:
            if self.frame is not None:
                self.dropped += 1
            self.frame = frame
            self.condition.notify()

    def take(self, timeout=.2):
        with self.condition:
            self.condition.wait_for(lambda: self.frame is not None, timeout=timeout)
            frame, self.frame = self.frame, None
            return frame

    def clear(self):
        with self.condition:
            self.frame = None
