// frontend/content.js

let SERVER_URL = "https://9054-210-119-237-104.ngrok-free.app";
// ngrok URL이 재시작마다 바뀌므로 chrome.storage에서 동적으로 읽기
// 팝업 UI 또는 popup.js에서 chrome.storage.local.set({ vv_server_url: "..." }) 으로 변경 가능
chrome.storage.local.get(["vv_server_url"], (r) => {
  if (r.vv_server_url) SERVER_URL = r.vv_server_url;
});

let mediaRecorder;
let audioChunks = [];

// ── 접근성 모드 상태 ──
const vvA11y = { zoom: 100, filter: null };

const A11Y_FILTERS = {
  high_contrast: "contrast(250%) brightness(110%)",
  grayscale:     "grayscale(100%)",
  dark_mode:     "invert(100%) hue-rotate(180deg)",
};

const A11Y_NAMES = {
  high_contrast: "고대비 모드",
  grayscale:     "흑백 모드 (색맹)",
  dark_mode:     "다크 모드",
};

function applyA11yZoom(level) {
  vvA11y.zoom = level;
  document.documentElement.style.zoom = level === 100 ? "" : `${level}%`;
  showA11yToast(level === 100 ? "확대 해제" : `화면 ${level}% 확대`);
}

function applyA11yFilter(mode) {
  if (vvA11y.filter === mode) {
    vvA11y.filter = null;
    document.documentElement.style.filter = "";
    showA11yToast("필터 해제");
  } else {
    vvA11y.filter = mode;
    document.documentElement.style.filter = A11Y_FILTERS[mode];
    showA11yToast(A11Y_NAMES[mode] + " 켜짐");
  }
}

function resetA11y() {
  vvA11y.zoom = 100;
  vvA11y.filter = null;
  document.documentElement.style.zoom = "";
  document.documentElement.style.filter = "";
  // 포커스 하이라이트 제거
  const old = document.getElementById("vv-focus-style");
  if (old) old.remove();
  showA11yToast("접근성 설정 초기화");
}

function toggleFocusHighlight() {
  const existing = document.getElementById("vv-focus-style");
  if (existing) {
    existing.remove();
    showA11yToast("포커스 하이라이트 해제");
  } else {
    const style = document.createElement("style");
    style.id = "vv-focus-style";
    style.textContent = `
      *:focus, *:hover {
        outline: 4px solid #facc15 !important;
        outline-offset: 2px !important;
        background-color: rgba(250, 204, 21, 0.15) !important;
      }`;
    document.head.appendChild(style);
    showA11yToast("포커스 하이라이트 켜짐");
  }
}

function showA11yToast(msg) {
  let toast = document.getElementById("vv-a11y-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "vv-a11y-toast";
    Object.assign(toast.style, {
      position: "fixed", bottom: "24px", right: "24px",
      background: "#1e40af", color: "white",
      padding: "12px 18px", borderRadius: "10px",
      fontSize: "15px", fontWeight: "bold",
      zIndex: "2147483647", pointerEvents: "none",
      boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
      transition: "opacity 0.4s",
    });
    document.body.appendChild(toast);
  }
  toast.textContent = "♿ " + msg;
  toast.style.opacity = "1";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { toast.style.opacity = "0"; }, 2500);
}

// 1-0. 현재 viewport에 보이는 텍스트만 추출 (LLM 관련성 높음)
function getViewportText() {
  const vh = window.innerHeight, vw = window.innerWidth;
  const seen = new Set();
  return [...document.querySelectorAll("*")]
    .filter(el => {
      if (el.children.length > 0) return false;
      const r = el.getBoundingClientRect();
      return r.top >= -10 && r.bottom <= vh + 10 &&
             r.left >= -10 && r.right <= vw + 10 &&
             r.width > 0 && r.height > 0;
    })
    .map(el => (el.innerText || el.textContent || "").trim())
    .filter(t => { if (!t || seen.has(t)) return false; seen.add(t); return true; })
    .join("\n");
}

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
    // cross-origin iframe DOMException은 무시
  }
  return text;
}

