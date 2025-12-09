# backend/ai/agent.py
from .config import USE_MOCK_AGENT
import torch
import time
import json
import re
import math
from PIL import Image
from typing import Any

if not USE_MOCK_AGENT:
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    from qwen_vl_utils import process_vision_info

class OpenCUAgent:
    def __init__(self):
        if not USE_MOCK_AGENT:
            print("🧠 Vision Agent (Qwen2-VL + Action) 로딩 중...")
            model_path = "Qwen/Qwen2-VL-7B-Instruct"

            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                model_path,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True,
            )
            self.processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
            print(f"🔍 모델 디바이스: {self.model.device}")
        else:
            print("🧠 OpenCUA Mock 모드 대기 중")

    def inference(self, image_path, command, dom_text):
        if USE_MOCK_AGENT:
            return {"action": "none"}, "테스트 완료"

        # 이미지 로드
        image = Image.open(image_path).convert('RGB')
        orig_w, orig_h = image.size

        # DOM 길이 제한
        if len(dom_text) > 3000:
            safe_dom = dom_text[:2000] + "\n...[중략]...\n" + dom_text[-1000:]
        else:
            safe_dom = dom_text

        # 1. 시스템 프롬프트: 행동 + 설명 동시 수행 허용
        system_prompt = (
            "당신은 시각장애인을 돕는 웹 브라우저 제어 AI입니다. "
            "사용자의 명령을 분석하여 **행동(Action)**과 **답변(Response)**을 생성하세요.\n\n"
            
            "**[필수 출력 규칙]**\n"
            "1. **행동(클릭 등)이 필요한 경우**:\n"
            "   - 반드시 답변의 맨 마지막에 **JSON 포맷**을 포함하세요.\n"
            "   - 예시: \n```json\n{\"type\": \"action\", \"name\": \"click\", \"target_name\": \"사이즈 버튼\", \"box_2d\": [ymin, xmin, ymax, xmax]}\n```\n"
            "2. **설명/답변**:\n"
            "   - JSON 앞부분에는 사용자의 질문에 대한 친절한 답변을 한국어 구어체로 작성하세요.\n"
            "   - 만약 클릭을 해야 정보를 알 수 있다면(예: 드롭다운), '버튼을 눌러 확인해볼게요.'라고 말하고 클릭 JSON을 출력하세요.\n"
            "   - 특수문자(**, ##)는 사용하지 마세요."
        )

        # 2. 유저 프롬프트
        user_content = [
            {"type": "image", "image": image_path},
            {"type": "text", "text": (
                f"현재 화면 DOM 정보: {safe_dom}\n\n"
                f"사용자 명령: \"{command}\"\n\n"
                "위 명령을 수행하세요. 질문에 답하고, 필요하다면 클릭 행동(JSON)을 수행하세요."
            )},
        ]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # 3. 전처리
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        vision_infos: Any = process_vision_info(messages)

        image_inputs = None
        video_inputs = None
        video_kwargs = {}

        if isinstance(vision_infos, (list, tuple)):
            if len(vision_infos) == 3:
                image_inputs, video_inputs, video_kwargs = vision_infos
            elif len(vision_infos) == 2:
                image_inputs, video_inputs = vision_infos
                video_kwargs = {}
        if video_kwargs is None: video_kwargs = {}

        processor_args = {
            "text": [text],
            "images": image_inputs,
            "padding": True,
            "return_tensors": "pt",
        }
        if video_inputs is not None: processor_args["videos"] = video_inputs
        if video_kwargs: processor_args.update(video_kwargs)

        inputs = self.processor(**processor_args).to(self.model.device)

        # 🕒 시간 측정 시작
        start_time_str = time.strftime('%H:%M:%S')
        start_time = time.time()
        print(f"\n⏳ [Start] AI 추론 시작 ({start_time_str}) | 명령어: {command}")

        # 4. 추론
        try:
            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=512,
                    do_sample=False, 
                    temperature=0.1, 
                )
        except Exception as e:
            print(f"❌ 추론 에러: {e}")
            return {"action": "none"}, "에러가 발생했습니다."
        
        # 🕒 시간 측정 종료
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"⏱️ [End] 모델 추론 완료 | 소요 시간: {elapsed_time:.2f}초")

        # 5. 결과 파싱 및 분리 (핵심 로직)
        output_ids = generated_ids[:, inputs.input_ids.shape[1]:]
        output_text = self.processor.batch_decode(output_ids, skip_special_tokens=True)[0].strip()

        action_response = {"action": "none"}
        summary_response = output_text

        # 1) Markdown Code Block 제거 (```json ... ```)
        clean_text = output_text
        json_pattern = r"```json\s*(\{.*?\})\s*```"
        json_match = re.search(json_pattern, output_text, re.DOTALL)

        if not json_match:
            # 코드블록이 없으면 그냥 중괄호 찾기
            json_pattern = r"(\{.*\})"
            json_match = re.search(json_pattern, output_text, re.DOTALL)

        # 2) JSON이 발견된 경우
        if json_match:
            try:
                json_str = json_match.group(1)
                data = json.loads(json_str)
                
                # 텍스트 답변에서 JSON 부분 제거 (순수 답변만 남기기)
                summary_response = output_text.replace(json_match.group(0), "").strip()
                # 혹시 남은 찌꺼기 제거
                summary_response = summary_response.replace("```json", "").replace("```", "").strip()
                if not summary_response:
                    summary_response = f"{data.get('target_name')} 요소를 클릭합니다."

                if data.get("type") == "action":
                    # 좌표 변환 (0~1000 -> 절대 좌표)
                    box = data.get("box_2d", [0,0,0,0])
                    
                    # 중심점 계산
                    cx_1000 = (box[1] + box[3]) / 2
                    cy_1000 = (box[0] + box[2]) / 2
                    
                    # 절대 좌표 (Physical Pixel)
                    abs_x = int((cx_1000 / 1000) * orig_w)
                    abs_y = int((cy_1000 / 1000) * orig_h)
                    
                    print(f"📐 좌표 변환: {cx_1000:.1f},{cy_1000:.1f} (1000분율) -> {abs_x},{abs_y}")

                    action_response = {
                        "action": "click",
                        "x_raw": abs_x,
                        "y_raw": abs_y,
                        "target": data.get("target_name", "타겟"),
                        "type": "absolute"
                    }
            except json.JSONDecodeError:
                print("⚠️ JSON 파싱 실패, 텍스트 답변만 반환")
        
        return action_response, summary_response