# 사용자 등급 시스템 설계 문서

## 1. 개요

### 1.1 목적
- 사용자 역할(Role) 기반 접근 제어 시스템 구축
- 마스터 관리자용 Admin API 제공
- 등급별 기능 및 데이터 접근 차등화

### 1.2 등급 정의

| 등급 | 코드 | 설명 | 대상 |
|------|------|------|------|
| 마스터 | `master` | 전체 시스템 관리 권한 | 서비스 운영자 |
| 경매입찰업체 | `bidder` | 입찰 관련 전용 기능 | 등록된 경매 업체 |
| 유료 사용자 | `premium` | 전체 데이터 접근 | 구독 결제 사용자 |
| 무료 사용자 | `free` | 기본 기능만 사용 | 일반 가입자 (기본값) |
| 게스트 | `guest` | 공개 데이터만 접근 | 비로그인 사용자 |

---

## 2. 데이터베이스 설계

### 2.1 users 테이블 변경

```sql
-- 기존 컬럼
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
google_sub      TEXT UNIQUE NOT NULL
email           TEXT UNIQUE NOT NULL
name            TEXT
profile_image   TEXT
last_login_at   TIMESTAMPTZ
last_logout_at  TIMESTAMPTZ
created_at      TIMESTAMPTZ DEFAULT now()

-- 추가할 컬럼
role            TEXT NOT NULL DEFAULT 'free'
role_updated_at TIMESTAMPTZ
role_updated_by UUID REFERENCES users(id)
```

### 2.2 role 컬럼 제약조건

```sql
ALTER TABLE users
ADD CONSTRAINT users_role_check
CHECK (role IN ('master', 'bidder', 'premium', 'free'));
```

> **참고**: `guest`는 비로그인 상태이므로 DB에 저장하지 않음

### 2.3 마이그레이션 SQL

```sql
-- 1. role 컬럼 추가
ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'free';
ALTER TABLE users ADD COLUMN role_updated_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN role_updated_by UUID REFERENCES users(id);

-- 2. 제약조건 추가
ALTER TABLE users ADD CONSTRAINT users_role_check
CHECK (role IN ('master', 'bidder', 'premium', 'free'));

-- 3. 초기 마스터 설정 (필요시)
UPDATE users SET role = 'master' WHERE email = 'admin@example.com';
```

---

## 3. API 설계

### 3.1 Admin API 엔드포인트

| Method | Endpoint | 설명 | 권한 |
|--------|----------|------|------|
| GET | `/api/admin/users` | 사용자 목록 조회 | master |
| GET | `/api/admin/users/{user_id}` | 사용자 상세 조회 | master |
| PATCH | `/api/admin/users/{user_id}/role` | 사용자 등급 변경 | master |
| GET | `/api/admin/stats` | 등급별 사용자 통계 | master |

---

### 3.2 사용자 목록 조회

```
GET /api/admin/users?page=1&limit=20&role=free&search=email
Authorization: Bearer {masterToken}
```

**Query Parameters:**

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| page | int | N | 페이지 번호 (기본값: 1) |
| limit | int | N | 페이지당 수 (기본값: 20, 최대: 100) |
| role | string | N | 등급 필터 (master, bidder, premium, free) |
| search | string | N | 이메일/이름 검색 |

**Response (200 OK):**

```json
{
  "pagination": {
    "page": 1,
    "limit": 20,
    "total_items": 150,
    "total_pages": 8,
    "has_next": true,
    "has_prev": false
  },
  "items": [
    {
      "id": "uuid-string",
      "email": "user@example.com",
      "name": "홍길동",
      "profile_image": "https://...",
      "role": "free",
      "created_at": "2025-12-01T10:00:00Z",
      "last_login_at": "2025-12-27T09:30:00Z"
    }
  ]
}
```

---

### 3.3 사용자 등급 변경

```
PATCH /api/admin/users/{user_id}/role
Authorization: Bearer {masterToken}
Content-Type: application/json

{
  "role": "premium"
}
```

**Request Body:**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| role | string | Y | 변경할 등급 (master, bidder, premium, free) |

**Response (200 OK):**

```json
{
  "id": "uuid-string",
  "email": "user@example.com",
  "name": "홍길동",
  "role": "premium",
  "role_updated_at": "2025-12-27T10:00:00Z",
  "role_updated_by": "master-user-uuid"
}
```

**Errors:**

| 코드 | 설명 |
|------|------|
| 400 | 유효하지 않은 등급 |
| 401 | 인증 필요 |
| 403 | master 권한 필요 |
| 404 | 사용자를 찾을 수 없음 |

---

### 3.4 등급별 사용자 통계

```
GET /api/admin/stats
Authorization: Bearer {masterToken}
```

**Response (200 OK):**

