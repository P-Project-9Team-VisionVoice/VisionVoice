// content.js
let recorder;
let chunks = [];

chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === "toggle") {
        recorder?.state === "recording" ? stop() : start();
    }
});

async function start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    chunks = [];

    recorder.ondataavailable = e => chunks.push(e.data);
    recorder.onstop = processData;

    recorder.start();
    beep(880);
}

function stop() {
    recorder.stop();
    beep(440);
}

function beep(freq) {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    osc.frequency.value = freq;
    osc.connect(ctx.destination);
    osc.start();
    setTimeout(() => osc.stop(), 100);
}

// Blob을 Base64 문자열로 변환하는 유틸리티
function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

async function processData() {
    console.log("🚀 Processing data...");

    const audioBlob = new Blob(chunks, { type: "audio/webm" });
    const audioBase64 = await blobToBase64(audioBlob); // Blob -> Base64 변환
    const dom = document.body.innerText.slice(0, 3000);

    console.log("📡 Sending data to background script...");

    // background.js로 모든 데이터 전송
    chrome.runtime.sendMessage(
        {
            type: "PROCESS_AI_REQUEST",
            payload: {
                audioBase64: audioBase64,
                dom: dom
            }
        },
        (response) => {
            if (chrome.runtime.lastError) {
                console.error("❌ Runtime Error:", chrome.runtime.lastError);
                return;
            }
            console.log("✅ Received response from background:", response);
            handleAgentResult(response);
        }
    );
}

function handleAgentResult(result) {
    if (!result) return;

    // 화면 조작(Action)
    if (result.intent === "action" && result.actions) {
        result.actions.forEach(act => {
            if (act.type === "click") {
                const el = document.elementFromPoint(act.x, act.y);
                if (el) {
                    console.log("🖱️ Clicking:", el);

                    // 시각적 피드백
                    showClickIndicator(act.x, act.y);

                    el.click();
                } else {
                    console.warn("⚠️ No element found at:", act.x, act.y);
                }
            }
        });
    }
}

function showClickIndicator(x, y) {
    const dot = document.createElement("div");
    dot.style.position = "fixed";
    dot.style.left = x + "px";
    dot.style.top = y + "px";
    dot.style.width = "20px";
    dot.style.height = "20px";
    dot.style.backgroundColor = "red";
    dot.style.borderRadius = "50%";
    dot.style.zIndex = "9999";
    dot.style.pointerEvents = "none";
    document.body.appendChild(dot);
    setTimeout(() => dot.remove(), 1000);
}