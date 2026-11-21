"""
Hardware: conveyor + segregation + parallel LCD

Conveyor speed: PWM on L293D Enable pin (EN1).
  Wire L293D EN1 -> Pi physical pin 11 (default).
  CONV_SPEED = 0-100 (default 95)

LCD: thread-safe writes + clear/blank to avoid mixed/garbage characters.
Segregation decision uses major (highest) confidence; Unknown → defect side.
"""

from __future__ import annotations

import os
import threading
import time

# LCD BOARD pins
LCD_RS = int(os.getenv("LCD_RS", "40"))
LCD_E = int(os.getenv("LCD_E", "38"))
LCD_D4 = int(os.getenv("LCD_D4", "31"))
LCD_D5 = int(os.getenv("LCD_D5", "33"))
LCD_D6 = int(os.getenv("LCD_D6", "35"))
LCD_D7 = int(os.getenv("LCD_D7", "37"))

# L293D direction
CONV_A = int(os.getenv("CONV_A", "13"))
CONV_B = int(os.getenv("CONV_B", "15"))
SEG_A = int(os.getenv("SEG_A", "16"))
SEG_B = int(os.getenv("SEG_B", "18"))

# L293D Enable (PWM speed) — WIRE EN1 to this pin
CONV_EN = int(os.getenv("CONV_EN", "11"))   # physical pin 11
SEG_EN = int(os.getenv("SEG_EN", "12"))     # physical pin 12 (optional)

# Speed 0-100  (lower = slower). Default 95
CONV_SPEED = int(os.getenv("CONV_SPEED", "95"))
SEG_SPEED = int(os.getenv("SEG_SPEED", "100"))

PAUSE_SEC = float(os.getenv("PAUSE_SEC", "5.0"))
SEG_PULSE_SEC = float(os.getenv("SEG_PULSE_SEC", "6.0"))
COOLDOWN_SEC = float(os.getenv("COOLDOWN_SEC", "3.0"))

_gpio_ok = False
_lcd = None
_lcd_lock = threading.Lock()
_lock = threading.Lock()
_conveyor_running = False
_busy = False
_cooldown_until = 0.0
_seg_side = None
_pwm_conv = None
_pwm_seg = None


def init_hardware() -> dict:
    global _gpio_ok, _lcd, _seg_side, _pwm_conv, _pwm_seg
    _seg_side = None
    try:
        import RPi.GPIO as GPIO

        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)

        for pin in (CONV_A, CONV_B, SEG_A, SEG_B, CONV_EN, SEG_EN):
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

        # PWM on enable pins for speed control
        _pwm_conv = GPIO.PWM(CONV_EN, 500)  # 500 Hz
        _pwm_seg = GPIO.PWM(SEG_EN, 500)
        _pwm_conv.start(0)
        _pwm_seg.start(0)

        _gpio_ok = True
        print("[HW] L293D ready (BOARD + PWM)")
        print(f"[HW] Conveyor dir {CONV_A}/{CONV_B} EN={CONV_EN} speed={CONV_SPEED}%")
        print(f"[HW] Seg dir {SEG_A}/{SEG_B} EN={SEG_EN} speed={SEG_SPEED}%")
    except Exception as e:
        _gpio_ok = False
        _pwm_conv = None
        _pwm_seg = None
        print(f"[HW] GPIO not available: {e}")

    try:
        from RPLCD.gpio import CharLCD
        import RPi.GPIO as GPIO

        _lcd = CharLCD(
            pin_rs=LCD_RS,
            pin_e=LCD_E,
            pins_data=[LCD_D4, LCD_D5, LCD_D6, LCD_D7],
            numbering_mode=GPIO.BOARD,
            cols=16,
            rows=2,
            pin_rw=None,
        )
        time.sleep(0.1)
        with _lcd_lock:
            _lcd.clear()
            time.sleep(0.05)
            _lcd.write_string("PCB Vision AI")
            _lcd.crlf()
            _lcd.write_string("System Ready")
        print("[HW] Parallel LCD ready")
    except Exception as e:
        _lcd = None
        print(f"[HW] LCD not available: {e}")

    return {"gpio": _gpio_ok, "lcd": _lcd is not None, "conv_speed": CONV_SPEED}


