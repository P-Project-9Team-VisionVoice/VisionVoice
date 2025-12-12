from PIL import Image
import json
import re
import logging
from .config import USE_MOCK_AGENT

if not USE_MOCK_AGENT:
    import torch
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor

# 로거 설정
logger = logging.getLogger(__name__)

# DOM 텍스트 최대 길이 (토큰 기준)
MAX_DOM_LENGTH = 6000

# 모델 생성 토큰 수
MAX_NEW_TOKENS = 1024

ACTION_GUIDE = """
당신은 'VisionVoice'라는 웹 조작 에이전트입니다.
사용자의 음성 명령과 웹 페이지의 DOM 텍스트, 스크린샷을 보고
'어떤 동작들을 어떤 순서로 수행해야 하는지'를 JSON으로만 출력해야 합니다.

[출력 형식 규칙]

1. 반드시 유효한 JSON만 출력하십시오.
2. JSON 바깥에 한국어 설명, 자연어 텍스트, 코멘트 등을 절대 추가하지 마십시오.
3. 최상위 구조는 다음과 같습니다.

{
  "action": "click",
  "x": 0.5,
  "y": 0.5,
  "actions": [
    { ... 개별 액션 ... }
  ],
  "finished": false
}

- action : 대표 액션 타입 (actions[0].action 과 동일하게 맞춰주세요)
- x, y   : 좌표 기반 대표 액션(click)의 0~1 비율 좌표 (클릭이 아닐 경우 0.0)
- actions: 실제로 수행해야 하는 액션들의 리스트 (순서 중요)
- finished: 사용자의 목표가 완전히 달성되었다고 판단되면 true, 아직 더 필요하면 false

[지원하는 개별 액션 타입들]

1) 클릭(click)
{
  "action": "click",
  "x": 0.52,
  "y": 0.18
}

2) 스크롤(scroll)
{
  "action": "scroll",
  "direction": "down",
  "amount": 300
}

3) 입력(type)
{
  "action": "type",
  "text": "가천대학교 시간표"
}

4) 키 입력(press)
{
  "action": "press",
  "key": "enter"
}

5) 페이지 이동(navigate)
{
  "action": "navigate",
  "url": "https://www.gov.kr"
}

[주의 사항]

- DOM 텍스트와 스크린샷을 활용하여 실제로 존재하는 버튼/링크/입력창만 조작하세요.
- 존재하지 않는 UI를 상상하거나, 의미 없는 랜덤 좌표를 생성하지 마십시오.
- x, y 좌표는 반드시 0.0 ~ 1.0 사이 값이어야 합니다.
- 반드시 JSON 형식만 출력하고, 추가 설명은 출력하지 마세요.
"""


