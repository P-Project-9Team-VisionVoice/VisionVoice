# backend/main.py
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional
import os

# 커스텀 AI 모듈 임포트
from ai.stt import STTModule
from ai.simple_agent import OpenCUAgent
from ai.tts import TTSModule

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 임시 저장소 설정
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)
app.mount("/temp", StaticFiles(directory=TEMP_DIR), name="temp")

# AI 모듈 초기화 (서버 켤 때 한 번만 실행)
stt_module = STTModule()
agent_module = OpenCUAgent()
tts_module = TTSModule()


@app.post("/process")
async def process(
    audio: UploadFile = File(...),
    screenshot: UploadFile = File(...),
    dom: str = Form(""),
    dom_elements: str = Form("[]"),
):
    print("🚀 요청 수신!")

    # 1. 파일 저장
    audio_path = f"{TEMP_DIR}/input.webm"
    image_path = f"{TEMP_DIR}/input.png"
    tts_path = f"{TEMP_DIR}/output.mp3"

    # 파일 내용 확인용 로그
    audio_content = await audio.read()
    print(f"🎤 오디오 크기: {len(audio_content)} bytes")
    
    if len(audio_content) == 0:
        return {"action": {"action": "none"}, "summary": "오디오가 전달되지 않았습니다.", "audio_base64": None}

    with open(audio_path, "wb") as f:
        f.write(audio_content)
    
    with open(image_path, "wb") as f:
        f.write(await screenshot.read())

    # 2. 파이프라인 실행
    try:
        # (1) STT
        command = stt_module.transcribe(audio_path)
        print(f"User Command: {command}")

        # (2) OpenCUA
        # dom이 비어있으면 기본 텍스트 전달
        safe_dom = dom if dom else "웹 페이지 텍스트 정보 없음"
        action, summary = agent_module.inference(image_path, command, safe_dom, dom_elements)
        print(f"AI Action: {action}, Summary: {summary}")

        # (3) TTS
        await tts_module.generate_audio(summary, tts_path)

        # Base64 변환 (Mixed Content 해결용)
        import base64
        with open(tts_path, "rb") as audio_file:
            audio_base64 = base64.b64encode(audio_file.read()).decode("utf-8")

        return {
            "command": command,
            "action": action,
            "summary": summary,
            "audio_base64": audio_base64,
        }
        
    except Exception as e:
        print(f"❌ 처리 중 에러 발생: {e}")
        import traceback
        traceback.print_exc()
        return {"action": {"action": "none"}, "summary": "처리 중 오류가 발생했습니다.", "audio_base64": None}


@app.post("/speak")
async def speak(text: str = Form(...)):
    """UI 안내 메시지를 SunHiNeural TTS로 변환"""
    import base64, time
    tts_path = f"{TEMP_DIR}/speak_{int(time.time()*1000) % 100000}.mp3"
    await tts_module.generate_audio(text, tts_path)
    with open(tts_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")
    return {"audio_base64": audio_b64}

