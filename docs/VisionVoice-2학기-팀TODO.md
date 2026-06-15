# VisionVoice 졸업작품 2 — 2학기 개발 계획

## 전체 목표

> **"시각장애인을 위한 능동형 AI 에이전트"의 정확도를 끌어올리고, 브라우저 밖까지 확장한다.**

1학기에 MVP를 만들어서 동작하는 것까지 확인했고,
2학기에는 **정확도 개선** + **Tool 확장(MCP)** + **Fine-tuning**으로 완성도를 높인다.

---

## 현재 시스템 한계 (왜 개선해야 하는가)

| 문제 | 원인 | 영향 |
|---|---|---|
| 클릭 정확도 낮음 | Qwen2-VL의 bbox 예측이 부정확 | 엉뚱한 곳 클릭 |
| DOM 정보 빈약 | `innerText` 3000자 잘라서 전달 | AI가 페이지 구조 파악 못함 |
| 단일 턴만 가능 | 한 번 명령 → 한 번 액션 → 끝 | 복합 명령 수행 불가 |
| 브라우저 밖 불가 | Chrome Extension 한정 | 파일/메일/캘린더 등 접근 불가 |

---

## 2학기 Phase 로드맵

```
Phase 1 (5~6월)    정확도 개선 — 프롬프트, DOM 전처리, 스코어링
Phase 2 (6~7월)    평가 체계 — 데이터셋 구축 + 정량 벤치마크
Phase 3 (7~9월)    Tool 확장 — MCP 컨셉 기반 멀티앱 연동
Phase 4 (9~10월)   Fine-tuning — QLoRA 기반 경량 학습
Phase 5 (11~12월)  통합 + 최종 발표 준비
```

---

## 역할 분담

| 담당 | 이름 | 주요 역할 | GPU 필요 |
|---|---|---|---|
| **리드** | 조혜원 | 아키텍처 설계, 멀티턴 에이전트, Fine-tuning, Tool Router | O (DGX) |
| **A** | (이름) | DOM 전처리 고도화 + 파일시스템 Tool | X |
| **B** | (이름) | 프롬프트 엔지니어링 + intent 분류 | Colab 무료 |
| **C** | (이름) | Grounding 스코어링 개선 + Gmail Tool | X |
| **D** | (이름) | 평가 데이터셋 구축 + 문서 정리 | X |

---

## 팀원별 상세 TODO

---

### 팀원 A — DOM 전처리 고도화 + 파일시스템 Tool

#### Task A-1: DOM 구조화 추출 모듈 (Phase 1)

**현재 문제:**
현재 content.js에서 DOM을 이렇게 보내고 있음:
```js
const dom = document.body.innerText.replace(/\s+/g, ' ').slice(0, 3000);
```
→ 그냥 텍스트 덩어리라서 AI가 어떤 버튼이 어디 있는지 모름.

**해야 할 것:**
content.js에 `extractStructuredDOM()` 함수 만들기.
클릭 가능하고 의미 있는 요소만 추출해서 번호 매기기.

**목표 출력 형식:**
```
[1] <button> 검색 (x:450, y:120)
[2] <a> 로그인 (x:890, y:30)
[3] <input placeholder="검색어를 입력하세요"> (x:400, y:120)
[4] <a> 메일 (x:100, y:200)
[5] <button> 장바구니 (x:800, y:30)
```

**구현 방법:**
```js
function extractStructuredDOM() {
    const selectors = 'a, button, input, textarea, [role="button"], [role="link"], select';
    const elements = document.querySelectorAll(selectors);
    let result = [];
    let index = 1;

    elements.forEach(el => {
        const rect = el.getBoundingClientRect();
        // 화면에 보이는 요소만
        if (rect.width === 0 || rect.height === 0) return;
        if (rect.top > window.innerHeight || rect.bottom < 0) return;

        const tag = el.tagName.toLowerCase();
        const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim();
        if (!text) return;

        result.push(`[${index}] <${tag}> ${text.slice(0, 50)} (x:${Math.round(rect.left + rect.width/2)}, y:${Math.round(rect.top + rect.height/2)})`);
        index++;
    });

    return result.join('\n').slice(0, 4000);
}
```

**완료 조건:**
- [ ] 네이버, 유튜브, 무신사에서 각각 추출 테스트
- [ ] 기존 innerText 방식과 비교해서 AI 응답 품질 차이 확인
- [ ] content.js에 통합하여 서버로 전달

**참고 파일:** `VisionVoice/colab-mvp/chrome-extension/content.js` 51번째 줄

---

#### Task A-2: 파일시스템 Tool Server (Phase 3)

