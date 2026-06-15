"""
DGX Spark Qwen3-VL-8B 테스트 (prod workaround 포함)
"""
import time
import torch

# === Workaround: GB10에서 torch.prod() JIT 컴파일 실패 → CPU 경로 ===
_orig_prod = torch.prod
def _safe_prod(input, *args, **kwargs):
    if hasattr(input, 'is_cuda') and input.is_cuda:
        return _orig_prod(input.cpu(), *args, **kwargs).to(input.device)
    return _orig_prod(input, *args, **kwargs)
torch.prod = _safe_prod

# Tensor method 도 패치
_orig_tensor_prod = torch.Tensor.prod
def _safe_tensor_prod(self, *args, **kwargs):
    if self.is_cuda:
        return _orig_tensor_prod(self.cpu(), *args, **kwargs).to(self.device)
    return _orig_tensor_prod(self, *args, **kwargs)
torch.Tensor.prod = _safe_tensor_prod

from PIL import Image, ImageDraw
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor

MODEL_PATH = "/home/devlofi/models/Qwen3-VL-8B-Instruct"

print("=" * 60)
print("Qwen3-VL-8B DGX Spark 추론 테스트")
print("=" * 60)

print(f"\n[GPU] {torch.cuda.get_device_name(0)}, bf16={torch.cuda.is_bf16_supported()}")

# 테스트 이미지
img = Image.new('RGB', (1280, 720), color='white')
d = ImageDraw.Draw(img)
d.rectangle([0, 0, 1280, 70], fill=(50, 50, 50))
d.text((20, 25), "VisionVoice Test Site", fill='white')
d.text((1100, 25), "Login", fill='white')
d.rectangle([400, 100, 880, 150], outline='black', width=2)
d.text((410, 115), "검색어를 입력하세요...", fill='gray')
d.rectangle([900, 100, 1000, 150], fill=(50, 100, 200))
d.text((920, 115), "검색", fill='white')
for txt, x in [("메일", 100), ("카페", 200), ("블로그", 300), ("쇼핑", 400)]:
    d.rectangle([x, 200, x+80, 240], fill=(240, 240, 240), outline='black')
    d.text((x+20, 210), txt, fill='black')
img_path = "/tmp/test_screenshot.png"
img.save(img_path)

print("\n[Loading] Qwen3-VL-8B...")
t0 = time.time()
processor = AutoProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = Qwen3VLForConditionalGeneration.from_pretrained(
    MODEL_PATH,
    dtype=torch.bfloat16,
    device_map="cuda:0",  # 명시적 단일 GPU
    trust_remote_code=True,
    attn_implementation="sdpa",
)
model.eval()
print(f"    loaded in {time.time()-t0:.1f}s")

# 3개 시나리오
test_cases = [
    "검색창에 '리그오브레전드'를 입력해줘",
    "메일 버튼을 클릭해줘",
    "이 화면을 간단히 설명해줘",
]

for i, command in enumerate(test_cases, 1):
    print(f"\n[Test {i}] '{command}'")
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": img_path},
            {"type": "text", "text": (
                "당신은 시각장애인을 돕는 웹 브라우저 제어 AI입니다. "
                "사용자 명령을 분석하여 JSON 형식으로 응답하세요.\n"
                "형식: {\"action\": \"click|input|explain\", \"target\": \"요소명\", "
                "\"bbox\": [x1,y1,x2,y2] (0~1000 정규화), \"speech\": \"한국어 답변\"}\n\n"
                f"명령: \"{command}\""
            )},
        ],
    }]

    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[img], padding=True, return_tensors="pt").to(model.device)

    t = time.time()
    with torch.no_grad():
        gen_ids = model.generate(**inputs, max_new_tokens=200, do_sample=False)
    elapsed = time.time() - t
    trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, gen_ids)]
    output = processor.batch_decode(trimmed, skip_special_tokens=True)[0]
    print(f"    ({elapsed:.1f}s) {output[:300]}")

print(f"\n[GPU Memory] {torch.cuda.memory_allocated()/1024**3:.2f}GB allocated")
print("\n" + "=" * 60)
print("✅ Qwen3-VL-8B DGX Spark 동작 확인")
print("=" * 60)
