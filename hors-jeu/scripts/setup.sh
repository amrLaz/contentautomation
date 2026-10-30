#!/usr/bin/env bash
# One-time setup for hors-jeu: a Python environment and the player detector (YOLOX-S, 36 MB, ONNX).
set -e
cd "$(dirname "$0")/.."
if ! command -v ffmpeg >/dev/null 2>&1; then echo "NEED_FFMPEG: install ffmpeg first"; exit 1; fi
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; .venv/bin/python -m pip install -q --upgrade pip; .venv/bin/python -m pip install -q numpy opencv-python pillow scipy; fi
mkdir -p models
if [ ! -s models/yolox.onnx ]; then
  echo "Downloading the player detector (36 MB)..."
  curl -sS -L --fail -o models/yolox.onnx https://huggingface.co/opencv/object_detection_yolox/resolve/main/object_detection_yolox_2022nov.onnx \
    || { echo "NEED_NETWORK: allow huggingface.co and *.hf.co in the network settings"; rm -f models/yolox.onnx; exit 1; }
fi
.venv/bin/python -c "import cv2, numpy, PIL, scipy; print('READY')"
