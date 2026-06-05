"""
DGX Spark에서 OpenCUA-7B 로딩 + 추론 테스트
목적: 환경 검증 (실제 정확도 테스트 아님)
"""
import time
import torch
from PIL import Image, ImageDraw
from transformers import AutoTokenizer, AutoModel, AutoImageProcessor

MODEL_PATH = "/home/devlofi/models/OpenCUA-7B"

print("=" * 60)
print("DGX Spark OpenCUA-7B 추론 테스트")
print("=" * 60)

# 1. GPU 상태 확인
print(f"\n[1] GPU 상태")
print(f"    CUDA available: {torch.cuda.is_available()}")
print(f"    Device: {torch.cuda.get_device_name(0)}")
print(f"    bf16 supported: {torch.cuda.is_bf16_supported()}")

# 2. 테스트 이미지 생성 (더미 웹페이지 모방)
print(f"\n[2] 테스트 이미지 생성")
img = Image.new('RGB', (1280, 720), color='white')
draw = ImageDraw.Draw(img)
# 검색창 모방
draw.rectangle([400, 100, 880, 150], outline='black', width=2)
draw.text((410, 115), "Search here...", fill='gray')
# 버튼 모방
draw.rectangle([900, 100, 1000, 150], fill='blue', outline='blue')
draw.text((930, 115), "Search", fill='white')
# 링크들
draw.text((100, 200), "메일", fill='blue')
draw.text((200, 200), "카페", fill='blue')
draw.text((300, 200), "블로그", fill='blue')
img_path = "/tmp/test_screenshot.png"
img.save(img_path)
print(f"    saved: {img_path}")

# 3. 모델 로드
print(f"\n[3] 모델 로드 시작...")
t0 = time.time()

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
print(f"    tokenizer: OK ({time.time()-t0:.1f}s)")

t1 = time.time()
model = AutoModel.from_pretrained(
    MODEL_PATH,
    dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True,
    attn_implementation="eager",
    low_cpu_mem_usage=True,
)
print(f"    model: OK ({time.time()-t1:.1f}s)")

# vision token ID 설정 (agent.py에서 하는 것과 동일)
if not hasattr(model.config, "vision_start_token_id"):
    v_start = tokenizer.convert_tokens_to_ids("<|vision_start|>")
    v_end = tokenizer.convert_tokens_to_ids("<|vision_end|>")
    model.config.vision_start_token_id = v_start if v_start is not None else 151652
    model.config.vision_end_token_id = v_end if v_end is not None else 151653

t1 = time.time()
image_processor = AutoImageProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
print(f"    image_processor: OK ({time.time()-t1:.1f}s)")

print(f"    model device: {model.device}")
print(f"    total load time: {time.time()-t0:.1f}s")

# 4. 간단한 추론
print(f"\n[4] 추론 테스트")
command = "검색창을 클릭해줘"

system_prompt = (
    "You are 'VisionVoice', a helpful AI assistant for visually impaired users. "
    "Output strictly in Korean. "
    "If an action is needed, output the Python code."
)

user_prompt_text = f"""
[Web Page Context / DOM Text]
검색창, 메일, 카페, 블로그

[User Command]
{command}

Please execute the command.
"""

messages = [
    {"role": "system", "content": system_prompt},
    {
        "role": "user",
        "content": [
            {"type": "image", "image": img_path},
            {"type": "text", "text": user_prompt_text},
        ],
    },
]

text_input = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
model_inputs = tokenizer([text_input], return_tensors="pt")
input_ids = model_inputs.input_ids.to(model.device)
attention_mask = model_inputs.attention_mask.to(model.device)

image_info = image_processor.preprocess(images=[img], return_tensors="pt")
pixel_values = image_info['pixel_values'].to(dtype=torch.bfloat16, device=model.device)
grid_thws = image_info['image_grid_thw'].to(model.device)

print(f"    command: '{command}'")
print(f"    generating...")
t_inf = time.time()

with torch.no_grad():
    generated_ids = model.generate(
        input_ids=input_ids,
        attention_mask=attention_mask,
        pixel_values=pixel_values,
        grid_thws=grid_thws,
        max_new_tokens=128,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
        use_cache=True,
    )

inf_time = time.time() - t_inf
output_ids = generated_ids[0][len(input_ids[0]):]
output_text = tokenizer.decode(output_ids, skip_special_tokens=True)

print(f"    inference time: {inf_time:.2f}s")
print(f"    output: {output_text}")

# 5. GPU 메모리 확인
print(f"\n[5] GPU 메모리 사용량")
print(f"    allocated: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
print(f"    reserved:  {torch.cuda.memory_reserved() / 1024**3:.2f} GB")

print(f"\n{'=' * 60}")
print(f"✅ 테스트 성공 - DGX Spark에서 OpenCUA-7B 정상 동작")
print(f"{'=' * 60}")
