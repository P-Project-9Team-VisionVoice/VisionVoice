"""
raw_samples.json → clean_samples.json
- 이상 bbox 제거 (범위 0~1000 초과)
- 중복 샘플 제거 (같은 이미지+타겟+액션)
- action 분포 요약 출력
"""
import json
from pathlib import Path

DATA_PATH = Path("/home/devlofi/HyeWon/finetune/dataset/raw_samples.json")
OUT_PATH  = Path("/home/devlofi/HyeWon/finetune/dataset/clean_samples.json")

with open(DATA_PATH, encoding="utf-8") as f:
    samples = json.load(f)

print(f"원본: {len(samples)}개")

# 1. 이상 bbox 제거
def valid_bbox(b, action):
    if action in ("explain", "scroll"):
        return True  # 전체화면 bbox는 허용
    if len(b) != 4:
        return False
    return all(0 <= v <= 1000 for v in b) and (b[2]-b[0]) >= 5 and (b[3]-b[1]) >= 5

filtered = [s for s in samples if valid_bbox(s.get("bbox", []), s.get("action", ""))]
print(f"이상 bbox 제거 후: {len(filtered)}개 (제거: {len(samples)-len(filtered)}개)")

# 2. 중복 제거 (같은 이미지+타겟+액션)
seen = set()
deduped = []
for s in filtered:
    key = (s.get("image", ""), s.get("target", ""), s.get("action", ""))
    if key not in seen:
        seen.add(key)
        deduped.append(s)

print(f"중복 제거 후: {len(deduped)}개 (제거: {len(filtered)-len(deduped)}개)")

# 3. id 재부여
for i, s in enumerate(deduped):
    s["id"] = f"vv_{i:04d}"

# 4. action 분포
from collections import Counter
dist = Counter(s["action"] for s in deduped)
print(f"\n[Action 분포]")
for act, cnt in sorted(dist.items(), key=lambda x: -x[1]):
    print(f"  {act:10s} {cnt:4d} ({100*cnt/len(deduped):.1f}%)")

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(deduped, f, ensure_ascii=False, indent=2)

print(f"\n✓ 저장: {OUT_PATH} ({len(deduped)}개)")
