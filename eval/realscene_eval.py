"""
VisionVoice 실제 스크린샷 기반 벤치마크
taining_datasets/ 실제 이미지 사용 (합성 아님)
Qwen3-VL / EvoCUA / OpenCUA 공통 시나리오
"""
import json, re, time, torch, os, sys
from qwen_vl_utils import process_vision_info
from PIL import Image
from pathlib import Path

IMG_DIR = Path("/home/devlofi/HyeWon/taining_datasets")

# ========== 모델 선택 ==========
MODEL_NAME = os.environ.get("VV_MODEL", "qwen3vl")  # qwen3vl | evocua | opencua | qwen2vl

if MODEL_NAME == "evocua":
    from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
    MODEL_PATH = "/home/devlofi/models/EvoCUA-8B"
    PROCESSOR_PATH = "/home/devlofi/models/Qwen3-VL-8B-Instruct"
    DISPLAY = "EvoCUA-8B"
    MAX_TOKENS = 1500
    USE_OPENCUA = False
    USE_QWEN2 = False
elif MODEL_NAME == "opencua":
    from transformers import AutoModel, AutoTokenizer
    MODEL_PATH = "/home/devlofi/models/OpenCUA-7B"
    PROCESSOR_PATH = MODEL_PATH
    DISPLAY = "OpenCUA-7B"
    MAX_TOKENS = 512
    USE_OPENCUA = True
    USE_QWEN2 = False
elif MODEL_NAME == "qwen2vl":
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    MODEL_PATH = "/home/devlofi/models/Qwen2-VL-7B-Instruct"
    PROCESSOR_PATH = MODEL_PATH
    DISPLAY = "Qwen2-VL-7B"
    MAX_TOKENS = 400
    USE_OPENCUA = False
    USE_QWEN2 = True
else:
    from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
    MODEL_PATH = "/home/devlofi/models/Qwen3-VL-8B-Instruct"
    PROCESSOR_PATH = "/home/devlofi/models/Qwen3-VL-8B-Instruct"
    DISPLAY = "Qwen3-VL-8B"
    MAX_TOKENS = 400
    USE_OPENCUA = False
    USE_QWEN2 = False

# GB10 workaround
_op = torch.prod
torch.prod = lambda i, *a, **kw: _op(i.cpu(), *a, **kw).to(i.device) if hasattr(i,'is_cuda') and i.is_cuda else _op(i, *a, **kw)

print("=" * 70)
print(f"VisionVoice 실제 스크린샷 벤치마크")
print(f"Model: {DISPLAY} | HW: DGX Spark (GB10)")
print("=" * 70)

# ========== 실제 이미지 기반 시나리오 ==========
# 4개 사이트 × 10개 시나리오 (실제 한국어 UI)
SCENARIOS = [
    # ----- 네이버 메인 -----
    {
        "id": "naver_m_01",
        "image": str(IMG_DIR / "naver_main.png"),
        "command": "검색창에 '오늘 날씨' 입력해줘",
        "expected": "input",
        "site": "naver",
    },
    {
        "id": "naver_m_02",
        "image": str(IMG_DIR / "naver_main.png"),
        "command": "이 화면 어떻게 구성돼 있는지 설명해줘",
        "expected": "explain",
        "site": "naver",
    },
    {
        "id": "naver_s_01",
        "image": str(IMG_DIR / "naver_search_input_open.png"),
        "command": "검색어 입력창을 클릭해줘",
        "expected": "click",
        "site": "naver",
    },
    # ----- 무신사 -----
    {
        "id": "musinsa_m_01",
        "image": str(IMG_DIR / "musinsa_main.png"),
        "command": "검색창 클릭해줘",
        "expected": "click",
        "site": "musinsa",
    },
    {
        "id": "musinsa_d_01",
        "image": str(IMG_DIR / "musinsa_detail_samyang_group_special_T.png"),
        "command": "이 상품 페이지 설명해줘",
        "expected": "explain",
        "site": "musinsa",
    },
    {
        "id": "musinsa_d_02",
        "image": str(IMG_DIR / "musinsa_short_sleeve_search.png"),
        "command": "아래로 스크롤해줘",
        "expected": "scroll",
        "site": "musinsa",
    },
    # ----- 유튜브 -----
    {
        "id": "youtube_m_01",
        "image": str(IMG_DIR / "youtube_main.png"),
        "command": "검색창에 '먹방' 입력해줘",
        "expected": "input",
        "site": "youtube",
    },
    {
        "id": "youtube_m_02",
        "image": str(IMG_DIR / "youtube_main.png"),
        "command": "화면 설명해줘",
        "expected": "explain",
        "site": "youtube",
    },
    {
        "id": "youtube_c_01",
        "image": str(IMG_DIR / "youtube_comments.png"),
        "command": "아래로 스크롤해서 댓글 더 보기",
        "expected": "scroll",
        "site": "youtube",
    },
    # ----- 스프레드시트 -----
    {
        "id": "sheet_01",
        "image": str(IMG_DIR / "spreadsheets_Gradu_list.png"),
        "command": "이 스프레드시트 내용 설명해줘",
        "expected": "explain",
        "site": "spreadsheet",
    },
]

