"""
PCB Vision AI — FastAPI backend
Runs on Raspberry Pi 4 with Edge Impulse YOLO / object-detection model.
"""

from __future__ import annotations

import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Paths & config
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "inspections.db"
MODEL_PATH = Path(os.getenv("EI_MODEL_PATH", str(BASE_DIR / "model.eim")))
# Allow overriding from env so you can point to any .eim location

app = FastAPI(title="PCB Vision AI API", version="1.0.0")

# Allow browser access from any origin (Pi IP, localhost, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------
import sqlite3


def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                image_name TEXT,
                source TEXT,
                inference_ms REAL,
                decision TEXT,
                detections TEXT NOT NULL
            )
            """
        )
        conn.commit()


init_db()

# ---------------------------------------------------------------------------
# Edge Impulse runner (lazy load)
# ---------------------------------------------------------------------------
_runner = None
_model_info: dict[str, Any] = {}
_model_labels: list[str] = []
_model_error: Optional[str] = None


def load_model() -> bool:
    """Load the .eim model. Returns True on success."""
    global _runner, _model_info, _model_labels, _model_error
    if _runner is not None:
        return True
    if not MODEL_PATH.exists():
        _model_error = f"Model file not found: {MODEL_PATH}"
        return False
    try:
        from edge_impulse_linux.image import ImageImpulseRunner

        _runner = ImageImpulseRunner(str(MODEL_PATH))
        _model_info = _runner.init()
        # labels can live in different places depending on model type
        labels = (
            _model_info.get("model_parameters", {}).get("labels")
            or _model_info.get("labels")
            or []
        )
        _model_labels = list(labels) if labels else []
        _model_error = None
        print(f"[EI] Loaded model: {_model_info.get('project', {}).get('name', 'unknown')}")
        print(f"[EI] Labels: {_model_labels}")
        return True
    except Exception as exc:
        _model_error = str(exc)
        traceback.print_exc()
        _runner = None
        return False


# Colors for each class (BGR) — similar to Edge Impulse smartphone view
_BOX_COLORS = [
    (255, 120, 50),   # blue-ish
    (50, 180, 255),   # orange
    (80, 220, 220),   # yellow
    (80, 200, 80),    # green
    (200, 80, 200),   # purple
    (80, 80, 255),    # red
]


def run_inference_on_image(img_bgr: np.ndarray) -> dict[str, Any]:
    """
    Run Edge Impulse inference on an OpenCV BGR image.
    Returns detections, timing, and an annotated JPEG (base64) with boxes drawn.
    """
    import base64
    import cv2

    if not load_model() or _runner is None:
        raise RuntimeError(_model_error or "Model not loaded")

    orig_h, orig_w = img_bgr.shape[:2]
    img_rgb = img_bgr[:, :, ::-1].copy()

    features, cropped = _runner.get_features_from_image(img_rgb)
    t0 = time.perf_counter()
    res = _runner.classify(features)
    inference_ms = (time.perf_counter() - t0) * 1000.0

    # Cropped image size = model input space for bounding boxes
    if cropped is not None and hasattr(cropped, "shape"):
        crop_h, crop_w = cropped.shape[:2]
    else:
        # fallback from model parameters
        mp = _model_info.get("model_parameters", {})
        crop_w = int(mp.get("image_input_width") or mp.get("input_width") or orig_w)
        crop_h = int(mp.get("image_input_height") or mp.get("input_height") or orig_h)

    # Scale factors: model-space → original image
    # get_features_from_image typically letterbox/center-crops to square
    scale = min(orig_w / crop_w, orig_h / crop_h) if crop_w and crop_h else 1.0
    # If it was a center crop fit, boxes map with this scale and offset
    pad_x = (orig_w - crop_w * (orig_w / crop_w if crop_w else 1)) / 2  # simplified
    # Better: assume EI keeps aspect by fitting shortest side (common)
    sx = orig_w / crop_w if crop_w else 1.0
    sy = orig_h / crop_h if crop_h else 1.0

    detections = []
    result = res.get("result", {})

    if "bounding_boxes" in result:
        for i, bb in enumerate(result["bounding_boxes"]):
            # Boxes are in crop/model coordinates — map to original frame
            x = int(bb.get("x", 0) * sx)
            y = int(bb.get("y", 0) * sy)
            w = int(bb.get("width", 0) * sx)
            h = int(bb.get("height", 0) * sy)
            detections.append(
                {
                    "class_name": bb.get("label", "unknown"),
                    "confidence": float(bb.get("value", 0.0)),
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                }
            )
    elif "classification" in result:
        for label, score in result["classification"].items():
            if score >= 0.5:
                detections.append(
                    {
                        "class_name": label,
                        "confidence": float(score),
                        "x": 0,
                        "y": 0,
                        "width": 0,
                        "height": 0,
                    }
                )

    # Draw Edge-Impulse-style boxes — green for pcb_good, other colors for defects
    annotated = img_bgr.copy()
    GREEN = (80, 200, 80)
    for i, d in enumerate(detections):
        if d["width"] <= 0 or d["height"] <= 0:
            continue
        is_good = not is_defect_class(d["class_name"])
        color = GREEN if is_good else _BOX_COLORS[i % len(_BOX_COLORS)]
        x, y, w, h = d["x"], d["y"], d["width"], d["height"]
        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
        label = f"{d['class_name']} {d['confidence']:.0%}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        ty = max(y - 6, th + 4)
        cv2.rectangle(annotated, (x, ty - th - 6), (x + tw + 8, ty + 2), color, -1)
        cv2.putText(
            annotated,
            label,
            (x + 4, ty - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    # Banner using your trained labels (pcb_good = good, others = defect)
    decision = make_decision(detections)
    banner_color = GREEN if "DEFECT" not in decision else (80, 80, 255)
    cv2.rectangle(annotated, (0, 0), (orig_w, 36), (20, 20, 20), -1)
    cv2.putText(
        annotated,
        decision,
        (10, 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        banner_color,
        2,
        cv2.LINE_AA,
    )

    # Encode annotated image as JPEG base64 for the browser
    ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    annotated_b64 = base64.b64encode(buf).decode("ascii") if ok else None

    timing = res.get("timing", {})
    total_ms = float(timing.get("dsp", 0) + timing.get("classification", 0)) or inference_ms

    return {
        "detections": detections,
        "inference_ms": round(total_ms, 1),
        "annotated_jpeg_b64": annotated_b64,
        "image_width": orig_w,
        "image_height": orig_h,
        "raw_result": result,
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class Detection(BaseModel):
    class_name: str
    confidence: float = Field(ge=0, le=1)
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


class InspectionIn(BaseModel):
    image_name: str = "frame.jpg"
    source: str = "edge-impulse"
    inference_ms: float = 0
    detections: List[Detection] = []


# Classes that mean the board is GOOD (not a defect)
GOOD_CLASSES = {"pcb_good", "good", "ok", "pass", "no_defect"}

# Minimum confidence to trust a trained class
MIN_CONF = float(__import__("os").getenv("MIN_CONF", "0.45"))
# Below this = noise (ignore). Between NOISE and MIN_CONF with enough signal = Unknown_PCB
NOISE_CONF = float(__import__("os").getenv("NOISE_CONF", "0.22"))


def is_defect_class(name: str) -> bool:
    n = (name or "").strip().lower()
    return n not in GOOD_CLASSES and n not in ("unknown_pcb", "unknown")


def _det_fields(d):
    if hasattr(d, "class_name"):
        return d.class_name, float(getattr(d, "confidence", 0) or 0)
    if isinstance(d, dict):
        return d.get("class_name", ""), float(d.get("confidence", 0) or 0)
    return "", 0.0


def make_decision(detections: list) -> str:
    """
    Decision follows ONLY the SINGLE highest-confidence detection (major result).
    If both pcb_good and a defect (e.g. capacitor_missing) appear, the one with
    the higher confidence wins — no mixing of weaker boxes into the final call.
      - best is good class (pcb_good) and conf >= MIN_CONF → GOOD BOARD
      - best is Unknown_PCB / unknown → Unknown_PCB  (→ defect side)
      - best is a defect class and conf >= MIN_CONF → DEFECT DETECTED
      - best conf only mid-range → Unknown_PCB
      - else (empty / noise) → NO DEFECT DETECTED
    """
    best_name, best_conf = "", -1.0
    for d in detections or []:
        name, conf = _det_fields(d)
        if name and conf > best_conf:
            best_name, best_conf = name, conf

    if best_conf < NOISE_CONF or not best_name:
        return "NO DEFECT DETECTED"

    nlow = best_name.strip().lower()

    if best_conf < MIN_CONF:
        return "Unknown_PCB"

    if nlow in ("unknown_pcb", "unknown"):
        return "Unknown_PCB"
    if nlow in GOOD_CLASSES or not is_defect_class(best_name):
        return "GOOD BOARD"
    return "DEFECT DETECTED"


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "PCB Vision AI"}


@app.get("/api/edge/status")
def edge_status():
    """Real connection status to the Edge Impulse model on this device."""
    connected = load_model()
    project_name = "—"
    if connected and _model_info:
        project_name = _model_info.get("project", {}).get("name") or "loaded"
    labels = list(_model_labels or [])
    # Always expose Unknown_PCB on the dashboard label list
    if not any(str(x).lower() == "unknown_pcb" for x in labels):
        labels = labels + ["Unknown_PCB"]
    return {
        "connected": connected,
        "provider": "Edge Impulse",
        "model": project_name,
        "target": "Raspberry Pi 4",
        "model_path": str(MODEL_PATH),
        "labels": labels,
        "error": _model_error,
    }


@app.post("/api/inspections")
def create_inspection(item: InspectionIn):
    decision = make_decision(item.detections)
    ts = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO inspections
            (timestamp, image_name, source, inference_ms, decision, detections)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                item.image_name,
                item.source,
                item.inference_ms,
                decision,
                json.dumps([d.model_dump() for d in item.detections]),
            ),
        )
        iid = cur.lastrowid
        conn.commit()
    return {
        "id": iid,
        "timestamp": ts,
        **item.model_dump(),
        "decision": decision,
    }


@app.get("/api/inspections")
def list_inspections(limit: int = 100):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM inspections ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        {**dict(r), "detections": json.loads(r["detections"])} for r in rows
    ]


@app.get("/api/analytics")
def analytics():
    with get_db() as conn:
        rows = conn.execute("SELECT decision, detections FROM inspections").fetchall()
    total = len(rows)
    defective = sum(1 for r in rows if r["decision"] == "DEFECT DETECTED")
    good = sum(
        1
        for r in rows
        if r["decision"] in ("GOOD BOARD", "NO DEFECT DETECTED")
    )
    unknown = sum(
        1 for r in rows if "UNKNOWN" in str(r["decision"]).upper()
    )
    counts: dict[str, int] = {}
    for r in rows:
        for d in json.loads(r["detections"]):
            name = d.get("class_name", "unknown")
            counts[name] = counts.get(name, 0) + 1
    return {
        "total": total,
        "defective": defective,
        "good": good,
        "unknown": unknown,
        "defects": counts,
    }


@app.post("/api/infer")
async def infer_image(file: UploadFile = File(...)):
    """
    Accept an image from the browser (or camera snapshot),
    run Edge Impulse inference, store the result, and return it.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")

    try:
        import cv2
    except ImportError:
        raise HTTPException(500, "OpenCV not installed on this device")

    data = await file.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Could not decode image")

    try:
        result = run_inference_on_image(img)
    except Exception as exc:
        raise HTTPException(503, f"Inference failed: {exc}")

    # Persist
    detections = [Detection(**d) for d in result["detections"]]
    payload = InspectionIn(
        image_name=file.filename or "live_frame.jpg",
        source="edge-impulse-live",
        inference_ms=result["inference_ms"],
        detections=detections,
    )
    saved = create_inspection(payload)
    # Attach annotated image (not stored in DB) for live display
    saved["annotated_jpeg_b64"] = result.get("annotated_jpeg_b64")
    saved["image_width"] = result.get("image_width")
    saved["image_height"] = result.get("image_height")
    return saved


