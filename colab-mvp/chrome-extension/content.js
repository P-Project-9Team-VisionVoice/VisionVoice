// content.js
let recorder;
let chunks = [];

// 1. 녹음 제어
chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === "toggle") {
        recorder?.state === "recording" ? stop() : start();
    }
});

// 2. 녹음 시작/종료
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
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result);
        reader.readAsDataURL(blob);
    });
}

// 3. 데이터 전송
async function processData() {
    console.log("🚀 Processing data...");
    const audioBlob = new Blob(chunks, { type: "audio/webm" });
    const audioBase64 = await blobToBase64(audioBlob);
    const dom = document.body.innerText.replace(/\s+/g, ' ').slice(0, 3000);

    chrome.runtime.sendMessage(
        { type: "PROCESS_AI_REQUEST", payload: { audioBase64, dom } },
        (response) => {
            if (chrome.runtime.lastError) return;
            console.log("✅ Result:", response);
            handleAgentResult(response);
        }
    );
}

async function handleAgentResult(result) {
    if (!result) return;

    if (
        (result.intent === "action" || result.intent === "scroll") &&
        result.actions
    ) {
        let successCount = 0;
        const vw = window.innerWidth;
        const vh = window.innerHeight;

        for (const act of result.actions) {
            console.log(`🤖 Action: ${act.type}`, act);

            // 뒤로가기
            if (act.type === "go_back") {
                window.history.back();
                sendTTS("이전 페이지로 이동합니다.");
                continue;
            }

            // 스크롤
            if (act.type === "scroll") {
                let amount = window.innerHeight * 0.8;

                if (act.amount && act.amount !== "null" && !isNaN(parseInt(act.amount))) {
                    amount = parseInt(act.amount);
                }

                const direction = act.direction === "up" ? -1 : 1;

                // 윈도우 스크롤 + 내부 컨테이너 스크롤 동시 시도
                performSmartScroll(amount * direction);

                sendTTS(act.direction === "up" ? "위로 올립니다." : "아래로 내립니다.");
                successCount++;
                continue;
            }

            // 클릭 & 입력
            let targetEl = null;
            let targetX, targetY;

            // [Box Search]
            if (act.bbox) {
                const [xmin, ymin, xmax, ymax] = act.bbox;
                const rxMin = (xmin / 1000) * vw;
                const ryMin = (ymin / 1000) * vh;
                const rxMax = (xmax / 1000) * vw;
                const ryMax = (ymax / 1000) * vh;

                showDebugBox(rxMin, ryMin, rxMax - rxMin, ryMax - ryMin, "red");

                // act.type을 넘겨서 input 태그 가산점 부여
                const boxResult = findBestElementInBox(rxMin, ryMin, rxMax, ryMax, act.text_content, act.type);
                if (boxResult.score > 80) targetEl = boxResult.element;
            }

            // [Global Search]
            if (!targetEl) {
                const keywords = new Set();
                if (act.text_content) keywords.add(act.text_content);
                if (result.recognized_text) keywords.add(result.recognized_text);

                targetEl = findElementGlobally(Array.from(keywords), act.type);
            }

            // INPUT fallback (검색창 안전망)
            if (act.type === "input" && !targetEl) {
                targetEl = document.querySelector(
                    'input[type="search"], input[placeholder*="검색"], input'
                );
            }

            // [Action Execution]
            if (targetEl) {
                let execEl = targetEl;

                if (act.type === "click") {
                    execEl = getClickableParent(targetEl);
                }

                console.log("🎯 Final Target:", execEl);
                const rect = execEl.getBoundingClientRect();

                targetX = rect.left + rect.width / 2;
                targetY = rect.top + rect.height / 2;

                showDebugBox(rect.left, rect.top, rect.width, rect.height, "green");

                if (act.type === "click") await performClick(execEl);
                else if (act.type === "input") await performInput(execEl, act.value);

                successCount++;
            } else {
                // Fallback 좌표 클릭
                if (act.bbox) {
                    const [xmin, ymin, xmax, ymax] = act.bbox;
                    await performClickAtCoords((xmin + xmax) / 2000 * vw, (ymin + ymax) / 2000 * vh);
                }
            }
        }

        if (successCount > 0) sendTTS("완료했습니다.");
        else sendTTS("실패했습니다.");
    }
}

function performSmartScroll(amount) {
    // 1. 기본 윈도우 스크롤 시도
    window.scrollBy({ top: amount, behavior: "smooth" });

    // 2. 화면 내에서 스크롤 가능한 가장 큰 요소 찾기
    const candidates = document.querySelectorAll("div, main, section, article, ul");
    let bestContainer = null;
    let maxArea = 0;

    candidates.forEach(el => {
        const style = window.getComputedStyle(el);
        const overflowY = style.overflowY;

        // 스크롤 가능한 속성을 가졌는지 확인
        const isScrollable = (overflowY === 'auto' || overflowY === 'scroll') &&
            (el.scrollHeight > el.clientHeight);

        if (isScrollable) {
            const r = el.getBoundingClientRect();
            // 화면에 보이고 크기가 큰지 확인
            if (r.width > 0 && r.height > 0 && r.top < window.innerHeight && r.bottom > 0) {
                const area = r.width * r.height;
                if (area > maxArea) {
                    maxArea = area;
                    bestContainer = el;
                }
            }
        }
    });

    // 3. 찾았으면 거기도 스크롤
    if (bestContainer) {
        console.log("📜 Scrolling Container:", bestContainer);
        bestContainer.scrollBy({ top: amount, behavior: "smooth" });
    }
}

