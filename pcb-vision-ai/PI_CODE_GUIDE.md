# Raspberry Pi 4 — Complete Code Guide

All code that runs **on the Pi** is inside the `pcb-vision-ai` folder.

```
pcb-vision-ai/
├── backend/                    ← Python (runs on Pi)
│   ├── main.py                 ← FastAPI server + Edge Impulse inference
│   ├── test_model.py           ← Standalone camera test (no web needed)
│   ├── requirements.txt
│   └── model.eim               ← YOUR trained model (22 MB)
├── frontend/                   ← React dashboard (runs on Pi, opens in browser)
│   ├── src/main.jsx
│   ├── src/styles.css
│   ├── package.json
│   └── vite.config.js
└── scripts/
    ├── start-backend.sh
    └── start-frontend.sh
```

---

## Part A — Test the model alone (recommended first)

This proves your `.eim` works on the Pi **before** starting the website.

```bash
cd ~/pcb-vision-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# make model executable
chmod +x model.eim

# test with live camera (press Q to quit)
python test_model.py

# OR test with a photo
python test_model.py /home/pi/test_pcb.jpg
```

You should see labels and bounding boxes drawn on the camera window.

---

## Part B — Full web platform (dashboard + history)

### Terminal 1 — Backend (AI + database)

```bash
cd ~/pcb-vision-ai/backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

Look for: `Model load: OK`

### Terminal 2 — Frontend (website)

```bash
cd ~/pcb-vision-ai/frontend
npm install          # only first time
npm run dev
```

Open browser: `http://<PI_IP>:5173`

---

## What each file does on the Pi

| File | Role |
|------|------|
| `backend/main.py` | Loads `model.eim`, runs inference when browser sends a photo, saves results to SQLite, serves REST API |
| `backend/test_model.py` | Simple camera loop – no browser, no database – pure Edge Impulse test |
| `backend/model.eim` | Your trained PCB defect detector (object detection) |
| `backend/requirements.txt` | `fastapi`, `uvicorn`, `edge-impulse-linux`, `opencv`, `numpy` |
| `frontend/src/main.jsx` | Dashboard UI: live camera, Run Edge detection button, history table, analytics |
| `frontend/src/styles.css` | Dark industrial theme (no more black empty panels) |
| `frontend/vite.config.js` | Proxies `/api` → backend so it works from any PC on the network |

---

## API endpoints (all run on Pi port 8000)

| Method | URL | What it does |
|--------|-----|--------------|
| GET | `/api/health` | Server alive? |
| GET | `/api/edge/status` | Is model loaded? Labels? |
| POST | `/api/infer` | Send JPEG → run Edge Impulse → save + return result |
| POST | `/api/demo` | Fake inspection (UI test) |
| GET | `/api/inspections` | History list |
| GET | `/api/analytics` | Totals + defect counts |

---

## One-line start scripts

```bash
# backend
bash ~/pcb-vision-ai/scripts/start-backend.sh

# frontend (other terminal)
bash ~/pcb-vision-ai/scripts/start-frontend.sh
```
