// popup.js — content script에 접근성 명령 전달 + 상태 동기화

function send(mode) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs[0]) return;
    chrome.tabs.sendMessage(
      tabs[0].id,
      { action: "accessibility", mode },
      (resp) => {
        if (chrome.runtime.lastError) return; // content script 없는 탭 무시
        if (resp) syncUI(resp);
      }
    );
  });
}

function syncUI(state) {
  // 확대 버튼 활성화
  document.querySelectorAll("[id^='btn-zoom']").forEach(b => b.classList.remove("active"));
  const zoomMap = { 100: "btn-zoom100", 150: "btn-zoom150", 200: "btn-zoom200" };
  const zoomBtn = document.getElementById(zoomMap[state.zoom]);
  if (zoomBtn) zoomBtn.classList.add("active");

  // 필터 버튼 활성화
  ["high_contrast", "grayscale", "dark_mode"].forEach(f => {
    const btn = document.getElementById("btn-" + f);
    if (btn) btn.classList.toggle("active", state.filter === f);
  });

  // 하이라이트 버튼
  if (state.highlight !== undefined) {
    const btn = document.getElementById("btn-highlight");
    if (btn) btn.classList.toggle("active", state.highlight);
  }
}

// 팝업 열릴 때 버튼 연결 + 현재 상태 가져오기
document.addEventListener("DOMContentLoaded", () => {
  // 버튼 이벤트 연결
  document.getElementById("btn-zoom100").addEventListener("click", () => send("zoom_100"));
  document.getElementById("btn-zoom150").addEventListener("click", () => send("zoom_150"));
  document.getElementById("btn-zoom200").addEventListener("click", () => send("zoom_200"));
  document.getElementById("btn-high_contrast").addEventListener("click", () => send("high_contrast"));
  document.getElementById("btn-grayscale").addEventListener("click", () => send("grayscale"));
  document.getElementById("btn-dark_mode").addEventListener("click", () => send("dark_mode"));
  document.getElementById("btn-highlight").addEventListener("click", () => send("highlight"));
  document.getElementById("btn-reset").addEventListener("click", () => send("reset"));

  // 현재 상태 동기화
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs[0]) return;
    chrome.tabs.sendMessage(
      tabs[0].id,
      { action: "get_a11y_state" },
      (resp) => {
        if (chrome.runtime.lastError) return;
        if (resp) syncUI(resp);
      }
    );
  });
});