```json
{
  "total_users": 150,
  "by_role": {
    "master": 2,
    "bidder": 10,
    "premium": 25,
    "free": 113
  },
  "recent_signups": {
    "today": 5,
    "this_week": 23,
    "this_month": 67
  }
}
```

---

## 4. 인증/인가 설계

### 4.1 권한 체크 Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Request   │────▶│  JWT 검증    │────▶│  Role 확인  │
└─────────────┘     └──────────────┘     └──────────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                    ▼                           ▼                           ▼
             ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
             │   master    │            │   bidder    │            │  free/prem  │
             │  Admin API  │            │  입찰 API   │            │  일반 API   │
             └─────────────┘            └─────────────┘            └─────────────┘
```

### 4.2 권한 데코레이터 설계

```python
# app/utils/auth.py에 추가

def require_role(*allowed_roles: str):
    """
    역할 기반 접근 제어 데코레이터

    사용법:
        @router.get("/admin/users")
        @require_role("master")
        async def list_users(current_user: dict = Depends(get_current_user)):
            ...
    """
    async def role_checker(current_user: dict = Depends(get_current_user)):
        user = users_repo.get_by_id(current_user["id"])
        if not user or user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="접근 권한이 없습니다"
            )
        return {**current_user, "role": user.get("role")}
    return role_checker
```

### 4.3 get_current_user 수정

```python
async def get_current_user(...) -> dict:
    # ... 기존 코드 ...

    return {
        "id": payload["sub"],
        "email": payload["email"],
        "role": user.get("role", "free")  # role 추가
    }
```

---

## 5. 등급별 기능 제한

### 5.1 기능 접근 매트릭스

| 기능 | guest | free | premium | bidder | master |
|------|-------|------|---------|--------|--------|
| 경매 목록 조회 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 차량 상세 조회 | △ | ✓ | ✓ | ✓ | ✓ |
| VIN 정보 조회 | ✗ | ✗ | ✓ | ✓ | ✓ |
| 즐겨찾기 | ✗ | ✓ | ✓ | ✓ | ✓ |
| 시세 히스토리 | ✗ | △ | ✓ | ✓ | ✓ |
| 입찰 기능 | ✗ | ✗ | ✗ | ✓ | ✓ |
| 사용자 관리 | ✗ | ✗ | ✗ | ✗ | ✓ |
| 시스템 설정 | ✗ | ✗ | ✗ | ✗ | ✓ |

> △: 제한적 접근 (일부 데이터만, 일일 제한 등)

### 5.2 Rate Limit 차등 적용

| 등급 | 분당 요청 수 | 일일 요청 수 |
|------|-------------|-------------|
| guest | 10 | 100 |
| free | 30 | 1,000 |
| premium | 100 | 10,000 |
| bidder | 100 | 10,000 |
| master | 무제한 | 무제한 |

---

## 6. 구현 계획

### Phase 1: 기본 인프라 (우선 구현)
- [ ] DB 마이그레이션 (role 컬럼 추가)
- [ ] users_repo에 role 관련 함수 추가
- [ ] get_current_user에 role 반환 추가
- [ ] require_role 데코레이터 구현

### Phase 2: Admin API
- [ ] GET /api/admin/users (사용자 목록)
- [ ] GET /api/admin/users/{id} (사용자 상세)
- [ ] PATCH /api/admin/users/{id}/role (등급 변경)
- [ ] GET /api/admin/stats (통계)

### Phase 3: 기능 제한 적용
- [ ] VIN 정보 접근 제한 (premium 이상)
- [ ] 시세 히스토리 제한 (free: 최근 1개월만)
- [ ] Rate Limit 등급별 차등 적용

### Phase 4: 입찰 기능 (추후)
- [ ] 입찰 관련 API 설계
- [ ] bidder 전용 기능 구현

---

## 7. 보안 고려사항

### 7.1 등급 변경 감사 로그
- 모든 등급 변경은 `role_updated_at`, `role_updated_by` 기록
- 추후 별도 audit_logs 테이블 도입 검토

### 7.2 마스터 계정 보호
- 마스터 → 다른 등급 변경 시 경고
- 최소 1명의 마스터는 유지되도록 검증

### 7.3 자기 자신 등급 변경 불가
- 마스터라도 본인 등급은 변경 불가 (다른 마스터가 변경)

---

## 8. 클라이언트 연동 가이드

### 8.1 로그인 응답에 role 포함

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "name": "홍길동",
    "role": "free"
  }
}
```

### 8.2 클라이언트 권한 체크

```typescript
// 클라이언트에서 역할 기반 UI 표시
const canAccessAdmin = user.role === 'master';
const canViewVIN = ['master', 'bidder', 'premium'].includes(user.role);
```

---

## 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| 1.0 | 2025-12-27 | 초안 작성 |
