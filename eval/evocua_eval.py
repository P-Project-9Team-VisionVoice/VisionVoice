"""
VisionVoice 4-1학기 초기 벤치마크
Qwen3-VL-8B vs 1학기 Qwen2-VL-7B 비교용 초기 측정

10개 미니 시나리오 (합성 이미지 기반)
- 1학기 4-site 평가의 축소판
- 4-1학기 Phase A 착수 시점 기록용
"""
import json
import time
import torch

# GB10 prod workaround
_op = torch.prod
torch.prod = lambda i, *a, **kw: _op(i.cpu(), *a, **kw).to(i.device) if hasattr(i,'is_cuda') and i.is_cuda else _op(i, *a, **kw)
_tp = torch.Tensor.prod
torch.Tensor.prod = lambda self, *a, **kw: _tp(self.cpu(), *a, **kw).to(self.device) if self.is_cuda else _tp(self, *a, **kw)

from PIL import Image, ImageDraw, ImageFont
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor

MODEL_PATH = "/home/devlofi/models/EvoCUA-8B"
PROCESSOR_PATH = "/home/devlofi/models/Qwen3-VL-8B-Instruct"
IMG_DIR = "/home/devlofi/HyeWon/eval_images"
import os
os.makedirs(IMG_DIR, exist_ok=True)

print("=" * 70)
print("VisionVoice 4-1 Phase A 초기 벤치마크")
print("EvoCUA-8B on DGX Spark (GB10)")
print("=" * 70)

# ========== 시나리오 정의 ==========
# 10개 시나리오: 4-1 Phase A 초기 미니 평가 데이터셋
# 기능별 분포: input(2), click(4), scroll(1), navigate(1), explain(2)

SCENARIOS = []

def make_naver_like(path):
    """네이버 메인 유사 레이아웃"""
    img = Image.new('RGB', (1280, 800), color='white')
    d = ImageDraw.Draw(img)
    # 헤더
    d.rectangle([0, 0, 1280, 60], fill=(0, 199, 60))
    d.text((20, 20), "N", fill='white')
    # 검색창
    d.rectangle([300, 90, 980, 140], outline='black', width=2, fill='white')
    d.text((310, 105), "검색어를 입력해주세요", fill='gray')
    d.rectangle([990, 90, 1060, 140], fill=(0, 199, 60))
    d.text((1010, 105), "검색", fill='white')
    # 서비스 아이콘
    services = [("메일", 100), ("카페", 200), ("블로그", 300), ("쇼핑", 400),
                ("뉴스", 500), ("지도", 600), ("웹툰", 700)]
    for txt, x in services:
        d.rectangle([x, 180, x+70, 240], fill=(240, 240, 240))
        d.text((x+15, 205), txt, fill='black')
    # 뉴스 영역
    d.text((100, 300), "주요 뉴스", fill='black')
    d.rectangle([100, 330, 600, 500], outline='gray')
    d.text((120, 400), "오늘의 이슈", fill='black')
    # 로그인
    d.rectangle([1100, 170, 1200, 210], outline='black')
    d.text((1120, 180), "로그인", fill='black')
    img.save(path)

def make_youtube_like(path):
    """유튜브 유사 레이아웃"""
    img = Image.new('RGB', (1280, 800), color=(15, 15, 15))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1280, 55], fill=(33, 33, 33))
    d.text((20, 18), "YouTube", fill='red')
    d.rectangle([400, 15, 800, 45], outline='gray', fill=(60, 60, 60))
    d.text((410, 22), "검색", fill='white')
    # 사이드바
    menu = [("홈", 80), ("Shorts", 120), ("구독", 160), ("라이브러리", 200)]
    for txt, y in menu:
        d.rectangle([10, y, 150, y+35], fill=(40, 40, 40))
        d.text((20, y+10), txt, fill='white')
    # 영상 카드
    for i in range(3):
        x = 200 + i * 350
        d.rectangle([x, 100, x+300, 280], fill=(40, 40, 40))
        d.rectangle([x, 100, x+300, 250], fill=(80, 80, 80))
        d.text((x+10, 260), f"영상 {i+1}", fill='white')
    img.save(path)

