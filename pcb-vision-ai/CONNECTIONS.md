# Hardware connections (Raspberry Pi 4 — BOARD physical pin numbers)

## 1. Power (KA7805 / multi-voltage supply)

| Supply | Pi |
|--------|-----|
| GND | Pin **6** (GND) — **common ground with motor PSU** |
| 5V logic (optional to Pi) | Prefer separate Pi USB-C power for the board |

Motors use **external 12V**. Never power motors from Pi 5V pins.

---

## 2. LCD 16×2 (4-bit parallel)

| LCD pin | Signal | Pi BOARD pin |
|---------|--------|--------------|
| 1 | VSS | **6** GND |
| 2 | VDD | **2** or **4** (5V) |
| 3 | V0 | Contrast pot (middle); pot ends to 5V and GND |
| 4 | RS | **40** |
| 5 | RW | **34** (GND) — write only |
| 6 | E | **38** |
| 11 | D4 | **31** |
| 12 | D5 | **33** |
| 13 | D6 | **35** |
| 14 | D7 | **37** |
| 15 | A (backlight+) | 5V via ~220 Ω |
| 16 | K (backlight−) | GND |

D0–D3 not used.

**Software pins:** RS=40, E=38, D4=31, D5=33, D6=35, D7=37  

If the screen is blank, adjust the **contrast pot** first.

---

## 3. L293D dual H-bridge (motors)

### Conveyor motor (channel 1)

| L293D | Pi BOARD | Function |
|-------|----------|----------|
| **EN1** | **11** | PWM speed (required for CONV_SPEED) |
| C1A / IN1 | **13** | Direction |
| C1B / IN2 | **15** | Direction |
| OUT1, OUT2 | Conveyor DC motor | |
| VS / motor power | External **12V** | |
| GND | Pi GND + 12V GND | Common ground |

If EN1 is tied to 5V instead of pin 11, belt always runs full speed.

### Segregation motor (channel 2)

| L293D | Pi BOARD | Function |
|-------|----------|----------|
| **EN2** | **12** | PWM (optional) |
| C2A / IN3 | **16** | Direction (left/right) |
| C2B / IN4 | **18** | Direction |
| OUT3, OUT4 | Segregation DC motor (rack) | |

- **GOOD** → slide left  
- **DEFECT / Unknown_PCB** → slide right  

Wrong direction → swap that motor’s two wires only.

---

## 4. Camera

USB webcam on any USB port. Software uses index **0** (`CAMERA_INDEX=0`), OpenCV `CAP_V4L2`.

---

## 5. Pin summary diagram

```
Pi BOARD:
  11 ── EN1 (conveyor speed PWM)
  12 ── EN2 (segregation PWM)
  13 ── C1A conveyor
  15 ── C1B conveyor
  16 ── C2A segregation
  18 ── C2B segregation
  31 ── LCD D4
  33 ── LCD D5
  35 ── LCD D6
  37 ── LCD D7
  38 ── LCD E
  40 ── LCD RS
   6 ── GND (common)
   2/4 ── 5V (LCD only)
```

