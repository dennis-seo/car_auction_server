# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI-based server for car auction data management. Crawls auction CSV data from external sources, stores it locally or in Supabase, and serves it via REST API.

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