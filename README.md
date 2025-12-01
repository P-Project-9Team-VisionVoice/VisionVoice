# VisionVoice MVP

## 1. 설치 (Setup)

1. Python 3.10 이상 설치
2. 라이브러리 설치
   ```bash
   pip install -r backend/requirements.txt
   ```

## 2. 서버 실행 (Backend)

1. backend/ai/config.py에서 USE_MOCK 옵션 확인 (개발할 땐 True, 실제 모델 돌릴 땐 False)
2. 터미널에서 실행:
   ```cd backend
   uvicorn main:app --reload
   ```

## 3. 확장 프로그램 실행 (Frontend)

1. 크롬 주소창 chrome://extensions
2. 우측 상단 개발자 모드 켜기
3. 압축해제된 확장 프로그램을 로드합니다 -> frontend 폴더 선택
4. 웹페이지에서 Ctrl + Shift + S 눌러서 테스트
