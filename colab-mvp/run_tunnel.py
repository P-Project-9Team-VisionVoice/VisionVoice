# run_tunnel.py
from pyngrok import ngrok
import uvicorn

# 기존 터널이 있다면 닫기
ngrok.kill()

# 1. 포트 8000을 열어줌
http_tunnel = ngrok.connect(8000) # type: ignore
print(f"🚀 Public URL: {http_tunnel.public_url}")

# 2. 프로그램이 바로 안 꺼지게 대기
input("🔥 엔터를 누르면 터널이 종료됩니다...")