-- Migration: 002_add_user_role
-- Description: users 테이블에 role 관련 컬럼 추가
-- Date: 2025-12-27

-- 1. role 컬럼 추가 (기본값: free)
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'free';

-- 2. role 변경 추적 컬럼 추가
ALTER TABLE users ADD COLUMN IF NOT EXISTS role_updated_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS role_updated_by UUID REFERENCES users(id);

-- 3. role 값 제약조건 추가
-- 주의: 이미 존재하는 제약조건이 있으면 먼저 삭제 필요
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_role_check'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_role_check
        CHECK (role IN ('master', 'bidder', 'premium', 'free'));
    END IF;
END $$;

-- 4. role 컬럼에 인덱스 추가 (검색 성능 향상)
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- 5. 초기 마스터 설정 (필요시 아래 주석 해제 후 이메일 수정)
-- UPDATE users SET role = 'master' WHERE email = 'your-admin@example.com';

-- Rollback (필요시):
-- ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
-- DROP INDEX IF EXISTS idx_users_role;
-- ALTER TABLE users DROP COLUMN IF EXISTS role_updated_by;
-- ALTER TABLE users DROP COLUMN IF EXISTS role_updated_at;
-- ALTER TABLE users DROP COLUMN IF EXISTS role;
