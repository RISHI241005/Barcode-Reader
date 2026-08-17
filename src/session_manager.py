"""In-memory active user session management with configurable inactivity timeout (Part 6)."""

import os
import time
from typing import Optional

from src.models import User
from src.utils import get_logger

logger = get_logger()

DEFAULT_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))


class SessionManager:
    """Manages the authenticated user session, activity timestamps, and inactivity expiration."""

    def __init__(self, timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES):
        self.timeout_seconds = max(60, timeout_minutes * 60)
        self.current_user: Optional[User] = None
        self.login_time: float = 0.0
        self.last_activity_time: float = 0.0

    def create_session(self, user: User):
        """Initialize an active session for the authenticated user without storing sensitive secrets."""
        self.current_user = user
        now = time.time()
        self.login_time = now
        self.last_activity_time = now
        logger.info(f"Active session created for user `{user.username}` (ID: {user.id}, Role: {user.role}).")

    def touch(self):
        """Update last activity timestamp to prevent premature inactivity expiration."""
        if self.current_user:
            self.last_activity_time = time.time()

    def is_expired(self) -> bool:
        """Check if session has exceeded the inactivity timeout limit."""
        if not self.current_user:
            return False
        elapsed = time.time() - self.last_activity_time
        return elapsed > self.timeout_seconds

    def is_authenticated(self) -> bool:
        """Check if a valid, unexpired user session exists."""
        if not self.current_user:
            return False
        if self.is_expired():
            logger.info(f"Session for `{self.current_user.username}` expired due to inactivity.")
            self.clear_session()
            return False
        return True

    def clear_session(self):
        """Terminate active session and clear user reference."""
        if self.current_user:
            logger.info(f"Session terminated for user `{self.current_user.username}`.")
        self.current_user = None
        self.login_time = 0.0
        self.last_activity_time = 0.0

    @property
    def user_id(self) -> Optional[int]:
        """Return active user ID."""
        return self.current_user.id if self.current_user else None

    @property
    def username(self) -> Optional[str]:
        """Return active username."""
        return self.current_user.username if self.current_user else None

    @property
    def is_admin(self) -> bool:
        """Return whether active user has admin privileges."""
        return self.current_user.is_admin if self.current_user else False
