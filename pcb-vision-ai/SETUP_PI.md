# Setup guide — run on another Raspberry Pi / system

## Requirements

- Raspberry Pi 4 (recommended), **64-bit** Raspberry Pi OS  
- USB camera  
- Node.js 18+ (for frontend)  
- Python 3.9+  

---

## 1. Copy project

From Windows (PowerShell), example:

```powershell
scp -r .\pcb-vision-ai pi@PI_IP:~/
```

Or unzip the full package on the Pi:

```bash
cd ~
unzip -o PCB_Vision_AI_FULL_PACKAGE.zip
```

---

## 2. System packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip libatlas-base-dev libopenjp2-7 \
  libportaudio2 portaudio19-dev
```

Install Node.js 20 if needed:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

---

## 3. Backend

```bash
cd ~/pcb-vision-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
chmod +x model.eim

# Optional tuning
export CONV_SPEED=25
export SEG_PULSE_SEC=6.5
export PAUSE_SEC=5

uvicorn main:app --host 0.0.0.0 --port 8000
```

Expect:

```text
Model load: OK
[HW] L293D ready
[HW] Parallel LCD ready
```

If model error: `chmod +x model.eim`  
If `edge_impulse_linux` missing: `pip install edge-impulse-linux six`

---

## 4. Frontend

```bash
cd ~/pcb-vision-ai/frontend
npm install
npm run dev -- --host 0.0.0.0
```

Open: `http://PI_IP:5173`

---

## 5. Use

1. Wire hardware per **CONNECTIONS.md**  
2. Start backend + frontend  
3. Dashboard → confirm model **connected** and labels list  
4. **Live Inspection** → **Start live detection** (conveyor ON)  
5. Place PCB under camera → pause → LCD → sort → resume  
6. **Stop live detection** → conveyor OFF  

---

## 6. API tests

```bash
curl -s http://127.0.0.1:8000/api/edge/status
curl -X POST http://127.0.0.1:8000/api/hardware/conveyor/start
curl -X POST http://127.0.0.1:8000/api/hardware/test/good
curl -X POST http://127.0.0.1:8000/api/hardware/test/defect
```

---

## 7. RealVNC (no HDMI)

```bash
sudo raspi-config   # Interface Options → VNC → Enable
hostname -I
```

On laptop: RealVNC Viewer → Pi IP.

---

## 8. Troubleshooting

| Issue | Fix |
|-------|-----|
| Model not executable | `chmod +x model.eim` |
| No module edge_impulse_linux | Activate venv, `pip install edge-impulse-linux` |
| Camera fail | `CAMERA_INDEX=0`, try USB port, `ls /dev/video*` |
| LCD blank | Contrast pot, 5V/GND, check pins 31–40 |
| Belt full speed | Wire **EN1 to pin 11**, set CONV_SPEED |
| Wrong sort side | Swap segregation motor wires |

