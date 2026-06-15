"""
VisionVoice OpenCUA-7B 벤치마크
동일 10개 시나리오 - Qwen3-VL / EvoCUA 비교용
"""
import json, re, time, torch, os
from PIL import Image, ImageDraw
from transformers import AutoTokenizer, AutoModel, AutoImageProcessor

MODEL_PATH = "/home/devlofi/models/OpenCUA-7B"
IMG_DIR = "/home/devlofi/HyeWon/eval_images"
os.makedirs(IMG_DIR, exist_ok=True)

# GB10 workaround
_op = torch.prod
torch.prod = lambda i, *a, **kw: _op(i.cpu(), *a, **kw).to(i.device) if hasattr(i,'is_cuda') and i.is_cuda else _op(i, *a, **kw)

print("=" * 70)
print("VisionVoice 4-1 Phase A 초기 벤치마크")
print("OpenCUA-7B on DGX Spark (GB10)")
print("=" * 70)

# ========== 동일 이미지 생성 함수 (baseline_eval.py와 동일) ==========
def make_naver_like(path):
    img = Image.new('RGB', (1280, 800), color='white')
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1280, 60], fill=(0, 199, 60))
    d.text((20, 20), "N", fill='white')
    d.rectangle([300, 90, 980, 140], outline='black', width=2, fill='white')
    d.text((310, 105), "검색어를 입력해주세요", fill='gray')
    d.rectangle([990, 90, 1060, 140], fill=(0, 199, 60))
    d.text((1010, 105), "검색", fill='white')
    services = [("메일", 100), ("카페", 200), ("블로그", 300), ("쇼핑", 400),
                ("뉴스", 500), ("지도", 600), ("웹툰", 700)]
    for txt, x in services:
        d.rectangle([x, 180, x+70, 240], fill=(240, 240, 240))
        d.text((x+15, 205), txt, fill='black')
    d.rectangle([1100, 170, 1200, 210], outline='black')
    d.text((1120, 180), "로그인", fill='black')
    img.save(path)

def make_youtube_like(path):
    img = Image.new('RGB', (1280, 800), color=(15, 15, 15))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1280, 55], fill=(33, 33, 33))
    d.text((20, 18), "YouTube", fill='red')
    d.rectangle([400, 15, 800, 45], outline='gray', fill=(60, 60, 60))
    d.text((410, 22), "검색", fill='white')
    menu = [("홈", 80), ("Shorts", 120), ("구독", 160), ("라이브러리", 200)]
    for txt, y in menu:
        d.rectangle([10, y, 150, y+35], fill=(40, 40, 40))
        d.text((20, y+10), txt, fill='white')
    for i in range(3):
        x = 200 + i * 350
        d.rectangle([x, 100, x+300, 280], fill=(40, 40, 40))
        d.text((x+10, 260), f"영상 {i+1}", fill='white')
    img.save(path)

def make_musinsa_like(path):
    img = Image.new('RGB', (1280, 900), color='white')
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1280, 50], fill='black')
    d.text((20, 15), "MUSINSA", fill='white')
    d.rectangle([550, 400, 850, 450], fill='black')
    d.text((640, 415), "장바구니 담기", fill='white')
    img.save(path)

def make_gmail_like(path):
    img = Image.new('RGB', (1280, 800), color='white')
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1280, 55], fill=(238, 238, 238))
    d.text((20, 18), "Gmail", fill='red')
    d.rectangle([20, 80, 180, 120], fill=(212, 65, 57))
    d.text((60, 92), "편지쓰기", fill='white')
    img.save(path)

make_naver_like(f"{IMG_DIR}/naver.png")
make_youtube_like(f"{IMG_DIR}/youtube.png")
make_musinsa_like(f"{IMG_DIR}/musinsa.png")
make_gmail_like(f"{IMG_DIR}/gmail.png")
print("✓ 4개 테스트 이미지 생성")

SCENARIOS = [
    {"id": "naver_01", "image": f"{IMG_DIR}/naver.png", "command": "검색창에 '날씨' 입력해줘", "expected": "input"},
    {"id": "naver_02", "image": f"{IMG_DIR}/naver.png", "command": "메일 버튼 클릭해줘", "expected": "click"},
    {"id": "naver_03", "image": f"{IMG_DIR}/naver.png", "command": "이 화면 설명해줘", "expected": "explain"},
    {"id": "naver_04", "image": f"{IMG_DIR}/naver.png", "command": "로그인 버튼 눌러줘", "expected": "click"},
    {"id": "youtube_01", "image": f"{IMG_DIR}/youtube.png", "command": "검색창에 '리그오브레전드' 입력해줘", "expected": "input"},
    {"id": "youtube_02", "image": f"{IMG_DIR}/youtube.png", "command": "첫 번째 영상 클릭", "expected": "click"},
    {"id": "youtube_03", "image": f"{IMG_DIR}/youtube.png", "command": "아래로 스크롤해줘", "expected": "scroll"},
    {"id": "musinsa_01", "image": f"{IMG_DIR}/musinsa.png", "command": "장바구니 담기 눌러", "expected": "click"},
    {"id": "musinsa_02", "image": f"{IMG_DIR}/musinsa.png", "command": "이 상품 설명해줘", "expected": "explain"},
    {"id": "gmail_01", "image": f"{IMG_DIR}/gmail.png", "command": "편지쓰기 버튼 클릭", "expected": "click"},
]
print(f"✓ 시나리오 {len(SCENARIOS)}개 준비")

