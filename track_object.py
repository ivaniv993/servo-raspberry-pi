#!/usr/bin/env python3
"""
YOLO object tracking with a pan/tilt servo rig on Raspberry Pi 5.

Pipeline:
  1. Capture frames from a USB webcam (OpenCV / V4L2).
  2. Run YOLO (best.pt, or an exported NCNN model dir) on each frame.
  3. Pick one target detection and compute its offset from the frame center.
  4. Feed that offset into a proportional controller driving two SG90 servos
     (pan = horizontal, tilt = vertical) via lgpio, so the camera re-centers
     on the target.

Wiring (same as servo_control.py, BCM numbering):
  Pan servo  (horizontal) signal -> GPIO18, physical pin 12
  Tilt servo (vertical)   signal -> GPIO13, physical pin 33
  Both servo grounds -> Pi GND (e.g. physical pin 6) AND external supply GND (common ground)
  Both servo power    -> external 5-6V supply (+), NOT the Pi's 5V pin

Install:
  pip install ultralytics opencv-python
  sudo apt install python3-lgpio

Run:
  python track_object.py --model best.pt --source 0 --imgsz 480 --conf 0.35
  python track_object.py --model best.pt --no-show          # headless, e.g. over SSH
  python track_object.py --model best.pt --dry-run          # log offsets/angles, skip GPIO (test off-Pi)
  python track_object.py --model best.pt --target-class cup # only track a specific class

Tuning:
  --kp-pan / --kp-tilt   max degrees of correction per frame at full (edge-of-frame) offset
  --deadzone             normalized offset (0-1) below which no correction is applied (anti-jitter)
  --invert-pan/--invert-tilt   flip correction direction if the rig moves the wrong way
  --max-lost-frames      frames without a detection before logging "target lost" (servos hold position)

Log file: track_object.log (also printed to console)
"""

import argparse
import logging
import sys
import time

import cv2
from ultralytics import YOLO

try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False

# ---- Servo / GPIO config (matches servo_control.py) ----
PAN_PIN = 18     # horizontal, physical pin 12
TILT_PIN = 13    # vertical,   physical pin 33
FREQ = 50
ANGLE_MIN = 0
ANGLE_MAX = 180
ANGLE_CENTER = 90
PULSE_MIN = 0.5  # ms at 0 deg
PULSE_MAX = 2.5  # ms at 180 deg

LOG_FILE = "track_object.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("track")


def angle_to_duty(angle):
    """Convert angle (0-180) to duty cycle percent for a 20 ms period."""
    pulse_ms = PULSE_MIN + (PULSE_MAX - PULSE_MIN) * angle / 180.0
    return pulse_ms / 20.0 * 100.0


class ServoController:
    """Wraps the two lgpio PWM outputs and keeps track of current angles."""

    def __init__(self, dry_run=False):
        self.dry_run = dry_run or not LGPIO_AVAILABLE
        self.pan_angle = ANGLE_CENTER
        self.tilt_angle = ANGLE_CENTER
        self.h = None

        if self.dry_run:
            reason = "lgpio not installed" if not LGPIO_AVAILABLE else "--dry-run"
            log.warning("Servo dry-run mode (%s): angles will be computed and logged, "
                        "but no GPIO output will be produced.", reason)
        else:
            self.h = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(self.h, PAN_PIN)
            lgpio.gpio_claim_output(self.h, TILT_PIN)
            self._apply(PAN_PIN, self.pan_angle)
            self._apply(TILT_PIN, self.tilt_angle)
            log.info("Servos initialized: pan=GPIO%d tilt=GPIO%d, centered at %d deg",
                     PAN_PIN, TILT_PIN, ANGLE_CENTER)

    def _apply(self, pin, angle):
        if self.dry_run:
            return
        lgpio.tx_pwm(self.h, pin, FREQ, angle_to_duty(angle))

    def set_pan(self, angle):
        self.pan_angle = max(ANGLE_MIN, min(ANGLE_MAX, angle))
        self._apply(PAN_PIN, self.pan_angle)

    def set_tilt(self, angle):
        self.tilt_angle = max(ANGLE_MIN, min(ANGLE_MAX, angle))
        self._apply(TILT_PIN, self.tilt_angle)

    def close(self):
        if self.dry_run:
            return
        lgpio.tx_pwm(self.h, PAN_PIN, 0, 0)
        lgpio.tx_pwm(self.h, TILT_PIN, 0, 0)
        lgpio.gpiochip_close(self.h)
        log.info("PWM stopped, GPIO released. Final: pan=%d tilt=%d deg",
                 self.pan_angle, self.tilt_angle)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="best.pt", help="path to best.pt or an exported NCNN model dir")
    p.add_argument("--source", default="0", help="camera index or video/stream URL")
    p.add_argument("--imgsz", type=int, default=480, help="inference size (lower = faster)")
    p.add_argument("--conf", type=float, default=0.35)
    p.add_argument("--iou", type=float, default=0.45)
    p.add_argument("--width", type=int, default=640, help="capture width")
    p.add_argument("--height", type=int, default=480, help="capture height")
    p.add_argument("--no-show", action="store_true", help="headless mode (no preview window)")
    p.add_argument("--save", default="", help="optional annotated output .mp4 path")

    p.add_argument("--target-class", default="", help="only track detections of this class name; "
                                                        "empty = consider all classes")
    p.add_argument("--select", choices=["conf", "area"], default="conf",
                   help="when multiple detections qualify, pick the one with highest "
                        "confidence (conf) or largest box area (area)")

    p.add_argument("--kp-pan", type=float, default=15.0,
                   help="proportional gain in degrees/frame at full normalized offset (pan)")
    p.add_argument("--kp-tilt", type=float, default=15.0,
                   help="proportional gain in degrees/frame at full normalized offset (tilt)")
    p.add_argument("--deadzone", type=float, default=0.05,
                   help="normalized offset (0-1) below which no correction is applied")
    p.add_argument("--invert-pan", action="store_true", help="flip pan correction direction")
    p.add_argument("--invert-tilt", action="store_true", help="flip tilt correction direction")
    p.add_argument("--max-lost-frames", type=int, default=15,
                   help="consecutive missed frames before logging that the target is lost")
    p.add_argument("--dry-run", action="store_true",
                   help="compute detections/offsets/angles but do not drive GPIO "
                        "(useful for testing off the Pi)")
    return p.parse_args()


