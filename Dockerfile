# Python 3.11 슬림 이미지 사용 (경량화)
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 표준 라이브러리만 사용하므로 추가 패키지 설치 불필요

# 애플리케이션 코드 복사
COPY . .

# 비루트 사용자 생성 및 전환 (보안)
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# 서버가 사용할 포트 노출
EXPOSE 8000

# 환경변수 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 서버 실행 명령
CMD ["python", "server.py"]