"""Install the verified scrcpy 4.1 server locally, without modifying system packages."""
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = "4.1"
SHA256 = "deacb991ed2509715160ffdc7907e47b4160eb30d1566217e9047fd5b8850cae"


def main():
    target = ROOT / "runtime/tools/scrcpy-server-v4.1"
    target.parent.mkdir(parents=True, exist_ok=True)
    data = target.read_bytes() if target.exists() else urllib.request.urlopen(
        f"https://github.com/Genymobile/scrcpy/releases/download/v{VERSION}/scrcpy-server-v{VERSION}", timeout=60
    ).read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("scrcpy server integrity check failed")
    target.write_bytes(data)
    print(target)


if __name__ == "__main__":
    main()