def lcd_show(line1: str, line2: str = "") -> None:
    """Thread-safe LCD update — clean 16x2, no mixed/garbage characters."""
    def clean(s):
        s = "".join(c if 32 <= ord(c) < 127 else " " for c in (s or ""))
        return s[:16].ljust(16)

    l1 = clean(line1)
    l2 = clean(line2)
    print(f"[LCD] {l1.strip()} | {l2.strip()}")

    if _lcd is None:
        return

    with _lcd_lock:
        try:
            # Full clear + blank both lines first to avoid leftover / mixed chars
            _lcd.clear()
            time.sleep(0.08)
            _lcd.cursor_pos = (0, 0)
            _lcd.write_string(" " * 16)
            time.sleep(0.02)
            _lcd.cursor_pos = (1, 0)
            _lcd.write_string(" " * 16)
            time.sleep(0.04)
            _lcd.cursor_pos = (0, 0)
            _lcd.write_string(l1)
            time.sleep(0.04)
            _lcd.cursor_pos = (1, 0)
            _lcd.write_string(l2)
            time.sleep(0.04)
        except Exception as e:
            print(f"[LCD] error: {e}")



def _conv_forward() -> None:
    if not _gpio_ok:
        print(f"[HW] CONV forward {CONV_SPEED}%")
        return
    import RPi.GPIO as GPIO

    GPIO.output(CONV_A, GPIO.HIGH)
    GPIO.output(CONV_B, GPIO.LOW)
    if _pwm_conv:
        _pwm_conv.ChangeDutyCycle(max(0, min(100, CONV_SPEED)))


def _conv_stop() -> None:
    if not _gpio_ok:
        return
    import RPi.GPIO as GPIO

    GPIO.output(CONV_A, GPIO.LOW)
    GPIO.output(CONV_B, GPIO.LOW)
    if _pwm_conv:
        _pwm_conv.ChangeDutyCycle(0)


def _seg_left() -> None:
    if not _gpio_ok:
        print("[HW] SEG left")
        return
    import RPi.GPIO as GPIO

    GPIO.output(SEG_A, GPIO.HIGH)
    GPIO.output(SEG_B, GPIO.LOW)
    if _pwm_seg:
        _pwm_seg.ChangeDutyCycle(max(0, min(100, SEG_SPEED)))


def _seg_right() -> None:
    if not _gpio_ok:
        print("[HW] SEG right")
        return
    import RPi.GPIO as GPIO

    GPIO.output(SEG_A, GPIO.LOW)
    GPIO.output(SEG_B, GPIO.HIGH)
    if _pwm_seg:
        _pwm_seg.ChangeDutyCycle(max(0, min(100, SEG_SPEED)))


def _seg_stop() -> None:
    if not _gpio_ok:
        return
    import RPi.GPIO as GPIO

    GPIO.output(SEG_A, GPIO.LOW)
    GPIO.output(SEG_B, GPIO.LOW)
    if _pwm_seg:
        _pwm_seg.ChangeDutyCycle(0)


def conveyor_start() -> None:
    global _conveyor_running
    with _lock:
        _conv_forward()
        _conveyor_running = True
    lcd_show("Conveyor ON", "Waiting PCB...")


def conveyor_stop() -> None:
    global _conveyor_running
    with _lock:
        _conv_stop()
        _conveyor_running = False
    lcd_show("Conveyor OFF", "")



# Samples collected while board is STOPPED in front of camera
_sample_lock = threading.Lock()
_samples = []  # list of dicts: decision, name, conf
_inspecting = False


def lcd_from_live(decision: str, detections: list) -> None:
    """Do not spam LCD during free run — only status when idle (no garbage flicker)."""
    # Live stream should not overwrite LCD with every frame (causes mixed chars).
    # LCD is updated only: Conveyor ON/OFF, Inspecting..., final sort decision.
    return


def push_inspection_sample(decision: str, detections: list) -> None:
    """Called from live loop while board is stopped — collect stationary frames."""
    global _samples
    if not _inspecting:
        return
    best_name, best_conf = "", -1.0
    for det in detections or []:
        if hasattr(det, "class_name"):
            name = det.class_name
            conf = float(getattr(det, "confidence", 0) or 0)
        elif isinstance(det, dict):
            name = det.get("class_name", "")
            conf = float(det.get("confidence", 0) or 0)
        else:
            continue
        if name and conf > best_conf:
            best_name, best_conf = name, conf
    d = str(decision or "")
    with _sample_lock:
        _samples.append({
            "decision": d,
            "name": best_name,
            "conf": best_conf,
        })


