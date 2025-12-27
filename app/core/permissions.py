"""
권한 및 역할 관리 모듈

사용자 역할(Role) 정의 및 권한 체크 유틸리티
확장성을 고려하여 역할과 권한을 분리하여 관리
"""

from enum import Enum
from functools import wraps
from typing import Callable, List, Optional, Set

from fastapi import Depends, HTTPException, status


class UserRole(str, Enum):
    """
    사용자 역할 정의

    역할은 계층 구조를 가지며, 상위 역할은 하위 역할의 권한을 포함
    계층: master > bidder > premium > free > guest
    """
    MASTER = "master"      # 전체 시스템 관리
    BIDDER = "bidder"      # 경매입찰업체
    PREMIUM = "premium"    # 유료 사용자
    FREE = "free"          # 무료 사용자 (기본값)
    GUEST = "guest"        # 비로그인 사용자

    @classmethod
    def values(cls) -> List[str]:
        """모든 역할 값 반환"""
        return [role.value for role in cls]

    @classmethod
    def db_values(cls) -> List[str]:
        """DB에 저장 가능한 역할 값 (guest 제외)"""
        return [role.value for role in cls if role != cls.GUEST]

    @classmethod
    def is_valid(cls, role: str) -> bool:
        """유효한 역할인지 확인"""
        return role in cls.values()

    @classmethod
    def is_valid_for_db(cls, role: str) -> bool:
        """DB에 저장 가능한 역할인지 확인"""
        return role in cls.db_values()


class Permission(str, Enum):
    """
    세부 권한 정의

    역할과 별개로 세부 기능별 권한을 정의
    추후 역할-권한 매핑 테이블로 확장 가능
    """
    # 사용자 관리
    USER_LIST = "user:list"
    USER_READ = "user:read"
    USER_UPDATE_ROLE = "user:update_role"

    # 경매 데이터
    AUCTION_READ = "auction:read"
    AUCTION_READ_VIN = "auction:read_vin"
    AUCTION_READ_FULL_HISTORY = "auction:read_full_history"

    # 즐겨찾기
    FAVORITE_READ = "favorite:read"
    FAVORITE_WRITE = "favorite:write"

    # 입찰 (추후)
    BID_READ = "bid:read"
    BID_WRITE = "bid:write"

    # 시스템 관리
    SYSTEM_ADMIN = "system:admin"
    SYSTEM_STATS = "system:stats"


# 역할별 권한 매핑
# 확장 시 DB 테이블로 이동 가능
ROLE_PERMISSIONS: dict[UserRole, Set[Permission]] = {
    UserRole.MASTER: {
        # 마스터는 모든 권한
        Permission.USER_LIST,
        Permission.USER_READ,
        Permission.USER_UPDATE_ROLE,
        Permission.AUCTION_READ,
        Permission.AUCTION_READ_VIN,
        Permission.AUCTION_READ_FULL_HISTORY,
        Permission.FAVORITE_READ,
        Permission.FAVORITE_WRITE,
        Permission.BID_READ,
        Permission.BID_WRITE,
        Permission.SYSTEM_ADMIN,
        Permission.SYSTEM_STATS,
    },
    UserRole.BIDDER: {
        Permission.AUCTION_READ,
        Permission.AUCTION_READ_VIN,
        Permission.AUCTION_READ_FULL_HISTORY,
        Permission.FAVORITE_READ,
        Permission.FAVORITE_WRITE,
        Permission.BID_READ,
        Permission.BID_WRITE,
    },
    UserRole.PREMIUM: {
        Permission.AUCTION_READ,
        Permission.AUCTION_READ_VIN,
        Permission.AUCTION_READ_FULL_HISTORY,
        Permission.FAVORITE_READ,
        Permission.FAVORITE_WRITE,
    },
    UserRole.FREE: {
        Permission.AUCTION_READ,
        Permission.FAVORITE_READ,
        Permission.FAVORITE_WRITE,
    },
    UserRole.GUEST: {
        Permission.AUCTION_READ,
    },
}


def get_role_permissions(role: UserRole) -> Set[Permission]:
    """역할의 권한 목록 반환"""
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(role: UserRole, permission: Permission) -> bool:
    """특정 역할이 특정 권한을 가지고 있는지 확인"""
    return permission in get_role_permissions(role)


def has_any_permission(role: UserRole, permissions: List[Permission]) -> bool:
    """특정 역할이 주어진 권한 중 하나라도 가지고 있는지 확인"""
    role_perms = get_role_permissions(role)
    return any(perm in role_perms for perm in permissions)


def has_all_permissions(role: UserRole, permissions: List[Permission]) -> bool:
    """특정 역할이 주어진 권한을 모두 가지고 있는지 확인"""
    role_perms = get_role_permissions(role)
    return all(perm in role_perms for perm in permissions)


class RoleChecker:
    """
    역할 기반 접근 제어 클래스

    FastAPI Depends와 함께 사용하여 엔드포인트별 접근 제어

    사용법:
        @router.get("/admin/users")
        async def list_users(
            current_user: dict = Depends(require_roles(UserRole.MASTER))
        ):
            ...
    """

    def __init__(self, allowed_roles: List[UserRole]):
        self.allowed_roles = allowed_roles

    async def __call__(self, current_user: dict) -> dict:
        """현재 사용자의 역할 확인"""
        user_role = current_user.get("role", UserRole.FREE.value)

        if user_role not in [role.value for role in self.allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="접근 권한이 없습니다"
            )

        return current_user


class PermissionChecker:
    """
    권한 기반 접근 제어 클래스

    역할 대신 세부 권한으로 접근 제어

    사용법:
        @router.get("/vehicles/{id}/vin")
        async def get_vin(
            current_user: dict = Depends(require_permissions(Permission.AUCTION_READ_VIN))
        ):
            ...
    """

    def __init__(self, required_permissions: List[Permission], require_all: bool = True):
        self.required_permissions = required_permissions
        self.require_all = require_all

    async def __call__(self, current_user: dict) -> dict:
        """현재 사용자의 권한 확인"""
        user_role_str = current_user.get("role", UserRole.FREE.value)

        try:
            user_role = UserRole(user_role_str)
        except ValueError:
            user_role = UserRole.FREE

        if self.require_all:
            has_access = has_all_permissions(user_role, self.required_permissions)
        else:
            has_access = has_any_permission(user_role, self.required_permissions)

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="접근 권한이 없습니다"
            )

        return current_user


def require_roles(*roles: UserRole) -> RoleChecker:
    """
    역할 기반 접근 제어 의존성 생성

    Args:
        *roles: 허용할 역할들

    Returns:
        RoleChecker 인스턴스

    사용법:
        @router.get("/admin/users")
        async def list_users(
            current_user: dict = Depends(get_current_user),
            _: dict = Depends(require_roles(UserRole.MASTER))
        ):
            ...
    """
    return RoleChecker(list(roles))


def require_permissions(
    *permissions: Permission,
    require_all: bool = True
) -> PermissionChecker:
    """
    권한 기반 접근 제어 의존성 생성

    Args:
        *permissions: 필요한 권한들
        require_all: True면 모든 권한 필요, False면 하나만 있어도 됨

    Returns:
        PermissionChecker 인스턴스
    """
    return PermissionChecker(list(permissions), require_all)


# 자주 사용되는 역할 조합 상수
ADMIN_ROLES = [UserRole.MASTER]
PAID_ROLES = [UserRole.MASTER, UserRole.BIDDER, UserRole.PREMIUM]
AUTHENTICATED_ROLES = [UserRole.MASTER, UserRole.BIDDER, UserRole.PREMIUM, UserRole.FREE]
