# 👁️ VisionVoice
### 시각장애인을 위한 능동형 AI 웹 에이전트

**VisionVoice**는 시각장애 사용자가 음성 명령만으로 웹을 자유롭게 탐색할 수 있도록 돕는 AI 웹 에이전트입니다.

사용자의 음성을 입력받아 현재 화면을 분석하고, 클릭·입력·스크롤 등 실제 웹 인터랙션을 대신 수행합니다.  
4-1학기에는 모델을 **Qwen3-VL-8B**(DGX Spark 로컬 서버)로 전환하고, **Hybrid Grounding v2**, **LoRA 파인튜닝**, **접근성 대시보드**를 추가하였습니다.

---

## ✨ 핵심 기능

| 기능 | 설명 |
|---|---|
| 🎙️ **음성 명령 인식 (STT)** | Faster-Whisper 기반 로컬 한국어 음성 인식 |
| 👁️ **화면 인식 + 행동 추론** | Qwen3-VL-8B (bf16, DGX Spark) — 스크린샷 + DOM으로 액션 생성 |
| 🎯 **Hybrid Grounding v2** | findByText → CSS Selector → OmniParser v2 픽셀좌표 3-tier 폴백 |
| ♿ **접근성 대시보드** | 고대비 / 흑백 / 다크모드 / 화면 확대 / 하이라이팅 CSS 즉시 적용 |
| 🧠 **LoRA 파인튜닝** | 한국어 웹 데이터셋 898개로 Qwen3-VL-8B LoRA 학습 (rank=16, bf16) |
| 🔊 **음성 피드백 (TTS)** | Azure TTS (ko-KR-SunHiNeural) 로 실행 결과 안내 |

---

## 🛠️ 기술 스택

| 구분 | 기술 | 설명 |
|---|---|---|
| **Frontend** | Chrome Extension (JS) | 화면 캡처, 마이크 녹음, DOM 추출, 웹 인터랙션, 접근성 패널 |
| **Backend** | Python 3.10, FastAPI | STT / VLM 에이전트 / TTS 통합 서버 (단일 서버) |
| **VLM** | Qwen3-VL-8B-Instruct (bf16) | 화면 분석 및 액션 생성 (HuggingFace) |
| **Grounding** | OmniParser v2 (YOLO) | VLM bbox를 UI 요소로 정밀화 |
| **STT** | Faster-Whisper (large-v3) | 로컬 한국어 음성 인식 |
| **TTS** | edge-tts (SunHiNeural) | 한국어 음성 합성 |
| **Fine-tuning** | LoRA (rank=16, bf16) | Qwen3-VL-8B LoRA 학습 (llama-factory) |
| **Infra** | DGX Spark (GB10, 128GB), ngrok | 로컬 GPU 서버 + 외부 터널 |

---

## 🏗️ 시스템 아키텍처

```
[사용자 음성]
     │
     ▼
[Chrome Extension]
  ├─ 마이크 녹음 (WebM)
  ├─ 스크린샷 캡처
  └─ DOM 요소 추출 (최대 60개, CSS Selector 포함)
     │
     ▼ (ngrok 터널)
[FastAPI 서버 — DGX Spark]
  ├─ STT: Faster-Whisper → 한국어 텍스트
  ├─ VLM: Qwen3-VL-8B → Action JSON
  │        { action, target, bbox, css_selector, speech }
  └─ TTS: edge-tts → MP3 (Base64)
     │
     ▼
[Chrome Extension]
  ├─ Hybrid Grounding v2
  │    1. findByText (텍스트 매칭)
  │    2. CSS Selector (DOM 직접 지정)
  │    3. OmniParser v2 IoU≥0.15 정밀화 → 픽셀좌표 클릭
  └─ 웹 인터랙션 실행 (click / input / scroll / back / accessibility)
```

<img width="2400" height="1270" alt="image" src="https://github.com/user-attachments/assets/da20d470-c124-48f9-94a8-b5c1f2387f86" />


---

## 📁 프로젝트 구조