**목표:**
사용자가 "바탕화면에 있는 과제.pdf 읽어줘" 같은 명령을 했을 때, 로컬 파일에 접근하는 서버.

**구현:**
Python FastAPI로 간단한 REST API 만들기.

```python
# tools/filesystem_tool.py
from fastapi import FastAPI
from pathlib import Path
import fitz  # PyMuPDF

app = FastAPI()

ALLOWED_BASE = Path.home()  # 사용자 홈 디렉토리 기준

@app.post("/tool/read-file")
async def read_file(path: str):
    """파일 내용 읽기 (txt, pdf 지원)"""
    file_path = ALLOWED_BASE / path
    if not file_path.exists():
        return {"error": f"파일을 찾을 수 없습니다: {path}"}

    if file_path.suffix == '.pdf':
        doc = fitz.open(str(file_path))
        text = "\n".join([page.get_text() for page in doc])
        return {"content": text[:5000], "type": "pdf"}
    else:
        text = file_path.read_text(encoding='utf-8', errors='ignore')
        return {"content": text[:5000], "type": "text"}

@app.post("/tool/list-files")
async def list_files(directory: str = ""):
    """디렉토리 파일 목록"""
    target = ALLOWED_BASE / directory
    if not target.is_dir():
        return {"error": "디렉토리가 아닙니다"}

    files = []
    for f in sorted(target.iterdir()):
        files.append({
            "name": f.name,
            "type": "dir" if f.is_dir() else "file",
            "size": f.stat().st_size if f.is_file() else None
        })
    return {"files": files[:50]}
```

**완료 조건:**
- [ ] read-file, list-files 엔드포인트 동작 확인
- [ ] PDF, TXT 파일 읽기 테스트
- [ ] 에러 처리 (파일 없음, 권한 없음 등)

---

### 팀원 B — 프롬프트 엔지니어링 + Intent 분류

#### Task B-1: 프롬프트 버전 관리 + A/B 테스트 (Phase 1)

**현재 문제:**
`colab-ai.py`의 프롬프트가 한 덩어리로 되어 있고, 체계적인 실험 없이 감으로 작성됨.

**해야 할 것:**

1. **실패 케이스 수집**
   - 현재 시스템으로 테스트해서 실패하는 케이스 모으기
   - 스프레드시트에 기록:

   | # | 사이트 | 명령어 | 기대 액션 | 실제 결과 | 실패 원인 |
   |---|---|---|---|---|---|
   | 1 | 네이버 | "메일 클릭해줘" | click 메일 | click 카페 | bbox 부정확 |
   | 2 | 유튜브 | "검색창에 입력해줘" | input | click 검색아이콘 | intent 분류 실패 |

2. **프롬프트 버전별 실험**
   - Google Colab 무료 GPU (T4)로 Qwen2-VL-7B 4-bit 로드 가능
   - 같은 테스트 케이스에 프롬프트만 바꿔가며 성공률 비교
   - 프롬프트 변경 포인트:
     - few-shot 예시 추가 (성공적인 입출력 사례 2~3개 프롬프트에 포함)
     - 액션 타입별 분리 프롬프트 (클릭용 / 입력용 / 설명용)
     - 한국어 vs 영어 프롬프트 비교

3. **결과 정리 형식:**
   | 프롬프트 버전 | 테스트 수 | 성공 | 실패 | 성공률 |
   |---|---|---|---|---|
   | v1 (현재) | 20 | 8 | 12 | 40% |
   | v2 (few-shot 추가) | 20 | 13 | 7 | 65% |
   | v3 (액션 분리) | 20 | 15 | 5 | 75% |

**완료 조건:**
- [ ] 실패 케이스 최소 20개 수집
- [ ] 프롬프트 3개 버전 이상 실험
- [ ] 비교 결과 스프레드시트 정리

---

#### Task B-2: Intent 라우터 프롬프트 (Phase 3)

**목표:**
Tool 확장 시 사용자 명령을 어디로 보낼지 분류하는 프롬프트 작성.

**분류 카테고리:**
```
web_action  → 기존 VisionVoice 파이프라인 (클릭, 스크롤, 입력)
web_explain → 화면 설명
file_read   → 로컬 파일 읽기
email       → 이메일 발송
general     → 일반 질문/대화
```

**프롬프트 예시:**
```
사용자의 명령을 분류하세요. 반드시 아래 카테고리 중 하나만 출력하세요.

카테고리: web_action, web_explain, file_read, email, general

예시:
- "검색창에 패딩 입력해줘" → web_action
- "이 화면 설명해줘" → web_explain
- "바탕화면에 있는 과제.pdf 읽어줘" → file_read
- "이 내용 메일로 보내줘" → email
- "오늘 날씨 알려줘" → general

명령: "{user_command}"
카테고리:
```

