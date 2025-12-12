// frontend/content.js

let mediaRecorder;
let audioChunks = [];

// 1. 모든 프레임 텍스트 재귀 추출
function getAllVisibleText(win = window) {
  let text = "";
  try {
    if (win.document && win.document.body) {
      text += win.document.body.innerText + "\n";
    }
    for (let i = 0; i < win.frames.length; i++) {
      try {
        text += getAllVisibleText(win.frames[i]);
      } catch (e) {
        // Cross-Origin iframe은 무시
      }
    }
  } catch (e) {
    console.warn("텍스트 추출 중 에러:", e);
  }
  return text;
}

// 2. Deep Element From Point (iframe 내부까지)
function getDeepElementFromPoint(x, y) {
  let el = document.elementFromPoint(x, y);
  while (el && el.tagName === "IFRAME") {
    try {
      const rect = el.getBoundingClientRect();
      const innerX = x - rect.left;
      const innerY = y - rect.top;
      const innerEl = el.contentDocument.elementFromPoint(innerX, innerY);
      if (innerEl) {
        el = innerEl;
        x = innerX;
        y = innerY;
      } else {
        break;
      }
    } catch (e) {
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

    chrome.runtime.sendMessage({ action: "capture" }, (dataUrl) => {
      if (dataUrl) {
        processRequest(audioBlob, dataUrl);
      }
    });
  };

  mediaRecorder.start();
}

function stopRecording() {
  if (mediaRecorder) mediaRecorder.stop();
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

    // 1. 오디오 재생
    if (data.audio_base64) {
      try {
        const audio = new Audio("data:audio/mp3;base64," + data.audio_base64);
        audio.play().catch((e) => console.warn("자동 재생 차단됨:", e));
      } catch (e) {
        console.error("오디오 재생 오류:", e);
      }
    } else if (data.audio_url) {
      new Audio(data.audio_url)
        .play()
        .catch((e) => console.warn("Mixed Content:", e));
    }

    // 2. 액션 수행
    if (data.action) {
      const act = data.action.action;

      if (act === "click") {
        const hasCoord =
          data.action.x_raw != null && data.action.y_raw != null;

        if (hasCoord) {
          const ratio = window.devicePixelRatio || 1;
          const x = data.action.x_raw / ratio;
          const y = data.action.y_raw / ratio;

          console.log(`🖱️ 좌표 클릭 시도: ${x}, ${y}`);
          showClickIndicator(x, y);
          const element = getDeepElementFromPoint(x, y);
          if (element) {
            element.focus();
            ["mousedown", "mouseup", "click"].forEach((evt) => {
              element.dispatchEvent(
                new MouseEvent(evt, {
                  view: window,
                  bubbles: true,
                  cancelable: true,
                  clientX: x,
                  clientY: y,
                }),
              );
            });
          } else {
            console.warn("❌ 요소를 찾을 수 없습니다.");
          }
        } else {
          // 좌표 없는 click: target_name으로 DOM에서 추정
          const label = data.action.target || "";
          console.log(`🖱️ 텍스트 기반 클릭 시도: ${label}`);
          const candidates = Array.from(
            document.querySelectorAll("button, a, div, span"),
          );
          const el = candidates.find((e) =>
            e.innerText && e.innerText.includes(label),
          );
          if (el) {
            showClickIndicator(
              el.getBoundingClientRect().left + el.offsetWidth / 2,
              el.getBoundingClientRect().top + el.offsetHeight / 2,
            );
            el.click();
          } else {
            console.warn("❌ 텍스트로 요소를 찾을 수 없습니다.");
          }
        }
      } else if (act === "scroll") {
        const dir = data.action.direction || "down";
        const amount = data.action.amount || 300;
        const dy = dir === "up" ? -amount : amount;
        console.log(`🧷 스크롤: ${dir} ${amount}px`);
        window.scrollBy({ top: dy, behavior: "smooth" });
      } else if (act === "input") {
        const text = data.action.text || "";
        console.log(`⌨️ 입력 시도: "${text}"`);
        let el = document.activeElement;
        if (!el || el === document.body) {
          el = document.querySelector("input[type='text'], input:not([type]), textarea");
        }
        if (el) {
          el.focus();
          el.value = text;
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
        } else {
          console.warn("❌ 입력창을 찾을 수 없습니다.");
        }
      } else if (act === "navigate") {
        console.log(`🌐 페이지 이동 시도: ${data.action.target}`);
        const links = Array.from(document.querySelectorAll("a, button"));
        const target = links.find((l) =>
          l.innerText && l.innerText.includes(data.action.target),
        );
        if (target) target.click();
        else console.warn("❌ 이동 대상 링크를 찾을 수 없습니다.");
      } else if (act === "close") {
        console.log(`❌ 팝업 닫기 시도: ${data.action.target}`);
        const candidates = Array.from(
          document.querySelectorAll("button, span, div"),
        );
        const label = data.action.target || "";
        const target = candidates.find(
          (el) =>
            /닫기|close|×/i.test(el.innerText || "") ||
            (label && el.innerText && el.innerText.includes(label)),
        );
        if (target) target.click();
        else console.warn("❌ 닫기 버튼을 찾을 수 없습니다.");
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
    position: "fixed",
    left: x + "px",
    top: y + "px",
    width: "20px",
    height: "20px",
    backgroundColor: "rgba(255, 0, 0, 0.7)",
    borderRadius: "50%",
    zIndex: "999999",
    pointerEvents: "none",
    boxShadow: "0 0 10px white",
    transition: "transform 0.2s",
  });
  document.body.appendChild(dot);
  setTimeout(() => (dot.style.transform = "scale(0.5)"), 50);
  setTimeout(() => dot.remove(), 2000);
}
