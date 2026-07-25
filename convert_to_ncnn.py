from ultralytics import YOLO
YOLO("best.pt").export(format="ncnn", imgsz=480)   # → best_ncnn_model
