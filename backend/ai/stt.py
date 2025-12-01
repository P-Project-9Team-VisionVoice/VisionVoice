from .config import USE_MOCK_STT

if not USE_MOCK_STT:
    from faster_whisper import WhisperModel


class STTModule:
    def __init__(self):
        if not USE_MOCK_STT:
            print("🎤 STT 모델 로딩 중... (Whisper)")
            # GPU 없으면 device="cpu", compute_type="int8"로 변경
            self.model = WhisperModel("medium", device="cuda", compute_type="float16")
        else:
            print("🎤 STT Mock 모드 대기 중")

    def transcribe(self, audio_path):
        if USE_MOCK_STT:
            return "장바구니에 담아줘"

        segments, _ = self.model.transcribe(audio_path, language="ko")
        return "".join([s.text for s in segments])
