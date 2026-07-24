#!/usr/bin/env python3
"""
Live webcam inference with a YOLO best.pt model on Raspberry Pi 5.

Install:
    pip install ultralytics opencv-python

Run:
    python detect_live.py --model best.pt --source 0 --imgsz 480 --conf 0.35
"""

import argparse
import time

import cv2
from ultralytics import YOLO


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="best.pt")
    p.add_argument("--source", default="0", help="camera index or video/stream URL")
    p.add_argument("--imgsz", type=int, default=480, help="inference size (lower = faster)")
    p.add_argument("--conf", type=float, default=0.35)
    p.add_argument("--iou", type=float, default=0.45)
    p.add_argument("--width", type=int, default=640, help="capture width")
    p.add_argument("--height", type=int, default=480, help="capture height")
    p.add_argument("--no-show", action="store_true", help="headless mode (no window)")
    p.add_argument("--save", default="", help="optional output .mp4 path")
    return p.parse_args()


def open_capture(source, width, height):
    src = int(source) if source.isdigit() else source
    # V4L2 backend is the reliable one on Pi OS for USB/CSI (libcamera-v4l2) cameras
    cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera source: {source}")

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # keep latency low
    return cap


def main():
    args = parse_args()

    model = YOLO(args.model)
    model.fuse()
    names = model.names
    print("Classes:", names)

    cap = open_capture(args.source, args.width, args.height)

    writer = None
    if args.save:
        fps_out = cap.get(cv2.CAP_PROP_FPS) or 15
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(args.save, cv2.VideoWriter_fourcc(*"mp4v"), fps_out, (w, h))

    fps, alpha, prev = 0.0, 0.9, time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Frame grab failed; retrying...")
                time.sleep(0.05)
                continue

            results = model.predict(
                frame,
                imgsz=args.imgsz,
                conf=args.conf,
                iou=args.iou,
                device="cpu",
                verbose=False,
            )
            r = results[0]
            annotated = r.plot()

            now = time.time()
            inst = 1.0 / max(now - prev, 1e-6)
            prev = now
            fps = inst if fps == 0 else alpha * fps + (1 - alpha) * inst

            cv2.putText(
                annotated, f"{fps:.1f} FPS  |  {len(r.boxes)} det",
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2
            )

            for box in r.boxes:
                cls = names[int(box.cls[0])]
                print(f"{cls} {float(box.conf[0]):.2f} "
                      f"{[round(v) for v in box.xyxy[0].tolist()]}")

            if writer is not None:
                writer.write(annotated)

            if not args.no_show:
                cv2.imshow("YOLO — Raspberry Pi 5", annotated)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