def open_capture(source, width, height):
    src = int(source) if source.isdigit() else source
    # V4L2 backend is the reliable one on Pi OS for USB cameras
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


def pick_target(boxes, names, target_class, select):
    """Return the single best-matching detection box, or None."""
    candidates = []
    for box in boxes:
        cls_name = names[int(box.cls[0])]
        if target_class and cls_name != target_class:
            continue
        candidates.append(box)

    if not candidates:
        return None

    if select == "area":
        def score(b):
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            return (x2 - x1) * (y2 - y1)
    else:
        def score(b):
            return float(b.conf[0])

    return max(candidates, key=score)


def compute_offset(box, frame_w, frame_h):
    """Offset of a box's center from the frame center.

    Returns (cx, cy, dx_px, dy_px, dx_norm, dy_norm):
      cx, cy       absolute pixel center of the box
      dx_px, dy_px signed pixel offset from frame center (+x = right, +y = down)
      dx_norm      dx_px / (frame_w / 2), in [-1, 1]
      dy_norm      dy_px / (frame_h / 2), in [-1, 1]
    """
    x1, y1, x2, y2 = box.xyxy[0].tolist()
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    frame_cx = frame_w / 2.0
    frame_cy = frame_h / 2.0
    dx_px = cx - frame_cx
    dy_px = cy - frame_cy
    dx_norm = dx_px / frame_cx
    dy_norm = dy_px / frame_cy
    return cx, cy, dx_px, dy_px, dx_norm, dy_norm


def main():
    args = parse_args()

    model = YOLO(args.model)
    model.fuse()
    names = model.names
    log.info("Loaded model %s. Classes: %s", args.model, names)

    cap = open_capture(args.source, args.width, args.height)

    writer = None
    if args.save:
        fps_out = cap.get(cv2.CAP_PROP_FPS) or 15
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(args.save, cv2.VideoWriter_fourcc(*"mp4v"), fps_out, (w, h))

    servo = ServoController(dry_run=args.dry_run)
    pan_dir = -1.0 if args.invert_pan else 1.0
    tilt_dir = -1.0 if args.invert_tilt else 1.0

    lost_frames = 0
    fps, alpha, prev = 0.0, 0.9, time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                log.warning("Frame grab failed; retrying...")
                time.sleep(0.05)
                continue

            h, w = frame.shape[:2]

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

            # Frame-center crosshair, always drawn for visual reference
            cv2.drawMarker(annotated, (w // 2, h // 2), (255, 0, 0),
                            cv2.MARKER_CROSS, 24, 2)

            box = pick_target(r.boxes, names, args.target_class, args.select)

            if box is not None:
                lost_frames = 0
                cls_name = names[int(box.cls[0])]
                conf = float(box.conf[0])
                cx, cy, dx_px, dy_px, dx_n, dy_n = compute_offset(box, w, h)

                if abs(dx_n) > args.deadzone:
                    servo.set_pan(servo.pan_angle + pan_dir * args.kp_pan * dx_n)
                if abs(dy_n) > args.deadzone:
                    servo.set_tilt(servo.tilt_angle + tilt_dir * args.kp_tilt * dy_n)

                cv2.circle(annotated, (int(cx), int(cy)), 6, (0, 0, 255), -1)
                cv2.line(annotated, (w // 2, h // 2), (int(cx), int(cy)), (0, 0, 255), 2)

                log.info(
                    "%-12s conf=%.2f offset_px=(%+5.0f,%+5.0f) offset_norm=(%+.2f,%+.2f) "
                    "-> pan=%3d tilt=%3d",
                    cls_name, conf, dx_px, dy_px, dx_n, dy_n, servo.pan_angle, servo.tilt_angle,
                )
            else:
                lost_frames += 1
                if lost_frames == args.max_lost_frames:
                    log.info("Target lost for %d frames; holding position pan=%d tilt=%d",
                             lost_frames, servo.pan_angle, servo.tilt_angle)

            now = time.time()
            inst = 1.0 / max(now - prev, 1e-6)
            prev = now
            fps = inst if fps == 0 else alpha * fps + (1 - alpha) * inst

            cv2.putText(
                annotated, f"{fps:.1f} FPS | pan={servo.pan_angle} tilt={servo.tilt_angle}",
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
            )

            if writer is not None:
                writer.write(annotated)

            if not args.no_show:
                cv2.imshow("YOLO tracking - Raspberry Pi 5", annotated)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break

    except KeyboardInterrupt:
        log.info("Interrupted by Ctrl+C")
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()
        servo.close()


if __name__ == "__main__":
    main()
