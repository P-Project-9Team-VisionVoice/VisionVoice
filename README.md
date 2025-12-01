# 👁️ VisionVoice: 시각장애인을 위한 능동형 AI 웹 에이전트

**VisionVoice**는 시각장애인이 웹을 더 능동적으로 탐색할 수 있도록 돕는 AI 서비스입니다.
사용자의 음성 명령을 듣고, AI가 화면을 분석하여 원하는 버튼을 대신 클릭하거나 화면을 요약해 줍니다.

---

## 🛠️ 기술 스택 (Tech Stack)

| 구분          | 기술                     | 설명                                     |
| :------------ | :----------------------- | :--------------------------------------- |
| **Frontend**  | Chrome Extension (JS)    | 화면 캡처, 마이크 녹음, 클릭 이벤트 수행 |
| **Backend**   | Python, FastAPI          | API 서버, AI 모델 연동                   |
| **AI Model**  | OpenCUA-7B               | 화면 분석 및 행동 좌표 생성 (Brain)      |
| **STT / TTS** | Faster-Whisper, Edge-TTS | 음성 인식 및 음성 합성                   |

---

## 프로젝트 다운로드

```bash
git clone [레포지토리 주소]
cd VisionVoice
```

## 🚀 설치 및 실행 가이드 (Getting Started)

이 프로젝트를 실행하려면 **Python 3.10 이상**이 필요합니다.

## 1. 설치 (Setup)

1. Python 3.10 이상 설치
2. 가상환경 만들기
   ```bash
   python -m venv venv
   ```
3. 가상환경 켜기

- 윈도우(Windows): .`\venv\Scripts\activate` 입력
- 맥(Mac): `source venv/bin/activate` 입력
  (성공하면 터미널 맨 앞에 (venv)라고 초록색 글씨가 뜸)

4. 라이브러리 설치
   가상환경 켜진 상태((venv)가 보이는 상태)에서 입력:
   ```bash
   pip install -r requirements.txt
   ```

[ VS Code에서 `Python: Select Interpreter`가 `('venv': venv)`로 잘 선택되어 있는지 확인하세요. ]

## 2. 서버 실행 (Backend)

1. `backend/ai/config.py`에서 `USE_MOCK` 옵션 확인 (개발할 땐 `True`, 실제 모델 돌릴 땐 `False`)
2. 터미널에서 실행:
   ```bash
   cd backend
   uvicorn main:app --reload
   ```
   - 브라우저에서 `http://localhost:8000에` 접속했을 때 `{"status": "VisionVoice Server is Running!"}`이 뜨면 성공!

## 3. 확장 프로그램 실행 (Frontend)

1. 크롬 브라우저 주소창에 `chrome://extensions` 입력
2. 우측 상단 **[개발자 모드]** 스위치 켜기
3. 좌측 상단 **[압축해제된 확장 프로그램을 로드합니다]** 클릭
4. 다운로드 받은 프로젝트 폴더 안의 `frontend` 폴더 선택
5. 확장 프로그램 목록에 `VisionVoice MVP`가 생겼는지 확인

## 🕹️ 사용 방법 (How to use)

1. 서버가 켜져 있어야 합니다. (터미널 끄지 마세요!)
2. 테스트하고 싶은 웹페이지(예: 네이버 쇼핑)로 이동합니다.
3. 키보드 단축키 `Ctrl + Shift + S` (맥은 `Command + Shift + S`)를 누릅니다.
4. **"띠링~"** 소리가 나면 마이크에 대고 명령합니다. (예: "장바구니 담아줘")
5. 명령이 끝나면 다시 단축키(`Ctrl + Shift + S`)를 누릅니다.
6. **"띠리링~"** 소리와 함께 잠시 후 AI가 동작을 수행합니다.
