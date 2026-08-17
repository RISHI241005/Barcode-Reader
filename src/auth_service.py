"""Authentication service managing user registration, logins, password changes, and audit logging (Part 6)."""

from typing import Optional, Tuple

from src.models import User
from src.user_repository import UserRepository
from src.audit_repository import AuditRepository
from src.session_manager import SessionManager
from src.security import (
    hash_password,
    verify_password,
    validate_username,
    validate_email,
    validate_password,
    check_login_lockout,
    record_failed_login,
    record_successful_login,
)
from src.utils import get_logger

logger = get_logger()


class AuthService:
    """Coordinates authentication flows, credential verification, rate-limiting, and session creation."""

    def __init__(
        self,
        user_repo: Optional[UserRepository] = None,
        session_mgr: Optional[SessionManager] = None,
        audit_repo: Optional[AuditRepository] = None,
    ):
        self.user_repo = user_repo or UserRepository()
        self.session_mgr = session_mgr or SessionManager()
        self.audit_repo = audit_repo or AuditRepository()

    def register(
        self,
        username: str,
        email: str,
        password: str,
        confirm_password: str,
        role: str = "USER",
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """Validate registration input, hash password, and create a new account."""
        # 1. Input validations
        u_ok, u_err = validate_username(username)
        if not u_ok:
            return False, None, u_err

        e_ok, e_err = validate_email(email)
        if not e_ok:
            return False, None, e_err

        p_ok, p_err = validate_password(password)
        if not p_ok:
            return False, None, p_err

        if password != confirm_password:
            return False, None, "Passwords do not match."

        # 2. Hash password securely
        try:
            pwd_hash = hash_password(password)
        except Exception as e:
            logger.error(f"Failed to generate password hash: {e}")
            return False, None, "Password processing error. Please try again."

        # 3. Create User object and save
        new_user = User(
            username=username.strip(),
            email=email.strip().lower(),
            password_hash=pwd_hash,
            role=role.upper(),
            is_active=True,
        )

        ok, user_id, err = self.user_repo.create_user(new_user)
        if not ok:
            return False, None, err

        new_user.id = user_id

        # 4. Audit Log
        action_name = "ADMIN_CREATED" if role.upper() == "ADMIN" else "USER_REGISTERED"
        self.audit_repo.log_action(
            action=action_name,
            user_id=user_id,
            username=new_user.username,
            description=f"Account created with role {new_user.role}",
            target_type="User",
            target_id=str(user_id),
        )

        return True, new_user, None

    def login(self, identifier: str, password: str) -> Tuple[bool, Optional[User], Optional[str]]:
        """Authenticate user by username or email, verify password hash, and initialize session."""
        if not identifier or not password:
            return False, None, "Please enter both username/email and password."

        clean_ident = identifier.strip()

        # 1. Rate-limiting check
        is_locked, lock_msg = check_login_lockout(clean_ident)
        if is_locked:
            logger.warning(f"Login rejected for `{clean_ident}`: Account is temporarily locked out.")
            return False, None, lock_msg

        # 2. Look up user by username or email
        user = self.user_repo.get_user_by_username_or_email(clean_ident)
        if not user:
            record_failed_login(clean_ident)
            self.audit_repo.log_action(
                action="LOGIN_FAILED",
                username=clean_ident,
                description="Unknown user identifier",
                target_type="Auth",
            )
            return False, None, "Invalid username/email or password."

        # 3. Check if account is active
        if not user.is_active:
            logger.warning(f"Login rejected: Account `{user.username}` is deactivated.")
            self.audit_repo.log_action(
                action="LOGIN_REJECTED",
                user_id=user.id,
                username=user.username,
                description="Attempted login on deactivated account",
                target_type="User",
                target_id=str(user.id),
            )
            return False, None, "This account is currently inactive. Please contact an administrator."

        # 4. Verify password hash
        if not verify_password(password, user.password_hash):
            record_failed_login(clean_ident)
            self.audit_repo.log_action(
                action="LOGIN_FAILED",
                user_id=user.id,
                username=user.username,
                description="Incorrect password",
                target_type="Auth",
            )
            return False, None, "Invalid username/email or password."

        # 5. Successful login
        record_successful_login(clean_ident)
        self.user_repo.update_last_login(user.id)
        self.session_mgr.create_session(user)

        self.audit_repo.log_action(
            action="USER_LOGIN",
            user_id=user.id,
            username=user.username,
            description=f"Successful login (Role: {user.role})",
            target_type="Session",
        )

        return True, user, None

    def change_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
        confirm_new_password: str,
    ) -> Tuple[bool, Optional[str]]:
        """Validate current password and update with newly hashed password."""
        if not current_password or not new_password or not confirm_new_password:
            return False, "All password fields are required."

        p_ok, p_err = validate_password(new_password)
        if not p_ok:
            return False, p_err

        if new_password != confirm_new_password:
            return False, "New passwords do not match."

        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            return False, "User account not found."

        if not verify_password(current_password, user.password_hash):
            return False, "Current password is incorrect."

        new_hash = hash_password(new_password)
        ok, err = self.user_repo.update_password(user_id, new_hash)
        if not ok:
            return False, err

        self.audit_repo.log_action(
            action="PASSWORD_CHANGED",
            user_id=user.id,
            username=user.username,
            description="User changed own password",
            target_type="User",
            target_id=str(user.id),
        )

        return True, None

    def logout(self):
        """Terminate the active user session and record audit event."""
        if self.session_mgr.is_authenticated():
            user = self.session_mgr.current_user
            self.audit_repo.log_action(
                action="USER_LOGOUT",
                user_id=user.id if user else None,
                username=user.username if user else "anonymous",
                description="User logged out",
                target_type="Session",
            )
        self.session_mgr.clear_session()
