"""
VisionVoice 학습 데이터 자동 수집
Playwright로 한국 주요 사이트 스크린샷 + DOM bbox 추출
"""
import json
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path("/home/devlofi/HyeWon/finetune/dataset")
IMG_DIR = OUTPUT_DIR / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR.mkdir(parents=True, exist_ok=True)

SITES = [
    # ── 포털/검색 ──
    ("naver_main",       "https://www.naver.com"),
    ("naver_shopping",   "https://shopping.naver.com"),
    ("naver_news",       "https://news.naver.com"),
    ("google_main",      "https://www.google.com"),
    ("daum_main",        "https://www.daum.net"),
    ("papago",           "https://papago.naver.com"),
    # ── 동영상/미디어/웹툰 ──
    ("youtube_main",     "https://www.youtube.com"),
    ("naver_webtoon",    "https://comic.naver.com"),
    ("joongang_news",    "https://www.joongang.co.kr"),
    # ── 커머스/쇼핑 ──
    ("musinsa_main",     "https://www.musinsa.com"),
    ("coupang_main",     "https://www.coupang.com"),
    ("gmarket_main",     "https://www.gmarket.co.kr"),
    ("st11_main",        "https://www.11st.co.kr"),
    ("oliveyoung_main",  "https://www.oliveyoung.co.kr"),
    ("kurly_main",       "https://www.kurly.com"),
    ("auction_main",     "https://www.auction.co.kr"),
    # ── 여행/예약 ──
    ("cgv_main",         "https://www.cgv.co.kr"),
    ("megabox_main",     "https://www.megabox.co.kr"),
    ("korail_main",      "https://www.letskorail.com"),
    ("interpark_ticket", "https://tickets.interpark.com"),
    # ── 정부/공공 ──
    ("gov24_main",       "https://www.gov.kr"),
    ("hometax_main",     "https://www.hometax.go.kr"),
    ("nhis_main",        "https://www.nhis.or.kr"),
    # ── 커뮤니티/SNS ──
    ("kakao_main",       "https://www.kakao.com"),
    ("dcinside_main",    "https://www.dcinside.com"),
    ("fmkorea_main",     "https://www.fmkorea.com"),
    ("reddit_main",      "https://www.reddit.com"),
    # ── 금융/핀테크 ──
    ("toss_main",        "https://toss.im"),
    ("kakaobank_main",   "https://www.kakaobank.com"),
    # ── 지도/서비스 ──
    ("naver_map",        "https://map.naver.com"),
]

SELECTOR = "a, button, input, textarea, select, [role='button'], [role='link'], [role='menuitem']"

# 각 target 텍스트에 대한 명령어 템플릿 (다양한 표현)
CLICK_TEMPLATES = [
    "{target} 클릭해줘",
    "{target} 눌러줘",
    "{target} 눌러봐",
    "{target} 열어줘",
    "{target} 가줘",
    "{target} 선택해줘",
    "{target} 버튼 클릭해줘",
    "{target} 눌러",
]
INPUT_TEMPLATES = [
    "{target}에 입력하고 싶어",
    "{target} 칸 클릭해줘",
    "{target} 입력창 눌러줘",
    "{target} 선택해줘",
]
EXPLAIN_TEMPLATES = [
    "이 화면 설명해줘",
    "지금 화면 어떻게 생겼어?",
    "화면에 뭐가 있어?",
    "이 페이지 뭔지 설명해줘",
    "지금 뭐가 보여?",
]
SCROLL_TEMPLATES = [
    "아래로 내려줘",
    "스크롤 내려줘",
    "더 내려줘",
    "위로 올려줘",
    "스크롤 올려줘",
]


def collect_site(page, site_id, url):
    print(f"\n[{site_id}] {url} 접속 중...")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
    except Exception as e:
        print(f"  접속 실패: {e}")
        return []

    img_path = IMG_DIR / f"{site_id}.png"
    page.screenshot(path=str(img_path), full_page=False)
    print(f"  스크린샷: {img_path.name}")

    elements = page.query_selector_all(SELECTOR)
    samples = []

    for el in elements:
        try:
            if not el.is_visible():
                continue
            box = el.bounding_box()
            if not box:
                continue
            if box["width"] < 10 or box["height"] < 10:
                continue
            # 화면 밖 요소 제외 (x, y 모두 체크)
            if box["y"] > 800 or box["y"] < 0:
                continue
            if box["x"] > 1280 or box["x"] < 0:
                continue

            tag = el.evaluate("el => el.tagName.toLowerCase()")
            text = (
                el.inner_text().strip()
                or el.get_attribute("placeholder")
                or el.get_attribute("aria-label")
                or el.get_attribute("title")
                or ""
            )
            text = text.replace("\n", " ").strip()[:50]
            if not text:
                continue

            action = "input" if tag in ("input", "textarea", "select") else "click"

            # 0~1000 정규화 좌표 (Qwen3-VL 포맷)
            vw = page.viewport_size["width"]
            vh = page.viewport_size["height"]
            bbox = [
                round(box["x"] / vw * 1000),
                round(box["y"] / vh * 1000),
                round((box["x"] + box["width"]) / vw * 1000),
                round((box["y"] + box["height"]) / vh * 1000),
            ]

            # 명령어 템플릿 선택
            templates = INPUT_TEMPLATES if action == "input" else CLICK_TEMPLATES
            import random
            command = random.choice(templates).format(target=text)

            speech = (
                f"'{text}' 입력창을 선택하겠습니다."
                if action == "input"
                else f"'{text}'을(를) 클릭하겠습니다."
            )

            samples.append({
                "id": f"{site_id}_{len(samples):03d}",
                "image": f"images/{site_id}.png",
                "command": command,
                "action": action,
                "target": text,
                "bbox": bbox,
                "speech": speech,
            })
        except Exception:
            continue

    # explain + scroll 샘플 추가 (사이트당 각 3개)
    import random
    for tmpl in random.sample(EXPLAIN_TEMPLATES, min(3, len(EXPLAIN_TEMPLATES))):
        samples.append({
            "id": f"{site_id}_explain_{len(samples):03d}",
            "image": f"images/{site_id}.png",
            "command": tmpl,
            "action": "explain",
            "target": "전체 화면",
            "bbox": [0, 0, 1000, 1000],
            "speech": "화면을 분석하겠습니다.",
        })
    for tmpl in random.sample(SCROLL_TEMPLATES, min(2, len(SCROLL_TEMPLATES))):
        direction = "down" if "내려" in tmpl else "up"
        samples.append({
            "id": f"{site_id}_scroll_{len(samples):03d}",
            "image": f"images/{site_id}.png",
            "command": tmpl,
            "action": "scroll",
            "target": "페이지",
            "bbox": [0, 0, 1000, 1000],
            "speech": "스크롤하겠습니다.",
            "direction": direction,
        })

    print(f"  수집: {len(samples)}개 샘플")
    return samples


def main():
    all_samples = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ko-KR",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        for site_id, url in SITES:
            page = context.new_page()
            samples = collect_site(page, site_id, url)
            all_samples.extend(samples)
            page.close()

        browser.close()

    out_path = OUTPUT_DIR / "raw_samples.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_samples, f, ensure_ascii=False, indent=2)

    print(f"\n총 {len(all_samples)}개 샘플 저장 → {out_path}")


if __name__ == "__main__":
    main()
