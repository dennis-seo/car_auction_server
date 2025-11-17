# Supabase 전환 (기존 Spanner 구조 동일)

Cloud Spanner에서 사용하던 테이블 구조(원본 CSV BYTES + 메타데이터)를 Supabase Postgres 상에서 그대로 재현하도록 코드를 수정했습니다. 아래 순서를 따르면 별도 Storage 버킷 없이도 동일한 형태로 동작합니다.

## 1. Supabase 프로젝트 준비
1. Supabase 대시보드에서 `kanghun-private's Project`를 연 뒤 **Project Settings → API**에서 `Project URL`과 `service_role` 키를 확인합니다.
2. Supabase SQL Editor에서 아래 DDL을 실행해 날짜·행 단위 테이블을 만듭니다. CSV의 각 열이 그대로 Postgres 컬럼으로 들어가므로 `SELECT * FROM auction_data WHERE date='250901'` 같이 조회할 수 있습니다.

```sql
create table if not exists public.auction_data (
    date text not null,
    row_index integer not null,
    post_title text,
    sell_number text,
    car_number text,
    color text,
    fuel text,
    image text,
    km text,
    price text,
    title text,
    trans text,
    year text,
    auction_name text,
    vin text,
    score text,
    source_filename text,
    filename text,
    updated_at timestamptz not null default timezone('utc', now()),
    primary key (date, row_index)
);

create table if not exists public.auction_data_history (
    id bigserial primary key,
    date text not null,
    row_index integer not null,
    post_title text,
    sell_number text,
    car_number text,
    color text,
    fuel text,
    image text,
    km text,
    price text,
    title text,
    trans text,
    year text,
    auction_name text,
    vin text,
    score text,
    source_filename text,
    filename text,
    updated_at timestamptz not null,
    history_ingested_at timestamptz not null default timezone('utc', now())
);
```

> 메인 테이블은 날짜별 최신 데이터를 항상 1회분만 보관하고, 히스토리 테이블은 업로드 때마다 append됩니다. 필요 없다면 `.env`에서 `SUPABASE_HISTORY_TABLE` 줄을 비워두면 됩니다.

## 2. 환경 변수 설정
`.env` 또는 배포 환경에 아래 값을 채워 넣습니다. 이름과 기본 구조는 예전 Spanner 설정과 거의 동일합니다.

```
SUPABASE_ENABLED=true
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service_role 키>
SUPABASE_TABLE=auction_data                 # 주 테이블
# SUPABASE_HISTORY_TABLE=auction_data_history  # (선택) 히스토리 테이블
```

`SUPABASE_ANON_KEY`를 넣으면 읽기 요청만 따로 분리할 수 있지만, 서버 측에서는 service role 키 하나만으로도 충분합니다.

## 3. 초기 데이터 적재
기존 `sources/` 디렉터리에 있는 CSV를 그대로 올리려면:

```bash
python -m app.scripts.backfill_supabase --dir sources --overwrite
```

`--dry-run` 옵션으로 먼저 어떤 날짜가 올라갈지 확인할 수 있습니다.

## 4. 운영 시나리오 / 주의 사항
- 서버는 CSV를 파싱해 `auction_data` 행으로 넣고, `/api/files/{date}` 요청 시 다시 CSV 문자열로 직렬화합니다. 따라서 DB에서 `SELECT *` 한 결과와 API 응답이 항상 동기화됩니다.
- 히스토리 테이블을 켜 두면 동일 데이터를 그대로 append 하므로, 과거 스냅샷 비교가 필요할 때 유용합니다.
- Spanner 시절과 같은 권한 분리를 유지하려면 Supabase RLS 정책을 추가하고 서비스 키만 서버에서 사용하면 됩니다.
- Firestore에 남아 있는 기존 데이터가 있다면 `python -m app.scripts.firestore_to_supabase --collection auction_data`로 손쉽게 Supabase 테이블로 옮길 수 있습니다. 히스토리 컬렉션을 별도로 옮기려면 `--collection auction_data_history --target-table auction_data_history --target-history-table ''` 옵션을 추가해 실행하세요.

이 과정을 완료하면 이전과 동일하게 “날짜별 1행” 구조로 Supabase에서 데이터를 관리할 수 있습니다.
