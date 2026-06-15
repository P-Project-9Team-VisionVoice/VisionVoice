# VisionVoice 프론트엔드 발표 준비 가이드

---

## 파일 구조

```
frontend/
├── manifest.json   ← Chrome Extension 설정 파일 (전체 메타데이터)
├── background.js   ← 백그라운드에서 단축키/스크린샷 처리
├── content.js      ← 각 웹페이지에 주입되는 핵심 로직
├── popup.html      ← Extension 아이콘 클릭 시 나오는 팝업 UI
└── popup.js        ← 팝업 버튼(확대/고대비 등) 이벤트 처리
```

---

## 1. manifest.json — Extension 설정 파일

Chrome Extension이 설치될 때 브라우저가 이 파일을 읽어서 동작 방식을 등록함.

주요 항목:

```json
"permissions": ["activeTab", "scripting", "desktopCapture", "storage"]
```
- `activeTab`: 현재 탭 접근 권한
- `desktopCapture`: 스크린샷 권한
- `storage`: 설정값 저장 (예: 처음 실행 여부)

```json
"content_scripts": [{ "matches": ["<all_urls>"], "js": ["content.js"] }]
```
→ 모든 URL에서 content.js를 자동 주입. Extension 설치하면 어떤 웹사이트를 열어도 content.js가 그 페이지 안에서 실행됨.

```json
"commands": {
  "toggle-recording": { "suggested_key": { "default": "Ctrl+Shift+S" } }
}
```
→ 단축키를 Chrome에 등록. Chrome이 직접 이 키 조합을 감시함.

---

## 2. 단축키 → 녹음 시작/종료 흐름

```
사용자가 Ctrl+Shift+S 누름
        ↓
Chrome 내장 커맨드 시스템이 감지
(manifest.json에 "toggle-recording"으로 등록되어 있으니까)
        ↓
background.js의 chrome.commands.onCommand("toggle-recording") 이벤트 발생
        ↓
background.js → content.js로 { action: "toggle" } 메시지 전송
        ↓
content.js의 chrome.runtime.onMessage 리스너가 수신
        ↓
mediaRecorder.state === "recording" 이면 → stopRecording()
아니면                                    → startRecording()
```

**background.js는 왜 필요해?**

content.js(페이지 안)는 보안상 스크린샷을 직접 찍을 수 없음.
background.js (Service Worker)가 단축키 감지 + 스크린샷 담당.
이벤트가 왔을 때만 깨어나서 처리하고 다시 대기 → 소켓처럼 항상 듣고 있는 구조.

---

## 3. 녹음 — 스크린샷 — 전송

### 녹음 (content.js)

```
startRecording() 실행
        ↓
navigator.mediaDevices.getUserMedia({ audio: true })
→ 마이크 권한 요청, 스트림 획득
        ↓
MediaRecorder로 녹음 시작
→ 오디오 청크가 audioChunks 배열에 쌓임
→ 포맷: audio/webm (크롬 MediaRecorder 기본 포맷, 별도 변환 불필요)
        ↓
다시 Ctrl+Shift+S 누르면 → stopRecording()
→ mediaRecorder.onstop 콜백 실행
```

### 스크린샷

```
content.js가 background.js에 { action: "capture" } 요청
        ↓
background.js: chrome.tabs.captureVisibleTab()
→ 현재 viewport에 렌더링된 화면을 PNG로 캡처
→ base64 dataURL로 반환
        ↓
content.js가 받아서 Blob으로 변환
```

**captureVisibleTab 특성:**
- 현재 보이는 화면을 그대로 찍음
- 150% 확대 중이면 확대된 화면이 찍힘
- 개발자도구로 width 줄이면 줄어든 화면이 찍힘
- Chrome Extension API라서 content.js에서 직접 못 쓰고 background.js에서만 사용 가능

### 백엔드 전송 (content.js → 서버)

```
fetch(SERVER_URL + "/process", {
  method: "POST",
  body: FormData {
    audio:        오디오 blob (webm)
    screenshot:   스크린샷 blob (png)
    dom:          페이지 텍스트 (최대 3000자)
    dom_elements: 인터랙티브 요소 목록 (최대 60개, JSON)
  }
})
```

