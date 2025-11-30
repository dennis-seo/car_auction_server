-- auction_records 테이블 생성 스크립트
-- Supabase PostgreSQL에서 실행

-- 기존 테이블이 있다면 삭제 (주의: 데이터 손실)
-- DROP TABLE IF EXISTS auction_records;

CREATE TABLE IF NOT EXISTS auction_records (
    id BIGSERIAL PRIMARY KEY,

    -- 차량 식별
    vin VARCHAR(30),                        -- 차대번호 (없을 수 있음)
    car_number VARCHAR(20) NOT NULL,        -- 차량번호

    -- 경매 정보
    auction_date DATE NOT NULL,             -- 경매 날짜
    sell_number INTEGER NOT NULL,           -- 출품번호
    auction_house VARCHAR(50),              -- 경매장명

    -- 정규화된 필드 (분석용) - JSON 기준 ID
    manufacturer_id VARCHAR(10),            -- 제조사 ID (car_models.json 기준)
    model_id VARCHAR(10),                   -- 모델 ID (car_models.json 기준)
    trim_id VARCHAR(10),                    -- 트림 ID (car_models.json 기준)

    -- 정규화된 필드 (분석용) - 텍스트 값
    manufacturer VARCHAR(50),               -- 제조사: 현대, 기아, 벤츠 등
    model VARCHAR(100),                     -- 모델명: 쏘나타, 그랜저 등
    sub_model VARCHAR(100),                 -- 세부모델: DN8, IG 등
    trim VARCHAR(150),                      -- 트림: 프레스티지, 프리미엄 등
    year INTEGER,                           -- 연식
    fuel_type VARCHAR(20),                  -- 연료: 가솔린, 디젤, LPG, 전기, 하이브리드, 수소
    transmission VARCHAR(20),               -- 변속기: 자동, 수동
    engine_cc INTEGER,                      -- 배기량(cc)
    usage_type VARCHAR(20),                 -- 용도: 자가용, 렌터카

    -- 상태 정보
    km INTEGER,                             -- 주행거리
    price INTEGER,                          -- 낙찰가(만원)
    score VARCHAR(20),                      -- 평가등급 (정규화)
    color VARCHAR(30),                      -- 색상
    image_url TEXT,                         -- 이미지 URL

    -- 원본 필드 보존 (기존 API 호환용)
    raw_post_title TEXT,                    -- 원본 Post Title
    raw_title TEXT,                         -- 원본 title
    raw_color TEXT,                         -- 원본 color
    raw_fuel TEXT,                          -- 원본 fuel
    raw_trans TEXT,                         -- 원본 trans
    raw_score TEXT,                         -- 원본 score

    -- 메타 정보
    source_filename VARCHAR(100),           -- 원본 파일명
    created_at TIMESTAMPTZ DEFAULT NOW(),   -- 생성일시

    -- 유니크 제약 (동일 경매일+출품번호+경매장은 중복 불가)
    CONSTRAINT uq_auction_record UNIQUE(auction_date, sell_number, auction_house)
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_ar_auction_date ON auction_records(auction_date);
CREATE INDEX IF NOT EXISTS idx_ar_manufacturer ON auction_records(manufacturer);
CREATE INDEX IF NOT EXISTS idx_ar_model ON auction_records(model);
CREATE INDEX IF NOT EXISTS idx_ar_manufacturer_model ON auction_records(manufacturer, model);
CREATE INDEX IF NOT EXISTS idx_ar_manufacturer_id ON auction_records(manufacturer_id);
CREATE INDEX IF NOT EXISTS idx_ar_model_id ON auction_records(model_id);
CREATE INDEX IF NOT EXISTS idx_ar_trim_id ON auction_records(trim_id);
CREATE INDEX IF NOT EXISTS idx_ar_year ON auction_records(year);
CREATE INDEX IF NOT EXISTS idx_ar_price ON auction_records(price);
CREATE INDEX IF NOT EXISTS idx_ar_vin ON auction_records(vin) WHERE vin IS NOT NULL AND vin != '';
CREATE INDEX IF NOT EXISTS idx_ar_car_number ON auction_records(car_number);
CREATE INDEX IF NOT EXISTS idx_ar_fuel_type ON auction_records(fuel_type);

-- RLS (Row Level Security) 정책 설정 (Supabase 권장)
ALTER TABLE auction_records ENABLE ROW LEVEL SECURITY;

-- 읽기 정책: 모든 사용자 허용
CREATE POLICY "Allow public read access" ON auction_records
    FOR SELECT USING (true);

-- 쓰기 정책: service_role만 허용
CREATE POLICY "Allow service role write access" ON auction_records
    FOR ALL USING (auth.role() = 'service_role');

-- 코멘트 추가
COMMENT ON TABLE auction_records IS '경매 차량 데이터 (정규화 + 원본 보존)';
COMMENT ON COLUMN auction_records.vin IS '차대번호 - 차량 고유 식별자 (없을 수 있음)';
COMMENT ON COLUMN auction_records.manufacturer_id IS '제조사 ID (car_models.json 기준)';
COMMENT ON COLUMN auction_records.model_id IS '모델 ID (car_models.json 기준)';
COMMENT ON COLUMN auction_records.trim_id IS '트림 ID (car_models.json 기준)';
COMMENT ON COLUMN auction_records.manufacturer IS '제조사 (파싱된 값)';
COMMENT ON COLUMN auction_records.model IS '모델명 (파싱된 값)';
COMMENT ON COLUMN auction_records.raw_post_title IS '원본 Post Title (API 호환용)';

-- 기존 테이블에 ID 컬럼 추가 (마이그레이션용)
-- ALTER TABLE auction_records ADD COLUMN IF NOT EXISTS manufacturer_id VARCHAR(10);
-- ALTER TABLE auction_records ADD COLUMN IF NOT EXISTS model_id VARCHAR(10);
-- ALTER TABLE auction_records ADD COLUMN IF NOT EXISTS trim_id VARCHAR(10);
