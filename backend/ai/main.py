from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import shutil
import os

# 커스텀 AI 모듈 임포트
from ai.stt import STTModule
from ai.agent import OpenCUAgent
from ai.tts import TTSModule

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 임시 저장소 설정
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)
app.mount("/temp", StaticFiles(directory=TEMP_DIR), name="temp")

# AI 모듈 초기화 (서버 켤 때 한 번만 실행됨)
stt_module = STTModule()
agent_module = OpenCUAgent()
tts_module = TTSModule()


@app.post("/process")
async def process(
    audio: UploadFile = File(...),
    screenshot: UploadFile = File(...),
    dom: str = Form(...),
):
    print("🚀 요청 수신!")

    # 1. 파일 저장
    audio_path = f"{TEMP_DIR}/input.webm"
    image_path = f"{TEMP_DIR}/input.png"
    tts_path = f"{TEMP_DIR}/output.mp3"

    with open(audio_path, "wb") as f:
        f.write(await audio.read())
    with open(image_path, "wb") as f:
        f.write(await screenshot.read())

    # 2. 파이프라인 실행
    # (1) STT
    command = stt_module.transcribe(audio_path)
    print(f"User Command: {command}")

    # (2) OpenCUA
    action, summary = agent_module.inference(image_path, command, dom)
    print(f"AI Action: {action}, Summary: {summary}")

    # (3) TTS
    await tts_module.generate_audio(summary, tts_path)

    return {
        "command": command,
        "action": action,
        "summary": summary,
        "audio_url": "http://localhost:8000/temp/output.mp3",
    }
