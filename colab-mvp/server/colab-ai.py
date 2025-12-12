# server/colab-ai.py
import os
import torch
import math
import json
import io
import base64
import re
from PIL import Image
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

from transformers import (
    Qwen2VLForConditionalGeneration,
    AutoProcessor,
    BitsAndBytesConfig
)

import os
HF_TOKEN = os.environ.get("HF_TOKEN")
assert HF_TOKEN is not None, "HF_TOKEN environment variable is required"

# ---------------------------------------------------------
# 1. 모델 로딩
# ---------------------------------------------------------
MODEL = "Qwen/Qwen2-VL-7B-Instruct"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16
)

print("⏳ Loading model...")
processor = AutoProcessor.from_pretrained(
    MODEL,
    trust_remote_code=True,
    token=os.environ["HF_TOKEN"]
)

model = Qwen2VLForConditionalGeneration.from_pretrained(
    MODEL,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
    token=os.environ["HF_TOKEN"]
)

model.eval()
print("✅ Model ready")

# ---------------------------------------------------------
# 2. Utils
# ---------------------------------------------------------
def smart_resize(height, width, factor=28, min_pixels=3136, max_pixels=1003520):
    if height * width > max_pixels:
        ratio = math.sqrt(max_pixels / (height * width))
        height, width = int(height * ratio), int(width * ratio)
    elif height * width < min_pixels:
        ratio = math.sqrt(min_pixels / (height * width))
        height, width = int(height * ratio), int(width * ratio)

    return round(height / factor) * factor, round(width / factor) * factor


def base64_to_pil(b64):
    if "," in b64:
        b64 = b64.split(",")[1]
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")

# ---------------------------------------------------------
# 3. Agent
# ---------------------------------------------------------
RESPONSE_SCHEMA = """
반드시 JSON 형식으로만 출력하세요.

{
  "intent": "action | explain | answer",
  "actions": [
    {
      "type": "click",
      "bbox": [xmin, ymin, xmax, ymax],
      "text_content": "표시된 텍스트",
      "description": "설명"
    },
    {
      "type": "scroll",
      "direction": "up | down",
      "amount": "null 또는 숫자(픽셀)"
    },
    {
      "type": "go_back"
    },
    {
      "type": "input",
      "value": "입력할 내용(필수)",
      "bbox": [xmin, ymin, xmax, ymax]
    }
  ],
  "speech": "응답",
  "finished": true
}

[출력 계약]
- intent는 반드시 "action" | "explain" | "answer" 중 하나만 사용한다.
- intent가 "action"이면 actions 배열을 반드시 포함한다.
- actions[].type은 반드시 "click" | "input" | "scroll" | "go_back" 중 하나만 사용한다.
- 스크롤 요청은 intent="action" + type="scroll"로만 표현한다. (intent="scroll" 금지)
- 검색이나 입력을 요청받으면 절대로 'click' 타입을 생성하지 않는다.
- 대신 반드시 'input' 타입을 사용하고, 'value' 필드에 입력할 정확한 텍스트를 넣는다.

규칙:
1. 'bbox'는 0~1000 범위의 [xmin, ymin, xmax, ymax] 입니다.
2. 'text_content'에는 해당 요소에 시각적으로 보이는 텍스트를 적으세요.
3. 인접한 요소는 분리해서 타겟만 정확히 잡으세요.
4. 이전 페이지 요청 시 'go_back' 타입을 사용하세요.
5. 스크롤 요청 시 'scroll' 타입을 사용하세요.
6. 입력이나 검색, 타이핑 요청 시 'input' 타입을 사용하세요.
"""

def agent_step(image, dom_text, user_goal):
    orig_w, orig_h = image.size
    h, w = smart_resize(orig_h, orig_w)
    image = image.resize((w, h), Image.Resampling.LANCZOS)

    prompt = f"""
당신은 시각장애인을 돕는 정밀한 웹 브라우징 AI입니다.

[사용자 요청]
{user_goal}

[DOM]
{dom_text[:1200]}

[규칙]
1. 사용자가 원하는 요소의 **정확한 위치(bbox)**와 **표시된 텍스트(text_content)**를 찾으세요.
2. **Visual Fidelity**: text_content에는 버튼이나 링크에 적힌 텍스트를 **화면에 보이는 그대로** 적으세요.
3. 텍스트는 화면에 보이는 그대로(영어면 영어, 한글이면 한글) 적으세요.
4. '오프라인 스토어'나 '로그인' 같이 텍스트가 명확하면 bbox보다 text_content를 우선시합니다.
5. 사용자가 '내려줘', '더 보여줘' 하면 scroll action을 생성하세요.
6. bbox는 0~1000 범위의 정규화 좌표입니다.

{RESPONSE_SCHEMA}
"""

    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": prompt}
        ]
    }]

    text_input = processor.apply_chat_template(messages, add_generation_prompt=True)

    inputs = processor(
        text=[text_input],
        images=[image],
        return_tensors="pt"
    ).to(model.device)

    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=1024)

    decoded = processor.batch_decode(
        outputs[:, inputs.input_ids.shape[1]:],
        skip_special_tokens=True
    )[0]

    match = re.search(r"\{.*\}", decoded, re.DOTALL)
    return json.loads(match.group(0)) if match else {
        "intent": "answer",
        "speech": "오류가 발생했습니다."
    }

# ---------------------------------------------------------
# 4. API
# ---------------------------------------------------------
app = FastAPI()

class AgentRequest(BaseModel):
    dom: str
    goal: str
    image_base64: str

@app.post("/infer")
def infer(req: AgentRequest):
    image = base64_to_pil(req.image_base64)
    return agent_step(image, req.dom, req.goal)

# ---------------------------------------------------------
# 5. Entry
# ---------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)