def _pick_stationary_decision(samples: list) -> tuple:
    """
    Skip the first capture (often wrong while board is still moving in).
    Use the 2nd sample if available; otherwise the last sample.
    Among samples after the first, prefer highest confidence, but if any
    strong DEFECT/Unknown appears after frame 1, that wins over a weaker good.
    Returns (is_defect, is_unknown, line1, line2, target)
    """
    if not samples:
        return True, True, "Unknown_PCB", "No sample", "defect"

    # Prefer samples from index 1 onward (stationary in front of camera)
    pool = samples[1:] if len(samples) >= 2 else samples[:]
    # Also keep last few for stability
    if len(pool) > 5:
        pool = pool[-5:]

    best = max(pool, key=lambda s: s.get("conf", 0))
    # If any later sample is defect/unknown with conf close to best, prefer defect (safer)
    defect_candidates = []
    good_candidates = []
    for s in pool:
        du = str(s.get("decision", "")).upper()
        conf = float(s.get("conf", 0) or 0)
        if "UNKNOWN" in du:
            defect_candidates.append(s)
        elif du.startswith("DEFECT"):
            defect_candidates.append(s)
        elif "GOOD" in du:
            good_candidates.append(s)

    chosen = best
    if defect_candidates:
        chosen = max(defect_candidates, key=lambda s: s.get("conf", 0))
        # Only override a much stronger GOOD if defect conf is meaningful
        if good_candidates:
            g = max(good_candidates, key=lambda s: s.get("conf", 0))
            # User rule: major confidence wins — if good is clearly higher, keep good
            if float(g.get("conf", 0)) > float(chosen.get("conf", 0)):
                chosen = g

    d = str(chosen.get("decision", ""))
    du = d.upper()
    name = str(chosen.get("name") or "")
    conf = float(chosen.get("conf", 0) or 0)
    pct = int(round(conf * 100))
    name_short = name.replace("_", " ")[:10]

    if "UNKNOWN" in du:
        return True, True, "Unknown_PCB", (f"{name_short} {pct}%".strip() if name else "Not trained")[:16], "defect"
    if du.startswith("DEFECT"):
        return True, False, "DEFECT DETECTED", (f"{name_short} {pct}%".strip() if name else "Defect")[:16], "defect"
    if "GOOD" in du:
        return False, False, "PCB GOOD", (f"{name_short} {pct}%".strip() if name else "Good board")[:16], "good"
    return True, True, "Unknown_PCB", "Check board", "defect"


def is_busy() -> bool:
    return _busy or time.time() < _cooldown_until


def is_conveyor_running() -> bool:
    return _conveyor_running


def on_inspection_result(is_defect: bool = False, label_summary: str = "", is_unknown: bool = False) -> None:
    """
    Board detected while moving:
      1) Stop conveyor immediately
      2) LCD: Inspecting...
      3) Collect camera samples while stopped (push_inspection_sample from live loop)
      4) After PAUSE_SEC, decide from 2nd/later frames (not first moving-in frame)
      5) LCD + segregation from that final decision only
      6) Resume conveyor
    """
    global _busy, _cooldown_until, _seg_side, _conveyor_running, _inspecting, _samples

    if _busy or time.time() < _cooldown_until:
        return

    def sequence():
        global _busy, _cooldown_until, _seg_side, _conveyor_running, _inspecting, _samples
        _busy = True
        _inspecting = True
        with _sample_lock:
            _samples = []
        try:
            with _lock:
                _conv_stop()
                _conveyor_running = False

            lcd_show("Inspecting...", "Hold still")
            print(f"[HW] Board seen — stop {PAUSE_SEC}s, collect stationary frames")
            time.sleep(PAUSE_SEC)

            _inspecting = False
            with _sample_lock:
                samples = list(_samples)

            print(f"[HW] Collected {len(samples)} samples (skip first / use 2nd+ for decision)")
            for i, s in enumerate(samples):
                print(f"  [{i}] {s.get('decision')} {s.get('name')} {s.get('conf', 0):.2f}")

            to_defect, is_unk, line1, line2, target = _pick_stationary_decision(samples)
            lcd_show(line1, line2)
            print(f"[HW] FINAL decision target={target} LCD={line1}|{line2}")

            time.sleep(0.4)

            if _seg_side == target:
                print(f"[HW] Already on {target} — no move")
                lcd_show(line1, "Already sorted")
                time.sleep(0.3)
            else:
                if to_defect:
                    _seg_right()
                else:
                    _seg_left()
                time.sleep(SEG_PULSE_SEC)
                _seg_stop()
                _seg_side = target

            with _lock:
                _conv_forward()
                _conveyor_running = True
            lcd_show("Conveyor ON", "Waiting PCB...")
            _cooldown_until = time.time() + COOLDOWN_SEC
        except Exception as e:
            print(f"[HW] sequence error: {e}")
            try:
                _seg_stop()
                _conv_forward()
                _conveyor_running = True
            except Exception:
                pass
        finally:
            _inspecting = False
            _busy = False

    threading.Thread(target=sequence, daemon=True).start()


def shutdown() -> None:
    try:
        _conv_stop()
        _seg_stop()
        if _pwm_conv:
            _pwm_conv.stop()
        if _pwm_seg:
            _pwm_seg.stop()
        if _gpio_ok:
            import RPi.GPIO as GPIO
            GPIO.cleanup()
    except Exception:
        pass
    if _lcd:
        try:
            with _lcd_lock:
                _lcd.clear()
        except Exception:
            pass