@app.post("/api/demo")
def demo_inspection():
    """Quick demo record (no model required) for UI testing."""
    sample = InspectionIn(
        image_name="demo_pcb.jpg",
        source="demo",
        inference_ms=42.0,
        detections=[
            Detection(class_name="IC_missing", confidence=0.95, x=114, y=89, width=71, height=137),
            Detection(class_name="Pins_missing", confidence=0.78, x=220, y=36, width=38, height=63),
            Detection(class_name="Component_missing", confidence=0.85, x=122, y=63, width=58, height=25),
        ],
    )
    return create_inspection(sample)


# ---------------------------------------------------------------------------
# Pi USB camera (OpenCV) — works without browser camera permission
# ---------------------------------------------------------------------------
_CAM_INDEX = int(os.getenv("CAMERA_INDEX", "0"))


def _open_camera():
    import cv2

    # Raspberry Pi USB cams need V4L2 backend
    for idx in (_CAM_INDEX, 0, 1, 2):
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            for _ in range(5):
                cap.read()
            return cap, idx
    return None, None


@app.get("/api/camera/status")
def camera_status():
    import cv2

    cap, idx = _open_camera()
    if cap is None:
        return {"ok": False, "index": None, "error": "No camera found"}
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return {"ok": False, "index": idx, "error": "Camera opened but no frame"}
    h, w = frame.shape[:2]
    return {"ok": True, "index": idx, "width": w, "height": h}