**통신 방식:** fetch API (axios 아님)

**서버 주소:** ngrok URL (예: `https://xxxx.ngrok-free.app`)

---

## 4. ngrok이 뭐야?

DGX Spark는 학교 내부 네트워크에 있어서 외부 인터넷에서 직접 못 접근함.
ngrok이 그 사이를 연결해주는 **터널링 서비스**.

```
Chrome Extension (어디서든)
        ↓ https://xxxx.ngrok-free.app/process
ngrok 서버 (인터넷)
        ↓ 내부 터널
DGX Spark 로컬 서버 :8000
```

`ngrok http 8000` 명령 한 줄이면 외부에서 접근 가능한 URL이 생김.
(VPN과 비슷한 개념, 훨씬 간단)

---

## 5. DOM 추출 — innerText

```js
document.body.innerText
```

**어떤 형태로 나와?**

HTML 태그나 CSS/JS 코드는 전혀 안 나오고, 화면에 렌더링된 텍스트만 나옴.

네이버 메인 예시:
```
네이버
메일  카페  블로그  지식iN  쇼핑  뉴스
검색어를 입력해 주세요
스포츠  연예  경제  사회
오늘의 주요뉴스...
```

- `<style>.foo{color:red}</style>` → 안 나옴
- `<script>console.log('hi')</script>` → 안 나옴
- `display: none` 요소 → 안 나옴
- 스크롤 안 보이는 부분도 포함 (현재 화면만이 아님)

**왜 3000자로 자르나?** 백엔드 LLM 프롬프트 토큰 제한 때문. 3000자 넘으면 잘라냄.

**dom_elements는 왜 60개?** 버튼/링크/입력창 등 인터랙티브 요소만 수집하는데 60개 넘으면 LLM이 처리하기 너무 많고 payload도 커짐.

---

## 6. 클릭 동작 — Hybrid Grounding

VLM이 "장바구니 클릭"이라고 판단하면 content.js가 3가지 방법으로 요소를 찾음:

```
① 이름 매칭 (findByText)
   "장바구니"라는 텍스트를 가진 요소를 DOM에서 직접 탐색
   → 가장 짧고 구체적인 요소 선택
   → VLM 좌표/셀렉터 환각에 가장 강함

② CSS 셀렉터
   백엔드가 dom_elements 기반으로 만들어서 보낸 선택자
   (예: #cart-btn, [aria-label="장바구니"])

③ 픽셀 좌표
   VLM bbox 중심점 → elementFromPoint()
   → 실제 클릭 가능한 요소 위일 때만 사용

우선순위: ①이름 > ②셀렉터 > ③좌표
```

클릭할 때 화면에 색깔 박스로 어떤 방법으로 찾았는지 시각적으로 보여줌 (디버그 오버레이).

---

## 7. 액션 종류

백엔드 VLM이 음성 명령을 분석해서 아래 중 하나를 결정해서 보내줌:

| action | 설명 |
|--------|------|
| `click` | 버튼/링크 클릭 (Hybrid Grounding 3단계) |
| `input` | 텍스트 입력. `submit: true`면 Enter까지 자동 발사 |
| `scroll` | 스크롤. `direction: up/down`, `amount: px` |
| `navigate` | 페이지 내 링크 이동. 텍스트로 `<a>` 탐색 후 클릭 |
| `accessibility` | 고대비/다크모드/확대. `mode` 필드로 세부 구분 |
| `close` | 닫기 버튼 클릭. `/닫기|close|×/` 패턴 탐색 |
| `explain` | 화면 설명만. 클릭 없이 TTS 안내만 출력 |

**검색(search)은?** 별도 action 없이 `input + submit: true` 조합으로 처리.
백엔드가 검색으로 판단하면:
```json
{ "action": "input", "text": "축구", "submit": true }
```
→ 입력창에 텍스트 넣고 3초 뒤 Enter 키 이벤트 발생

---

## 8. TTS 출력

### 백엔드에서 MP3 받아서 재생

