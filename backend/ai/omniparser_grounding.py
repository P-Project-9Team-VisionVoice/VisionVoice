"""
OmniParser Hybrid Grounding v2
VLM이 예측한 rough bbox를 OmniParser YOLO로 정밀화

파이프라인:
  1. VLM (Qwen3-VL-8B) → rough bbox (0~1000 normalized)
  2. OmniParser YOLO  → 전체 화면의 UI 요소 감지
  3. VLM bbox와 가장 많이 겹치는 OmniParser 요소 선택
  4. 해당 요소 중심점으로 정밀 클릭
"""

import torch
from PIL import Image
from pathlib import Path

OMNI_MODEL_PATH = "/home/devlofi/models/OmniParser-v2.0"

_yolo_model = None


def _load_yolo():
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        print("🔍 OmniParser YOLO 로딩...")
        _yolo_model = YOLO(f"{OMNI_MODEL_PATH}/icon_detect/model.pt")
        print("✓ OmniParser YOLO 로딩 완료")
    return _yolo_model


def _iou(box_a, box_b):
    """box: [x1, y1, x2, y2] pixel"""
    xa1, ya1, xa2, ya2 = box_a
    xb1, yb1, xb2, yb2 = box_b
    ix1 = max(xa1, xb1); iy1 = max(ya1, yb1)
    ix2 = min(xa2, xb2); iy2 = min(ya2, yb2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (xa2 - xa1) * (ya2 - ya1)
    area_b = (xb2 - xb1) * (yb2 - yb1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def refine_bbox(image_path: str, vlm_box_norm: list, orig_w: int, orig_h: int,
                iou_threshold: float = 0.15) -> dict:
    """
    VLM bbox를 OmniParser로 정밀화.

    Args:
        image_path:    스크린샷 경로
        vlm_box_norm:  VLM 예측 bbox [y1, x1, y2, x2] 0~1000 normalized (Qwen 형식)
        orig_w, orig_h: 원본 이미지 크기
        iou_threshold: 겹침 최소 기준

    Returns:
        dict with keys: x, y (클릭 좌표), box_px, source ('omniparser' or 'vlm')
    """
    # VLM bbox 픽셀 변환 (Qwen 형식: [y1, x1, y2, x2])
    y1_n, x1_n, y2_n, x2_n = vlm_box_norm
    vlm_px = [
        int(x1_n / 1000 * orig_w),
        int(y1_n / 1000 * orig_h),
        int(x2_n / 1000 * orig_w),
        int(y2_n / 1000 * orig_h),
    ]
    vlm_cx = (vlm_px[0] + vlm_px[2]) // 2
    vlm_cy = (vlm_px[1] + vlm_px[3]) // 2

    try:
        yolo = _load_yolo()
        results = yolo(image_path, conf=0.05, iou=0.7, verbose=False)
        boxes = results[0].boxes

        best_iou  = iou_threshold
        best_box  = None

        for box in boxes:
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            score = _iou(vlm_px, [x1, y1, x2, y2])
            if score > best_iou:
                best_iou = score
                best_box = [x1, y1, x2, y2]

        if best_box:
            cx = (best_box[0] + best_box[2]) // 2
            cy = (best_box[1] + best_box[3]) // 2
            print(f"📐 OmniParser 정밀화 성공 | IoU={best_iou:.3f} | "
                  f"VLM ({vlm_cx},{vlm_cy}) → OmniParser ({cx},{cy})")
            return {"x": cx, "y": cy, "box_px": best_box, "source": "omniparser"}

    except Exception as e:
        print(f"⚠️ OmniParser 실패 ({e}), VLM bbox 사용")

    # fallback: VLM bbox 중심점 그대로 사용
    print(f"📐 VLM bbox 사용 (fallback) | 클릭 ({vlm_cx},{vlm_cy})")
    return {"x": vlm_cx, "y": vlm_cy, "box_px": vlm_px, "source": "vlm"}
