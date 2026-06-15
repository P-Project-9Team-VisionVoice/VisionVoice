"""
VisionVoice - Playwright DOM Agent (실험)

현재 방식:  스크린샷 → VLM → bbox 픽셀 좌표 → Chrome Extension 클릭
이 방식:    Playwright 브라우저 제어 → 스크린샷 → VLM → DOM 셀렉터 → .click()

장점: 픽셀 오차 없음, 좌표 추정 불필요, DOM 직접 조작
단점: 사용자 실제 브라우저가 아닌 Playwright 내장 브라우저 사용
"""

import torch
import time
import json
import re
import os
import tempfile
from pathlib import Path
from PIL import Image
from typing import Any

from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
from playwright.sync_api import sync_playwright, Page

MODEL_PATH = "/home/devlofi/models/Qwen2-VL-7B-Instruct"
SCREENSHOT_DIR = Path("/tmp/playwright_vv")
SCREENSHOT_DIR.mkdir(exist_ok=True)


SYSTEM_PROMPT = """\
당신은 시각장애인을 돕는 웹 브라우저 제어 AI입니다.
Playwright로 브라우저를 직접 제어하므로, 픽셀 좌표 대신 CSS 셀렉터나 텍스트로 요소를 지정하세요.

[지원 액션]
- click:    특정 요소 클릭
  {"type":"action","name":"click","selector":"input[title='검색']","fallback_text":"검색"}
- input:    입력창에 텍스트 입력
  {"type":"action","name":"input","selector":"input[title='검색']","text":"파이썬 강의","fallback_text":"검색창"}
- navigate: URL로 이동
  {"type":"action","name":"navigate","url":"https://www.naver.com"}
- scroll:   스크롤
  {"type":"action","name":"scroll","direction":"down","amount":500}
- describe: 화면 설명 (액션 없음)

[셀렉터 우선순위]
1. 가장 구체적인 CSS 셀렉터 (id, aria-label, title, placeholder 속성 등)
2. 없으면 fallback_text: 해당 텍스트를 포함하는 요소 찾기

[출력 규칙]
- 답변 마지막에 JSON 하나만 출력
- JSON 앞에 1~2문장 한국어 설명
"""