@app.get("/api/camera/snapshot")
def camera_snapshot():
    """Grab one frame from the Pi USB camera and return JPEG."""
    import cv2
    from fastapi.responses import Response

    cap, idx = _open_camera()
    if cap is None:
        raise HTTPException(503, "No camera found on Pi")
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise HTTPException(503, "Failed to capture frame")
    ok2, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok2:
        raise HTTPException(500, "JPEG encode failed")
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@app.post("/api/camera/infer")
def camera_infer():
    """
    Capture from Pi USB camera → real Edge Impulse model → annotated image + save.
    Single-shot path (also used if stream is not wanted).
    """
    import cv2

    cap, idx = _open_camera()
    if cap is None:
        raise HTTPException(503, "No camera found on Pi")
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise HTTPException(503, "Failed to capture frame")

    try:
        result = run_inference_on_image(frame)
    except Exception as exc:
        raise HTTPException(503, f"Inference failed: {exc}")

    detections = [Detection(**d) for d in result["detections"]]
    payload = InspectionIn(
        image_name="pi_camera_frame.jpg",
        source="edge-impulse-live",
        inference_ms=result["inference_ms"],
        detections=detections,
    )
    saved = create_inspection(payload)
    saved["annotated_jpeg_b64"] = result.get("annotated_jpeg_b64")
    saved["image_width"] = result.get("image_width")
    saved["image_height"] = result.get("image_height")
    saved["camera_index"] = idx
    _update_live_state(saved)
    # Drive conveyor pause + segregation + LCD from real model decision
    _trigger_hardware(saved.get("decision", ""), detections)
    return saved


