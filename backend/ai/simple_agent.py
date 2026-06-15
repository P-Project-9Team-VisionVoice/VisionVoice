# backend/ai/simple_agent.py
from .config import USE_MOCK_AGENT
import torch
import time
import json
import re
from PIL import Image
from typing import Any
from .omniparser_grounding import refine_bbox

if not USE_MOCK_AGENT:
    from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
    from qwen_vl_utils import process_vision_info


class OpenCUAgent:
    def __init__(self):
        if not USE_MOCK_AGENT:
            print("🧠 Vision Agent (Qwen3-VL-8B) 로딩 중...")
            model_path = "/home/devlofi/models/Qwen3-VL-8B-Instruct"

            self.model = Qwen3VLForConditionalGeneration.from_pretrained(
                model_path,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True,
            )
            self.processor = AutoProcessor.from_pretrained(
                model_path,
                trust_remote_code=True,
            )
            print(f"🔍 모델 디바이스: {self.model.device}")
        else:
            print("🧠 OpenCUA Mock 모드 대기 중")

    def inference(self, image_path, command, dom_text, dom_elements="[]"):
        if USE_MOCK_AGENT:
            return {"action": "none"}, "테스트 완료"

        # 이미지 로드
        image = Image.open(image_path).convert("RGB")
        orig_w, orig_h = image.size

        # DOM 길이 제한
        if len(dom_text) > 3000:
            safe_dom = dom_text[:2000] + "\n...[중략]...\n" + dom_text[-1000:]
        else:
            safe_dom = dom_text

        # 1. 시스템 프롬프트: 행동 + 설명 동시 수행 허용
        system_prompt = (
            "당신은 시각장애인을 돕는 웹 브라우저 제어 AI입니다. "
            "사용자의 명령을 분석하여 행동(Action)과 답변(Response)을 생성하세요.\n\n"
            "[지원되는 액션 타입]\n"
            "- click: 특정 버튼/링크를 클릭합니다. DOM 요소 목록에서 일치하는 selector가 있으면 css_selector도 함께 출력하세요.\n"
            "  예: {\"type\": \"action\", \"name\": \"click\", \"target_name\": \"사이즈 버튼\", \"box_2d\": [ymin, xmin, ymax, xmax], \"css_selector\": \"#size-btn\"}\n"
            "- scroll: 화면을 위/아래로 스크롤합니다.\n"
            "  예: {\"type\": \"action\", \"name\": \"scroll\", \"direction\": \"down\", \"amount\": 300}\n"
            "- input: 입력창을 클릭한 뒤 텍스트를 입력합니다. '검색해줘' 처럼 제출까지 원하면 submit을 true로 설정하세요.\n"
            "  예(입력만): {\"type\": \"action\", \"name\": \"input\", \"target_name\": \"검색창\", \"box_2d\": [ymin, xmin, ymax, xmax], \"text\": \"패딩\", \"submit\": false}\n"
            "  예(입력+검색): {\"type\": \"action\", \"name\": \"input\", \"target_name\": \"검색창\", \"box_2d\": [ymin, xmin, ymax, xmax], \"text\": \"패딩\", \"submit\": true}\n"
            "- navigate: 링크나 버튼을 눌러 다른 페이지로 이동합니다.\n"
            "  예: {\"type\": \"action\", \"name\": \"navigate\", \"target_name\": \"장바구니 페이지\"}\n"
            "- close: 팝업이나 알림창을 닫습니다.\n"
            "  예: {\"type\": \"action\", \"name\": \"close\", \"target_name\": \"팝업 닫기 버튼\"}\n"
            "- accessibility: 접근성 설정을 변경합니다 (고대비/확대/다크모드 등).\n"
            "  예: {\"type\": \"action\", \"name\": \"accessibility\", \"mode\": \"high_contrast\"}\n"
            "  mode 값: high_contrast(고대비), grayscale(흑백/색맹), dark_mode(다크모드), "
            "zoom_150(150%확대), zoom_200(200%확대), zoom_100(기본크기), highlight(포커스하이라이트), reset(초기화)\n\n"
            "[필수 출력 규칙]\n"
            "1. 사용자 명령에 '클릭', '눌러', '선택해', '스크롤', '내려줘', '올려줘', '입력해', '검색해', '이동해', '닫아줘' 같은 단어가 하나라도 있으면,\n"
            "   반드시 위 액션 타입 중 하나를 선택해 JSON을 출력해야 합니다.\n"
            "2. JSON은 항상 답변의 맨 마지막에 출력하고, 하나의 JSON만 출력하세요.\n"
            "3. JSON 앞부분에는 사용자의 질문에 대한 친절한 설명을 한국어 구어체로 1~3문장만 작성하세요.\n"
            "4. JSON 안의 문자열은 모두 쌍따옴표(\"\")만 사용하고, 주석이나 추가 텍스트를 넣지 마세요.\n"
        )

        # 2. 유저 프롬프트 (규칙 설명은 빼고, 화면/명령만 전달)
        user_content = [
            {"type": "image", "image": image_path},
            {
                "type": "text",
                "text": (
                    f"[웹 페이지 텍스트]\n{safe_dom}\n\n"
                    f"[클릭 가능한 DOM 요소 목록 (CSS 셀렉터 포함)]\n{dom_elements[:2000]}\n\n"
                    f"[사용자 명령]\n\"{command}\"\n\n"
                    "위 정보를 참고해서 사용자의 명령을 수행하거나 화면을 설명해 주세요. "
                    "클릭 대상이 DOM 요소 목록에 있으면 해당 css_selector를 JSON에 포함하세요."
                ),
            },
        ]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # 3. 전처리
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
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
        if video_kwargs is None:
            video_kwargs = {}

        processor_args = {
            "text": [text],
            "images": image_inputs,
            "padding": True,
            "return_tensors": "pt",
        }
        if video_inputs is not None:
            processor_args["videos"] = video_inputs
        if video_kwargs:
            processor_args.update(video_kwargs)

        inputs = self.processor(**processor_args).to(self.model.device)

        # 🕒 시간 측정 시작
        start_time_str = time.strftime("%H:%M:%S")
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

        # 5. 결과 파싱 및 분리
        output_ids = generated_ids[:, inputs.input_ids.shape[1] :]
        output_text = self.processor.batch_decode(
            output_ids, skip_special_tokens=True
        )[0].strip()

        action_response = {"action": "none"}
        summary_response = output_text

        # JSON 추출: ```json {...} ``` 또는 bare {...}
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output_text, re.DOTALL)
        if not json_match:
            json_match = re.search(r"(\{[^{}]*\})", output_text, re.DOTALL)

        if json_match:
            try:
                json_str = json_match.group(1)
                data = json.loads(json_str)

                # 텍스트 답변에서 JSON 부분 제거
                summary_response = output_text.replace(json_match.group(0), "").strip()
                summary_response = (
                    summary_response.replace("``````", "").strip()
                )
                if not summary_response:
                    target = data.get("target_name") or data.get("name") or "요청"
                    summary_response = f"{target}을(를) 수행합니다."

                if data.get("type") == "action":
                    name = data.get("name")

                    if name == "click":
                        box = data.get("box_2d")
                        if box and len(box) == 4:
                            # Hybrid Grounding v2: VLM bbox → OmniParser 정밀화
                            refined = refine_bbox(
                                image_path=image_path,
                                vlm_box_norm=box,   # [y1, x1, y2, x2] 0~1000
                                orig_w=orig_w,
                                orig_h=orig_h,
                            )
                            abs_x = refined["x"]
                            abs_y = refined["y"]
                            grounding_source = refined["source"]
                            print(
                                f"📐 Hybrid Grounding v2 ({grounding_source}): ({abs_x},{abs_y})"
                            )
                            action_response = {
                                "action": "click",
                                "x_raw": abs_x,
                                "y_raw": abs_y,
                                "box_px": refined.get("box_px"),
                                "css_selector": data.get("css_selector"),
                                "target": data.get("target_name", "타겟"),
                                "type": "absolute",
                                "grounding": grounding_source,
                            }
                        else:
                            # 좌표가 없으면 타겟 이름 기반 클릭으로 fallback
                            action_response = {
                                "action": "click",
                                "x_raw": None,
                                "y_raw": None,
                                "target": data.get("target_name", "타겟"),
                                "type": "no_coordinate",
                            }

                    elif name == "scroll":
                        action_response = {
                            "action": "scroll",
                            "direction": data.get("direction", "down"),
                            "amount": int(data.get("amount", 300)),
                        }

                    elif name == "input":
                        box = data.get("box_2d")
                        x_raw, y_raw, grounding_src = None, None, None
                        if box and len(box) == 4:
                            refined = refine_bbox(
                                image_path=image_path,
                                vlm_box_norm=box,
                                orig_w=orig_w,
                                orig_h=orig_h,
                            )
                            x_raw = refined["x"]
                            y_raw = refined["y"]
                            grounding_src = refined["source"]
                            print(f"📐 Input Grounding ({grounding_src}): ({x_raw},{y_raw})")
                        action_response = {
                            "action": "input",
                            "target": data.get("target_name", "입력창"),
                            "text": data.get("text", ""),
                            "submit": bool(data.get("submit", False)),
                            "x_raw": x_raw,
                            "y_raw": y_raw,
                        }

                    elif name == "navigate":
                        action_response = {
                            "action": "navigate",
                            "target": data.get("target_name", ""),
                        }

                    elif name == "close":
                        action_response = {
                            "action": "close",
                            "target": data.get("target_name", "팝업"),
                        }

            except json.JSONDecodeError:
                print("⚠️ JSON 파싱 실패, 텍스트 답변만 반환")

        return action_response, summary_response
