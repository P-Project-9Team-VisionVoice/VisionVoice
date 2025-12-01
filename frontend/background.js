chrome.commands.onCommand.addListener((command) => {
  if (command === "toggle-recording") {
    // 활성 탭에 메시지 전송
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) chrome.tabs.sendMessage(tabs[0].id, { action: "toggle" });
    });
  }
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
