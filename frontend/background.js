// frontend/background.js
chrome.commands.onCommand.addListener((command) => {
  const actionMap = {
    "toggle-recording": "toggle",
    "open-panel": "toggle-panel",
  };
  const action = actionMap[command];
  if (!action) return;

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs[0]) return;
    chrome.tabs.sendMessage(tabs[0].id, { action }, () => {
      if (chrome.runtime.lastError) {
        console.warn("VisionVoice: content script not ready on this tab");
      }
    });
  });
});

// 스크린샷 요청 처리
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "capture") {
    chrome.tabs.captureVisibleTab(null, { format: "png" }, (dataUrl) => {
      sendResponse(dataUrl);
    });
    return true; // 비동기 응답
  }
});