**완료 조건:**
- [ ] 분류 정확도 90% 이상 달성 (30개 테스트)
- [ ] 경계 케이스 처리 (복합 명령 등)

---

### 팀원 C — Grounding 스코어링 개선 + Gmail Tool

#### Task C-1: 스코어링 알고리즘 튜닝 (Phase 1)

**현재 코드:** `colab-mvp/chrome-extension/content.js`의 `calculateScore` 함수

**현재 가중치:**
```
Input Tag:      +2000  (input 요청 시)
Text Exact:     +500
Text Include:   +300 또는 +50
Tag Bonus:      +100   (a, button, input, textarea)
Box Inside:     +200
Length Penalty:  -1000  (innerText > 50자)
```

**개선 포인트:**
1. `aria-label` 매칭 가중치 추가 (많은 웹사이트가 aria-label로 버튼 설명함)
2. `data-testid`, `title` 속성 매칭 추가
3. 요소 크기(너무 작은 요소 페널티) 추가
4. 화면 중심 거리에 따른 가중치 (AI bbox 중심에 가까울수록 높은 점수)

**실험 방법:**
- 팀원 B가 수집한 실패 케이스를 가지고 테스트
- Chrome DevTools Console에서 직접 `calculateScore` 호출해서 디버깅 가능
- 가중치 변경 → 같은 케이스 재테스트 → 성공 여부 확인

**구현 예시 (추가할 부분):**
```js
function calculateScore(el, targetText, actionType, isInsideBox = false) {
    let score = 0;

    // ... 기존 로직 ...

    // [추가 1] aria-label 매칭
    const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
    if (target && ariaLabel.includes(target)) score += 400;

    // [추가 2] title 속성 매칭
    const title = (el.getAttribute('title') || '').toLowerCase();
    if (target && title.includes(target)) score += 300;

    // [추가 3] 요소 크기 페널티 (너무 작으면 의도한 타겟이 아닐 가능성)
    const rect = el.getBoundingClientRect();
    if (rect.width < 10 || rect.height < 10) score -= 500;

    // [추가 4] 화면에 안 보이는 요소 페널티
    if (rect.top > window.innerHeight || rect.bottom < 0) score -= 2000;

    return score;
}
```

**완료 조건:**
- [ ] 기존 실패 케이스 중 5개 이상 추가로 성공시키기
- [ ] 새로운 가중치 표 문서화
- [ ] 기존 성공 케이스가 깨지지 않는지 회귀 테스트

---

#### Task C-2: Gmail Tool Server (Phase 3)

**목표:**
사용자가 "이 내용을 메일로 보내줘" 했을 때 Gmail API로 메일 발송.

**구현:**
```python
# tools/gmail_tool.py
from fastapi import FastAPI
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText

app = FastAPI()

@app.post("/tool/send-email")
async def send_email(to: str, subject: str, body: str):
    """이메일 발송"""
    # Gmail API 인증은 OAuth2 token 필요
    creds = Credentials.from_authorized_user_file('token.json')
    service = build('gmail', 'v1', credentials=creds)

    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service.users().messages().send(
        userId='me', body={'raw': raw}
    ).execute()

    return {"status": "sent", "to": to}
```

**완료 조건:**
- [ ] Gmail API OAuth2 설정 완료
- [ ] 테스트 메일 발송 성공
- [ ] 에러 처리 (인증 실패, 주소 오류 등)

---

### 팀원 D — 평가 데이터셋 구축 + 문서 정리

#### Task D-1: 평가 데이터셋 v1 (Phase 2)

**이게 왜 중요한가:**
현재 "정확도가 낮다"는 말을 감으로만 하고 있음. 숫자로 증명해야 보고서에 설득력이 생김.

**데이터셋 구조:**
```
evaluation/
├── scenarios.json          # 전체 시나리오 목록
├── screenshots/            # 각 시나리오별 스크린샷
│   ├── naver_01.png
│   ├── youtube_01.png
│   └── ...
└── results/                # 테스트 결과
    ├── v1_baseline.json
    └── v2_improved.json
```

**scenarios.json 형식:**
```json
[
  {
    "id": "naver_01",
    "site": "naver.com",
    "page": "메인 페이지",
    "screenshot": "screenshots/naver_01.png",
    "command": "메일 클릭해줘",
    "expected_action": {
      "type": "click",
      "target_text": "메일",
      "target_tag": "a"
    },
    "difficulty": "easy"
  },
  {
    "id": "youtube_01",
    "site": "youtube.com",
    "page": "메인 페이지",
    "screenshot": "screenshots/youtube_01.png",
    "command": "검색창에 리그오브레전드 입력해줘",
    "expected_action": {
      "type": "input",
      "target_text": "검색",
      "value": "리그오브레전드"
    },
    "difficulty": "medium"
  }
]
```

