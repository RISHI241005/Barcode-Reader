"""Centralized permission and authorization service for Role-Based Access Control (RBAC) (Part 6)."""

from enum import Enum
from typing import Optional, Set

from src.models import User
from src.utils import get_logger

logger = get_logger()


class Permission(str, Enum):
    """Enumeration of granular system permissions."""

    SCAN_BARCODE = "SCAN_BARCODE"
    SAVE_SCAN = "SAVE_SCAN"
    VIEW_OWN_HISTORY = "VIEW_OWN_HISTORY"
    VIEW_ALL_HISTORY = "VIEW_ALL_HISTORY"
    DELETE_OWN_SCAN = "DELETE_OWN_SCAN"
    DELETE_ANY_SCAN = "DELETE_ANY_SCAN"
    EXPORT_OWN_SCANS = "EXPORT_OWN_SCANS"
    EXPORT_ALL_SCANS = "EXPORT_ALL_SCANS"
    LOOKUP_PRODUCT = "LOOKUP_PRODUCT"
    VIEW_PRODUCTS = "VIEW_PRODUCTS"
    MANAGE_PRODUCT_CACHE = "MANAGE_PRODUCT_CACHE"
    VIEW_PERSONAL_ANALYTICS = "VIEW_PERSONAL_ANALYTICS"
    VIEW_SYSTEM_ANALYTICS = "VIEW_SYSTEM_ANALYTICS"
    MANAGE_USERS = "MANAGE_USERS"
    VIEW_AUDIT_LOGS = "VIEW_AUDIT_LOGS"
    CHANGE_OWN_PASSWORD = "CHANGE_OWN_PASSWORD"
    ACCESS_ADMIN_PANEL = "ACCESS_ADMIN_PANEL"


# Explicit Role-to-Permissions Mapping
ROLE_PERMISSIONS = {
    "USER": {
        Permission.SCAN_BARCODE,
        Permission.SAVE_SCAN,
        Permission.VIEW_OWN_HISTORY,
        Permission.DELETE_OWN_SCAN,
        Permission.EXPORT_OWN_SCANS,
        Permission.LOOKUP_PRODUCT,
        Permission.VIEW_PRODUCTS,
        Permission.VIEW_PERSONAL_ANALYTICS,
        Permission.CHANGE_OWN_PASSWORD,
    },
    "ADMIN": {
        Permission.SCAN_BARCODE,
        Permission.SAVE_SCAN,
        Permission.VIEW_OWN_HISTORY,
        Permission.VIEW_ALL_HISTORY,
        Permission.DELETE_OWN_SCAN,
        Permission.DELETE_ANY_SCAN,
        Permission.EXPORT_OWN_SCANS,
        Permission.EXPORT_ALL_SCANS,
        Permission.LOOKUP_PRODUCT,
        Permission.VIEW_PRODUCTS,
        Permission.MANAGE_PRODUCT_CACHE,
        Permission.VIEW_PERSONAL_ANALYTICS,
        Permission.VIEW_SYSTEM_ANALYTICS,
        Permission.MANAGE_USERS,
        Permission.VIEW_AUDIT_LOGS,
        Permission.CHANGE_OWN_PASSWORD,
        Permission.ACCESS_ADMIN_PANEL,
    },
}


class AuthorizationService:
    """Evaluates granular permissions based on user role and state."""

    @staticmethod
    def get_permissions_for_role(role: str) -> Set[Permission]:
        """Return the set of allowed permissions for a role."""
        return ROLE_PERMISSIONS.get(role.upper(), set())

    @staticmethod
    def has_permission(user: Optional[User], permission: Permission) -> bool:
        """Check whether a user is active and possesses the requested permission."""
        if not user or not user.is_active:
            return False

        user_perms = ROLE_PERMISSIONS.get(user.role.upper(), set())
        has_perm = permission in user_perms
        if not has_perm:
            logger.warning(
                f"Authorization denied: User `{user.username}` (Role: {user.role}) "
                f"lacks permission `{permission.value}`."
            )
        return has_perm

    @staticmethod
    def can_modify_scan(user: Optional[User], scan_user_id: Optional[int]) -> bool:
        """Determine whether user has permission to delete or modify a specific scan record."""
        if not user or not user.is_active:
            return False

        # Admin can modify any scan
        if user.is_admin:
            return True

        # Normal user can only modify own scans
        return scan_user_id is not None and user.id == scan_user_id
