from .config import USE_MOCK_AGENT

if not USE_MOCK_AGENT:
    import torch
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor


class OpenCUAgent:
    def __init__(self):
        if not USE_MOCK_AGENT:
            print("🧠 OpenCUA 모델 로딩 중...")
            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                "xlangai/OpenCUA-7B", torch_dtype=torch.bfloat16, device_map="auto"
            )
            self.processor = AutoProcessor.from_pretrained("xlangai/OpenCUA-7B")
        else:
            print("🧠 OpenCUA Mock 모드 대기 중")

    def inference(self, image_path, command, dom_text):
        if USE_MOCK_AGENT:
            # 프론트엔드 테스트용 가짜 좌표 (비율)
            return {
                "action": "click",
                "x": 0.5,
                "y": 0.5,
            }, "장바구니 버튼을 클릭했습니다."

        # 여기에 실제 추론 로직 작성 (processor -> generate -> decode)
        # ...
        return {"action": "click", "x": 0.0, "y": 0.0}, "실제 모델 응답입니다."
