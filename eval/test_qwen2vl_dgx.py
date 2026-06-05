"""Qwen2-VL-7B DGX Spark 테스트 (nvrtc 이슈 확인용)"""
import time, torch
from PIL import Image, ImageDraw
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor

MODEL_PATH = "/home/devlofi/models/Qwen2-VL-7B-Instruct"
print(f"torch: {torch.__version__}, device: {torch.cuda.get_device_name(0)}")

img = Image.new('RGB', (1280, 720), color='white')
d = ImageDraw.Draw(img)
d.rectangle([400, 100, 880, 150], outline='black', width=2)
d.text((410, 115), "검색창", fill='black')
img_path = "/tmp/test_qwen2.png"
img.save(img_path)

print("Loading Qwen2-VL-7B...")
t0 = time.time()
processor = AutoProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = Qwen2VLForConditionalGeneration.from_pretrained(
    MODEL_PATH, dtype=torch.bfloat16, device_map="auto",
    trust_remote_code=True, attn_implementation="sdpa"
)
print(f"Loaded: {time.time()-t0:.1f}s")

messages = [{"role": "user", "content": [
    {"type": "image", "image": img_path},
    {"type": "text", "text": "이 화면에 뭐가 보여?"}
]}]
text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = processor(text=[text], images=[img], return_tensors="pt", padding=True).to(model.device)

print("Generating...")
t1 = time.time()
with torch.no_grad():
    out = model.generate(**inputs, max_new_tokens=100, do_sample=False)
print(f"Generation: {time.time()-t1:.1f}s")
gen = [o[len(i):] for i, o in zip(inputs.input_ids, out)]
print(f"Output: {processor.batch_decode(gen, skip_special_tokens=True)[0][:200]}")
