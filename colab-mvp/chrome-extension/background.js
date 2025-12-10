// background.js
chrome.commands.onCommand.addListener((command) => {
    if (command === "toggle-recording") {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs[0]) {
                chrome.tabs.sendMessage(tabs[0].id, { action: "toggle" });
            }
        });
    }
});

// DataURL(Base64)을 Blob으로 변환하는 함수
function dataURLtoBlob(dataURL) {
    const arr = dataURL.split(',');
    const mime = arr[0].match(/:(.*?);/)[1];
    const bstr = atob(arr[1]);
    let n = bstr.length;
    const u8arr = new Uint8Array(n);
    while (n--) {
        u8arr[n] = bstr.charCodeAt(n);
    }
    return new Blob([u8arr], { type: mime });
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    // 1. 기존 스크린샷 캡처 요청
    if (request.type === "CAPTURE_SCREENSHOT") {
        chrome.tabs.captureVisibleTab(null, { format: "png" }, (dataUrl) => {
            sendResponse(dataUrl);
        });
        return true;
    }

    // 2. AI 처리 요청
    if (request.type === "PROCESS_AI_REQUEST") {
        const { audioBase64, dom } = request.payload;

        // 비동기 처리를 위해 즉시 return true 하고 내부에서 async 실행
        (async () => {
            try {
                // 1) 스크린샷 캡처
                const screenshotDataUrl = await chrome.tabs.captureVisibleTab(null, { format: "png" });

                // 2) 데이터 변환 (Base64 String -> Blob)
                const audioBlob = dataURLtoBlob(audioBase64);
                const screenshotBlob = dataURLtoBlob(screenshotDataUrl);

                // 3) FormData 생성
                const fd = new FormData();
                fd.append("screenshot", screenshotBlob, "screenshot.png");
                fd.append("audio", audioBlob, "audio.webm");
                fd.append("dom", dom);

                console.log("📡 Fetching localhost:8000/process from background...");

                // run_tunnel.py 실행해서 나온 local Fast API ngrok 주소
                const NEW_NGROK_URL = "https://1ee624642065.ngrok-free.app/process";

                const res = await fetch(NEW_NGROK_URL, {
                    method: "POST",
                    headers: {
                        "ngrok-skip-browser-warning": "69420"
                    },
                    body: fd
                });

                if (!res.ok) {
                    throw new Error(`Server error: ${res.status}`);
                }

                // 1. 일단 받습니다.
                let result = await res.json();

                if (typeof result === "string") {
                    console.log("⚠️ 결과가 문자열입니다. JSON 파싱을 시도합니다.");
                    const cleanJson = result.replace(/```json|```/g, "").trim();
                    result = JSON.parse(cleanJson);
                }

                if (result.recognized_text) {
                    console.log(`🎤 사용자의 말(STT): "${result.recognized_text}"`);
                }

                console.log("✅ Final Object:", result);

                // 🔊 TTS 실행
                if (result.speech) {
                    chrome.tts.stop();
                    setTimeout(() => {
                        chrome.tts.speak(result.speech, {
                            lang: 'ko-KR',
                            rate: 1.0,
                            enqueue: false
                        });
                    }, 100);
                }

                // 5) 결과를 content script로 반환
                sendResponse(result);

            } catch (error) {
                console.error("❌ Error in background fetch:", error);

                chrome.tts.speak("죄송합니다. 오류가 발생했습니다.", { lang: 'ko-KR' });

                sendResponse({ speech: "오류가 발생했습니다. 다시 시도해주세요." });
            }
        })();

        return true;
    }

    // 3. 액션 결과 TTS 요청 (content.js에서 보낸 성공/실패 메시지 읽기)
    if (request.type === "SPEAK_RESULT") {
        const message = request.text;
        chrome.tts.speak(message, {
            lang: 'ko-KR',
            rate: 1.0,
            enqueue: true // 앞선 안내 멘트가 끝나면 이어서 말하기
        });
    }
});