```
VisionVoice/
├── backend/                         # FastAPI + AI 서버
│   ├── main.py                      # /process, /speak 엔드포인트
│   ├── requirements.txt
│   └── ai/
│       ├── simple_agent.py          # Qwen3-VL-8B 에이전트 (Hybrid Grounding)
│       ├── omniparser_grounding.py  # OmniParser v2 bbox 정밀화
│       ├── stt.py                   # Faster-Whisper STT
│       └── tts.py                   # edge-tts TTS
├── frontend/                        # Chrome Extension
│   ├── content.js                   # DOM 추출, 접근성 패널, 인터랙션 실행
│   ├── background.js                # 단축키 처리
│   ├── manifest.json
│   ├── popup.html
│   └── popup.js
├── finetune/                        # LoRA 파인튜닝 파이프라인
│   ├── collect_data.py              # 웹 상호작용 데이터 수집
│   ├── auto_label.py                # Qwen3-VL로 자동 라벨링
│   ├── convert_dataset.py           # Qwen3-VL 학습 포맷 변환
│   ├── train_qwen3vl.py             # LoRA 학습 스크립트
│   └── dataset/
│       ├── train.json               # 718개
│       └── val.json                 # 180개
├── eval/                            # 벤치마크 평가
│   ├── realscene_eval.py            # 실제 화면 시나리오 평가
│   ├── finetune_eval.py             # 파인튜닝 vs 베이스 모델 비교
│   └── results/                     # 평가 결과 JSON + 시각화
├── colab-mvp/                       # 3-2학기 MVP (참고용)
│   ├── server/
│   └── chrome-extension/
└── docs/                            # 발표 자료, 아키텍처 다이어그램
```

---

## 🚀 실행 환경

- **Python** ≥ 3.10
- **CUDA GPU** (VRAM 16GB 이상 권장, bf16 기준)
- **Chrome Browser**
- **ngrok** 계정 + authtoken

---

## 🔧 설치 및 실행 가이드

### 1️⃣ Repository Clone

```bash
git clone <repository-url>
cd VisionVoice
```

---

### 2️⃣ Python 환경 설정

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

### 3️⃣ 모델 다운로드

```bash
# Qwen3-VL-8B
huggingface-cli download Qwen/Qwen3-VL-8B-Instruct --local-dir ~/models/Qwen3-VL-8B-Instruct

# OmniParser v2
huggingface-cli download microsoft/OmniParser-v2.0 --local-dir ~/models/OmniParser-v2.0
```

> `backend/ai/config.py`에서 모델 경로를 환경에 맞게 수정하세요.

---

### 4️⃣ 백엔드 서버 실행 (DGX / 로컬 GPU 서버)

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

### 5️⃣ ngrok 터널 실행

```bash
ngrok http 8000
```

출력되는 ngrok 주소를 `frontend/content.js` 상단의 `SERVER_URL`에 지정합니다.

```js
const SERVER_URL = "https://xxxx.ngrok-free.app";
```

---

### 6️⃣ Chrome Extension 로드

1. Chrome → `chrome://extensions`
2. **개발자 모드 ON**
3. **압축해제된 확장 프로그램 로드**
4. `frontend/` 폴더 선택

---

## 🕹️ 사용 방법

### 음성 명령

| 단축키 | 동작 |
|---|---|
| `Ctrl+Shift+S` / `⌘+Shift+S` | 음성 명령 토글 (녹음 시작/전송) |

1. 테스트할 웹페이지 접속 (예: 네이버, 무신사, YouTube)
2. 단축키로 녹음 시작 → **삑 소리** 후 음성 명령 입력
3. 다시 단축키 → AI가 화면 분석 후 행동 수행
4. TTS로 실행 결과 안내

**명령 예시**
```
"검색창에 운동화 입력해줘"
"아래로 내려줘"
"이 화면 어떻게 구성됐는지 설명해줘"
"뒤로 가줘"
```

### 접근성 대시보드

| 단축키 | 동작 |
|---|---|
| `⌘+Shift+Y` (Mac) | 접근성 패널 토글 |

패널에서 **고대비 / 흑백 / 다크모드 / 화면 확대(110~150%) / 하이라이팅 / 초기화** 를 즉시 적용할 수 있습니다.

<p align="center"> 
<img width="200" alt="image" src="https://github.com/user-attachments/assets/4683bbc9-6e7b-4060-a73e-0b5eb7964a92" />
</p>

---

## 📊 멀티 모델 벤치마크 결과

> 실제 웹 스크린샷 10개 시나리오 (네이버, 무신사, YouTube, 스프레드시트)  
> 평가 환경: DGX Spark (GB10, 128GB), 2026-06-05

| 모델 | 정확도 | 평균 응답시간 |
|---|---|---|
| **Qwen3-VL-8B** (본 프로젝트) | **100%** | **13.98s** |
| Qwen2-VL-7B (이전 버전) | 100% | 15.16s |
| Qwen3-VL-8B-LoRA (파인튜닝) | 100% | 23.51s |
| EvoCUA-8B (비교군) | 100% | 63.33s |

