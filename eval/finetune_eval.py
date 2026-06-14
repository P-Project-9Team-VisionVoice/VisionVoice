"""
VisionVoice Fine-tuned 모델 벤치마크
Qwen3-VL-8B + LoRA (visionvoice-qwen3vl-final)
기존 realscene_eval.py 와 동일한 10개 시나리오
"""
import json, re, time, torch, os
from PIL import Image
from pathlib import Path
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from peft import PeftModel
from datetime import datetime
from qwen_vl_utils import process_vision_info

IMG_DIR   = Path("/home/devlofi/HyeWon/taining_datasets")
BASE_PATH = "/home/devlofi/models/Qwen3-VL-8B-Instruct"
LORA_PATH = "/home/devlofi/HyeWon/finetune/output/visionvoice-qwen3vl-final"
OUT_DIR   = Path("/home/devlofi/HyeWon/VisionVoice/eval/results")

# GB10 workaround
_op = torch.prod
torch.prod = lambda i, *a, **kw: (_op(i.cpu(), *a, **kw).to(i.device)
                                   if hasattr(i, 'is_cuda') and i.is_cuda
                                   else _op(i, *a, **kw))

SYSTEM_PROMPT = (
    "당신은 시각장애인을 위한 웹 브라우저 제어 AI입니다. "
    "사용자의 음성 명령과 현재 화면 스크린샷을 분석하여 수행해야 할 행동을 "
    "JSON 형식으로만 출력하세요.\n"
    "{\"action\": \"click|input|scroll|explain\", \"target\": \"요소명\", "
    "\"bbox\": [x1,y1,x2,y2], \"speech\": \"한국어 안내 멘트\"}"
)

SCENARIOS = [
    {"id": "naver_m_01",  "image": "naver_main.png",           "command": "검색창에 '오늘 날씨' 입력해줘",      "expected": "input",   "site": "naver"},
    {"id": "naver_m_02",  "image": "naver_main.png",           "command": "이 화면 어떻게 구성돼 있는지 설명해줘", "expected": "explain", "site": "naver"},
    {"id": "naver_s_01",  "image": "naver_search_input_open.png", "command": "검색어 입력창을 클릭해줘",         "expected": "click",   "site": "naver"},
    {"id": "musinsa_m_01","image": "musinsa_main.png",          "command": "검색 아이콘 눌러줘",               "expected": "click",   "site": "musinsa"},
    {"id": "musinsa_d_01","image": "musinsa_detail_samyang_group_special_T.png", "command": "장바구니에 담기 버튼 눌러줘", "expected": "click",  "site": "musinsa"},
    {"id": "musinsa_d_02","image": "musinsa_detail_samyang_group_special_T.png", "command": "아래로 스크롤 해줘",          "expected": "scroll", "site": "musinsa"},
    {"id": "youtube_m_01","image": "youtube_main.png",          "command": "홈 가줘",                        "expected": "click",   "site": "youtube"},
    {"id": "youtube_m_02","image": "youtube_main.png",          "command": "검색창 눌러줘",                   "expected": "click",   "site": "youtube"},
    {"id": "youtube_c_01","image": "youtube_comments.png",      "command": "댓글 달기 클릭해줘",              "expected": "click",   "site": "youtube"},
    {"id": "sheet_01",    "image": "spreadsheets_Gradu_list.png","command": "A1 셀 클릭해줘",                "expected": "click",   "site": "sheet"},
]

def load_model():
    print("모델 로딩 중 (Qwen3-VL-8B + LoRA)...")
    t0 = time.time()
    processor = AutoProcessor.from_pretrained(BASE_PATH, trust_remote_code=True)
    base = Qwen3VLForConditionalGeneration.from_pretrained(
        BASE_PATH, torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base, LORA_PATH)
    model.eval()
    print(f"✓ 로딩 완료 ({time.time()-t0:.1f}초)")
    return model, processor

def infer(model, processor, image_path, command):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "image", "image": str(image_path)},
            {"type": "text",  "text": command},
        ]},
    ]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text], images=image_inputs, videos=video_inputs,
        padding=True, return_tensors="pt",
    ).to(model.device)

    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=200, do_sample=False)
    elapsed = time.time() - t0

    pred = processor.batch_decode(
        out[:, inputs.input_ids.shape[1]:], skip_special_tokens=True
    )[0].strip()
    return pred, elapsed

def parse_action(text):
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group())
            return d.get("action", ""), d.get("bbox", []), d.get("target", ""), d.get("speech", ""), text
        except:
            pass
    # action 키워드 fallback
    for a in ["click", "input", "scroll", "explain"]:
        if a in text.lower():
            return a, [], "", "", text
    return "", [], "", "", text

def main():
    print("=" * 70)
    print("VisionVoice Fine-tuned 모델 벤치마크")
    print("Model: Qwen3-VL-8B + LoRA (visionvoice-qwen3vl-final)")
    print("=" * 70)

    model, processor = load_model()

    results = []
    correct = 0
    total_time = 0.0

    for sc in SCENARIOS:
        img_path = IMG_DIR / sc["image"]
        if not img_path.exists():
            print(f"  ⚠️  이미지 없음: {img_path}")
            results.append({**sc, "predicted_action": "N/A", "correct": False, "latency": 0})
            continue

        raw, elapsed = infer(model, processor, img_path, sc["command"])
        pred_action, bbox, target, speech, raw_out = parse_action(raw)
        is_correct = (pred_action == sc["expected"])
        if is_correct:
            correct += 1
        total_time += elapsed

        status = "✅" if is_correct else "❌"
        print(f"  {status} [{sc['id']}] {sc['command'][:30]}")
        print(f"       예상={sc['expected']}  예측={pred_action}  {elapsed:.1f}s  bbox={bbox}")

        results.append({
            "id": sc["id"],
            "site": sc["site"],
            "command": sc["command"],
            "expected_action": sc["expected"],
            "predicted_action": pred_action,
            "bbox": bbox,
            "target": target,
            "speech": speech,
            "latency": elapsed,
            "correct": is_correct,
            "raw_output": raw_out[:200],
        })

    accuracy = correct / len(SCENARIOS)
    avg_lat  = total_time / len(SCENARIOS)

    print("\n" + "=" * 70)
    print(f"결과: {correct}/{len(SCENARIOS)}  정확도={accuracy*100:.0f}%  평균응답={avg_lat:.1f}s")
    print("=" * 70)

    # 사이트별 집계
    site_stats = {}
    for r in results:
        s = r["site"]
        site_stats.setdefault(s, {"correct": 0, "total": 0})
        site_stats[s]["total"] += 1
        if r.get("correct"):
            site_stats[s]["correct"] += 1
    print("사이트별:", {k: f"{v['correct']}/{v['total']}" for k,v in site_stats.items()})

    # 저장
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"realscene_finetune_{ts}.json"
    json.dump({
        "date": ts,
        "model": "Qwen3-VL-8B-LoRA",
        "eval_type": "realscene",
        "hardware": "DGX Spark GB10",
        "total_scenarios": len(SCENARIOS),
        "correct": correct,
        "accuracy": accuracy,
        "avg_latency_sec": avg_lat,
        "site_stats": site_stats,
        "results": results,
    }, open(out_path, "w"), ensure_ascii=False, indent=2)
    print(f"\n저장: {out_path}")

if __name__ == "__main__":
    main()
