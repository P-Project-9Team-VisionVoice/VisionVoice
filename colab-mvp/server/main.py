# server/main.py

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import base64, requests, os, datetime, json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pydub import AudioSegment

from faster_whisper import WhisperModel

COLAB_URL = "https://be79bb94a356.ngrok-free.app/infer" 

# 디버깅 파일 저장 경로
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# 🚀 서버 시작할 때 모델 미리 로딩 (속도 향상)
print("🎤 Loading Whisper Model (Local)...")
# CPU 사용 시 "int8", GPU 사용 시 "float16" 권장
stt_model = WhisperModel("medium", device="cpu", compute_type="int8")
print("✅ Whisper Model Ready!")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def perform_stt(audio_path):
    """로컬 Whisper 모델을 사용하여 음성을 텍스트로 변환"""
    try:
        # 1. WebM -> Wav 변환 (Whisper는 Wav 선호)
        sound = AudioSegment.from_file(audio_path)
        wav_path = audio_path.replace(".webm", ".wav")
        sound.export(wav_path, format="wav")

        # 2. 로컬 모델로 추론 (인터넷 X)
        segments, _ = stt_model.transcribe(wav_path, language="ko")
        
        # 3. 결과 합치기
        text = "".join([s.text for s in segments])
        return text.strip()
    except Exception as e:
        print(f"⚠️ STT Error: {e}")
        return None

@app.post("/process")
async def process(
    audio: UploadFile = File(...),
    screenshot: UploadFile = File(...),
    dom: str = Form(...)
):
    # 1. 타임스탬프 생성 (디버깅용)
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n🚀 [New Request] {now} ------------------")

    # 2. 파일 읽기
    audio_bytes = await audio.read()
    screenshot_bytes = await screenshot.read()
    
    # 3. 로컬 파일 저장 (기존 디버깅 기능 유지)
    audio_filename = f"{TEMP_DIR}/{now}_audio.webm"
    image_filename = f"{TEMP_DIR}/{now}_screenshot.png"
    dom_filename = f"{TEMP_DIR}/{now}_dom.txt"

    with open(audio_filename, "wb") as f:
        f.write(audio_bytes)
    with open(image_filename, "wb") as f:
        f.write(screenshot_bytes)
    with open(dom_filename, "w", encoding="utf-8") as f:
        f.write(dom)
    
    print(f"💾 Files saved to {TEMP_DIR}/")

    # 4. STT 실행 (Whisper)
    print("🎤 Recognizing speech (Local Whisper)...")
    user_goal = perform_stt(audio_filename)

    if user_goal:
        print(f"🗣️ 인식된 명령어: \"{user_goal}\"")
    else:
        user_goal = "이 화면 설명해줘"
        print(f"⚠️ STT 실패 -> 기본값 사용: \"{user_goal}\"")

    # 5. Colab 전송 준비
    image_base64 = base64.b64encode(screenshot_bytes).decode()
    headers = {
        "ngrok-skip-browser-warning": "69420",
        "Content-Type": "application/json"
    }

    try:
        session = get_session()
        print(f"📡 Sending to Colab: {user_goal}")
        
        res = session.post(
            COLAB_URL,
            headers=headers,
            json={
                "goal": user_goal,
                "dom": dom,
                "image_base64": image_base64
            },
            timeout=120
        )
        res.raise_for_status()
        
        result = res.json()

        # 6. JSON 파싱 (문자열로 왔을 경우 처리)
        if isinstance(result, str):
            print("⚠️ Colab returned string JSON. Parsing...")
            clean_json = result.replace("```json", "").replace("```", "").strip()
            try:
                result = json.loads(clean_json)
            except json.JSONDecodeError:
                print("❌ JSON Parsing failed, using fallback.")
                result = {"speech": result, "intent": "answer", "actions": []}
        
        # 7. 인식된 텍스트 결과에 포함
        result["recognized_text"] = user_goal 
        
        print("✅ Colab responded successfully")
        return result
        
    except Exception as e:
        print(f"❌ Colab Connection Error: {e}")
        return {
            "intent": "answer",
            "speech": "죄송합니다. 처리 중 오류가 발생했습니다.",
            "actions": [],
            "recognized_text": user_goal
        }