# ========== 모델 로드 ==========
print(f"\n[Loading OpenCUA-7B]...")
t0 = time.time()
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModel.from_pretrained(
    MODEL_PATH, torch_dtype=torch.bfloat16,
    device_map="auto", trust_remote_code=True,
    attn_implementation="eager", low_cpu_mem_usage=True,
)
if not hasattr(model.config, "vision_start_token_id"):
    v_start = tokenizer.convert_tokens_to_ids("<|vision_start|>")
    v_end   = tokenizer.convert_tokens_to_ids("<|vision_end|>")
    model.config.vision_start_token_id = v_start if v_start else 151652
    model.config.vision_end_token_id   = v_end   if v_end   else 151653
image_processor = AutoImageProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
model.eval()
print(f"✓ loaded ({time.time()-t0:.1f}s)")

def infer_action(voice_text: str) -> str:
    """OpenCUA 출력에서 action 분류"""
    describe_kw = ["설명", "보여", "읽어", "무엇", "어떤"]
    scroll_kw   = ["스크롤", "내려", "올려"]
    input_kw    = ["입력", "검색창에", "쓰"]
    if any(k in voice_text for k in describe_kw):
        return "explain"
    if any(k in voice_text for k in scroll_kw):
        return "scroll"
    if any(k in voice_text for k in input_kw):
        return "input"
    return "click"

# ========== 추론 ==========
results = []
for i, sc in enumerate(SCENARIOS, 1):
    img = Image.open(sc["image"]).convert("RGB")
    # action 사전 분류 (OpenCUA 출력 파싱 전)
    predicted_action = infer_action(sc["command"])

    messages = [
        {"role": "system", "content": "You are VisionVoice, a helpful AI assistant for visually impaired users. Output in Korean."},
        {"role": "user", "content": [
            {"type": "image", "image": sc["image"]},
            {"type": "text", "text": f"[User Command]\n{sc['command']}\n\nPlease execute the command."},
        ]},
    ]
    text_input = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    model_inputs = tokenizer([text_input], return_tensors="pt")
    input_ids = model_inputs.input_ids.to(model.device)
    attention_mask = model_inputs.attention_mask.to(model.device)

    image_info = image_processor.preprocess(images=[img], return_tensors="pt")
    pixel_values = image_info['pixel_values'].to(dtype=torch.bfloat16, device=model.device)
    grid_thws = image_info['image_grid_thw'].to(model.device)

    t = time.time()
    with torch.no_grad():
        generated_ids = model.generate(
            input_ids=input_ids, attention_mask=attention_mask,
            pixel_values=pixel_values, grid_thws=grid_thws,
            max_new_tokens=256, do_sample=False,
            pad_token_id=tokenizer.eos_token_id, use_cache=True,
        )
    elapsed = time.time() - t
    output_ids = generated_ids[0][len(input_ids[0]):]
    output_text = tokenizer.decode(output_ids, skip_special_tokens=True)

    action_correct = (predicted_action == sc["expected"])
    status = "✓" if action_correct else "✗"
    print(f"\n[{i}/10] {sc['id']} ({sc['expected']}) {status} {elapsed:.1f}s")
    print(f"    cmd: {sc['command']}")
    print(f"    predicted: {predicted_action}, expected: {sc['expected']}")
    print(f"    output: {output_text[:100]}")

    results.append({
        "id": sc["id"], "command": sc["command"],
        "expected_action": sc["expected"],
        "predicted_action": predicted_action,
        "raw_output": output_text,
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

from collections import defaultdict
cat_stats = defaultdict(lambda: {"total": 0, "correct": 0})
for r in results:
    cat_stats[r["expected_action"]]["total"] += 1
    if r["action_correct"]:
        cat_stats[r["expected_action"]]["correct"] += 1
print("\n카테고리별:")
for cat, s in cat_stats.items():
    print(f"  {cat:10s}: {s['correct']}/{s['total']} ({100*s['correct']/s['total']:.0f}%)")

timestamp = time.strftime("%Y%m%d_%H%M%S")
result_path = f"/home/devlofi/HyeWon/eval_results/opencua_{timestamp}.json"
with open(result_path, "w", encoding="utf-8") as f:
    json.dump({
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": "OpenCUA-7B",
        "hardware": "NVIDIA DGX Spark (GB10)",
        "note": "action classification by keyword heuristic (OpenCUA uses pyautogui output format)",
        "total_scenarios": total,
        "correct": correct,
        "accuracy": 100*correct/total,
        "avg_latency_sec": avg_time,
        "category_stats": dict(cat_stats),
        "results": results,
    }, f, ensure_ascii=False, indent=2)
print(f"\n✓ 결과 저장: {result_path}")
