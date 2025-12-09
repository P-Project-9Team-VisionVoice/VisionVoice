# backend/ai/simple_agent.py

from .config import USE_MOCK_AGENT
import torch
from typing import Any

if not USE_MOCK_AGENT:
    from transformers import Qwen2VLForConditionalGeneration, AutoTokenizer, AutoProcessor
    from qwen_vl_utils import process_vision_info

class OpenCUAgent:
    def __init__(self):
        if not USE_MOCK_AGENT:
            print("🧠 Vision Agent (Qwen2-VL) 로딩 중...")

            model_path = "Qwen/Qwen2-VL-7B-Instruct"

            # 1. 모델 로드
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                model_path,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True,
            )

            # 2. 프로세서 로드
            self.processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)

            print(f"🔍 모델 디바이스: {self.model.device}")
        else:
            print("🧠 OpenCUA Mock 모드 대기 중")

    def inference(self, image_path, command, dom_text):
        if USE_MOCK_AGENT:
            return {"action": "none"}, "테스트 완료"

        # DOM 길이 제한
        if len(dom_text) > 3000:
            safe_dom = dom_text[:2000] + "\n...[중략]...\n" + dom_text[-1000:]
        else:
            safe_dom = dom_text

        # 1. Messages 구조 생성
        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 시각장애인을 위해 웹페이지와 세상을 설명해주는 따뜻하고 똑똑한 'AI 음성 비서'입니다. "
                    "다음 원칙을 반드시 지키세요:\n"
                    "1. 특수문자 금지: '', '##', '-' 같은 마크다운 문법을 절대 쓰지 마세요. TTS가 읽기 불편합니다.\n"
                    "2. 구어체 사용: 보고서처럼 번호를 매기지 말고, 옆에서 말해주듯이 자연스러운 문장으로 연결하세요.\n"
                    "3. 정확한 숫자: 가격, 후기 수, 평점 등을 혼동하지 말고 정확히 구분하세요. (예: '후기 1개'를 '재고 1개'로 착각 금지)\n"
                    "4. 지식 활용: 사용자가 화면에 있는 용어(예: 프리마로프트, 고어텍스 등)에 대해 물어보면, 당신의 배경지식을 활용해 친절히 설명해 주세요."
                    "쇼핑몰, 관공서(정부24), 뉴스 기사, PDF 뷰어, 로그인 화면 등 어떤 페이지가 주어지더라도 "
                    "페이지의 성격을 먼저 파악하고, 사용자가 해당 페이지에서 가장 필요로 할 핵심 정보를 "
                    "시각적 요소(이미지/레이아웃)와 텍스트 정보를 종합하여 설명하세요."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image_path,
                    },
                    {
                        "type": "text",
                        "text": (
                            f"다음은 현재 웹페이지의 텍스트 정보(DOM)입니다:\n{safe_dom}\n\n"
                            f"사용자 명령: {command}\n\n"
                            "위 정보를 바탕으로, 다음 [상황별 가이드]에 맞춰 현재 화면을 설명해 주세요:\n\n"
                            
                            "[상황별 가이드]\n"
                            "1. 관공서/신청서 (예: 정부24, 은행):\n"
                            "   - 현재 어떤 민원/업무 페이지인지 명확히 알림.\n"
                            "   - 입력해야 할 칸(Input), 체크해야 할 항목, '신청하기/확인' 버튼의 위치를 강조.\n"
                            "2. 정보/문서 (예: 뉴스, 블로그, 위키):\n"
                            "   - 전체적인 제목과 핵심 내용을 요약.\n"
                            "   - 본문이 너무 길면 서론을 요약하고 '더 읽으시겠습니까?' 뉘앙스로 안내.\n"
                            "3. 쇼핑/이미지 (예: 무신사, 인스타):\n"
                            "   - 상품/사진의 시각적 특징(색상, 모양)과 중요 정보(가격, 옵션) 묘사.\n"
                            "4. 기능 수행 (예: 로그인, 검색):\n"
                            "   - 아이디/비밀번호 입력란 위치, 로그인 버튼, 혹은 검색 결과 요약.\n\n"
                            
                            "[공통 원칙]\n"
                            "- 단순히 텍스트를 나열하지 말고, '구조'와 '맥락'을 설명할 것.\n"
                            "- 시각적으로 강조된 부분(큰 글씨, 유색 버튼)은 중요하게 언급할 것.\n"
                            "- 자연스러운 한국어 구어체로 답변할 것."
                        ),
                    },
                ],
            },
        ]

        # 2. 입력 데이터 전처리 (Chat Template 적용)
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        
        # 3. Vision Info 추출 (버전 호환성 + None 처리)
        vision_infos: Any = process_vision_info(messages)
        
        # 변수 초기화
        image_inputs = None
        video_inputs = None
        video_kwargs = {}

        # 반환값 개수에 따른 언패킹
        if len(vision_infos) == 3:
            image_inputs, video_inputs, video_kwargs = vision_infos
        elif len(vision_infos) == 2:
            image_inputs, video_inputs = vision_infos
            video_kwargs = {}
        
        # video_kwargs가 혹시 None이면 빈 딕셔너리로 변경 (에러 방지 핵심)
        if video_kwargs is None:
            video_kwargs = {}

        # 4. Processor 입력 인자 동적 구성 (Safe Argument Construction)
        # None인 값은 아예 전달하지 않도록 딕셔너리를 직접 만듭니다.
        processor_args = {
            "text": [text],
            "images": image_inputs,
            "padding": True,
            "return_tensors": "pt",
        }

        # 비디오가 있을 때만 추가
        if video_inputs is not None:
            processor_args["videos"] = video_inputs
        
        # 추가 인자가 있을 때만 병합
        if video_kwargs:
            processor_args.update(video_kwargs)

        # 최종 입력 생성
        inputs = self.processor(**processor_args)
        
        # GPU 이동
        inputs = inputs.to(self.model.device)

        # 5. 추론 생성
        with torch.no_grad():
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
            )

        # 6. 결과 디코딩
        output_ids = generated_ids[:, inputs.input_ids.shape[1]:]
        output_text = self.processor.batch_decode(
            output_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]

        return {"action": "none"}, output_text.strip()