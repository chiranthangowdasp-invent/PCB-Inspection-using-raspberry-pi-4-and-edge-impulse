#!/usr/bin/env python3
"""
Standalone test for your Edge Impulse .eim on Raspberry Pi 4
Run this FIRST before starting the full web app.

Usage:
  cd ~/pcb-vision-ai/backend
  source .venv/bin/activate
  python test_model.py                  # use webcam
  python test_model.py photo.jpg        # classify a single image
"""

import sys
import time
from pathlib import Path

MODEL = Path(__file__).parent / "model.eim"

def main():
    if not MODEL.exists():
        print(f"ERROR: model not found → {MODEL}")
        print("Copy your .eim file here and rename it to model.eim")
        sys.exit(1)

    print(f"Loading model: {MODEL} ({MODEL.stat().st_size // 1024 // 1024} MB)")
    from edge_impulse_linux.image import ImageImpulseRunner
    import cv2
    import numpy as np

    with ImageImpulseRunner(str(MODEL)) as runner:
        info = runner.init()
        name = info.get("project", {}).get("name", "unknown")
        labels = info.get("model_parameters", {}).get("labels") or info.get("labels") or []
        print(f"Model loaded: {name}")
        print(f"Labels: {labels}")
        print("-" * 50)

        # ---- single image mode ----
        if len(sys.argv) > 1:
            img_path = sys.argv[1]
            img = cv2.imread(img_path)
            if img is None:
                print(f"Cannot read image: {img_path}")
                sys.exit(1)
            img_rgb = img[:, :, ::-1].copy()
            features, _ = runner.get_features_from_image(img_rgb)
            t0 = time.perf_counter()
            res = runner.classify(features)
            ms = (time.perf_counter() - t0) * 1000
            print_result(res, ms)
            return

        # ---- live camera mode ----
        print("Opening camera... (press Q to quit)")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("ERROR: Cannot open camera (try index 1: VideoCapture(1))")
            sys.exit(1)

        frame_count = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_count += 1
            # run every 5th frame to keep FPS usable on Pi 4
            if frame_count % 5 != 0:
                cv2.imshow("PCB Vision AI - press Q to quit", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            img_rgb = frame[:, :, ::-1].copy()
            features, cropped = runner.get_features_from_image(img_rgb)
            t0 = time.perf_counter()
            res = runner.classify(features)
            ms = (time.perf_counter() - t0) * 1000

            # draw boxes
            boxes = res.get("result", {}).get("bounding_boxes", [])
            for bb in boxes:
                x, y, w, h = int(bb["x"]), int(bb["y"]), int(bb["width"]), int(bb["height"])
                label = f'{bb["label"]} {bb["value"]:.0%}'
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 180), 2)
                cv2.putText(frame, label, (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 180), 1)

            cv2.putText(frame, f"{ms:.0f} ms  |  {len(boxes)} objects", (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (57, 216, 255), 2)
            cv2.imshow("PCB Vision AI - press Q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()


def print_result(res, ms):
    result = res.get("result", {})
    if "bounding_boxes" in result:
        boxes = result["bounding_boxes"]
        print(f"Found {len(boxes)} object(s) in {ms:.1f} ms")
        for bb in boxes:
            print(f"  {bb['label']:20s}  conf={bb['value']:.2f}  "
                  f"x={bb['x']} y={bb['y']} w={bb['width']} h={bb['height']}")
    elif "classification" in result:
        print(f"Classification in {ms:.1f} ms")
        for label, score in sorted(result["classification"].items(), key=lambda x: -x[1]):
            print(f"  {label:20s}  {score:.2%}")
    else:
        print("Unexpected result:", result)


if __name__ == "__main__":
    main()
