# backend/main.py
import os
import logging

from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form , BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional
import os

# 커스텀 AI 모듈 임포트
from ai.stt import STTModule
from ai.simple_agent import OpenCUAgent
from ai.tts import TTSModule

# 로깅 설정 
logging.basicConfig(level=logging.ERROR) #에러 날 때만 기록
logger = logging.getLogger(__name__)

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

# 파일 삭제 함수 
def cleanup_files(file_paths: List[str]):
    for path in file_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"🗑️ [파일 삭제 완료] {path}")
        except Exception as e:
            logger.error(f"파일 삭제 실패 ({path}): {e}")

@app.post("/process")
async def process(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    screenshot: UploadFile = File(...),
    dom: str = Form(""),
):
    print("요청 수신!")

    # 1. 파일 저장
    audio_path = f"{TEMP_DIR}/input.webm"
    image_path = f"{TEMP_DIR}/input.png"
    tts_path = f"{TEMP_DIR}/output.mp3"
    
    # 응답 후 삭제 예약
    background_tasks.add_task(cleanup_files, [audio_path, image_path, tts_path])

    try:
        # 파일 저장
        audio_content = await audio.read()
        if len(audio_content) == 0:
            print(f"오디오가 비어있어요!")
            return {"action": {"action": "none"}, "summary": "오디오 오류"}

        with open(audio_path, "wb") as f:
            f.write(audio_content)
        with open(image_path, "wb") as f:
            f.write(await screenshot.read())
            
        print(f"파일 저장 완료 ({len(audio_content)} bytes). STT 변환 중...")
            
        # (1) STT
        command = stt_module.transcribe(audio_path)
        print(f"사용자 명령: {command}")

        # (2) OpenCUA
        # dom이 비어있으면 기본 텍스트 전달
        print(f"화면 분석 및 AI 생각 중...")
        safe_dom = dom if dom else "웹 페이지 텍스트 정보 없음"
        action, summary = agent_module.inference(image_path, command, safe_dom)
        print(f"판단 결과: {action}, 요약 내용: {summary}")

        # (3) TTS
        print(f"TTS 생성 중...")
        await tts_module.generate_audio(summary, tts_path)

        # Base64 변환 (Mixed Content 해결용)
        import base64
        with open(tts_path, "rb") as audio_file:
            audio_base64 = base64.b64encode(audio_file.read()).decode("utf-8")
            
        print(f"처리 완료! 클라이언트로 응답 전송.")
        print("-" * 30)

        return {
            "command": command,
            "action": action,
            "summary": summary,
            "audio_base64": audio_base64,
        }
        
    except Exception as e:
        logger.error(f"처리 중 에러 발생: {e}", exc_info=True)
        return {"action": {"action": "none"}, "summary": "처리 중 오류가 발생했습니다.", "audio_base64": None}

