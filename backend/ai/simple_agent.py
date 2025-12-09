# backend/ai/simple_agent.py

from .config import USE_MOCK_AGENT
import torch
from PIL import Image

if not USE_MOCK_AGENT:
    from transformers.models.auto.tokenization_auto import AutoTokenizer
    from transformers.models.auto.modeling_auto import AutoModelForVision2Seq
    from transformers.models.auto.image_processing_auto import AutoImageProcessor


class OpenCUAgent:
    def __init__(self):
        if not USE_MOCK_AGENT:
            print("🧠 Vision Agent (임시) 로딩 중...")

            model_path = "Qwen/Qwen2-VL-7B-Instruct"

            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True
            )
            self.image_processor = AutoImageProcessor.from_pretrained(
                model_path,
                trust_remote_code=True
            )
            self.model = AutoModelForVision2Seq.from_pretrained(
                model_path,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True,
            )

            print(f"🔍 CUDA 상태: available={torch.cuda.is_available()}, device_count={torch.cuda.device_count()}")
            if torch.cuda.is_available():
                print(f"🔍 현재 GPU: {torch.cuda.get_device_name(0)}")
        else:
            print("🧠 OpenCUA Mock 모드 대기 중")

    def inference(self, image_path, command, dom_text):
        if USE_MOCK_AGENT:
            return {"action": "click", "x": 0.5, "y": 0.5}, "테스트 완료"

        image = Image.open(image_path).convert("RGB")

        # DOM 요약 + 명령을 텍스트로 구성
        if len(dom_text) > 2000:
            safe_dom = dom_text[:1500] + "\n...[중략]...\n" + dom_text[-500:]
        else:
            safe_dom = dom_text

        prompt = (
            "당신은 시각장애인을 돕는 한국어 스크린 리더입니다. "
            "아래의 웹 페이지 텍스트와 스크린샷을 참고해서, "
            "현재 화면이 어떤 페이지인지와 중요한 정보만 간단히 설명해 주세요.\n\n"
            "설명 규칙:\n"
            "1. 스크린리더가 이미 읽을 수 있는 긴 본문 텍스트나 리스트는 절대로 그대로 반복하지 마세요.\n"
            "2. 대신, 페이지의 용도(예: 쇼핑 상품 상세, 뉴스 기사 등), 중요한 버튼/링크(예: 장바구니, 구매하기, 검색),\n"
            "   눈으로만 볼 수 있는 이미지/배너의 대략적인 내용만 말해 주세요.\n"
            "3. 최대 5문장 안에서만 말해 주세요.\n"
            "4. 답변에는 아래의 텍스트 내용을 그대로 복사하지 말고, 반드시 요약/설명 형태로 말해 주세요.\n\n"
            f"[웹 페이지 텍스트]\n{safe_dom}\n\n"
            f"[사용자 명령]\n{command}\n"
            "이제 위 규칙을 꼭 지키면서, 한 번만 자연스럽게 한국어로 설명해 주세요."
        )

        # 1) 텍스트 토큰화
        text_inputs = self.tokenizer(
            prompt,
            return_tensors="pt"
        )

        # 2) 이미지 전처리
        image_inputs = self.image_processor(
            images=image,
            return_tensors="pt"
        )

        # 3) 모델 입력 병합 + 디바이스 이동
        inputs = {
            **text_inputs,
            **image_inputs,
        }
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=768,
                do_sample=False,
            )

        text = self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

        # 일단 액션은 none만 반환 (MVP: 설명만)
        return {"action": "none"}, text
