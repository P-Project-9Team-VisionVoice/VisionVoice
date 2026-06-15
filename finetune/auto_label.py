"""
Qwen3-VL로 한국 웹 스크린샷 자동 라벨링
15개 이미지 → (command, bbox, action) 쌍 생성
"""
import json
import re
import time
import torch
from pathlib import Path
from PIL import Image
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor


MODEL_PATH = "/home/devlofi/models/Qwen3-VL-8B-Instruct"
IMG_DIR = Path("/home/devlofi/HyeWon/taining_datasets")
OUT_PATH = Path("/home/devlofi/HyeWon/finetune/dataset/train.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

LABEL_PROMPT = """이 웹페이지 스크린샷에서 사용자가 클릭하거나 입력할 수 있는 UI 요소들을 찾아줘.
각 요소에 대해 다음 형식으로 JSON 배열을 출력해줘. 반드시 JSON만 출력하고 다른 말은 하지 마.

[
  {
    "action": "click 또는 input 또는 scroll 또는 explain",
    "target": "요소 이름 (한국어)",
    "bbox": [x1, y1, x2, y2],
    "command": "시각장애인이 할 법한 자연스러운 한국어 음성 명령",
    "speech": "AI가 행동 후 말할 한국어 안내 멘트"
  }
]

규칙:
- bbox는 0~1000 사이의 정규화된 좌표 (이미지 전체 크기를 1000으로 봤을 때의 위치)
- 예: 화면 정중앙이면 [500, 500, 550, 530] 형태
- 화면에 보이는 요소만 포함
- 최소 5개, 최대 15개 요소
- command는 다양하게 ("~해줘", "~눌러줘", "~클릭해줘", "~열어줘" 등)
- explain 액션 1개 반드시 포함 (전체 화면 설명)
- scroll 액션 1개 반드시 포함"""

SYSTEM = "당신은 시각장애인을 위한 웹 접근성 데이터 라벨러입니다. 웹 스크린샷을 분석하여 UI 요소의 위치와 상호작용 방법을 정확하게 JSON으로 출력합니다."


def normalize_bbox(bbox, w, h):
    """모델이 이미 0~1000으로 줬으면 그대로, 픽셀 좌표면 변환"""
    x1, y1, x2, y2 = bbox
    # 값이 이미 0~1000 범위면 그대로 사용
    if max(x1, y1, x2, y2) <= 1000:
        return [
            max(0, min(1000, round(x1))),
            max(0, min(1000, round(y1))),
            max(0, min(1000, round(x2))),
            max(0, min(1000, round(y2))),
        ]
    # 픽셀 좌표면 정규화
    return [
        max(0, min(1000, round(x1 / w * 1000))),
        max(0, min(1000, round(y1 / h * 1000))),
        max(0, min(1000, round(x2 / w * 1000))),
        max(0, min(1000, round(y2 / h * 1000))),
    ]


def label_image(model, processor, img_path):
    img = Image.open(img_path).convert("RGB")
    w, h = img.size

    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": str(img_path)},
                {"type": "text", "text": LABEL_PROMPT},
            ],
        },
    ]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[img], return_tensors="pt").to(model.device)

    with torch.no_grad():
        gen_ids = model.generate(**inputs, max_new_tokens=1500, do_sample=False, temperature=None, top_p=None)
    trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, gen_ids)]
    output = processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()

    # JSON 파싱
    match = re.search(r'\[.*\]', output, re.DOTALL)
    if not match:
        print(f"  ⚠ JSON 파싱 실패: {output[:100]}")
        return []

    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        print(f"  ⚠ JSON 에러: {e}")
        return []

    # 정규화 + 학습 포맷 변환
    samples = []
    img_ref = str(img_path)
    for i, item in enumerate(items):
        if not all(k in item for k in ["action", "target", "bbox", "command", "speech"]):
            continue
        bbox = item["bbox"]
        if len(bbox) != 4:
            continue
        norm_bbox = normalize_bbox(bbox, w, h)
        samples.append({
            "id": f"{img_path.stem}_{i:02d}",
            "image": img_ref,
            "conversations": [
                {
                    "from": "system",
                    "value": (
                        "당신은 시각장애인을 위한 웹 브라우저 제어 AI입니다. "
                        "사용자의 음성 명령과 현재 화면 스크린샷을 분석하여 "
                        "수행해야 할 행동을 JSON 형식으로만 출력하세요.\n"
                        '출력 형식: {"action": "click|input|scroll|explain", '
                        '"target": "요소명", "bbox": [x1,y1,x2,y2], "speech": "한국어 안내"}'
                    ),
                },
                {
                    "from": "human",
                    "value": f"<image>\n{item['command']}",
                },
                {
                    "from": "gpt",
                    "value": json.dumps({
                        "action": item["action"],
                        "target": item["target"],
                        "bbox": norm_bbox,
                        "speech": item["speech"],
                    }, ensure_ascii=False),
                },
            ],
        })
    return samples


def main():
    images = sorted(IMG_DIR.glob("*.png")) + sorted(IMG_DIR.glob("*.jpg"))
    print(f"이미지 {len(images)}개 발견")

    print(f"\n모델 로딩: {MODEL_PATH}")
    processor = AutoProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.bfloat16,
        device_map="cuda:0",
        trust_remote_code=True,
        attn_implementation="sdpa",
    )
    model.eval()
    print("✓ 모델 로딩 완료\n")

    all_samples = []
    for img_path in images:
        print(f"[{len(all_samples)+1}] {img_path.name} 라벨링 중...")
        t = time.time()
        samples = label_image(model, processor, img_path)
        print(f"  → {len(samples)}개 샘플 생성 ({time.time()-t:.1f}s)")
        all_samples.extend(samples)

    # 90/10 분리
    import random
    random.shuffle(all_samples)
    split = int(len(all_samples) * 0.9)
    train, val = all_samples[:split], all_samples[split:]

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(train, f, ensure_ascii=False, indent=2)
    val_path = OUT_PATH.parent / "val.json"
    with open(val_path, "w", encoding="utf-8") as f:
        json.dump(val, f, ensure_ascii=False, indent=2)

    print(f"\n완료! 학습: {len(train)}개 / 검증: {len(val)}개")
    print(f"저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
