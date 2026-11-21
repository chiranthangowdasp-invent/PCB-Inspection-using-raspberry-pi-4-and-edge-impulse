#!/bin/bash
cd "$(dirname "$0")/../backend"
source .venv/bin/activate
chmod +x model.eim 2>/dev/null
export CONV_SPEED="${CONV_SPEED:-25}"
export SEG_PULSE_SEC="${SEG_PULSE_SEC:-6.5}"
uvicorn main:app --host 0.0.0.0 --port 8000
