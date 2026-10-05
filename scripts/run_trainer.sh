#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
# Reuse the existing Android SDK when platform-tools is outside PATH.
if ! command -v adb >/dev/null 2>&1; then
  jutsu_android_sdk="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}}"
  if [[ -x "$jutsu_android_sdk/platform-tools/adb" ]]; then
    export PATH="$jutsu_android_sdk/platform-tools:$PATH"
  fi
fi
exec "$project_dir/.venv/bin/python" -m jutsu_invoker.cli live "$@"
