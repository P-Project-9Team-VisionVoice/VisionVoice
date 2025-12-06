# backend/ai/tts.py
from .config import USE_MOCK_TTS
import edge_tts


class TTSModule:
    async def generate_audio(self, text, output_path):
        if USE_MOCK_TTS:
            # 빈 파일 생성 (에러 방지)
            with open(output_path, "wb") as f:
                f.write(b"dummy")
            return

        communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
        await communicate.save(output_path)
