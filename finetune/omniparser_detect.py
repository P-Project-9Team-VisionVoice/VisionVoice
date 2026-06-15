"""
OmniParser-v2.0 YOLO UI element detection
taining_datasets/ 이미지에서 UI 요소 bbox 자동 감지
→ review_omni/ 에 시각화 저장
"""
import json
import os
from pathlib import Path

import torch
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

OMNI_DIR = "/home/devlofi/models/OmniParser-v2.0"
IMG_DIR = Path("/home/devlofi/HyeWon/taining_datasets")
OUT_DIR = Path("/home/devlofi/HyeWon/finetune/dataset/review_omni")
OUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("OmniParser-v2.0 UI Element Detection")
print(f"Input:  {IMG_DIR}")
print(f"Output: {OUT_DIR}")
print("=" * 60)

# YOLO 로드 (icon_detect)
print("\n[1/3] YOLO 모델 로딩...")
yolo = YOLO(f"{OMNI_DIR}/icon_detect/model.pt")
print("✓ YOLO loaded")

def load_font(size=16):
    for p in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

font = load_font()

# 이미지 목록
images = sorted(IMG_DIR.glob("*.png")) + sorted(IMG_DIR.glob("*.jpg"))
print(f"\n[2/3] {len(images)}개 이미지 처리 중...")

all_detections = {}
for img_path in images:
    img = Image.open(img_path).convert("RGB")
    W, H = img.size

    results = yolo(img_path, conf=0.05, iou=0.7, verbose=False)
    boxes_raw = results[0].boxes

    draw = ImageDraw.Draw(img)
    detections = []

    for i, box in enumerate(boxes_raw):
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        conf = float(box.conf[0])

        # 0~1000 정규화 bbox
        bbox_norm = [
            round(x1 / W * 1000),
            round(y1 / H * 1000),
            round(x2 / W * 1000),
            round(y2 / H * 1000),
        ]

        color = (37, 99, 235)  # 파란색
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

        label = f"{i+1} ({conf:.2f})"
        lx, ly, lx2, ly2 = draw.textbbox((0, 0), label, font=font)
        lw, lh = lx2 - lx + 6, ly2 - ly + 4
        label_y = max(0, y1 - lh)
        draw.rectangle([x1, label_y, x1 + lw, label_y + lh], fill=color)
        draw.text((x1 + 3, label_y + 2), label, fill="white", font=font)

        detections.append({
            "idx": i + 1,
            "bbox_px": [round(x1), round(y1), round(x2), round(y2)],
            "bbox_norm": bbox_norm,
            "conf": round(conf, 3),
        })

    out_path = OUT_DIR / f"{img_path.stem}_omni.png"
    img.save(out_path)
    all_detections[img_path.name] = detections
    print(f"  {img_path.name}: {len(detections)}개 요소 감지 → {out_path.name}")

# JSON 저장
json_path = OUT_DIR / "omni_detections.json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(all_detections, f, ensure_ascii=False, indent=2)

print(f"\n[3/3] 완료")
print(f"  시각화: {OUT_DIR}/")
print(f"  감지 결과 JSON: {json_path}")
total = sum(len(v) for v in all_detections.values())
print(f"  총 감지 요소: {total}개 ({len(images)}개 이미지)")