**base64가 뭐야?**

MP3는 이진(binary) 파일 → JSON은 텍스트 포맷이라 binary를 직접 못 담음.
그래서 binary를 A-Z, a-z, 0-9 문자 64개로 표현하는 인코딩 방식 = base64.

```
[MP3 binary bytes] → base64 인코딩 → "SUQzBAAAAAAAI..." (JSON에 담을 수 있는 문자열)
```

**왜 파일 저장 없이 재생 가능해?**

```js
const blob = new Blob([binary], { type: "audio/mpeg" }); // 메모리상의 파일 객체
const url = URL.createObjectURL(blob);  // blob://abc123... 임시 URL 발급
new Audio(url).play();                  // 그 URL로 바로 재생
// 재생 끝나면 URL.revokeObjectURL(url)로 메모리 해제
```

`URL.createObjectURL`이 디스크 저장 없이 메모리 데이터에 임시 URL을 붙여줌.

### 백엔드 연결 실패 시 폴백

서버가 꺼져있거나 네트워크 오류 → fetch 실패 → catch 블록에서
브라우저 내장 `SpeechSynthesis` API로 TTS (음질은 떨어지지만 동작은 함)

---

## 9. 응답속도 30.7초 → 9.3초 이유

| | 1학기 (Colab) | 2학기 (DGX Spark) |
|--|--|--|
| 서버 위치 | Google 클라우드 | 학교 내부 (로컬) |
| 경로 | Extension → 인터넷 → Colab → 인터넷 → Extension | Extension → ngrok → DGX → ngrok → Extension |
| GPU 대기 | Colab 유휴 시 GPU 재연결 대기 있음 | 항상 켜져 있음, 대기 없음 |
| 모델 | Qwen2-VL-7B | Qwen3-VL-8B (추론 최적화) |

물리적 거리 + 항상 켜진 GPU = 3.3배 빠름

---

## 10. 접근성 기능 (팝업 패널)

Extension 아이콘 클릭하거나 `Ctrl+Shift+Y`로 패널 열면:
- 화면 확대: 100% / 150% / 200% (CSS `zoom` 적용)
- 고대비 모드: `filter: contrast(250%) brightness(110%)`
- 흑백 모드 (색맹 지원): `filter: grayscale(100%)`
- 다크 모드: `filter: invert(100%) hue-rotate(180deg)`
- 포커스 하이라이트: 마우스 올리면 노란 테두리

**음성으로도 제어 가능:** "고대비 켜줘", "200% 확대해줘" → 백엔드 안 거치고 content.js에서 바로 처리

---

## 11. Q&A 예상 질문

**"동영상은 못 봐요?"**
> 현재 정지 스크린샷만 분석함. 동영상 플레이어가 화면에 있으면 "현재 프레임"이 찍혀서 어떤 영상인지 대략 파악은 되지만, 영상 흐름 자체 추적은 안 됨.

**"화면 소리는 못 들어요?"**
> 마이크 입력만 수집함. 유튜브 영상 음성 같은 시스템 오디오는 별도 API가 필요해서 현재 미구현.

**"앱 설치 안 해도 돼요?"**
> Chrome Extension이라 설치 후 모든 웹사이트에서 바로 동작함. 웹사이트 코드 변경 없이 접근성 기능 추가되는 게 핵심.

**"음성으로 화면 확대도 돼요?"**
> 됨. "200% 확대해줘"라고 말하면 백엔드 거치지 않고 Extension이 바로 CSS 적용함.

**"같은 이름 버튼이 화면에 여러 개면?"**
> 텍스트 매칭에서 가장 짧고 구체적인 요소를 우선 선택함. VLM이 준 좌표도 보조로 활용해서 맞는 위치 근처 요소를 우선함. 완벽하지 않고 현재 한계로 인식 중.

**"왜 Chrome만 지원해요? Firefox는요?"**
> Chrome Extension API(`chrome.tabs.captureVisibleTab`, `chrome.commands`)를 사용해서 Chrome/Edge 전용임. Firefox는 다른 Extension API 체계라 별도 포팅 필요.
