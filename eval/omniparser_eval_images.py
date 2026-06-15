"""
OmniParser-v2.0 — eval에 쓴 실제 스크린샷 10개에 UI element 감지
eval 결과의 VLM bbox vs OmniParser bbox 비교용
"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

OMNI_DIR = "/home/devlofi/models/OmniParser-v2.0"
IMG_BASE  = Path("/home/devlofi/HyeWon/taining_datasets")
OUT_DIR   = Path("/home/devlofi/HyeWon/eval_results/viz_omniparser")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ID_TO_IMG = {
    "naver_m_01": "naver_main.png",
    "naver_m_02": "naver_main.png",
    "naver_s_01": "naver_search_input_open.png",
    "musinsa_m_01": "musinsa_main.png",
    "musinsa_d_01": "musinsa_detail_samyang_group_special_T.png",
    "musinsa_d_02": "musinsa_short_sleeve_search.png",
    "youtube_m_01": "youtube_main.png",
    "youtube_m_02": "youtube_main.png",
    "youtube_c_01": "youtube_comments.png",
    "sheet_01":     "spreadsheets_Gradu_list.png",
}

SCENARIOS = [
    {"id": "naver_m_01",   "command": "검색창에 '오늘 날씨' 입력해줘"},
    {"id": "naver_s_01",   "command": "검색어 입력창을 클릭해줘"},
    {"id": "musinsa_m_01", "command": "검색창 클릭해줘"},
    {"id": "musinsa_d_01", "command": "이 상품 페이지 설명해줘"},
    {"id": "youtube_m_01", "command": "검색창에 '먹방' 입력해줘"},
    {"id": "sheet_01",     "command": "이 스프레드시트 내용 설명해줘"},
]

print("=" * 60)
print("OmniParser-v2.0 — eval 이미지 UI 요소 감지")
print("=" * 60)

yolo = YOLO(f"{OMNI_DIR}/icon_detect/model.pt")

def load_font(size=16):
    for p in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()
font = load_font()

# 이미 처리한 이미지 중복 제거
seen = {}
for sc in SCENARIOS:
    fname = ID_TO_IMG[sc["id"]]
    if fname not in seen:
        seen[fname] = sc

print(f"\n{len(seen)}개 이미지 처리 중...\n")

all_results = {}
for fname, sc in seen.items():
    img_path = IMG_BASE / fname
    img = Image.open(img_path).convert("RGB")
    W, H = img.size

    results = yolo(img_path, conf=0.05, iou=0.7, verbose=False)
    boxes = results[0].boxes
    draw = ImageDraw.Draw(img)

    detections = []
    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        conf = float(box.conf[0])
        bbox_norm = [round(x1/W*1000), round(y1/H*1000),
                     round(x2/W*1000), round(y2/H*1000)]

        draw.rectangle([x1, y1, x2, y2], outline=(37, 99, 235), width=2)
        label = f"{i+1}"
        lx,ly,lx2,ly2 = draw.textbbox((0,0), label, font=font)
        draw.rectangle([x1, y1, x1+(lx2-lx)+4, y1+(ly2-ly)+4], fill=(37,99,235))
        draw.text((x1+2, y1+2), label, fill="white", font=font)
        detections.append({"idx": i+1, "bbox_norm": bbox_norm, "conf": round(conf,3)})

    # 커맨드 헤더
    header_img = Image.new("RGB", (W, H+50), (30,30,30))
    header_img.paste(img, (0, 50))
    hd = ImageDraw.Draw(header_img)
    hd.text((8, 14), f"[OmniParser] {sc['command']} — {len(detections)}개 감지", fill="white", font=font)

    out_path = OUT_DIR / f"{sc['id']}_omni.png"
    header_img.save(out_path)
    all_results[fname] = {"scenario_id": sc["id"], "command": sc["command"],
                          "n_detected": len(detections), "detections": detections}
    print(f"  {sc['id']:20s} {len(detections):3d}개 감지 → {out_path.name}")

json_path = OUT_DIR / "omni_eval_detections.json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print(f"\n✓ 완료: {OUT_DIR}/")
print(f"  JSON: {json_path}")
