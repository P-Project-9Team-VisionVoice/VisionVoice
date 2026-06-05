"""
Draw VisionVoice bbox labels on screenshots for dataset review.

Supports both:
- dataset/raw_samples.json from collect_data.py
- dataset/train.json or val.json conversation format
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path("/home/devlofi/HyeWon/finetune")
DATA_DIR = ROOT / "dataset"
DEFAULT_INPUTS = [
    DATA_DIR / "raw_samples.json",
    DATA_DIR / "train.json",
]

COLORS = {
    "click": (239, 68, 68),
    "input": (37, 99, 235),
    "scroll": (107, 114, 128),
    "explain": (34, 197, 94),
    "navigate": (168, 85, 247),
}


def choose_default_input():
    for path in DEFAULT_INPUTS:
        if path.exists():
            return path
    raise FileNotFoundError(
        "No dataset found. Expected finetune/dataset/raw_samples.json or train.json."
    )


def load_font(size=18):
    for candidate in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def parse_assistant_json(sample):
    for turn in sample.get("conversations", []):
        if turn.get("from") == "gpt":
            try:
                return json.loads(turn.get("value", "{}"))
            except json.JSONDecodeError:
                return {}
    return {}


def normalize_sample(sample):
    if "conversations" in sample:
        answer = parse_assistant_json(sample)
        command = ""
        for turn in sample.get("conversations", []):
            if turn.get("from") == "human":
                command = turn.get("value", "").replace("<image>", "").strip()
                break
        return {
            "id": sample.get("id", ""),
            "image": sample.get("image", ""),
            "command": command,
            "action": answer.get("action", ""),
            "target": answer.get("target", ""),
            "bbox": answer.get("bbox", []),
            "speech": answer.get("speech", ""),
        }

    return {
        "id": sample.get("id", ""),
        "image": sample.get("image", ""),
        "command": sample.get("command", ""),
        "action": sample.get("action", ""),
        "target": sample.get("target", ""),
        "bbox": sample.get("bbox", []),
        "speech": sample.get("speech", ""),
    }


def resolve_image_path(image_value):
    path = Path(image_value)
    if path.is_absolute() and path.exists():
        return path

    candidates = [
        DATA_DIR / image_value,
        ROOT / image_value,
        DATA_DIR / path.name,
        Path("/home/devlofi/HyeWon") / image_value,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def denormalize_bbox(bbox, width, height):
    if len(bbox) != 4:
        return None
    x1, y1, x2, y2 = bbox
    return [
        round(x1 / 1000 * width),
        round(y1 / 1000 * height),
        round(x2 / 1000 * width),
        round(y2 / 1000 * height),
    ]


def is_fullscreen_bbox(bbox):
    if len(bbox) != 4:
        return False
    x1, y1, x2, y2 = bbox
    return x1 <= 5 and y1 <= 5 and x2 >= 995 and y2 >= 995


def draw_label(draw, xy, text, color, font):
    x1, y1, x2, y2 = xy
    draw.rectangle([x1, y1, x2, y2], outline=color, width=3)

    label = text[:70]
    left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
    label_w = right - left + 8
    label_h = bottom - top + 8
    label_y = max(0, y1 - label_h)
    draw.rectangle([x1, label_y, x1 + label_w, label_y + label_h], fill=color)
    draw.text((x1 + 4, label_y + 3), label, fill=(255, 255, 255), font=font)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DATA_DIR / "review")
    parser.add_argument("--include-fullscreen", action="store_true")
    args = parser.parse_args()

    input_path = args.input or choose_default_input()
    with open(input_path, encoding="utf-8") as f:
        raw = json.load(f)

    samples = [normalize_sample(item) for item in raw]
    samples = [
        item for item in samples
        if item.get("image") and isinstance(item.get("bbox"), list) and len(item["bbox"]) == 4
    ]

    args.output.mkdir(parents=True, exist_ok=True)
    grouped = defaultdict(list)
    for sample in samples:
        if not args.include_fullscreen and is_fullscreen_bbox(sample["bbox"]):
            continue
        grouped[sample["image"]].append(sample)

    font = load_font()
    rows = []
    for image_value, items in grouped.items():
        image_path = resolve_image_path(image_value)
        if not image_path.exists():
            print(f"missing image: {image_value}")
            continue

        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        draw = ImageDraw.Draw(image)

        for idx, sample in enumerate(items, 1):
            xy = denormalize_bbox(sample["bbox"], width, height)
            if not xy:
                continue
            color = COLORS.get(sample["action"], (245, 158, 11))
            text = f"{idx} {sample['action']} {sample['target']}"
            draw_label(draw, xy, text, color, font)
            rows.append({
                "id": sample["id"],
                "image": image_value,
                "action": sample["action"],
                "target": sample["target"],
                "command": sample["command"],
                "bbox": json.dumps(sample["bbox"], ensure_ascii=False),
            })

        out_name = f"{Path(image_value).stem}_boxes.png"
        out_path = args.output / out_name
        image.save(out_path)
        print(f"wrote {out_path} ({len(items)} boxes)")

    csv_path = args.output / "bbox_review_index.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "image", "action", "target", "command", "bbox"],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {csv_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