# Shared state for continuous live stream (latest result for UI side panel)
_live_state: dict[str, Any] = {
    "running": False,
    "latest": None,
    "frame_count": 0,
}


def _update_live_state(saved: dict):
    _live_state["latest"] = {
        "detections": saved.get("detections", []),
        "inference_ms": saved.get("inference_ms"),
        "decision": saved.get("decision"),
        "source": saved.get("source"),
        "timestamp": saved.get("timestamp"),
        "id": saved.get("id"),
    }


@app.get("/api/camera/live-status")
def live_status():
    return {
        "running": _live_state["running"],
        "frame_count": _live_state["frame_count"],
        "latest": _live_state["latest"],
        "edge_impulse_studio": "https://studio.edgeimpulse.com/studio/1094555",
        "edge_impulse_live": "https://studio.edgeimpulse.com/studio/1094555/live",
        "edge_impulse_classifier": "https://smartphone.edgeimpulse.com/classifier.html",
    }


@app.get("/api/camera/live")
def camera_live_stream():
    """
    Continuous MJPEG stream: Pi camera → Edge Impulse every frame → boxes drawn live.
    Open in browser as <img src="/api/camera/live"> — detection is always on.
    """
    import cv2
    import time as _time
    from fastapi.responses import StreamingResponse

    load_model()
    if _runner is None:
        raise HTTPException(503, _model_error or "Model not loaded")

    def generate():
        _live_state["running"] = True
        _live_state["frame_count"] = 0
        try:
            from hardware import conveyor_start
            conveyor_start()
            print("[HW] Live detection started — conveyor ON")
        except Exception as e:
            print(f"[HW] conveyor start: {e}")
        cap, idx = _open_camera()
        if cap is None:
            _live_state["running"] = False
            try:
                from hardware import conveyor_stop
                conveyor_stop()
            except Exception:
                pass
            return

        # Infer every N frames to keep FPS usable on Pi 4 (adjust if needed)
        infer_every = int(os.getenv("INFER_EVERY", "2"))
        save_every = int(os.getenv("SAVE_EVERY", "15"))  # save to DB every N inferences
        frame_i = 0
        infer_i = 0
        last_annotated = None
        last_result = None

        try:
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    _time.sleep(0.05)
                    continue

                frame_i += 1
                _live_state["frame_count"] = frame_i

                if frame_i % infer_every == 0:
                    try:
                        result = run_inference_on_image(frame)
                        last_result = result
                        # Decode annotated jpeg back to BGR for stream
                        import base64
                        import numpy as np

                        b64 = result.get("annotated_jpeg_b64")
                        if b64:
                            raw = base64.b64decode(b64)
                            arr = np.frombuffer(raw, dtype=np.uint8)
                            last_annotated = cv2.imdecode(arr, cv2.IMREAD_COLOR)

                        infer_i += 1
                        detections = [Detection(**d) for d in result["detections"]]
                        # Update side-panel state every inference
                        preview = {
                            "detections": [d.model_dump() for d in detections],
                            "inference_ms": result["inference_ms"],
                            "decision": make_decision(detections),
                            "source": "edge-impulse-live",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "id": None,
                        }
                        _live_state["latest"] = preview

                        # While stopped in front of camera, collect frames for final decision
                        try:
                            from hardware import is_busy, push_inspection_sample
                            if is_busy():
                                push_inspection_sample(preview["decision"], detections)
                        except Exception as _hw_e:
                            print(f"[HW] sample: {_hw_e}")

                        # Periodically persist to history DB
                        if infer_i % save_every == 0:
                            payload = InspectionIn(
                                image_name="live_stream.jpg",
                                source="edge-impulse-live",
                                inference_ms=result["inference_ms"],
                                detections=detections,
                            )
                            saved = create_inspection(payload)
                            preview["id"] = saved.get("id")
                            _live_state["latest"] = preview

                        # First sight of board: start stop-and-inspect (decision after hold)
                        dec = preview["decision"]
                        if dec in ("DEFECT DETECTED", "GOOD BOARD", "Unknown_PCB"):
                            _trigger_hardware(dec, detections)
                    except Exception as exc:
                        print(f"[live] inference error: {exc}")

                out = last_annotated if last_annotated is not None else frame
                # HUD overlay
                ms = (last_result or {}).get("inference_ms", 0)
                n = len((last_result or {}).get("detections") or [])
                cv2.putText(
                    out,
                    f"LIVE  {ms:.0f} ms  |  {n} obj  |  frame {frame_i}",
                    (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (57, 216, 255),
                    2,
                    cv2.LINE_AA,
                )
                ok2, buf = cv2.imencode(".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if not ok2:
                    continue
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
                )
        finally:
            cap.release()
            _live_state["running"] = False
            try:
                from hardware import conveyor_stop
                conveyor_stop()
                print("[HW] Live detection stopped — conveyor OFF")
            except Exception as e:
                print(f"[HW] conveyor stop: {e}")

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


def _trigger_hardware(decision: str, detections: list) -> None:
    """
    Start stop-and-inspect only. Final segregation uses frames collected
    while the board is stopped (2nd+ samples), not this first moving-in detection.
    """
    try:
        from hardware import is_busy, on_inspection_result
        if is_busy():
            return
        on_inspection_result()
    except Exception as e:
        print(f"[HW] trigger skipped: {e}")


@app.get("/api/hardware/status")
def hardware_status():
    try:
        from hardware import is_busy, is_conveyor_running

        return {
            "conveyor_running": is_conveyor_running(),
            "busy": is_busy(),
            "pause_sec": float(__import__("os").getenv("PAUSE_SEC", "5.0")),
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/hardware/conveyor/start")
def hw_conveyor_start():
    from hardware import conveyor_start

    conveyor_start()
    return {"ok": True, "conveyor": "on"}


@app.post("/api/hardware/conveyor/stop")
def hw_conveyor_stop():
    from hardware import conveyor_stop

    conveyor_stop()
    return {"ok": True, "conveyor": "off"}


@app.post("/api/hardware/test/good")
def hw_test_good():
    """Manual test: LCD GOOD + slide left."""
    from hardware import on_inspection_result

    on_inspection_result(is_defect=False, label_summary="TEST pcb_good")
    return {"ok": True, "action": "good / left"}


@app.post("/api/hardware/test/defect")
def hw_test_defect():
    """Manual test: LCD DEFECT + slide right."""
    from hardware import on_inspection_result

    on_inspection_result(is_defect=True, label_summary="TEST defect")
    return {"ok": True, "action": "defect / right"}


@app.on_event("startup")
def on_startup():
    print("[PCB Vision AI] Starting…")
    print(f"[PCB Vision AI] Model path: {MODEL_PATH}")
    if MODEL_PATH.exists():
        ok = load_model()
        print(f"[PCB Vision AI] Model load: {'OK' if ok else 'FAILED — ' + str(_model_error)}")
    else:
        print("[PCB Vision AI] No model.eim found — place your Edge Impulse .eim here")
        print("                 or set EI_MODEL_PATH=/path/to/your.eim")
    print(f"[PCB Vision AI] Camera index default: {_CAM_INDEX}")
    print("[PCB Vision AI] Live stream: GET /api/camera/live")
    try:
        from hardware import init_hardware, conveyor_stop

        hw = init_hardware()
        print(f"[PCB Vision AI] Hardware: {hw}")
        # Conveyor stays OFF until Live Detection is started
        conveyor_stop()
        print("[PCB Vision AI] Conveyor OFF — start Live Detection to run belt")
    except Exception as e:
        print(f"[PCB Vision AI] Hardware init skipped: {e}")


@app.on_event("shutdown")
def on_shutdown():
    try:
        from hardware import shutdown

        shutdown()
    except Exception:
        pass
