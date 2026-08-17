"""Unit tests for RBAC AuthorizationService and permission matrix (Part 6)."""

import pytest

from src.models import User
from src.authorization_service import AuthorizationService, Permission


def test_normal_user_permissions():
    """Test 1: Normal USER possesses personal scanning permissions and lacks admin permissions."""
    normal_user = User(id=1, username="regular_user", email="user@example.com", password_hash="h", role="USER", is_active=True)

    # Allowed for normal user
    assert AuthorizationService.has_permission(normal_user, Permission.SCAN_BARCODE) is True
    assert AuthorizationService.has_permission(normal_user, Permission.SAVE_SCAN) is True
    assert AuthorizationService.has_permission(normal_user, Permission.VIEW_OWN_HISTORY) is True
    assert AuthorizationService.has_permission(normal_user, Permission.DELETE_OWN_SCAN) is True
    assert AuthorizationService.has_permission(normal_user, Permission.LOOKUP_PRODUCT) is True
    assert AuthorizationService.has_permission(normal_user, Permission.VIEW_PERSONAL_ANALYTICS) is True

    # Forbidden for normal user
    assert AuthorizationService.has_permission(normal_user, Permission.ACCESS_ADMIN_PANEL) is False
    assert AuthorizationService.has_permission(normal_user, Permission.VIEW_ALL_HISTORY) is False
    assert AuthorizationService.has_permission(normal_user, Permission.DELETE_ANY_SCAN) is False
    assert AuthorizationService.has_permission(normal_user, Permission.MANAGE_USERS) is False
    assert AuthorizationService.has_permission(normal_user, Permission.VIEW_SYSTEM_ANALYTICS) is False
    assert AuthorizationService.has_permission(normal_user, Permission.VIEW_AUDIT_LOGS) is False


def test_admin_user_permissions():
    """Test 2: ADMIN possesses full administrative and scanning permissions."""
    admin_user = User(id=2, username="super_admin", email="admin@example.com", password_hash="h", role="ADMIN", is_active=True)

    assert AuthorizationService.has_permission(admin_user, Permission.SCAN_BARCODE) is True
    assert AuthorizationService.has_permission(admin_user, Permission.ACCESS_ADMIN_PANEL) is True
    assert AuthorizationService.has_permission(admin_user, Permission.VIEW_ALL_HISTORY) is True
    assert AuthorizationService.has_permission(admin_user, Permission.DELETE_ANY_SCAN) is True
    assert AuthorizationService.has_permission(admin_user, Permission.MANAGE_USERS) is True
    assert AuthorizationService.has_permission(admin_user, Permission.VIEW_SYSTEM_ANALYTICS) is True
    assert AuthorizationService.has_permission(admin_user, Permission.VIEW_AUDIT_LOGS) is True


def test_inactive_user_has_no_permissions():
    """Test 3: Deactivated user has all permissions revoked."""
    inactive_admin = User(id=3, username="banned_admin", email="banned@example.com", password_hash="h", role="ADMIN", is_active=False)

    assert AuthorizationService.has_permission(inactive_admin, Permission.SCAN_BARCODE) is False
    assert AuthorizationService.has_permission(inactive_admin, Permission.ACCESS_ADMIN_PANEL) is False