**수집할 사이트 + 시나리오:**

| 사이트 | 시나리오 수 | 예시 명령어 |
|---|---|---|
| 네이버 | 10개 | 메일 클릭, 검색, 뉴스 보기, 스크롤 등 |
| 유튜브 | 10개 | 검색, 동영상 클릭, 구독, 스크롤 등 |
| 무신사 | 5개 | 검색, 카테고리 클릭, 상품 클릭 등 |
| 쿠팡 | 5개 | 검색, 장바구니, 카테고리 등 |
| 구글 | 5개 | 검색, Gmail, Docs 등 |
| 기타 | 5개 | 정부24, 은행 사이트 등 |

**총 40개 이상 목표**

**난이도 분류:**
- `easy`: 큰 버튼/링크 클릭 (메일, 검색)
- `medium`: 입력 + 액션 조합 (검색어 입력 후 결과 클릭)
- `hard`: 복잡한 레이아웃에서 특정 요소 찾기

**완료 조건:**
- [ ] scenarios.json에 40개 이상 시나리오 정의
- [ ] 각 시나리오별 스크린샷 캡처 완료
- [ ] 현재 시스템으로 전체 테스트 1회 완료 → baseline 성공률 기록

---

#### Task D-2: 보고서/발표 자료 관리 (전체 기간)

- 각 Phase 종료 시 결과 정리
- 최종 발표 자료 제작 지원
- 팀 회의록 / 진행 상황 문서화

---

### 혜원 — 아키텍처 + 멀티턴 + Fine-tuning + Tool Router

#### Task H-1: 멀티턴 에이전트 (Phase 1~2)

현재 단일 턴(명령→액션→끝)을 멀티턴으로 확장:
```
명령 → 액션1 → 스크린샷 재촬영 → 확인 → 액션2 → ... → 완료
```

#### Task H-2: Tool Router 아키텍처 (Phase 3)

MCP 컨셉 기반으로 intent별 Tool 분기:
```
음성 → STT → Intent 분류 (팀원 B 프롬프트)
              ├── web_action  → 기존 파이프라인
              ├── file_read   → 팀원 A의 파일시스템 Tool
              ├── email       → 팀원 C의 Gmail Tool
              └── web_explain → 기존 파이프라인 (설명 모드)
```

#### Task H-3: Fine-tuning 환경 구축 + 실험 (Phase 4)

- DGX Spark에서 QLoRA 환경 세팅
- 팀원 D 데이터셋 기반 학습
- 학습 전/후 정확도 비교

---

## 주차별 마일스톤

| 주차 | 날짜 (예상) | 마일스톤 | 담당 |
|---|---|---|---|
| 1주차 | 4/21 ~ | DOM 전처리 v1 완성, 실패 케이스 20개 수집 | A, B |
| 2주차 | 4/28 ~ | 스코어링 v2 완성, 프롬프트 A/B 테스트 1차 | C, B |
| 3주차 | 5/5 ~ | 멀티턴 에이전트 프로토타입 | 혜원 |
| 4주차 | 5/12 ~ | 평가 데이터셋 v1 (40개) 완성 | D |
| 5주차 | 5/19 ~ | 정확도 1차 정량 평가 | 전원 |
| 6주차 | 5/26 ~ | 프롬프트 v3 + 스코어링 v3 | B, C |
| 7주차 | 6/2 ~ | 파일시스템 Tool 완성 | A |
| 8주차 | 6/9 ~ | Gmail Tool 완성 | C |
| 9주차 | 6/16 ~ | Tool Router 통합 | 혜원 |
| 10주차 | 6/23 ~ | intent 분류 통합 테스트 | B, 혜원 |
| — | 7~8월 | Fine-tuning 데이터 정제 + 실험 | 혜원, D |
| — | 9~10월 | Fine-tuning 결과 반영 + 정확도 2차 평가 | 전원 |
| — | 11~12월 | 최종 통합 + 발표 준비 | 전원 |

---

## 커뮤니케이션 규칙

- 매주 월요일: 주간 진행 상황 공유 (노션 or 카톡)
- 코드 변경: GitHub PR로 올리기 (직접 push 금지)
- 질문: GitHub Issue or 단톡방
- 각자 맡은 Task의 완료 조건 체크리스트 직접 업데이트할 것
