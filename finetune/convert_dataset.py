"""
raw_samples.json → Qwen3-VL SFT 학습 포맷 변환
TRL SFTTrainer용 conversations 형식
"""
import json
import random
from pathlib import Path

INPUT = Path("/home/devlofi/HyeWon/finetune/dataset/raw_samples.json")
OUTPUT = Path("/home/devlofi/HyeWon/finetune/dataset/train.json")

SYSTEM_PROMPT = (
    "당신은 시각장애인을 위한 웹 브라우저 제어 AI입니다. "
    "사용자의 음성 명령과 현재 화면 스크린샷을 분석하여 "
    "수행해야 할 행동을 JSON 형식으로만 출력하세요.\n"
    "출력 형식: {\"action\": \"click|input|scroll|explain\", "
    "\"target\": \"요소명\", "
    "\"bbox\": [x1,y1,x2,y2], "
    "\"speech\": \"한국어 안내 멘트\"}"
)


def convert(sample):
    action_json = {
        "action": sample["action"],
        "target": sample["target"],
        "bbox": sample["bbox"],
        "speech": sample["speech"],
    }
    if "direction" in sample:
        action_json["direction"] = sample["direction"]

    return {
        "id": sample["id"],
        "image": sample["image"],
        "conversations": [
            {
                "from": "system",
                "value": SYSTEM_PROMPT,
            },
            {
                "from": "human",
                "value": f"<image>\n{sample['command']}",
            },
            {
                "from": "gpt",
                "value": json.dumps(action_json, ensure_ascii=False),
            },
        ],
    }


def main():
    with open(INPUT, encoding="utf-8") as f:
        raw = json.load(f)

    print(f"원본 샘플: {len(raw)}개")

    # explain 샘플은 speech가 없으면 필터
    converted = [convert(s) for s in raw if s.get("target")]

    # 셔플
    random.shuffle(converted)

    # train / val 분리 (90 / 10)
    split = int(len(converted) * 0.9)
    train = converted[:split]
    val = converted[split:]

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(train, f, ensure_ascii=False, indent=2)

    val_path = OUTPUT.parent / "val.json"
    with open(val_path, "w", encoding="utf-8") as f:
        json.dump(val, f, ensure_ascii=False, indent=2)

    print(f"학습 데이터: {len(train)}개 → {OUTPUT}")
    print(f"검증 데이터: {len(val)}개  → {val_path}")
    print(f"\n샘플 예시:")
    print(json.dumps(train[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
