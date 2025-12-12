# 👁️ VisionVoice  
### 시각장애인을 위한 능동형 AI 웹 에이전트 (MVP)

**VisionVoice**는 시각장애 사용자가 웹을 더 능동적으로 탐색할 수 있도록 돕는 음성 기반 AI 웹 에이전트입니다.

사용자의 음성 명령을 입력으로 받아  
- 현재 화면을 분석하고
- 버튼, 입력창, 스크롤 등 웹 인터랙션을 추론한 뒤
- 실제 브라우저에서 해당 행동을 대신 수행합니다.

본 레포지토리는 **졸업작품 MVP 구현 버전**을 포함합니다.

---

## ✨ 핵심 기능

- 🎙️ **음성 명령 인식 (STT)**  
  - 로컬 Faster-Whisper 기반 한국어 음성 인식
- 👁️ **화면 인식 + 행동 추론 (Vision-Language Model)**  
  - 스크린샷 + DOM 텍스트를 기반으로 사용자 의도 분석
  - 클릭 / 입력 / 스크롤 / 뒤로가기 액션 생성
- 🖱️ **실제 웹 조작 (Chrome Extension)**  
  - AI가 생성한 action을 실제 브라우저에서 실행
- 🔊 **음성 피드백 (TTS)**  
  - 실행 결과를 음성으로 안내

---

## 🛠️ 기술 스택 (Tech Stack)

| 구분 | 기술 | 설명 |
|---|---|---|
| **Frontend** | Chrome Extension (JS) | 화면 캡처, 마이크 녹음, 웹 인터랙션 수행 |
| **Backend (Local)** | Python, FastAPI | STT 처리, AI 서버 중계 |
| **AI Server (Colab)** | FastAPI + Qwen2-VL-7B | 화면 분석 및 행동(action) 생성 |
| **STT** | Faster-Whisper | 로컬 음성 인식 |
| **TTS** | Chrome TTS API | 실행 결과 음성 안내 |
| **Infra** | ngrok | Colab ↔ Local 통신 |

---

## 📁 프로젝트 구조

```

VisionVoice/
├── backend/                # 초기 구조 (참고용)
├── frontend/               # Chrome Extension (초기 버전)
├── colab-mvp/              # ⭐ MVP 최종 구현
│   ├── requirements.txt
│   ├── run_tunnel.py
│   ├── server/
│   │   ├── main.py         # STT + 중계 서버 (Local)
│   │   └── colab-ai.py     # Vision AI 서버 (Colab)
│   └── chrome-extension/
│       ├── background.js
│       ├── content.js
│       └── manifest.json
└── README.md

````

---

## 🚀 실행 환경 요약

- **Python** ≥ 3.10
- **Chrome Browser**
- **Google Colab (GPU 권장)**
- **HuggingFace Account (토큰 필요)**

---

## 🔧 설치 및 실행 가이드 (MVP 기준)

### 1️⃣ Repository Clone

```bash
git clone <repository-url>
cd VisionVoice/colab-mvp
````

---

### 2️⃣ Python 환경 설정 (Local)

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

### 3️⃣ HuggingFace 토큰 설정 (필수)

```bash
export HF_TOKEN=hf_xxxxxxxxxxxxxxxxx
```

> ⚠️ 토큰은 **절대 코드에 직접 작성하지 않습니다.**

---

### 4️⃣ AI 서버 실행 (Colab)

1. Google Colab에서 `colab-mvp/server/colab-ai.py` 실행
2. GPU 런타임 사용 권장
3. 실행 후 출력되는 **ngrok URL 확인**

<br/>

\* 실제 구현 과정에서는 Google Colab에서 직접 실행하여 ngrok으로 local server와 통신하였습니다.

```text
🚀 Public URL: https://xxxx.ngrok-free.app
```

<br/>

\* 이 생성된 ngrok 주소를 main.py의 `COLAB_URL`으로 지정해줘야 합니다.

---

### 5️⃣ Local 서버 실행

`colab-mvp/server/main.py` 실행

```bash
cd colab-mvp/server
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

### 6️⃣ ngrok 터널 실행 (Local)

```bash
python run_tunnel.py
```

<br/>

\* 이 생성된 ngrok 주소를 background.js의 `NEW_NGROK_URL`으로 지정해줘야 합니다.

---

### 7️⃣ Chrome Extension 로드

1. Chrome → `chrome://extensions`
2. **개발자 모드 ON**
3. **압축해제된 확장 프로그램 로드**
4. `colab-mvp/chrome-extension` 선택
5. `서비스워커`를 클릭하여 디버깅 콘솔 확인 가능

---

## 🕹️ 사용 방법

1. Local 서버 + Colab 서버가 모두 실행 중인지 확인
2. 테스트할 웹페이지 접속 (예: 네이버 쇼핑)
3. 단축키 실행

   * Windows: `Ctrl + Shift + S`
   * Mac: `Command + Shift + S`
4. **삑 소리 후 음성 명령**

   * 예:

     * “검색창에 무신사 입력해줘”
     * “아래로 내려줘”
     * “이 화면 설명해줘”
5. 다시 단축키 입력 → AI가 행동 수행

---

## 🧠 시스템 아키텍처 요약

```
[User Voice]
    ↓
[Chrome Extension]
    ↓
[Local FastAPI Server]
  ├─ STT (Faster-Whisper)
  └─ Vision AI 요청
        ↓
    [Colab AI Server]
        ↓
    Action JSON
        ↓
[Chrome Extension]
    ↓
[Web Interaction]
```

---

## ⚠️ 제한 사항 (MVP)

* 일부 웹사이트는 보안 정책(CSP)으로 자동화가 제한될 수 있음
* ngrok 기반 통신 → 상용 서비스에는 부적합
* 좌표 기반 클릭은 UI 변경에 민감

---

## 🎓 프로젝트 성격

* **졸업작품 MVP**
* 시각장애인 웹 접근성 개선을 목표로 한 졸업작품 프로젝트
* 향후 계획:

  * 좌표 안정화
  * DOM-first 액션 전략
  * 멀티 스텝 에이전트 확장

---