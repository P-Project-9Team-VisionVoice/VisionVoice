// frontend/content.js

let mediaRecorder;
let audioChunks = [];

// 1. [일반화] 모든 프레임 텍스트 재귀 추출 함수
function getAllVisibleText(win = window) {
  let text = "";

  try {
    // 현재 창의 텍스트 추출
    if (win.document && win.document.body) {
      text += win.document.body.innerText + "\n";
    }

    // 내부의 모든 iframe/frame 순회
    for (let i = 0; i < win.frames.length; i++) {
      try {
        // 재귀 호출 (iframe 안의 iframe도 처리)
        text += getAllVisibleText(win.frames[i]);
      } catch (e) {
        // Cross-Origin(보안) 문제로 접근 못하는 iframe은 조용히 무시
        // console.warn("접근 불가 iframe 패스");
      }
    }
  } catch (e) {
    console.warn("텍스트 추출 중 에러:", e);
  }

  return text;
}

// 2. [일반화] Deep Element From Point (iframe 내부 클릭용)
function getDeepElementFromPoint(x, y) {
  let el = document.elementFromPoint(x, y);

  // 찾은 요소가 IFRAME이라면 내부로 진입 시도
  while (el && el.tagName === 'IFRAME') {
    try {
      const rect = el.getBoundingClientRect();
      const innerX = x - rect.left; // iframe 기준 상대 좌표 계산
      const innerY = y - rect.top;

      // iframe 내부에서 다시 요소 찾기
      const innerEl = el.contentDocument.elementFromPoint(innerX, innerY);

      if (innerEl) {
        el = innerEl; // 타겟 업데이트
        x = innerX;   // 좌표 업데이트 (중첩 iframe 대비)
        y = innerY;
      } else {
        break; // 내부에 요소 없으면 iframe 자체를 클릭
      }
    } catch (e) {
      // Cross-Origin iframe이라 내부 접근 불가하면 여기서 멈춤
      break;
    }
  }
  return el;
}

// 3. 메인 로직
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "toggle") {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      stopRecording();
    } else {
      startRecording();
    }
  }
});

async function startRecording() {
  playBeep("start");
  console.log("🎙️ 녹음 시작...");

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream);
  audioChunks = [];

  mediaRecorder.ondataavailable = (event) => {
    audioChunks.push(event.data);
  };

  mediaRecorder.onstop = async () => {
    console.log("🛑 녹음 종료, 처리 중...");
    playBeep("end");

    const audioBlob = new Blob(audioChunks, { type: "audio/webm" });

    // 백그라운드에 스크린샷 요청
    chrome.runtime.sendMessage({ action: "capture" }, (dataUrl) => {
      if (dataUrl) {
        processRequest(audioBlob, dataUrl);
      }
    });
  };

  mediaRecorder.start();
}

function stopRecording() {
  if (mediaRecorder) {
    mediaRecorder.stop();
  }
}

function dataURItoBlob(dataURI) {
  const byteString = atob(dataURI.split(",")[1]);
  const mimeString = dataURI.split(",")[0].split(":")[1].split(";")[0];
  const ab = new ArrayBuffer(byteString.length);
  const ia = new Uint8Array(ab);
  for (let i = 0; i < byteString.length; i++) {
    ia[i] = byteString.charCodeAt(i);
  }
  return new Blob([ab], { type: mimeString });
}

async function processRequest(audioBlob, screenshotDataUrl) {
  if (audioBlob.size === 0) console.warn("⚠️ 오디오 데이터 없음");

  const screenshotBlob = dataURItoBlob(screenshotDataUrl);

  // 일반화된 함수로 텍스트 추출 (최대 3000자 제한)
  const fullText = getAllVisibleText(window);
  console.log(`📝 통합 텍스트 길이: ${fullText.length}자`);

  const formData = new FormData();
  formData.append("audio", audioBlob, "input.webm");
  formData.append("screenshot", screenshotBlob, "input.png");
  formData.append("dom", fullText.substring(0, 3000) || "텍스트 없음");

  try {
    // const SERVER_URL = "http://localhost:8000";
    const SERVER_URL = "https://3f6bd2949154.ngrok-free.app";

    console.log("🚀 서버로 전송 중...");
    const response = await fetch(`${SERVER_URL}/process`, {
      method: "POST",
      body: formData,
    });

    const data = await response.json();
    console.log("✅ 결과 받음:", data);

    // 1. 오디오 재생 (Base64)
    if (data.audio_base64) {
      try {
        const audio = new Audio("data:audio/mp3;base64," + data.audio_base64);
        audio.play().catch(e => console.warn("자동 재생 차단됨:", e));
      } catch (e) {
        console.error("오디오 재생 오류:", e);
      }
    } else if (data.audio_url) {
      // 혹시 URL 방식일 경우 대비
      new Audio(data.audio_url).play().catch(e => console.warn("Mixed Content:", e));
    }

    // 2. 액션 수행 (클릭)
    if (data.action && data.action.action === "click") {
      const ratio = window.devicePixelRatio || 1;
      const x = data.action.x_raw / ratio;
      const y = data.action.y_raw / ratio;

      console.log(`🖱️ 클릭 시도: ${x}, ${y}`);
      showClickIndicator(x, y);

      // 일반화된 Deep Element 찾기 함수 사용
      const element = getDeepElementFromPoint(x, y);

      if (element) {
        console.log("🎯 타겟 요소 발견:", element);

        element.focus();
        element.click();

        // dispatchEvent (React/Vue 사이트 대응)
        ['mousedown', 'mouseup', 'click'].forEach(evt => {
          element.dispatchEvent(new MouseEvent(evt, {
            view: window,
            bubbles: true,
            cancelable: true,
            clientX: x,
            clientY: y
          }));
        });
      } else {
        console.warn("❌ 요소를 찾을 수 없습니다.");
      }
    }
  } catch (error) {
    console.error("❌ 처리 에러:", error);
  }
}

function playBeep(type) {
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.frequency.value = type === "start" ? 880 : 440;
  osc.start();
  setTimeout(() => osc.stop(), 100);
}

function showClickIndicator(x, y) {
  const dot = document.createElement("div");
  Object.assign(dot.style, {
    position: "fixed", left: x + "px", top: y + "px",
    width: "20px", height: "20px", backgroundColor: "rgba(255, 0, 0, 0.7)",
    borderRadius: "50%", zIndex: "999999", pointerEvents: "none",
    boxShadow: "0 0 10px white", transition: "transform 0.2s"
  });
  document.body.appendChild(dot);

  // 클릭 애니메이션
  setTimeout(() => dot.style.transform = "scale(0.5)", 50);
  setTimeout(() => dot.remove(), 2000);
}