// 2. 인터랙티브 요소 구조화 추출 (CSS 셀렉터 생성 포함)
function getInteractiveElements() {
  const els = document.querySelectorAll(
    'a[href], button, input, select, textarea, [role="button"], [role="link"], [role="searchbox"], [role="menuitem"]'
  );
  return [...els].slice(0, 60).map(el => {
    // CSS 셀렉터 생성 (신뢰도 순)
    let selector = null;
    if (el.id) {
      selector = `#${el.id}`;
    } else if (el.getAttribute("name")) {
      selector = `${el.tagName.toLowerCase()}[name="${el.getAttribute("name")}"]`;
    } else if (el.getAttribute("aria-label")) {
      selector = `[aria-label="${el.getAttribute("aria-label")}"]`;
    } else if (el.placeholder) {
      selector = `${el.tagName.toLowerCase()}[placeholder="${el.placeholder}"]`;
    } else if (el.getAttribute("data-testid")) {
      selector = `[data-testid="${el.getAttribute("data-testid")}"]`;
    }

    return {
      tag:   el.tagName.toLowerCase(),
      type:  el.type   || null,
      id:    el.id     || null,
      text:  (el.innerText || el.value || "").slice(0, 40).trim() || null,
      placeholder: el.placeholder || null,
      ariaLabel:   el.getAttribute("aria-label") || null,
      role:        el.getAttribute("role") || null,
      selector,
    };
  }).filter(e => e.text || e.placeholder || e.ariaLabel || e.selector);
}

// 3. Deep Element From Point (iframe 내부까지)
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

// 3-1. 요소가 화면에 실제로 보이는지
function isVisible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return false;
  if (r.bottom < 0 || r.top > (window.innerHeight || 0) + 2000) return false;
  const s = getComputedStyle(el);
  return s.visibility !== "hidden" && s.display !== "none" && s.pointerEvents !== "none" && s.opacity !== "0";
}

// 3-2. 타겟 이름(텍스트)으로 클릭 가능한 요소 찾기
//      Qwen2-VL의 좌표/셀렉터가 부정확해도 "농구","e스포츠" 같은 이름은 정확하므로 가장 신뢰도 높음
function findByText(name, boxPxCss = null) {
  const norm = (t) => (t || "").replace(/\s+/g, "").toLowerCase();
  const want = norm(name).replace(/(탭|버튼|메뉴|링크|아이콘|이미지)$/g, "");
  if (!want || want.length < 1) return null;

  const cand = [...document.querySelectorAll(
    "a, button, [role='button'], [role='link'], [role='menuitem'], [role='tab'], input[type='submit'], input[type='button']"
  )].filter(isVisible);

  const label = (el) => norm(
    el.innerText || el.textContent || el.value ||
    el.getAttribute("aria-label") || el.getAttribute("title") ||
    el.querySelector("img")?.getAttribute("alt") || ""
  );

  // bbox 중심점과 요소 중심 거리 계산 (px 기준)
  const distToBbox = (el) => {
    if (!boxPxCss || boxPxCss.length !== 4) return 0;
    const r = el.getBoundingClientRect();
    const elCx = r.left + r.width / 2, elCy = r.top + r.height / 2;
    const bCx = (boxPxCss[0] + boxPxCss[2]) / 2, bCy = (boxPxCss[1] + boxPxCss[3]) / 2;
    return Math.hypot(elCx - bCx, elCy - bCy);
  };

  // 1) 정확히 일치 — bbox 있으면 가장 가까운 것, 없으면 가장 짧은 것
  const exact = cand.filter((el) => label(el) === want);
  if (exact.length) {
    return exact.sort((a, b) =>
      boxPxCss ? distToBbox(a) - distToBbox(b) : label(a).length - label(b).length
    )[0];
  }
  // 2) 포함 — 가장 짧고 bbox에 가까운 것
  const partial = cand
    .filter((el) => { const l = label(el); return want.length >= 2 && l.includes(want) && l.length <= 200; })
    .sort((a, b) => boxPxCss ? distToBbox(a) - distToBbox(b) : label(a).length - label(b).length);
  return partial[0] || null;
}

