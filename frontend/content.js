let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];

chrome.runtime.onMessage.addListener((request) => {
  if (request.action === "toggle") {
    if (!isRecording) {
      startRecording();
    } else {
      stopRecordingAndSend();
    }
  }
});

function startRecording() {
  isRecording = true;
  console.log("🎤 녹음 시작");
  // 마이크 로직 구현
}

function stopRecordingAndSend() {
  isRecording = false;
  console.log("🛑 녹음 종료 & 전송");

  // 1. 백그라운드에 캡처 요청
  chrome.runtime.sendMessage({ action: "capture" }, (dataUrl) => {
    // 2. DOM 추출 (간소화)
    const dom = document.body.innerText.slice(0, 1000); // 임시

    // 3. 서버 전송 로직 구현
  });
}