function calculateScore(el, targetText, actionType, isInsideBox = false) {
    let score = 0;

    const domText = (el.innerText || "").replace(/\s+/g, '').toLowerCase();
    const domLabel = (el.getAttribute('aria-label') || "").replace(/\s+/g, '').toLowerCase();
    const domPlaceholder = (el.getAttribute('placeholder') || "").replace(/\s+/g, '').toLowerCase();
    const target = (targetText || "").replace(/\s+/g, '').toLowerCase();

    // 텍스트 길이 페널티
    if (domText.length > 50) score -= 1000;

    // 텍스트 매칭
    if (target.length > 0) {
        if (domText === target || domLabel === target || domPlaceholder === target) score += 500;
        else if (domText.includes(target) || domLabel.includes(target)) {
            if (domText.length < target.length * 2 + 5) score += 300;
            else score += 50;
        }
    }

    const tag = el.tagName.toLowerCase();

    // Input 우선순위 강화
    if (actionType === "input") {
        if (tag === 'input' || tag === 'textarea') score += 2000; // 절대적 우선순위
        if (el.getAttribute('contenteditable') === 'true') score += 1500;
    }

    if (['a', 'button', 'input', 'textarea'].includes(tag) || el.getAttribute('role') === 'button') score += 100;
    if (isInsideBox) score += 200;

    return score;
}

// 박스 내 요소 찾기
function findBestElementInBox(x1, y1, x2, y2, targetText, actionType) {
    const candidates = document.querySelectorAll("*");
    let bestCandidate = null;
    let maxScore = -9999;

    candidates.forEach(el => {
        if (el.style.zIndex === '999999') return;
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;

        const intersect = !(r.right < x1 || r.left > x2 || r.bottom < y1 || r.top > y2);
        if (intersect) {
            const score = calculateScore(el, targetText, actionType, true);
            if (score > maxScore) {
                maxScore = score;
                bestCandidate = el;
            }
        }
    });
    return { element: bestCandidate, score: maxScore };
}

// 전역 검색
function findElementGlobally(keywords, actionType) {
    const candidates = document.querySelectorAll("a, button, input, [role='button'], span, textarea");
    let bestEl = null;
    let maxScore = -9999;

    candidates.forEach(el => {
        if (el.style.zIndex === '999999') return;
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;

        keywords.forEach(kw => {
            const score = calculateScore(el, kw, actionType, false);
            if (score > maxScore) {
                maxScore = score;
                bestEl = el;
            }
        });
    });
    return bestEl;
}

// 클릭 가능한 부모 찾기
function getClickableParent(el) {
    let current = el;
    while (current && current !== document.body) {
        const tag = current.tagName.toLowerCase();
        if (['a', 'button', 'input', 'textarea'].includes(tag) ||
            current.onclick ||
            current.getAttribute('role') === 'button' ||
            getComputedStyle(current).cursor === 'pointer') {
            return current;
        }
        current = current.parentElement;
    }
    return el;
}

// 클릭
function performClick(el) {
    return new Promise((resolve) => {
        setTimeout(() => {
            el.focus();
            el.click();
            ['mousedown', 'mouseup'].forEach(evt => {
                el.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
            });
            resolve(true);
        }, 1000);
    });
}

// 좌표 클릭
function performClickAtCoords(x, y) {
    return new Promise((resolve) => {
        showClickIndicator(x, y);
        setTimeout(() => {
            const el = document.elementFromPoint(x, y);
            if (el) {
                const clickable = getClickableParent(el);
                clickable ? clickable.click() : el.click();
            }
            resolve(true);
        }, 1000);
    });
}

// 입력 (엔터 포함)
function performInput(el, text) {
    return new Promise((resolve) => {
        setTimeout(() => {
            el.focus();
            el.value = text;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));

            setTimeout(() => {
                el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
                resolve(true);
            }, 500);
        }, 1000);
    });
}

function showDebugBox(x, y, w, h, color = "red") {
    const box = document.createElement("div");
    Object.assign(box.style, {
        position: "fixed", left: x + "px", top: y + "px",
        width: w + "px", height: h + "px",
        border: `3px solid ${color}`,
        backgroundColor: color === "red" ? "rgba(255, 0, 0, 0.2)" : "rgba(0, 255, 0, 0.2)",
        zIndex: "999999", pointerEvents: "none"
    });
    document.body.appendChild(box);
    setTimeout(() => box.remove(), 1500);
}

function showClickIndicator(x, y) {
    const dot = document.createElement("div");
    dot.style.position = "fixed";
    dot.style.left = x + "px"; top: y + "px";
    dot.style.width = "20px"; height: "20px";
    dot.style.backgroundColor = "red"; dot.style.borderRadius = "50%";
    dot.style.zIndex = "999999";
    document.body.appendChild(dot);
    setTimeout(() => dot.remove(), 1000);
}

function sendTTS(text) {
    chrome.runtime.sendMessage({ type: "SPEAK_RESULT", text: text });
}