class OpenCUAgent:

    def __init__(self):
        if not USE_MOCK_AGENT:
            logger.info("🧠 OpenCUA 모델 로딩 중...")
            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                "xlangai/OpenCUA-7B",
                torch_dtype=torch.bfloat16,
                device_map="auto",
            )
            self.processor = AutoProcessor.from_pretrained("xlangai/OpenCUA-7B")
            logger.info("✅ 모델 로딩 완료")
        else:
            logger.info("🧪 MOCK 모드로 실행 중 (실제 모델 미사용)")

    def inference(self, image_path: str, command: str, dom_text: str):
        """메인 inference 함수"""

        if USE_MOCK_AGENT:
            logger.debug("🧪 MOCK 모드 실행")
            return self.mock_response(command)

        try:
            image = Image.open(image_path).convert("RGB")
        except Exception as e:
            logger.error(f"이미지 로드 실패: {e}")
            return self._error_response("이미지 로드 실패")

        # 모드 분기
        if self.is_explain_mode(command):
            return self.explain_mode(image, command)
        elif self.is_find_mode(command):
            return self.find_mode(image, command)
        elif self.is_summary_mode(command):
            return self.summary_mode(image, dom_text)
        else:
            return self.action_mode(image, command, dom_text)

    def mock_response(self, command: str):
        """MOCK 모드 응답 (딕셔너리 매핑으로 단순화)"""

        # 패턴별 응답 매핑
        patterns = [
            (["설명"], lambda: (
                [{"action": "none", "description": "네이버 메인 페이지입니다."}],
                "MOCK 설명"
            )),
            (["어디", "찾아", "위치"], lambda: (
                [{"action": "click", "x": 0.32, "y": 0.12, "description": "요소 위치"}],
                "MOCK 요소 찾기"
            )),
            (["요약", "중요"], lambda: (
                [{"action": "none"}],
                "MOCK 요약"
            )),
            (["스크롤", "내려", "올려"], lambda: (
                [{"action": "scroll", "direction": "up" if "올려" in command else "down", "amount": 300}],
                "MOCK 스크롤"
            )),
            (["입력", "쳐줘", "검색"], lambda: (
                [{"action": "type", "text": "가천대학교"}],
                "MOCK 입력"
            )),
            (["이동", "열어", "들어가"], lambda: (
                [{"action": "navigate", "url": "https://www.gov.kr"}],
                "MOCK 이동"
            )),
            (["엔터", "enter"], lambda: (
                [{"action": "press", "key": "enter"}],
                "MOCK 엔터"
            )),
        ]

        # 패턴 매칭
        for keywords, handler in patterns:
            if any(kw in command for kw in keywords):
                actions, summary = handler()
                return self._build_response(actions, False), summary

        # 기본: 중앙 클릭
        return self._build_response([{"action": "click", "x": 0.5, "y": 0.5}], False), "MOCK 기본 클릭"

    def _build_response(self, actions: list, finished: bool = False) -> dict:
        """표준 응답 형식 생성"""
        primary = actions[0] if actions else {"action": "none"}

        return {
            "action": primary.get("action", "none"),
            "x": self._clamp_coord(primary.get("x", 0.0)),
            "y": self._clamp_coord(primary.get("y", 0.0)),
            "actions": actions,
            "finished": finished,
        }

    def _error_response(self, error_msg: str) -> tuple:
        """에러 응답 생성"""
        return {
            "action": "none",
            "x": 0.0,
            "y": 0.0,
            "actions": [],
            "finished": False,
            "error": error_msg
        }, error_msg

    # 모드 판별
    def is_explain_mode(self, cmd):
        return any(kw in cmd for kw in ["설명", "explain", "뭐야"])

    def is_find_mode(self, cmd):
        return any(kw in cmd for kw in ["어디", "찾아", "위치", "find"])

    def is_summary_mode(self, cmd):
        return any(kw in cmd for kw in ["요약", "중요", "summary"])

    # 모드별 실행
    def explain_mode(self, image, command):
        prompt = f"""당신은 웹 화면 분석 보조 에이전트입니다.

사용자 요청: {command}

이미지를 보고 화면에 보이는 내용을 한국어로 자세하게 설명하세요.
주요 요소, 레이아웃, 텍스트 내용을 포함하세요."""

        return self.run_llm(image, prompt, mode="explain")

    def find_mode(self, image, command):
        prompt = f"""당신은 화면 속 UI 요소를 찾아주는 보조 에이전트입니다.

사용자 요청: {command}

이미지를 보고 사용자가 찾는 요소의 위치를 설명하고,
0~1 사이 비율 좌표(x, y)를 JSON 형식으로 출력하세요.

형식: {{"x": 0.5, "y": 0.3, "description": "요소 설명"}}"""

        return self.run_llm(image, prompt, mode="find")

    def summary_mode(self, image, dom_text):
        # DOM 텍스트 전처리
        safe_dom = self._preprocess_dom(dom_text)

        prompt = f"""다음 웹 페이지의 DOM 텍스트를 분석하여 중요한 정보를 요약하세요.

[DOM_TEXT]
{safe_dom}

요약은 한국어로, 핵심 내용만 2~3문장으로 출력하세요."""

        return self.run_llm(None, prompt, mode="summary")

    def action_mode(self, image, command, dom_text):
        """멀티 액션 모드"""
        safe_dom = self._preprocess_dom(dom_text)

        prompt = f"""{ACTION_GUIDE}

[DOM_TEXT]
{safe_dom}

[USER_COMMAND]
{command}

위 규칙을 지켜서 JSON만 출력하세요. 반드시 유효한 JSON 형식이어야 합니다."""

        return self.run_llm(image, prompt, mode="action")

    def run_llm(self, image, prompt, mode: str):
        """LLM 실행 공통 함수"""
        try:
            inputs = self.processor(
                text=prompt,
                images=image,
                return_tensors="pt"
            ).to(self.model.device)

            with torch.no_grad():
                output_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS,
                    do_sample=False,  # 결정론적 출력
                )

            output_text = self.processor.batch_decode(
                output_ids,
                skip_special_tokens=True
            )[0]

            logger.debug(f"모델 출력 ({mode}): {output_text[:200]}...")

            if mode == "action":
                parsed = self.parse_action_json(output_text)
                normalized = self.normalize_action_json(parsed)
                return normalized, "LLM action JSON"

            return {"output": output_text}, output_text

        except Exception as e:
            logger.error(f"LLM 실행 실패 ({mode}): {e}")
            return self._error_response(f"LLM 오류: {str(e)}")

    def _preprocess_dom(self, dom_text: str) -> str:
        """DOM 텍스트 전처리 - 스마트 자르기"""
        if not dom_text:
            return ""

        # 1. 길이 제한
        if len(dom_text) <= MAX_DOM_LENGTH:
            return dom_text

        # 2. 중요 섹션 추출 (예: nav, main, button, input 태그 우선)
        # 실제로는 더 정교한 로직 필요
        return dom_text[:MAX_DOM_LENGTH] + "\n... (생략)"

    def _extract_json_block(self, raw_text: str) -> str:
        """LLM 출력에서 JSON 블록만 최대한 안전하게 추출"""

        if not raw_text:
            return ""

        # 1) 앞뒤 공백 정리
        cleaned = raw_text.strip()

        # 2) ```json / ``` 코드블록 마크다운 제거
        if cleaned.startswith("```"):
            # ```json 으로 시작하는 경우도 처리
            cleaned = re.sub(r"^```json\s*", "```", cleaned, flags=re.IGNORECASE)
            if cleaned.endswith("```"):
                cleaned = cleaned[3:-3].strip()

        # 3) 정규식으로 JSON 패턴 찾기
        json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
        matches = re.finditer(json_pattern, cleaned, re.DOTALL)

        for match in matches:
            candidate = match.group(0)
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue

        # 4) 정규식으로도 못 찾으면, 단순 범위 기반 fallback
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return cleaned[start:end + 1]

        # 5) 진짜로 JSON 블록을 못 찾으면, 정제된 전체 텍스트 반환
        return cleaned

    def parse_action_json(self, raw_text: str) -> dict:
        """action JSON 파싱"""
        json_text = self._extract_json_block(raw_text)

        try:
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 파싱 실패: {e}")
            logger.debug(f"파싱 시도한 텍스트: {json_text}")
            return {"raw_output": raw_text, "parse_error": str(e)}

    def normalize_action_json(self, action_json: dict) -> dict:
        """action JSON 규격 보정.

        - raw_output이 있으면 파싱 실패로 간주하고 기본 응답 반환
        - actions가 없거나 리스트가 아니면 리스트로 보정
        - 상단 레벨에만 action/x/y가 있는 경우, 이를 1개짜리 액션으로 만들어 actions에 넣어줌
        - 모든 좌표는 0~1 범위로 clamp
        - finished 기본값은 False
        """

        # 0. 파싱 실패 케이스
        if not isinstance(action_json, dict) or "raw_output" in action_json:
            logger.error("JSON 파싱 실패 또는 비정상 형식, 기본 응답 반환")
            return self._build_response([{"action": "none"}], False)

        # 1. actions 필드 보정
        actions = action_json.get("actions")
        if not isinstance(actions, list):
            actions = []
        action_json["actions"] = actions

        # 2. 상단 레벨의 action/x/y만 있는 경우, 이를 1개짜리 액션으로 승격
        #    예: {"action": "click", "x": 0.3, "y": 0.4}
        if not actions:
            top_action = action_json.get("action")
            top_x = action_json.get("x", None)
            top_y = action_json.get("y", None)

            if top_action is not None and (top_x is not None or top_y is not None):
                actions.append({
                    "action": top_action,
                    "x": self._clamp_coord(top_x if top_x is not None else 0.0),
                    "y": self._clamp_coord(top_y if top_y is not None else 0.0),
                })
                action_json["actions"] = actions

        # 3. 각 액션의 좌표/필드 보정
        for action in actions:
            # action 타입 기본값
            if "action" not in action:
                action["action"] = "none"

            # 좌표 clamp
            if "x" in action:
                action["x"] = self._clamp_coord(action["x"])
            if "y" in action:
                action["y"] = self._clamp_coord(action["y"])

        # 4. 대표 액션 보정 (top-level "action")
        if "action" not in action_json:
            if actions:
                action_json["action"] = actions[0].get("action", "none")
            else:
                action_json["action"] = "none"

        # 5. 대표 좌표 보정 (top-level x, y)
        #    actions[0] 좌표를 우선 사용, 없으면 기존 값 clamp
        if actions:
            primary = actions[0]
            action_json["x"] = self._clamp_coord(primary.get("x", action_json.get("x", 0.0)))
            action_json["y"] = self._clamp_coord(primary.get("y", action_json.get("y", 0.0)))
        else:
            action_json["x"] = self._clamp_coord(action_json.get("x", 0.0))
            action_json["y"] = self._clamp_coord(action_json.get("y", 0.0))

        # 6. finished 기본값
        action_json.setdefault("finished", False)

        return action_json

    def _clamp_coord(self, value: float) -> float:
        """좌표를 0~1 범위로 제한"""
        try:
            val = float(value)
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            logger.warning(f"유효하지 않은 좌표 값: {value}")
            return 0.0

    def convert_coordinates(self, x_ratio: float, y_ratio: float,
                            orig_w: int, orig_h: int):
        """좌표 변환 (현재는 비율 그대로 반환)"""
        # 추후 devicePixelRatio 보정 등 추가 가능
        return self._clamp_coord(x_ratio), self._clamp_coord(y_ratio)