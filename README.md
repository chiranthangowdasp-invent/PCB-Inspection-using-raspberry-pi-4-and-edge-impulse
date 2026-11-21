# PCB Vision AI — Full Project Package

**Edge-AI PCB defect detection + conveyor segregation on Raspberry Pi 4**

Team 13 · RV Institute of Technology and Management · ECE  
Edge Impulse Project: **https://studio.edgeimpulse.com/studio/1094555**

---

## What this system does

1. USB camera on the Pi captures the board on a conveyor  
2. Edge Impulse object-detection model (`.eim`) runs on the Pi  
3. Decision: **GOOD BOARD** / **DEFECT DETECTED** / **Unknown_PCB** (by highest confidence)  
4. Conveyor pauses ~5 s → LCD shows result → segregation motor sorts to good/defect bin  
5. React web dashboard: Live Inspection, History, Analytics, Project Report  

---

## Package contents

```
pcb-vision-ai/
├── README.md                 ← this file
├── CONNECTIONS.md            ← full GPIO / LCD / motor wiring
├── SETUP_PI.md               ← step-by-step install & run
├── HARDWARE_WIRING.md        ← short pin reference
├── backend/
│   ├── main.py               ← FastAPI + Edge Impulse + live stream
│   ├── hardware.py           ← motors + LCD
│   ├── model.eim             ← deployed Edge Impulse model (~22 MB)
│   ├── requirements.txt
│   └── test_model.py
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/main.jsx, styles.css
├── docs/                     ← paper / PPT if included
└── scripts/                  ← optional start scripts
```

---

## Quick start (Raspberry Pi 4, 64-bit OS)

```bash
# 1) Backend
cd ~/pcb-vision-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x model.eim
uvicorn main:app --host 0.0.0.0 --port 8000

# 2) Frontend (other terminal)
cd ~/pcb-vision-ai/frontend
npm install
npm run dev
```

Browser: `http://localhost:5173` or `http://<pi-ip>:5173`  
→ **Live Inspection** → **Start live detection**

---

## Defaults (env overrides)

| Variable | Default | Meaning |
|----------|---------|---------|
| CONV_SPEED | 25 | Conveyor PWM % (needs EN1→pin 11) |
| SEG_PULSE_SEC | 6.5 | Segregation motor run time |
| SEG_SPEED | 100 | Segregation PWM % |
| PAUSE_SEC | 5 | Conveyor pause on detection |
| MIN_CONF | 0.45 | Trust trained class |
| NOISE_CONF | 0.22 | Ignore weaker noise |
| CAMERA_INDEX | 0 | USB camera index |

---

## Decision logic

- Highest-confidence detection wins  
- Strong **pcb_good** → GOOD → left bin  
- Strong **defect** → DEFECT → right bin  
- Mid confidence only → **Unknown_PCB** → defect side  
- Empty belt → no motor action  

---

## Docs

- **CONNECTIONS.md** — LCD, L293D, power  
- **SETUP_PI.md** — libraries, commands, troubleshooting  
- **docs/** — IEEE paper / review materials when present  