class PlaywrightAgent:
    def __init__(self):
        print("🎭 Playwright DOM Agent 로딩 중...")
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            MODEL_PATH,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True,
        )
        self.processor = AutoProcessor.from_pretrained(
            MODEL_PATH, trust_remote_code=True
        )
        self._pw = None
        self._browser = None
        self._page = None
        print("✓ PlaywrightAgent 준비 완료")

    # ── 브라우저 관리 ─────────────────────────────────────────────────────────

    def _ensure_browser(self):
        if self._page is None:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            self._page = self._browser.new_page(viewport={"width": 1280, "height": 800})
            print("🌐 Playwright 브라우저 시작")
        return self._page

    def navigate_to(self, url: str):
        page = self._ensure_browser()
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(1000)
        return page

    def _screenshot(self, page: Page) -> str:
        path = str(SCREENSHOT_DIR / f"shot_{int(time.time()*1000)}.png")
        page.screenshot(path=path, full_page=False)
        return path

    def _get_dom_summary(self, page: Page) -> str:
        try:
            dom = page.evaluate("""() => {
                const els = document.querySelectorAll(
                    'a, button, input, select, textarea, [role="button"], [role="link"], h1, h2, h3'
                );
                const items = [];
                for (const el of [...els].slice(0, 80)) {
                    const tag  = el.tagName.toLowerCase();
                    const text = (el.innerText || el.value || el.placeholder || el.title || el.getAttribute('aria-label') || '').trim().slice(0, 60);
                    const id_  = el.id ? `#${el.id}` : '';
                    const cls  = el.className ? `.${el.className.split(' ')[0]}` : '';
                    if (text) items.push(`[${tag}${id_}] ${text}`);
                }
                return items.join('\\n');
            }""")
            return dom[:3000]
        except Exception:
            return ""

    def close(self):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._page = self._browser = self._pw = None

    # ── VLM 추론 ─────────────────────────────────────────────────────────────

    def _vlm_infer(self, image_path: str, command: str, dom_text: str) -> tuple[dict, str]:
        image = Image.open(image_path).convert("RGB")

        dom_trimmed = dom_text[:2500] if len(dom_text) > 2500 else dom_text

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image_path},
                    {"type": "text", "text": f"[DOM 요소]\n{dom_trimmed}\n\n[명령]\n\"{command}\""},
                ],
            },
        ]

        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        vision_infos: Any = process_vision_info(messages)
        if isinstance(vision_infos, (list, tuple)) and len(vision_infos) == 3:
            image_inputs, video_inputs, video_kwargs = vision_infos
        elif isinstance(vision_infos, (list, tuple)) and len(vision_infos) == 2:
            image_inputs, video_inputs = vision_infos
            video_kwargs = {}
        else:
            image_inputs, video_inputs, video_kwargs = vision_infos, None, {}

        proc_args = {
            "text": [text],
            "images": image_inputs,
            "padding": True,
            "return_tensors": "pt",
        }
        if video_inputs is not None:
            proc_args["videos"] = video_inputs
        if video_kwargs:
            proc_args.update(video_kwargs)

        inputs = self.processor(**proc_args).to(self.model.device)

        t0 = time.time()
        with torch.no_grad():
            generated_ids = self.model.generate(
                **inputs, max_new_tokens=512, do_sample=False
            )
        elapsed = time.time() - t0
        print(f"⏱️ VLM 추론 {elapsed:.2f}초")

        output_ids = generated_ids[:, inputs.input_ids.shape[1]:]
        output_text = self.processor.batch_decode(
            output_ids, skip_special_tokens=True
        )[0].strip()

        # JSON 파싱
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output_text, re.DOTALL)
        if not json_match:
            json_match = re.search(r"(\{[^{}]*\})", output_text, re.DOTALL)

        action_data = {}
        summary = output_text
        if json_match:
            try:
                action_data = json.loads(json_match.group(1))
                summary = output_text.replace(json_match.group(0), "").strip()
            except json.JSONDecodeError:
                pass

        return action_data, summary, elapsed

    # ── DOM 액션 실행 ─────────────────────────────────────────────────────────

    def _execute_action(self, page: Page, data: dict) -> dict:
        name = data.get("name")
        result = {"success": False, "method": None, "error": None}

        try:
            if name == "click":
                selector = data.get("selector", "")
                fallback = data.get("fallback_text", "")

                if selector:
                    try:
                        page.click(selector, timeout=3000)
                        result.update({"success": True, "method": f"selector:{selector}"})
                        print(f"✅ 클릭 성공 (selector): {selector}")
                        return result
                    except Exception:
                        pass

                if fallback:
                    try:
                        page.get_by_text(fallback, exact=False).first.click(timeout=3000)
                        result.update({"success": True, "method": f"text:{fallback}"})
                        print(f"✅ 클릭 성공 (text): {fallback}")
                        return result
                    except Exception:
                        pass

                result["error"] = f"요소를 찾지 못함: {selector or fallback}"
                print(f"❌ 클릭 실패: {result['error']}")

            elif name == "input":
                selector = data.get("selector", "")
                text = data.get("text", "")
                fallback = data.get("fallback_text", "")

                if selector:
                    try:
                        page.fill(selector, text, timeout=3000)
                        result.update({"success": True, "method": f"selector:{selector}"})
                        print(f"✅ 입력 성공: '{text}' → {selector}")
                        return result
                    except Exception:
                        pass

                if fallback:
                    try:
                        page.get_by_placeholder(fallback).fill(text, timeout=3000)
                        result.update({"success": True, "method": f"placeholder:{fallback}"})
                        return result
                    except Exception:
                        pass

                result["error"] = "입력 요소를 찾지 못함"

            elif name == "navigate":
                url = data.get("url", "")
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(800)
                result.update({"success": True, "method": f"navigate:{url}"})

            elif name == "scroll":
                direction = data.get("direction", "down")
                amount = int(data.get("amount", 400))
                dy = amount if direction == "down" else -amount
                page.evaluate(f"window.scrollBy(0, {dy})")
                page.wait_for_timeout(400)
                result.update({"success": True, "method": f"scroll:{direction}"})

        except Exception as e:
            result["error"] = str(e)

        return result

    # ── 메인 인터페이스 ────────────────────────────────────────────────────────

    def run(self, url: str, command: str) -> dict:
        """
        URL + 음성 명령 → Playwright로 실행

        Returns:
            {
                action_data: VLM이 생성한 액션,
                exec_result: Playwright 실행 결과,
                summary: VLM 텍스트 답변,
                vlm_time: 추론 소요 시간,
                screenshot_before: 실행 전 스크린샷 경로,
                screenshot_after:  실행 후 스크린샷 경로,
            }
        """
        page = self.navigate_to(url)

        screenshot_before = self._screenshot(page)
        dom_text = self._get_dom_summary(page)

        print(f"\n🎤 명령: {command}")
        print(f"🌐 URL: {url}")
        print(f"📄 DOM 요소 {len(dom_text.splitlines())}개 추출")

        action_data, summary, vlm_time = self._vlm_infer(screenshot_before, command, dom_text)

        exec_result = {"success": False, "method": None, "error": "액션 없음"}
        if action_data.get("type") == "action":
            exec_result = self._execute_action(page, action_data)
            page.wait_for_timeout(800)

        screenshot_after = self._screenshot(page)

        return {
            "action_data": action_data,
            "exec_result": exec_result,
            "summary": summary,
            "vlm_time": vlm_time,
            "screenshot_before": screenshot_before,
            "screenshot_after": screenshot_after,
        }
