# backend/ai/stt.py
from .config import USE_MOCK_STT

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

        segments, _ = self.model.transcribe(
            audio_path, 
            language="ko", 
            beam_size=5,
            initial_prompt="이것은 컴퓨터 화면을 제어하는 명령어입니다. 메일, 클릭, 스크롤, 버튼."
        )
        return "".join([s.text for s in segments])