def make_musinsa_like(path):
    """무신사 유사 레이아웃 (상품 페이지)"""
    img = Image.new('RGB', (1280, 900), color='white')
    d = ImageDraw.Draw(img)
    # 네비
    d.rectangle([0, 0, 1280, 50], fill='black')
    d.text((20, 15), "MUSINSA", fill='white')
    d.text((1200, 15), "장바구니", fill='white')
    # 상품 이미지
    d.rectangle([100, 100, 500, 600], fill=(220, 220, 220))
    d.text((250, 350), "상품 이미지", fill='black')
    # 정보
    d.text((550, 120), "브랜드명", fill='gray')
    d.text((550, 150), "오버사이즈 티셔츠", fill='black')
    d.text((550, 200), "29,000원", fill='black')
    # 사이즈 버튼
    for i, s in enumerate(["S", "M", "L", "XL"]):
        x = 550 + i * 60
        d.rectangle([x, 260, x+50, 310], outline='black')
        d.text((x+18, 278), s, fill='black')
    # CTA 버튼
    d.rectangle([550, 400, 850, 450], fill='black')
    d.text((640, 415), "장바구니 담기", fill='white')
    d.rectangle([860, 400, 1100, 450], fill='red')
    d.text((930, 415), "바로 구매", fill='white')
    img.save(path)

def make_gmail_like(path):
    """Gmail 유사 레이아웃"""
    img = Image.new('RGB', (1280, 800), color='white')
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1280, 55], fill=(238, 238, 238))
    d.text((20, 18), "Gmail", fill='red')
    # 편지쓰기 버튼
    d.rectangle([20, 80, 180, 120], fill=(212, 65, 57))
    d.text((60, 92), "편지쓰기", fill='white')
    # 메일 리스트
    for i in range(5):
        y = 150 + i * 60
        d.rectangle([200, y, 1250, y+50], outline='gray')
        d.text((220, y+10), f"발신자 {i+1}", fill='black')
        d.text((400, y+10), f"제목: 테스트 메일 {i+1}", fill='black')
        d.text((1100, y+10), "오전 10:0" + str(i), fill='gray')
    img.save(path)

# 이미지 생성
make_naver_like(f"{IMG_DIR}/naver.png")
make_youtube_like(f"{IMG_DIR}/youtube.png")
make_musinsa_like(f"{IMG_DIR}/musinsa.png")
make_gmail_like(f"{IMG_DIR}/gmail.png")
print("✓ 4개 테스트 이미지 생성")

# 10개 시나리오
SCENARIOS = [
    {"id": "naver_01", "image": f"{IMG_DIR}/naver.png", "command": "검색창에 '날씨' 입력해줘",
     "expected": {"action": "input"}, "category": "input"},
    {"id": "naver_02", "image": f"{IMG_DIR}/naver.png", "command": "메일 버튼 클릭해줘",
     "expected": {"action": "click"}, "category": "click"},
    {"id": "naver_03", "image": f"{IMG_DIR}/naver.png", "command": "이 화면 설명해줘",
     "expected": {"action": "explain"}, "category": "explain"},
    {"id": "naver_04", "image": f"{IMG_DIR}/naver.png", "command": "로그인 버튼 눌러줘",
     "expected": {"action": "click"}, "category": "click"},
    {"id": "youtube_01", "image": f"{IMG_DIR}/youtube.png", "command": "검색창에 '리그오브레전드' 입력해줘",
     "expected": {"action": "input"}, "category": "input"},
    {"id": "youtube_02", "image": f"{IMG_DIR}/youtube.png", "command": "첫 번째 영상 클릭",
     "expected": {"action": "click"}, "category": "click"},
    {"id": "youtube_03", "image": f"{IMG_DIR}/youtube.png", "command": "아래로 스크롤해줘",
     "expected": {"action": "scroll"}, "category": "scroll"},
    {"id": "musinsa_01", "image": f"{IMG_DIR}/musinsa.png", "command": "장바구니 담기 눌러",
     "expected": {"action": "click"}, "category": "click"},
    {"id": "musinsa_02", "image": f"{IMG_DIR}/musinsa.png", "command": "이 상품 설명해줘",
     "expected": {"action": "explain"}, "category": "explain"},
    {"id": "gmail_01", "image": f"{IMG_DIR}/gmail.png", "command": "편지쓰기 버튼 클릭",
     "expected": {"action": "click"}, "category": "click"},
]

print(f"✓ 시나리오 {len(SCENARIOS)}개 준비")

# ========== 모델 로드 ==========
print(f"\n[Loading Qwen3-VL-8B]...")
t0 = time.time()
processor = AutoProcessor.from_pretrained(PROCESSOR_PATH, trust_remote_code=True)
model = Qwen3VLForConditionalGeneration.from_pretrained(
    MODEL_PATH, dtype=torch.bfloat16, device_map="cuda:0",
    trust_remote_code=True, attn_implementation="sdpa"
)
model.eval()
print(f"✓ loaded ({time.time()-t0:.1f}s)")

