# servo-raspberry-pi

- `detect_live.py` — live webcam YOLO detection preview, no servo control.
- `servo_control.py` — manual keyboard pan/tilt test (lgpio, GPIO18/GPIO13).
- `track_object.py` — combines the two: detects objects with `best.pt`, computes each
  detection's pixel/normalized offset from frame center, and drives the pan/tilt servos
  with a proportional controller to keep the target centered.
  ```
  python track_object.py --model best.pt --source 0
  python track_object.py --model best.pt --no-show          # headless over SSH
  python track_object.py --model best.pt --dry-run          # test off the Pi, no GPIO
  ```
  See the script's module docstring for full tuning options (gain, deadzone, inversion).

