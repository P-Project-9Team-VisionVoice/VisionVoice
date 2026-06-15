"""
Playwright DOM Agent 실험 테스트
현재 방식(픽셀 클릭) vs Playwright(DOM 직접) 비교

실행: /home/devlofi/miniforge3/bin/python3 test_playwright.py
"""

import sys
import time
sys.path.insert(0, "/home/devlofi/HyeWon/VisionVoice/backend")

from ai.playwright_agent import PlaywrightAgent

TESTS = [
    {
        "url": "https://www.naver.com",
        "command": "파이썬 강의 검색해줘",
    },
    {
        "url": "https://www.youtube.com",
        "command": "검색창에 BTS 입력해줘",
    },
]

def run_test(agent, test_case):
    url = test_case["url"]
    cmd = test_case["command"]

    print(f"\n{'='*60}")
    print(f"URL:  {url}")
    print(f"명령: {cmd}")
    print('='*60)

    t_start = time.time()
    result = agent.run(url, cmd)
    t_total = time.time() - t_start

    print(f"\n[VLM 출력]")
    print(f"  답변: {result['summary'][:100]}")
    print(f"  액션: {result['action_data']}")
    print(f"\n[실행 결과]")
    print(f"  성공: {result['exec_result']['success']}")
    print(f"  방법: {result['exec_result']['method']}")
    if result['exec_result']['error']:
        print(f"  오류: {result['exec_result']['error']}")
    print(f"\n[시간]")
    print(f"  VLM 추론: {result['vlm_time']:.2f}초")
    print(f"  전체:     {t_total:.2f}초")
    print(f"\n[스크린샷]")
    print(f"  실행 전: {result['screenshot_before']}")
    print(f"  실행 후: {result['screenshot_after']}")

    return result

if __name__ == "__main__":
    agent = PlaywrightAgent()

    try:
        for i, test in enumerate(TESTS):
            run_test(agent, test)
            if i < len(TESTS) - 1:
                time.sleep(1)
    finally:
        agent.close()
        print("\n✅ 테스트 완료")
