# tts.py
from .config import USE_MOCK_TTS
import edge_tts

class TTSModule:
    async def generate_audio(self, text, output_path):
        if USE_MOCK_TTS:
            with open(output_path, "wb") as f:
                f.write(b"dummy")
            return

        try:
            communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
            await communicate.save(output_path)
            print(f"✅ TTS 생성: {output_path}")
        except Exception as e:
            print(f"⚠️ TTS 실패 (fallback): {e}")
            open(output_path, "wb").write(b"")
