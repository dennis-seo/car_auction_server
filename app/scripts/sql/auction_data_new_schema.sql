-- auction_data 테이블 새 스키마
-- 기존 테이블 삭제 후 재생성 필요

-- 기존 테이블 삭제
DROP TABLE IF EXISTS auction_data;

-- 새 테이블 생성 (CSV 파일 원본 저장용)
CREATE TABLE auction_data (
    id BIGSERIAL PRIMARY KEY,
    date VARCHAR(10) UNIQUE NOT NULL,       -- 영업일 기준 날짜 (YYMMDD 형식)
    content TEXT NOT NULL,                   -- CSV 파일 내용 전체 (raw)
    updated_at TIMESTAMPTZ DEFAULT NOW(),    -- 업데이트 시간
    row_count INTEGER NOT NULL DEFAULT 0,    -- CSV 레코드 수
    file_hash VARCHAR(64),                   -- SHA256 해시 (중복 체크용)
    filename VARCHAR(100) NOT NULL           -- 원본 CSV 파일명
);

-- 인덱스 생성
CREATE INDEX idx_auction_data_date ON auction_data(date);
CREATE INDEX idx_auction_data_file_hash ON auction_data(file_hash);

-- RLS 설정
ALTER TABLE auction_data ENABLE ROW LEVEL SECURITY;

-- 읽기: 모든 사용자 허용
CREATE POLICY "Allow public read access" ON auction_data
    FOR SELECT USING (true);

-- 쓰기: service_role만 허용
CREATE POLICY "Allow service role write access" ON auction_data
    FOR ALL USING (auth.role() = 'service_role');

-- 코멘트 추가
COMMENT ON TABLE auction_data IS 'CSV 파일 원본 저장 테이블';
COMMENT ON COLUMN auction_data.date IS '경매 날짜 (영업일 기준, YYMMDD 형식)';
COMMENT ON COLUMN auction_data.content IS 'CSV 파일 전체 내용 (raw)';
COMMENT ON COLUMN auction_data.updated_at IS '업데이트 일시';
COMMENT ON COLUMN auction_data.row_count IS 'CSV 데이터 행 수';
COMMENT ON COLUMN auction_data.file_hash IS 'CSV 파일 SHA256 해시';
COMMENT ON COLUMN auction_data.filename IS '원본 CSV 파일명';
