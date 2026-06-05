"""
VisionVoice 데이터셋 품질 분석
raw_samples.json 통계 + 시각화 차트 생성
"""
import json
import numpy as np
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

DATA_PATH = Path("/home/devlofi/HyeWon/finetune/dataset/raw_samples.json")
OUT_DIR   = Path("/home/devlofi/HyeWon/finetune/dataset/quality_report")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 한글 폰트
for fp in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
    if Path(fp).exists():
        fm.fontManager.addfont(fp)
        plt.rcParams["font.family"] = "Noto Sans CJK JP" if "CJK" in fp else "DejaVu Sans"
        break
plt.rcParams["axes.unicode_minus"] = False

with open(DATA_PATH, encoding="utf-8") as f:
    samples = json.load(f)

print(f"\n{'='*60}")
print(f"VisionVoice 데이터셋 품질 분석")
print(f"파일: {DATA_PATH}")
print(f"{'='*60}")
print(f"총 샘플 수: {len(samples)}")

# ── 1. 사이트별 분포 ──
site_counts = Counter(Path(s.get("image", "")).stem for s in samples)
print(f"\n[사이트별 샘플 수] ({len(site_counts)}개 사이트)")
for site, cnt in sorted(site_counts.items(), key=lambda x: -x[1]):
    bar = "█" * (cnt // 5)
    print(f"  {site:25s} {cnt:4d}  {bar}")

# ── 2. Action 분포 ──
action_counts = Counter(s.get("action", "unknown") for s in samples)
print(f"\n[Action 분포]")
for action, cnt in sorted(action_counts.items(), key=lambda x: -x[1]):
    pct = cnt / len(samples) * 100
    bar = "█" * (cnt // 10)
    print(f"  {action:10s} {cnt:4d} ({pct:.1f}%)  {bar}")

# ── 3. BBox 유효성 ──
widths, heights = [], []
invalid_bbox = 0
for s in samples:
    b = s.get("bbox", [])
    if len(b) == 4 and all(0 <= v <= 1000 for v in b):
        widths.append(b[2] - b[0])
        heights.append(b[3] - b[1])
    else:
        invalid_bbox += 1

print(f"\n[BBox 유효성]")
print(f"  유효한 bbox:       {len(widths)}/{len(samples)}")
print(f"  범위 이상 bbox:    {invalid_bbox}")

if widths:
    print(f"\n[BBox 크기 통계 (0~1000 기준)]")
    print(f"  너비:  min={min(widths):.0f}  max={max(widths):.0f}  "
          f"mean={np.mean(widths):.0f}  median={np.median(widths):.0f}")
    print(f"  높이:  min={min(heights):.0f}  max={max(heights):.0f}  "
          f"mean={np.mean(heights):.0f}  median={np.median(heights):.0f}")

    too_small = sum(1 for w, h in zip(widths, heights) if w < 10 or h < 5)
    fullscreen = sum(1 for w, h in zip(widths, heights) if w > 800 and h > 800)
    print(f"  너무 작은 bbox (w<10 or h<5):   {too_small}  ← 제거 권장")
    print(f"  전체화면 bbox (w>800, h>800):    {fullscreen}  ← explain/scroll 정상")

# ── 4. 명령어 다양성 ──
commands = [s.get("command", "") for s in samples]
unique_cmds = len(set(commands))
print(f"\n[명령어 다양성]")
print(f"  고유 명령어: {unique_cmds}/{len(commands)} ({100*unique_cmds/len(commands):.1f}%)")

# ── 5. 중복 샘플 ──
seen, duplicates = set(), 0
for s in samples:
    key = (s.get("image", ""), s.get("target", ""), s.get("action", ""))
    if key in seen:
        duplicates += 1
    seen.add(key)
print(f"  중복 샘플 (같은 이미지+타겟+액션): {duplicates}  ← 제거 권장")

# ── 이상 샘플 예시 ──
small = [s for s in samples if len(s.get("bbox", [])) == 4
         and (s["bbox"][2]-s["bbox"][0] < 10 or s["bbox"][3]-s["bbox"][1] < 5)
         and s.get("action") not in ("explain", "scroll")]
if small:
    print(f"\n[이상 샘플 예시 — bbox 너무 작음]")
    for s in small[:5]:
        print(f"  {s['id']:35s} bbox={s['bbox']}  target={s.get('target','')[:30]}")

# ── 시각화 차트 ──
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle(f"VisionVoice Dataset Quality Report  (N={len(samples)})", fontsize=13, fontweight="bold")

# 사이트별 바 차트 (상위 20개)
top_sites = sorted(site_counts.items(), key=lambda x: -x[1])[:20]
s_names = [k for k, _ in top_sites]
s_cnts  = [v for _, v in top_sites]
axes[0, 0].barh(s_names, s_cnts, color="#3b82f6")
axes[0, 0].set_title("사이트별 샘플 수 (상위 20)")
axes[0, 0].set_xlabel("샘플 수")
axes[0, 0].invert_yaxis()

# Action 파이차트
act_labels = list(action_counts.keys())
act_sizes  = [action_counts[l] for l in act_labels]
colors = ["#ef4444", "#3b82f6", "#6b7280", "#22c55e", "#a855f7"]
axes[0, 1].pie(act_sizes, labels=act_labels, autopct="%1.1f%%",
               colors=colors[:len(act_labels)], startangle=90)
axes[0, 1].set_title("Action 분포")

# BBox 너비 히스토그램
if widths:
    axes[1, 0].hist(widths, bins=60, color="#f59e0b", edgecolor="white")
    axes[1, 0].set_title("BBox 너비 분포 (0~1000)")
    axes[1, 0].set_xlabel("너비")
    axes[1, 0].set_ylabel("빈도")
    axes[1, 0].axvline(np.median(widths), color="red", linestyle="--", label=f"중앙값={np.median(widths):.0f}")
    axes[1, 0].legend()

    axes[1, 1].hist(heights, bins=60, color="#8b5cf6", edgecolor="white")
    axes[1, 1].set_title("BBox 높이 분포 (0~1000)")
    axes[1, 1].set_xlabel("높이")
    axes[1, 1].set_ylabel("빈도")
    axes[1, 1].axvline(np.median(heights), color="red", linestyle="--", label=f"중앙값={np.median(heights):.0f}")
    axes[1, 1].legend()

plt.tight_layout()
chart_path = OUT_DIR / "quality_report.png"
plt.savefig(chart_path, dpi=150, bbox_inches="tight")
print(f"\n✓ 차트 저장: {chart_path}")
print(f"✓ 분석 완료")