Qwen3-VL-8B는 동일한 100% 정확도에서 **EvoCUA 대비 4.5배 빠른 응답속도**를 달성하였습니다.

---

## ⚠️ 제한 사항

- 일부 웹사이트는 보안 정책(CSP)으로 자동화가 제한될 수 있음
- ngrok 기반 통신 → 상용 배포에는 별도 서버 환경 필요
- 접근성 대시보드 단축키(`⌘+Shift+Y`)는 현재 Mac 전용

---

<details>
<summary>📦 3-2학기 MVP (초기 버전) — 클릭하여 펼치기</summary>

<br>

> 3-2학기에 구현된 MVP 버전입니다. Qwen2-VL-7B + Google Colab 기반이며, 현재는 `colab-mvp/` 폴더에 보존되어 있습니다.

---

## 👁️ VisionVoice — MVP

**VisionVoice**는 시각장애 사용자가 웹을 더 능동적으로 탐색할 수 있도록 돕는 음성 기반 AI 웹 에이전트입니다.

사용자의 음성 명령을 입력으로 받아 현재 화면을 분석하고, 버튼, 입력창, 스크롤 등 웹 인터랙션을 추론한 뒤 실제 브라우저에서 해당 행동을 대신 수행합니다.

### 핵심 기능

- 🎙️ **음성 명령 인식 (STT)** — 로컬 Faster-Whisper 기반 한국어 음성 인식
- 👁️ **화면 인식 + 행동 추론** — 스크린샷 + DOM 텍스트 기반 의도 분석, 클릭/입력/스크롤/뒤로가기 액션 생성
- 🖱️ **실제 웹 조작 (Chrome Extension)** — AI가 생성한 action을 실제 브라우저에서 실행
- 🔊 **음성 피드백 (TTS)** — 실행 결과를 음성으로 안내

### 기술 스택 (MVP)

| 구분 | 기술 | 설명 |
|---|---|---|
| **Frontend** | Chrome Extension (JS) | 화면 캡처, 마이크 녹음, 웹 인터랙션 수행 |
| **Backend (Local)** | Python, FastAPI | STT 처리, AI 서버 중계 |
| **AI Server (Colab)** | FastAPI + Qwen2-VL-7B | 화면 분석 및 행동(action) 생성 |
| **STT** | Faster-Whisper | 로컬 음성 인식 |
| **TTS** | Chrome TTS API | 실행 결과 음성 안내 |
| **Infra** | ngrok | Colab ↔ Local 통신 |

### 프로젝트 구조 (MVP)

```
colab-mvp/
├── requirements.txt
├── run_tunnel.py
├── server/
│   ├── main.py         # STT + 중계 서버 (Local)
│   └── colab-ai.py     # Vision AI 서버 (Colab)
└── chrome-extension/
    ├── background.js
    ├── content.js
    └── manifest.json
```

### 실행 가이드 (MVP)

**1. Clone & 의존성 설치**
```bash
git clone <repository-url>
cd VisionVoice/colab-mvp
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

**2. HuggingFace 토큰 설정**
```bash
export HF_TOKEN=hf_xxxxxxxxxxxxxxxxx
```

**3. Colab에서 AI 서버 실행**
- `colab-mvp/server/colab-ai.py`를 Google Colab (GPU 런타임)에서 실행
- 출력된 ngrok URL을 `main.py`의 `COLAB_URL`에 지정

**4. 로컬 서버 실행**
```bash
cd colab-mvp/server
uvicorn main:app --host 0.0.0.0 --port 8000
```

**5. ngrok 터널 (로컬)**
```bash
python run_tunnel.py
```
출력된 ngrok 주소를 `background.js`의 `NEW_NGROK_URL`에 지정

**6. Chrome Extension 로드**
- `chrome://extensions` → 개발자 모드 ON → `colab-mvp/chrome-extension` 선택

### 시스템 아키텍처 (MVP)

```
[User Voice] → [Chrome Extension] → [Local FastAPI]
                                         ├─ STT (Faster-Whisper)
                                         └─ → [Colab AI Server (Qwen2-VL-7B)]
                                                    ↓ Action JSON
                                     [Chrome Extension] → [Web Interaction]
```

### 제한 사항 (MVP)

- 일부 웹사이트는 보안 정책(CSP)으로 자동화가 제한될 수 있음
- ngrok 기반 통신 → 상용 서비스에는 부적합
- 좌표 기반 클릭은 UI 변경에 민감

</details>