// 3-3. 좌표가 가리키는 곳이 실제 클릭 가능한 요소인지 (빈 여백 클릭 방지)
function clickableAtPoint(x, y) {
  const hit = getDeepElementFromPoint(x, y);
  return hit ? hit.closest("a, button, [role='button'], [role='link'], [role='menuitem'], input, select, textarea, [onclick]") : null;
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

  if (request.action === "toggle-panel") {
    togglePanel();
  }

  // 팝업 / 음성명령 → 접근성 모드 제어
  if (request.action === "accessibility") {
    const mode = request.mode;
    if (mode === "zoom_150")      applyA11yZoom(150);
    else if (mode === "zoom_200") applyA11yZoom(200);
    else if (mode === "zoom_100") applyA11yZoom(100);
    else if (mode === "high_contrast" || mode === "grayscale" || mode === "dark_mode")
      applyA11yFilter(mode);
    else if (mode === "highlight") toggleFocusHighlight();
    else if (mode === "reset")    resetA11y();
    // 현재 상태 반환 (팝업 UI 동기화용)
    sendResponse({ zoom: vvA11y.zoom, filter: vvA11y.filter });
  }

  if (request.action === "get_a11y_state") {
    sendResponse({ zoom: vvA11y.zoom, filter: vvA11y.filter,
                   highlight: !!document.getElementById("vv-focus-style") });
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
      if (chrome.runtime.lastError) {
        console.error("❌ 스크린샷 요청 실패:", chrome.runtime.lastError.message);
        return;
      }
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

function showLoadingIndicator() {
  let el = document.getElementById("vv-loading");
  if (el) return;
  el = document.createElement("div");
  el.id = "vv-loading";
  Object.assign(el.style, {
    position: "fixed", bottom: "24px", right: "24px",
    background: "#1e40af", color: "white",
    padding: "12px 18px", borderRadius: "10px",
    fontSize: "15px", fontWeight: "bold",
    zIndex: "2147483647", pointerEvents: "none",
    boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
  });
  el.textContent = "⏳ 처리 중...";
  document.body.appendChild(el);
}

function hideLoadingIndicator() {
  document.getElementById("vv-loading")?.remove();
}

async function processRequest(audioBlob, screenshotDataUrl) {
  if (audioBlob.size === 0) console.warn("⚠️ 오디오 데이터 없음");

  speak("처리 중입니다");
  showLoadingIndicator();

  const screenshotBlob = dataURItoBlob(screenshotDataUrl);

  const viewportText = getViewportText();
  const fullText = getAllVisibleText(window);
  const domText = viewportText.length > 100 ? viewportText : fullText;
  console.log(`📝 viewport: ${viewportText.length}자 / 전체: ${fullText.length}자`);

  const formData = new FormData();
  formData.append("audio", audioBlob, "input.webm");
  formData.append("screenshot", screenshotBlob, "input.png");
  formData.append("dom", domText.substring(0, 3000) || "텍스트 없음");
  formData.append("dom_elements", JSON.stringify(getInteractiveElements()));
  formData.append("zoom_level", String(vvA11y.zoom));
  formData.append("device_pixel_ratio", String(window.devicePixelRatio || 1));

  try {
    console.log("🚀 서버로 전송 중...");
    const response = await fetch(`${SERVER_URL}/process`, {
      method: "POST",
      headers: { "ngrok-skip-browser-warning": "1" },
      body: formData,
    });

    const data = await response.json();
    hideLoadingIndicator();
    console.log("✅ 결과 받음:", data);

    // 0. 음성 명령 → 접근성 클라이언트 처리 (백엔드 액션보다 우선)
    if (tryVoiceA11y(data.command)) {
      // 접근성 명령은 처리 완료, TTS 피드백은 showA11yToast가 담당
      if (data.audio_base64) {
        // 그래도 서버 음성 안내는 재생
        const bytes = atob(data.audio_base64);
        const ab = new ArrayBuffer(bytes.length);
        const ia = new Uint8Array(ab);
        for (let i = 0; i < bytes.length; i++) ia[i] = bytes.charCodeAt(i);
        const url = URL.createObjectURL(new Blob([ab], { type: "audio/mpeg" }));
        const audio = new Audio(url);
        audio.onended = () => URL.revokeObjectURL(url);
        audio.play().catch(() => {});
      }
      return;
    }

    // 1. 오디오 재생
    if (data.audio_base64) {
      try {
        const bytes = atob(data.audio_base64);
        const ab = new ArrayBuffer(bytes.length);
        const ia = new Uint8Array(ab);
        for (let i = 0; i < bytes.length; i++) ia[i] = bytes.charCodeAt(i);
        const blob = new Blob([ab], { type: "audio/mpeg" });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.onended = () => URL.revokeObjectURL(url);
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
        const hasCoord = data.action.x_raw != null && data.action.y_raw != null;
        const cssSelector = data.action.css_selector;
        const targetName = (data.action.target || "").trim();
        const ratio = window.devicePixelRatio || 1;

        const boxPxCss = (() => {
          const bp = data.action.box_px;
          if (!bp || bp.length !== 4) return null;
          return bp.map(v => v / ratio);
        })();

        // 후보 3종을 각각 독립적으로 수집 (서로 다른 곳을 가리키는지 진단 표시용)
        // ① 모델이 말한 이름으로 텍스트 매칭 — 좌표/셀렉터 환각에 가장 강함
        const byText  = targetName ? findByText(targetName, boxPxCss) : null;

        // ② CSS 셀렉터 (보이는 첫 매칭만)
        let bySel = null;
        if (cssSelector) {
          try {
            for (const el of document.querySelectorAll(cssSelector)) {
              if (isVisible(el)) { bySel = el; break; }
            }
          } catch (e) { console.warn(`⚠️ 셀렉터 오류 (${cssSelector}):`, e); }
        }

        // ③ 픽셀 좌표 — 실제 클릭 가능한 요소 위일 때만
        let byCoord = null, coordXY = null;
        if (hasCoord) {
          const cx = data.action.x_raw / ratio, cy = data.action.y_raw / ratio;
          coordXY = { x: cx, y: cy };
          byCoord = clickableAtPoint(cx, cy);
        }

        // 우선순위: 이름 > 셀렉터 > 좌표
        const final = byText || bySel || byCoord || null;

        const cands = [];
        if (byText)  cands.push({ el: byText,  how: "text",     label: "① 이름 매칭",  color: "#22c55e" });
        if (bySel)   cands.push({ el: bySel,   how: "selector", label: "② 셀렉터",     color: "#3b82f6" });
        if (byCoord) cands.push({ el: byCoord, how: "coord",    label: "③ 좌표",       color: "#f59e0b" });

        // 진단 오버레이: 후보 전부 + 최종 선택 + 정보 패널 표시
        showDecisionOverlay(cands, final, {
          recommend: targetName,
          grounding: data.action.grounding,
          coordXY,
          boxPxCss,
        });

        if (final) {
          const r0 = final.getBoundingClientRect();
          if (r0.top < 0 || r0.bottom > (window.innerHeight || 0)) {
            final.scrollIntoView({ block: "center", behavior: "smooth" });
            await new Promise(res => setTimeout(res, 400));
          }
          await new Promise(res => setTimeout(res, 1600)); // 진단 박스를 볼 시간
          final.focus();
          final.click();
          const howFinal = cands.find(c => c.el === final)?.how || "?";
          console.log(`✅ 최종 클릭 (${howFinal}):`, (final.innerText || final.value || "").slice(0, 30));
        } else {
          console.warn(`❌ 클릭 대상 못 찾음 | target='${targetName}' selector='${cssSelector}'`);
          speak(`'${targetName || "해당 항목"}'을 찾지 못했어요. 화면에 보이는 이름으로 다시 말씀해 주세요.`);
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

        // 1) 좌표가 있으면 해당 위치 클릭해서 포커스
        const hasCoord = data.action.x_raw != null && data.action.y_raw != null;
        if (hasCoord) {
          const ratio = window.devicePixelRatio || 1;
          const x = data.action.x_raw / ratio;
          const y = data.action.y_raw / ratio;
          showClickIndicator(x, y);
          const clickEl = getDeepElementFromPoint(x, y);
          if (clickEl) {
            clickEl.focus();
            ["mousedown", "mouseup", "click"].forEach((evt) =>
              clickEl.dispatchEvent(new MouseEvent(evt, {
                view: window, bubbles: true, cancelable: true, clientX: x, clientY: y,
              }))
            );
          }
        }

        // 2) 포커스된 요소 또는 검색창 fallback에 텍스트 입력
        let el = document.activeElement;
        if (!el || el === document.body || el.tagName === "BODY") {
          el = document.querySelector(
            "input[type='search'], input[type='text'], input:not([type]), textarea"
          );
        }
        if (el) {
          el.focus();
          // React controlled component는 .value 직접 변경을 무시하므로 native setter로 우회
          const nativeSetter = Object.getOwnPropertyDescriptor(
            el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype,
            "value"
          )?.set;
          if (nativeSetter) nativeSetter.call(el, text);
          else el.value = text;
          el.dispatchEvent(new Event("input",  { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
          console.log(`✅ 입력 완료: "${text}" → ${el.tagName}#${el.id}`);

          // submit: true 이면 TTS 재생 후 Enter 키로 검색 제출
          if (data.action.submit) {
            setTimeout(() => {
              el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
              el.dispatchEvent(new KeyboardEvent("keypress",{ key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
              el.dispatchEvent(new KeyboardEvent("keyup",   { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
              console.log("🔍 검색 제출 (Enter)");
            }, 3000);  // TTS 재생 대기 후 제출
          }
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
      } else if (act === "accessibility") {
        // 음성 명령 → 접근성 모드 (서버가 mode 필드 반환)
        const mode = data.action.mode || "";
        if (mode === "zoom_150")      applyA11yZoom(150);
        else if (mode === "zoom_200") applyA11yZoom(200);
        else if (mode === "zoom_100") applyA11yZoom(100);
        else if (["high_contrast","grayscale","dark_mode"].includes(mode))
          applyA11yFilter(mode);
        else if (mode === "highlight") toggleFocusHighlight();
        else if (mode === "reset")     resetA11y();
      } else if (act === "close") {
        console.log(`❌ 팝업 닫기 시도: ${data.action.target}`);
        const label = data.action.target || "";
        const candidates = Array.from(document.querySelectorAll(
          "button, span, div, a, [role='button'], [role='dialog'] *"
        )).filter(isVisible);
        const getElText = (el) =>
          el.innerText || el.getAttribute("aria-label") ||
          el.getAttribute("title") || el.querySelector("img")?.getAttribute("alt") || "";
        const closeTarget = candidates.find(el => {
          const txt = getElText(el);
          return /닫기|close|×|✕|닫음|cancel/i.test(txt) || (label && txt.includes(label));
        });
        if (closeTarget) {
          closeTarget.click();
        } else if (data.action.x_raw != null && data.action.y_raw != null) {
          const ratio = window.devicePixelRatio || 1;
          const cx = data.action.x_raw / ratio, cy = data.action.y_raw / ratio;
          const hit = getDeepElementFromPoint(cx, cy);
          if (hit) { hit.click(); console.log("닫기: 좌표 폴백 클릭"); }
          else console.warn("❌ 닫기 버튼을 찾을 수 없습니다.");
        } else {
          console.warn("❌ 닫기 버튼을 찾을 수 없습니다.");
        }
      }
    }
  } catch (error) {
    hideLoadingIndicator();
    console.error("❌ 처리 에러:", error);
    speak("서버 연결에 실패했습니다. 잠시 후 다시 시도해주세요.");
  }
}

function playBeep(type) {
  // 음성 안내 (켜짐/꺼짐 명확히)
  speak(type === "start" ? "녹음 시작" : "녹음 종료");

  // 상승(시작) / 하강(종료) 2음 패턴
  try {
    const ctx = new AudioContext();
    ctx.resume().then(() => {
      const freqs = type === "start" ? [523, 784] : [784, 523];
      freqs.forEach((freq, i) => {
        const osc = ctx.createOscillator();
        const g   = ctx.createGain();
        osc.connect(g);
        g.connect(ctx.destination);
        osc.type = "sine";
        osc.frequency.value = freq;
        const t = ctx.currentTime + i * 0.18;
        g.gain.setValueAtTime(0.4, t);
        g.gain.exponentialRampToValueAtTime(0.001, t + 0.15);
        osc.start(t);
        osc.stop(t + 0.15);
      });
    });
  } catch (e) {}
}

// ── TTS 헬퍼 (백엔드 SunHiNeural, 실패 시 브라우저 폴백) ─────
async function speak(text) {
  try {
    const resp = await fetch(`${SERVER_URL}/speak`, {
      method: "POST",
      headers: { "ngrok-skip-browser-warning": "1",
                 "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ text }),
    });
    const data = await resp.json();
    if (!data.audio_base64) throw new Error("no audio");
    const bytes = atob(data.audio_base64);
    const ab = new ArrayBuffer(bytes.length);
    const ia = new Uint8Array(ab);
    for (let i = 0; i < bytes.length; i++) ia[i] = bytes.charCodeAt(i);
    const url = URL.createObjectURL(new Blob([ab], { type: "audio/mpeg" }));
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    audio.play().catch(() => {});
  } catch {
    // 백엔드 미연결 시 브라우저 TTS 폴백
    if (!window.speechSynthesis) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ko-KR";
    u.rate = 0.92;
    speechSynthesis.speak(u);
  }
}

// ── 첫 실행 음성 안내 ─────────────────────────────────────────
(function initWelcome() {
  const isMac = /Mac|iPhone|iPad/i.test(navigator.userAgent);
  const mod    = isMac ? "Command" : "Ctrl";
  const recKey = `${mod}+Shift+S`;
  const panKey  = `${mod}+Shift+Y`;

  chrome.storage.local.get(["vv_welcomed"], (r) => {
    if (r.vv_welcomed) return;
    chrome.storage.local.set({ vv_welcomed: true });
    setTimeout(() => {
      speak(
        `안녕하세요. 비전보이스입니다. ` +
        `${recKey}를 누르고 명령을 말씀하시면 웹을 제어할 수 있습니다. ` +
        `${panKey}를 누르면 접근성 패널이 열립니다. ` +
        `또는 음성으로 고대비 모드, 화면 확대, 다크 모드라고 말씀하셔도 됩니다.`
      );
    }, 1800);
  });
})();

// ── 인라인 접근성 패널 ────────────────────────────────────────
const PANEL_ID = "vv-a11y-panel";

function togglePanel() {
  const existing = document.getElementById(PANEL_ID);
  if (existing) {
    existing.remove();
    speak("접근성 패널을 닫았습니다.");
    return;
  }

  const isMac  = /Mac|iPhone|iPad/i.test(navigator.userAgent);
  const modSym = isMac ? "⌘" : "Ctrl";

  const panel = document.createElement("div");
  panel.id = PANEL_ID;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "VisionVoice 접근성 패널");
  panel.setAttribute("aria-modal", "true");
  Object.assign(panel.style, {
    position: "fixed", top: "0", right: "0",
    width: "320px", height: "100vh",
    background: "#0f172a", color: "#f1f5f9",
    zIndex: "2147483647", display: "flex",
    flexDirection: "column", padding: "20px 16px",
    boxSizing: "border-box", boxShadow: "-4px 0 24px rgba(0,0,0,0.6)",
    fontFamily: "sans-serif", overflowY: "auto",
  });

  panel.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
      <h2 id="vv-panel-title" style="margin:0;font-size:18px;color:#60a5fa;">♿ VisionVoice</h2>
      <button id="vv-panel-close" aria-label="패널 닫기"
        style="background:#1e3a5f;color:#f1f5f9;border:none;border-radius:6px;
               padding:6px 10px;cursor:pointer;font-size:14px;">✕ 닫기</button>
    </div>
    <p style="font-size:12px;color:#94a3b8;margin:0 0 16px;">
      ${modSym}+Shift+S: 음성 명령 &nbsp;|&nbsp; ${modSym}+Shift+Y: 패널 &nbsp;|&nbsp; Esc: 닫기
    </p>

    <section aria-labelledby="vv-sec-zoom">
      <h3 id="vv-sec-zoom" style="font-size:13px;color:#94a3b8;margin:0 0 8px;text-transform:uppercase;">화면 확대</h3>
      <div style="display:flex;gap:8px;margin-bottom:16px;">
        <button class="vv-btn" data-mode="zoom_100" aria-label="기본 크기 100%">100%</button>
        <button class="vv-btn" data-mode="zoom_150" aria-label="150% 확대">150%</button>
        <button class="vv-btn" data-mode="zoom_200" aria-label="200% 확대">200%</button>
      </div>
    </section>

    <section aria-labelledby="vv-sec-filter">
      <h3 id="vv-sec-filter" style="font-size:13px;color:#94a3b8;margin:0 0 8px;text-transform:uppercase;">색상 필터</h3>
      <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:16px;">
        <button class="vv-btn" data-mode="high_contrast" aria-label="고대비 모드 켜기/끄기">🔆 고대비 모드</button>
        <button class="vv-btn" data-mode="grayscale"     aria-label="흑백 모드 색맹 지원 켜기/끄기">⬜ 흑백 모드 (색맹)</button>
        <button class="vv-btn" data-mode="dark_mode"     aria-label="다크 모드 켜기/끄기">🌙 다크 모드</button>
      </div>
    </section>

    <section aria-labelledby="vv-sec-misc">
      <h3 id="vv-sec-misc" style="font-size:13px;color:#94a3b8;margin:0 0 8px;text-transform:uppercase;">기타</h3>
      <div style="display:flex;flex-direction:column;gap:8px;">
        <button class="vv-btn" data-mode="highlight" aria-label="포커스 하이라이트 켜기/끄기">🟡 포커스 하이라이트</button>
        <button class="vv-btn" data-mode="reset"     aria-label="모든 접근성 설정 초기화" style="color:#fca5a5;">🔄 모두 초기화</button>
      </div>
    </section>

    <p style="font-size:11px;color:#64748b;margin-top:auto;padding-top:16px;text-align:center;">
      음성으로도 제어 가능 — "고대비 켜줘", "200% 확대해줘"
    </p>
  `;

  // 버튼 공통 스타일
  const btnStyle = {
    background: "#1e3a5f", color: "#f1f5f9",
    border: "1px solid #334155", borderRadius: "8px",
    padding: "10px 14px", cursor: "pointer",
    fontSize: "14px", textAlign: "left", width: "100%",
  };
  panel.querySelectorAll(".vv-btn").forEach(btn => {
    Object.assign(btn.style, btnStyle);
    btn.addEventListener("focus",     () => { btn.style.outline = "2px solid #60a5fa"; });
    btn.addEventListener("blur",      () => { btn.style.outline = "none"; });
    btn.addEventListener("mouseenter",() => { btn.style.background = "#1e40af"; });
    btn.addEventListener("mouseleave",() => { btn.style.background = "#1e3a5f"; });
    btn.addEventListener("click", () => {
      const mode = btn.dataset.mode;
      if      (mode === "zoom_100") applyA11yZoom(100);
      else if (mode === "zoom_150") applyA11yZoom(150);
      else if (mode === "zoom_200") applyA11yZoom(200);
      else if (mode === "reset")    resetA11y();
      else                          applyA11yFilter(mode);
      speak(btn.getAttribute("aria-label") || btn.textContent);
    });
  });

  // 닫기 버튼
  panel.querySelector("#vv-panel-close").addEventListener("click", togglePanel);

  // Esc 닫기 + Tab 트랩
  panel.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { togglePanel(); return; }
    if (e.key === "Tab") {
      const focusable = [...panel.querySelectorAll("button")];
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  document.body.appendChild(panel);

  // 첫 버튼에 포커스
  setTimeout(() => panel.querySelector(".vv-btn")?.focus(), 50);

  speak(
    "접근성 패널이 열렸습니다. " +
    "Tab 키로 버튼을 이동하고 Enter로 실행합니다. " +
    "화면 확대: 백퍼센트, 백오십퍼센트, 이백퍼센트. " +
    "색상 필터: 고대비 모드, 흑백 모드, 다크 모드. " +
    "포커스 하이라이트, 모두 초기화. " +
    "Escape 키로 닫습니다."
  );
}

// ── 음성 명령 → 접근성 클라이언트 처리 ──────────────────────
function tryVoiceA11y(cmd) {
  if (!cmd) return false;
  if (/(고대비|고 대비|대비 높)/.test(cmd))        { applyA11yFilter("high_contrast"); return true; }
  if (/(흑백|색맹|그레이)/.test(cmd))               { applyA11yFilter("grayscale");     return true; }
  if (/(다크\s*모드|다크모드|dark)/.test(cmd))      { applyA11yFilter("dark_mode");     return true; }
  if (/200|이백/.test(cmd) && /확대/.test(cmd))     { applyA11yZoom(200);               return true; }
  if (/150|백오십/.test(cmd) && /확대/.test(cmd))   { applyA11yZoom(150);               return true; }
  if (/(확대\s*해제|기본\s*크기|100)/.test(cmd))    { applyA11yZoom(100);               return true; }
  if (/(포커스|하이라이트)/.test(cmd))              { toggleFocusHighlight();            return true; }
  if (/(초기화|리셋|모두\s*끄)/.test(cmd))          { resetA11y();                       return true; }
  if (/(패널|대시보드)\s*(열|켜|보)/.test(cmd))     { togglePanel();                     return true; }
  if (/(패널|대시보드)\s*(닫|끄)/.test(cmd))        {
    const p = document.getElementById(PANEL_ID);
    if (p) togglePanel();
    return true;
  }
  return false;
}

// 클릭 진단 오버레이: 모델 추천(이름)·셀렉터·좌표 후보를 색깔 박스로 동시에 보여주고,
// 최종 클릭 대상을 빨간 테두리로 강조 + 좌하단 정보 패널 표시
function showDecisionOverlay(cands, final, info) {
  document.querySelectorAll(".vv-dbg").forEach(e => e.remove());

  const mk = (styles) => {
    const d = document.createElement("div");
    d.className = "vv-dbg";
    Object.assign(d.style, {
      position: "fixed", zIndex: "2147483646", pointerEvents: "none", boxSizing: "border-box",
    }, styles);
    document.body.appendChild(d);
    return d;
  };

  // 🟡 VLM/OmniParser 예측 bbox (노란 점선 — 모델이 시각적으로 본 영역)
  if (info.boxPxCss) {
    const [bx1, by1, bx2, by2] = info.boxPxCss;
    mk({
      left: bx1 + "px", top: by1 + "px",
      width: (bx2 - bx1) + "px", height: (by2 - by1) + "px",
      border: "3px dashed #facc15",
      background: "rgba(250,204,21,0.08)",
      borderRadius: "6px",
    });
    const vlmTag = mk({
      left: bx1 + "px", top: Math.max(0, by1 - 22) + "px",
      background: "#ca8a04", color: "#fff", font: "bold 12px sans-serif",
      padding: "2px 6px", borderRadius: "4px", whiteSpace: "nowrap",
    });
    vlmTag.textContent = `🟡 VLM bbox (${info.grounding || "?"})`;
  }

  // 후보별 박스 + 라벨
  cands.forEach((c) => {
    const r = c.el.getBoundingClientRect();
    const isFinal = c.el === final;
    mk({
      left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px",
      border: `3px ${isFinal ? "solid" : "dashed"} ${c.color}`,
      background: c.color + "22", borderRadius: "8px",
    });
    const tag = mk({
      left: r.left + "px", top: Math.max(0, r.top - 22) + "px",
      background: c.color, color: "#fff", font: "bold 12px sans-serif",
      padding: "2px 6px", borderRadius: "4px", whiteSpace: "nowrap",
    });
    tag.textContent = c.label;
  });

  // 좌표 지점 십자 표시(빈 영역이라 후보가 없을 때도 어디를 찍었는지 보이게)
  if (info.coordXY) {
    mk({
      left: (info.coordXY.x - 7) + "px", top: (info.coordXY.y - 7) + "px",
      width: "14px", height: "14px", borderRadius: "50%",
      background: "rgba(245,158,11,0.9)", border: "2px solid #fff",
    });
  }

  // 최종 선택 강조
  if (final) {
    const r = final.getBoundingClientRect();
    mk({
      left: (r.left - 4) + "px", top: (r.top - 4) + "px",
      width: (r.width + 8) + "px", height: (r.height + 8) + "px",
      border: "4px solid #ef4444", borderRadius: "10px",
      boxShadow: "0 0 0 3px rgba(239,68,68,0.3)",
    });
    const badge = mk({
      left: Math.max(0, r.right - 96) + "px", top: Math.max(0, r.bottom - 26) + "px",
      background: "#ef4444", color: "#fff", font: "bold 13px sans-serif",
      padding: "3px 8px", borderRadius: "6px",
    });
    badge.textContent = "✅ 최종 클릭";
  }

  // 정보 패널
  const txt = (el) => el ? (el.innerText || el.value || "").replace(/\s+/g, " ").trim().slice(0, 28) : "—";
  const coordEl   = cands.find(c => c.how === "coord")?.el;
  const finalHow  = final ? (cands.find(c => c.el === final)?.label || "—") : "없음";
  const panel = mk({
    left: "16px", bottom: "16px", maxWidth: "460px",
    background: "rgba(15,23,42,0.95)", color: "#f1f5f9",
    font: "13px/1.6 sans-serif", padding: "12px 14px", borderRadius: "10px",
    boxShadow: "0 6px 24px rgba(0,0,0,0.45)", whiteSpace: "pre-wrap",
  });
  const bpStr = info.boxPxCss
    ? `[${info.boxPxCss.map(v => Math.round(v)).join(",")}]`
    : "없음";
  panel.innerHTML =
    `<b style="color:#60a5fa">🔍 VisionVoice 클릭 진단</b>\n` +
    `🟡 VLM bbox (${info.grounding || "?"}): ${bpStr}\n` +
    `🟢 이름 매칭: ${txt(cands.find(c=>c.how==="text")?.el)}\n` +
    `🔵 셀렉터: ${txt(cands.find(c=>c.how==="selector")?.el) || "매칭 실패"}\n` +
    `🟠 좌표 지점: ${txt(coordEl)}\n` +
    `🔴 최종 선택: ${finalHow} → ${txt(final)}`;

  setTimeout(() => document.querySelectorAll(".vv-dbg").forEach(e => e.remove()), 4500);
}

// x, y, box 모두 CSS 픽셀(viewport 기준)로 받는다 — devicePixelRatio 변환은 호출부에서 끝낸 상태
function showClickIndicator(x, y, boxCss) {
  // bbox 사각형 (실제 클릭 대상 요소 영역)
  if (boxCss && boxCss.length === 4) {
    const [x1, y1, x2, y2] = boxCss;
    const rect = document.createElement("div");
    Object.assign(rect.style, {
      position: "fixed",
      left:   x1 + "px",
      top:    y1 + "px",
      width:  (x2 - x1) + "px",
      height: (y2 - y1) + "px",
      border: "2px solid #3b82f6",
      background: "rgba(59, 130, 246, 0.12)",
      borderRadius: "4px",
      zIndex: "999998",
      pointerEvents: "none",
      boxSizing: "border-box",
    });
    document.body.appendChild(rect);
    setTimeout(() => rect.remove(), 2200);
  }

  // 클릭 중심점 (빨간 원)
  const dot = document.createElement("div");
  Object.assign(dot.style, {
    position: "fixed",
    left:   (x - 10) + "px",
    top:    (y - 10) + "px",
    width:  "20px",
    height: "20px",
    backgroundColor: "rgba(239, 68, 68, 0.85)",
    border: "2px solid white",
    borderRadius: "50%",
    zIndex: "999999",
    pointerEvents: "none",
    boxShadow: "0 0 8px rgba(239,68,68,0.6)",
    transition: "transform 0.15s, opacity 0.3s",
  });
  document.body.appendChild(dot);
  setTimeout(() => { dot.style.transform = "scale(1.4)"; dot.style.opacity = "0"; }, 150);
  setTimeout(() => dot.remove(), 2000);
}
