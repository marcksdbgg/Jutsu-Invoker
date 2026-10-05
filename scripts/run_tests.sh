#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
"$project_dir/.venv/bin/python" -m unittest discover -s tests -v
node --test tests/test_preview.cjs tests/sound.test.js