print(f"✓ 시나리오 {len(SCENARIOS)}개 (실제 스크린샷 기반)")
print(f"  사이트: naver({sum(1 for s in SCENARIOS if s['site']=='naver')}), " +
      f"musinsa({sum(1 for s in SCENARIOS if s['site']=='musinsa')}), " +
      f"youtube({sum(1 for s in SCENARIOS if s['site']=='youtube')}), " +
      f"spreadsheet({sum(1 for s in SCENARIOS if s['site']=='spreadsheet')})")

# ========== 모델 로드 ==========
print(f"\n[Loading {DISPLAY}]...")
t0 = time.time()
if USE_OPENCUA:
    processor = AutoTokenizer.from_pretrained(PROCESSOR_PATH, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        MODEL_PATH, dtype=torch.bfloat16, device_map="cuda:0",
        trust_remote_code=True,
    )
elif USE_QWEN2:
    processor = AutoProcessor.from_pretrained(PROCESSOR_PATH, trust_remote_code=True)
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        MODEL_PATH, torch_dtype=torch.bfloat16, device_map="cuda:0",
        trust_remote_code=True,
    )
else:
    processor = AutoProcessor.from_pretrained(PROCESSOR_PATH, trust_remote_code=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        MODEL_PATH, dtype=torch.bfloat16, device_map="cuda:0",
        trust_remote_code=True, attn_implementation="sdpa",
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
    W, H = img.size
    sc["_img_size"] = (W, H)  # OpenCUA bbox 정규화용

    if USE_OPENCUA:
        inputs = None
    elif USE_QWEN2:
        # Qwen2-VL: image content 형식이 다름
        messages = [{"role": "user", "content": [
            {"type": "image", "image": sc["image"]},
            {"type": "text", "text": f"{SYSTEM}\n\n명령: \"{sc['command']}\""}
        ]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(
            text=[text], images=image_inputs, videos=video_inputs,
            padding=True, return_tensors="pt"
        ).to(model.device)
    else:
        messages = [{"role": "user", "content": [
            {"type": "image", "image": sc["image"]},
            {"type": "text", "text": f"{SYSTEM}\n\n명령: \"{sc['command']}\""}
        ]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[img], padding=True, return_tensors="pt").to(model.device)

    t = time.time()
    if USE_OPENCUA:
        # OpenCUA: tokenizer 기반, pyautogui 코드 출력
        prompt = f"Task: {sc['command']}\nScreenshot: [image]\nAction:"
        enc = processor(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            gen_ids = model.generate(**enc, max_new_tokens=MAX_TOKENS, do_sample=False)
        output_raw = processor.decode(gen_ids[0][enc.input_ids.shape[1]:], skip_special_tokens=True).strip()
    else:
        with torch.no_grad():
            gen_ids = model.generate(**inputs, max_new_tokens=MAX_TOKENS, do_sample=False)
        trimmed = [o[len(inp):] for inp, o in zip(inputs.input_ids, gen_ids)]
        output_raw = processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()
    elapsed = time.time() - t

    parsed = None
    action_correct = False
    if USE_OPENCUA:
        # pyautogui 코드에서 action 분류
        raw_lower = output_raw.lower()
        if any(k in raw_lower for k in ["typewrite", "write(", "type(", "hotkey"]):
            guessed = "input"
        elif "scroll" in raw_lower:
            guessed = "scroll"
        elif any(k in raw_lower for k in ["click", "press", "doubleclick"]):
            guessed = "click"
        else:
            guessed = "explain"
        # (x,y) 좌표 bbox 추출
        coord = re.search(r'[\(\s](\d+)[,\s]+(\d+)[\)\s]', output_raw)
        if coord:
            cx, cy = int(coord.group(1)), int(coord.group(2))
            img_w, img_h = sc.get("_img_size", (1280, 800))
            nx = round(cx / img_w * 1000)
            ny = round(cy / img_h * 1000)
            bbox = [max(0, nx-20), max(0, ny-20), min(1000, nx+20), min(1000, ny+20)]
        else:
            bbox = None
        parsed = {"action": guessed, "bbox": bbox, "target": "", "speech": output_raw[:80]}
        action_correct = (guessed == sc["expected"])
    else:
        json_match = re.search(r'\{.*?\}', output_raw, re.DOTALL)
        try:
            if json_match:
                parsed = json.loads(json_match.group(0))
                action_correct = (parsed.get("action") == sc["expected"])
        except Exception:
            pass

    status = "✓" if action_correct else "✗"
    print(f"\n[{i}/{len(SCENARIOS)}] {sc['id']} [{sc['site']}] ({sc['expected']}) {status} {elapsed:.1f}s")
    print(f"    cmd: {sc['command']}")
    print(f"    got: {parsed.get('action') if parsed else 'PARSE_FAIL'}", end="")
    if parsed and parsed.get("target"):
        print(f" | target: {parsed.get('target')}", end="")
    print()
    if not parsed:
        print(f"    raw: {output_raw[:120]}")

    results.append({
        "id": sc["id"],
        "site": sc["site"],
        "image": sc["image"],
        "command": sc["command"],
        "expected_action": sc["expected"],
        "predicted_action": parsed.get("action") if parsed else None,
        "bbox": parsed.get("bbox") if parsed else None,
        "target": parsed.get("target") if parsed else None,
        "speech": parsed.get("speech") if parsed else None,
        "raw_output": output_raw,
        "elapsed_sec": elapsed,
        "action_correct": action_correct,
        "image_size": [W, H],
    })

# ========== 요약 ==========
print("\n" + "=" * 70)
total = len(results)
correct = sum(1 for r in results if r["action_correct"])
avg_time = sum(r["elapsed_sec"] for r in results) / total

print(f"\n[결과 요약] {DISPLAY} — 실제 스크린샷 기반")
print(f"  정확도 (Action): {correct}/{total} = {100*correct/total:.1f}%")
print(f"  평균 응답속도:   {avg_time:.2f}s")
print(f"  실행 환경:       DGX Spark (GB10)")

from collections import defaultdict
site_stats = defaultdict(lambda: {"total":0,"correct":0})
for r in results:
    site_stats[r["site"]]["total"] += 1
    if r["action_correct"]:
        site_stats[r["site"]]["correct"] += 1

print("\n사이트별:")
for site, s in site_stats.items():
    print(f"  {site:12s}: {s['correct']}/{s['total']} ({100*s['correct']/s['total']:.0f}%)")

print("\n[1학기 비교]")
print(f"  {'':20s} {'1학기 Qwen2-VL':18s} {'현재 ' + DISPLAY:20s}")
print(f"  {'임무 성공률':20s} {'65% (Colab T4)':18s} {f'{100*correct/total:.0f}%':20s}")
print(f"  {'평균 응답속도':20s} {'30.7s':18s} {f'{avg_time:.1f}s':20s}")
print(f"  {'평가 이미지':20s} {'합성 이미지':18s} {'실제 스크린샷':20s}")

os.makedirs("/home/devlofi/HyeWon/eval_results", exist_ok=True)
timestamp = time.strftime("%Y%m%d_%H%M%S")
result_path = f"/home/devlofi/HyeWon/eval_results/realscene_{MODEL_NAME}_{timestamp}.json"
with open(result_path, "w", encoding="utf-8") as f:
    json.dump({
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": DISPLAY,
        "eval_type": "real_screenshots",
        "hardware": "DGX Spark (GB10)",
        "total_scenarios": total,
        "correct": correct,
        "accuracy": 100*correct/total,
        "avg_latency_sec": avg_time,
        "site_stats": dict(site_stats),
        "results": results,
    }, f, ensure_ascii=False, indent=2)
print(f"\n✓ 결과 저장: {result_path}")
