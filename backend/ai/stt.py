# backend/ai/stt.py
from .config import USE_MOCK_STT
import subprocess, os

if not USE_MOCK_STT:
    from faster_whisper import WhisperModel


class STTModule:
    def __init__(self):
        if not USE_MOCK_STT:
            print("🎤 STT 모델 로딩 중... (CPU 모드로 전환)")
            self.model = WhisperModel("medium", device="cpu", compute_type="int8")
        else:
            print("🎤 STT Mock 모드 대기 중")

    def transcribe(self, audio_path):
        if USE_MOCK_STT:
            return "화면 설명해줘"

        # WebM(Opus) → WAV 변환 (Whisper 안정성)
        wav_path = audio_path.replace(".webm", ".wav")
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path],
                capture_output=True, timeout=10
            )
            transcribe_path = wav_path if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0 else audio_path
        except Exception:
            transcribe_path = audio_path

        segments, _ = self.model.transcribe(
            transcribe_path,
            language="ko",
            beam_size=5,
            vad_filter=True,
            initial_prompt="이것은 웹 브라우저를 제어하는 한국어 명령어입니다. 클릭, 스크롤, 입력, 설명, 이동."
        )
        return "".join([s.text for s in segments])
