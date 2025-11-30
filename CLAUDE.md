# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

자동차 경매 데이터를 수집, 저장, 제공하는 FastAPI 기반 백엔드 서버입니다.

### 주요 기능
- **데이터 수집 (Crawling)**: 외부 경매 사이트에서 CSV 형식의 경매 데이터를 주기적으로 크롤링
- **데이터 저장**: 로컬 파일 시스템 또는 Supabase(PostgreSQL)에 저장
- **REST API 제공**: 클라이언트 앱에서 날짜별 경매 데이터를 조회할 수 있는 API 제공

### 기술 스택
- **Framework**: FastAPI (Python 3.9+)
- **Database**: Supabase (PostgreSQL) 또는 로컬 파일 시스템
- **Deployment**: Docker + Google Cloud Run
- **CI/CD**: GitHub Actions

### 데이터 흐름
1. **크롤링**: 서버 시작 시 또는 스케줄러에 의해 외부 URL에서 CSV 데이터를 다운로드
2. **날짜 매핑**: 원본 파일의 날짜(YYMMDD)를 다음 영업일로 변환하여 저장 (예: 금요일 데이터 → 월요일로 저장)
3. **저장**: 설정에 따라 로컬 `sources/` 디렉토리 또는 Supabase 테이블에 저장
4. **API 응답**: 클라이언트 요청 시 CSV 파일 또는 JSON 형식으로 데이터 반환

### 프로젝트 구조
```
app/
├── api/v1/routes/     # API 엔드포인트 (dates, files, auction, admin)
├── core/              # 설정 (config.py)
├── crawler/           # 크롤링 로직 (downloader.py)
├── repositories/      # 데이터 저장소 (file_repo, supabase_repo, firestore_repo)
├── schemas/           # Pydantic 모델 (API 요청/응답 스키마)
├── services/          # 비즈니스 로직 (csv_service.py)
├── scripts/           # 마이그레이션/백필 스크립트
└── utils/             # 유틸리티 (bizdate.py - 영업일 계산)
```

## Commands

### Run Development Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Or directly:
python app/main.py
```

### Run Crawler Standalone
```bash
python -m app.crawler
```

### Backfill Scripts
```bash
# Backfill Supabase from local sources directory
python -m app.scripts.backfill_supabase --dir sources --overwrite

# Migrate Firestore to Supabase
python -m app.scripts.firestore_to_supabase --collection auction_data
```

### Docker Build & Run
```bash
docker build -t car-auction .
docker run -p 8000:8000 --env-file .env car-auction
```

## Architecture

### Data Flow
1. **Crawler** (`app/crawler/downloader.py`) fetches CSV from `CRAWL_URL`, caches ETag/Last-Modified to avoid redundant downloads
2. **Business Date Mapping** (`app/utils/bizdate.py`): Source dates (YYMMDD) are mapped to next business day for storage (Mon-Thu→next day, Fri→Mon, Sat/Sun→Mon)
3. **Storage**: Either local files in `sources/` directory OR parsed rows in Supabase tables

### API Endpoints
- `GET /api/dates` - List available dates
- `GET /api/csv/{date}` or `GET /api/files/{date}` - Download CSV for date
- `POST /api/admin/crawl` - Trigger crawl (requires `Authorization: Bearer {ADMIN_TOKEN}`)
- `POST /api/admin/ensure/{date}` - Ensure date exists in Supabase

### Repository Pattern
- `file_repo.py` - Local filesystem operations
- `supabase_repo.py` - Supabase REST API client (parses CSV rows into table records)
- `firestore_repo.py` - Legacy Firestore integration

### Storage Modes
Controlled by `SUPABASE_ENABLED` env var:
- **Local mode** (default): CSVs stored in `sources/` as files
- **Supabase mode**: CSV parsed into rows in `auction_data` table with optional `auction_data_history` for audit

## Key Configuration (via .env)

- `ADMIN_TOKEN` - Required for admin endpoints
- `CRAWL_URL` - Source URL for auction CSV data
- `SUPABASE_ENABLED` - Enable Supabase storage mode
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_TABLE` - Supabase connection

## CI/CD

- **deploy.yml**: Pushes to main trigger Docker build and Cloud Run deployment
- **update-data.yml**: Scheduled crawl trigger (weekdays 10-min intervals during KST evening, weekends every 4 hours)


## Git 커밋 메시지 규칙
- 한국어로 작성, 모든 변경사항 포함
- **중요**: 커밋 메시지에 Claude 관련 attribution 제외 (아래 내용 포함 금지)
    - `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
    - `Co-Authored-By: Claude <noreply@anthropic.com>`