# ========== 추론 ==========
SYSTEM = (
    "당신은 시각장애인을 돕는 웹 브라우저 제어 AI입니다. "
    "사용자 명령을 분석하여 JSON으로만 응답하세요.\n"
    "형식: {\"action\": \"click|input|scroll|explain|navigate\", "
    "\"target\": \"요소명\", \"bbox\": [x1,y1,x2,y2] (0~1000 정규화), "
    "\"speech\": \"한국어 답변\"}"
)

results = []
for i, sc in enumerate(SCENARIOS, 1):
    img = Image.open(sc["image"]).convert("RGB")
    messages = [{"role": "user", "content": [
        {"type": "image", "image": sc["image"]},
        {"type": "text", "text": f"{SYSTEM}\n\n명령: \"{sc['command']}\""}
    ]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[img], padding=True, return_tensors="pt").to(model.device)

    t = time.time()
    with torch.no_grad():
        gen_ids = model.generate(**inputs, max_new_tokens=1500, do_sample=False)
    elapsed = time.time() - t

    trimmed = [o[len(inp):] for inp, o in zip(inputs.input_ids, gen_ids)]
    output_raw = processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()

    # JSON 파싱 시도
    import re
    json_match = re.search(r'\{.*\}', output_raw, re.DOTALL)
    parsed = None
    action_correct = False
    try:
        if json_match:
            parsed = json.loads(json_match.group(0))
            action_correct = (parsed.get("action") == sc["expected"]["action"])
    except Exception:
        pass

    status = "✓" if action_correct else "✗"
    print(f"\n[{i}/10] {sc['id']} ({sc['category']}) {status} {elapsed:.1f}s")
    print(f"    cmd: {sc['command']}")
    print(f"    expected: {sc['expected']['action']}, got: {parsed.get('action') if parsed else 'PARSE_FAIL'}")
    if parsed:
        print(f"    bbox: {parsed.get('bbox')}, target: {parsed.get('target')}")
    else:
        print(f"    raw: {output_raw[:150]}")

    results.append({
        "id": sc["id"],
        "category": sc["category"],
        "command": sc["command"],
        "expected_action": sc["expected"]["action"],
        "predicted_action": parsed.get("action") if parsed else None,
        "bbox": parsed.get("bbox") if parsed else None,
        "target": parsed.get("target") if parsed else None,
        "speech": parsed.get("speech") if parsed else None,
        "raw_output": output_raw,
        "elapsed_sec": elapsed,
        "action_correct": action_correct,
    })

# ========== 요약 ==========
print("\n" + "=" * 70)
print("결과 요약")
print("=" * 70)
total = len(results)
correct = sum(1 for r in results if r["action_correct"])
avg_time = sum(r["elapsed_sec"] for r in results) / total

print(f"\n전체 정확도 (Action 분류): {correct}/{total} = {100*correct/total:.1f}%")
print(f"평균 응답 속도: {avg_time:.2f}s")

# 카테고리별
from collections import defaultdict
cat_stats = defaultdict(lambda: {"total": 0, "correct": 0})
for r in results:
    cat_stats[r["category"]]["total"] += 1
    if r["action_correct"]:
        cat_stats[r["category"]]["correct"] += 1

print("\n카테고리별:")
for cat, s in cat_stats.items():
    print(f"  {cat:10s}: {s['correct']}/{s['total']} ({100*s['correct']/s['total']:.0f}%)")

# 1학기 비교
print("\n[1학기 비교]")
print(f"{'지표':<25s} {'1학기 Qwen2-VL':<20s} {'4-1 EvoCUA-8B':<20s}")
print(f"{'-'*70}")
print(f"{'임무 성공률':<25s} {'65% (13/20)':<20s} {f'{100*correct/total:.0f}% ({correct}/{total})':<20s}")
print(f"{'평균 응답 속도':<25s} {'30.7s':<20s} {f'{avg_time:.1f}s':<20s}")
print(f"{'실행 환경':<25s} {'Colab T4':<20s} {'DGX Spark GB10':<20s}")

# 타임스탬프 포함 결과 저장
timestamp = time.strftime("%Y%m%d_%H%M%S")
result_path = f"/home/devlofi/HyeWon/eval_results/evocua_{timestamp}.json"
with open(result_path, "w", encoding="utf-8") as f:
    json.dump({
        "semester": "4-1 Phase A initial benchmark",
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": "EvoCUA-8B-20260105",
        "hardware": "NVIDIA DGX Spark (GB10)",
        "total_scenarios": total,
        "correct": correct,
        "accuracy": 100*correct/total,
        "avg_latency_sec": avg_time,
        "category_stats": dict(cat_stats),
        "results": results,
    }, f, ensure_ascii=False, indent=2)

print(f"\n✓ 결과 저장: {result_path}")
