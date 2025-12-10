from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
import torch
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn, threading
import base64, io, json
from PIL import Image

MODEL = "Qwen/Qwen2-VL-7B-Instruct"

processor = AutoProcessor.from_pretrained(
    MODEL,
    trust_remote_code=True
)
model = Qwen2VLForConditionalGeneration.from_pretrained(
    MODEL,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True
)

model.eval()
print("✅ model ready:", model.device)

RESPONSE_SCHEMA = """
반드시 JSON ONLY로 출력하세요.

{
  "intent": "action | explain | answer",
  "actions": [
    {"type": "click", "x": 123, "y": 456}
  ],
  "speech": "사용자에게 전달할 설명 또는 응답",
  "finished": true
}

규칙:
- intent=explain 또는 answer 인 경우 actions는 빈 배열 []
- intent=action 인 경우 actions는 1개 이상
- 화면 설명만 필요한 경우 explain
- 일반 지식 질문은 answer
- 실제 조작이 필요하면 action
- JSON 외 출력 금지
"""

from PIL import Image

def agent_step(
    image: Image.Image,
    dom_text: str,
    user_goal: str,
):
    prompt = f"""
당신은 시각장애인을 돕는 범용 웹 AI 에이전트입니다.

당신의 역할은 사용자의 요청을 보고
1️⃣ 화면 설명(explain),
2️⃣ 일반 질문 응답(answer),
3️⃣ 실제 화면 조작(action)
중 하나로 판단하는 것입니다.

[사용자 요청]
{user_goal}

[현재 화면 DOM 요약]
{dom_text[:1200]}

{RESPONSE_SCHEMA}
"""

    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": prompt}
        ]
    }]

    text = processor.apply_chat_template(
        messages,
        add_generation_prompt=True
    )

    inputs = processor(
        text=[text],
        images=[image],
        return_tensors="pt"
    ).to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            do_sample=False
        )

    decoded = processor.batch_decode(
        outputs[:, inputs.input_ids.shape[1]:],
        skip_special_tokens=True
    )[0]

    return decoded

def log(msg):
    with open("/content/debug.log", "a") as f:
        f.write(msg + "\n")

def base64_to_pil(b64):
    if "," in b64:
        b64 = b64.split(",")[1]
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")

app = FastAPI()

class AgentRequest(BaseModel):
    dom: str
    goal: str
    image_base64: str

@app.post("/infer")
def infer(req: AgentRequest):
    log("✅ /infer called")
    log(f"goal={req.goal}")

    image = base64_to_pil(req.image_base64)
    raw = agent_step(image, req.dom, req.goal)

    log("✅ inference done")
    return json.loads(raw)

def run():
    uvicorn.run(app, host="0.0.0.0", port=8001)

threading.Thread(target=run).start()
