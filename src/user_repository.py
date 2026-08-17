"""Repository layer for user management, role assignments, and authentication data in MySQL (Part 6)."""

from typing import List, Optional, Tuple
from mysql.connector import Error as MySQLError

from src.database import DatabaseManager
from src.models import User
from src.utils import get_logger

logger = get_logger()


class UserRepository:
    """Repository managing user accounts, permissions, password updates, and status toggles."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager or DatabaseManager()

    def create_user(self, user: User) -> Tuple[bool, Optional[int], Optional[str]]:
        """Insert a new user account into the MySQL database."""
        if not user.username or not user.email or not user.password_hash:
            return False, None, "Username, email, and password hash are required."

        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            # Check if username or email already exists
            cursor.execute(
                "SELECT username, email FROM users WHERE username = %s OR email = %s LIMIT 1;",
                (user.username.strip(), user.email.strip().lower()),
            )
            existing = cursor.fetchone()
            if existing:
                if existing[0].lower() == user.username.strip().lower():
                    return False, None, "Username is already registered."
                return False, None, "Email is already registered."

            sql = """
            INSERT INTO users (username, email, password_hash, role, is_active)
            VALUES (%s, %s, %s, %s, %s);
            """
            params = (
                user.username.strip(),
                user.email.strip().lower(),
                user.password_hash,
                user.role.upper(),
                user.is_active,
            )
            cursor.execute(sql, params)
            user_id = cursor.lastrowid
            conn.commit()

            logger.info(f"User account `{user.username}` created with ID {user_id} (Role: {user.role}).")
            return True, user_id, None

        except MySQLError as e:
            if conn:
                conn.rollback()
            if e.errno == 1062:
                return False, None, "Username or email is already registered."
            err_msg = f"Database error creating user: {e.msg}"
            logger.error(err_msg)
            return False, None, err_msg
        except Exception as e:
            if conn:
                conn.rollback()
            err_msg = f"Failed to create user: {str(e)}"
            logger.error(err_msg)
            return False, None, err_msg
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Fetch user by primary key ID."""
        return self._fetch_user_by_field("id", user_id)

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Fetch user by unique username."""
        return self._fetch_user_by_field("username", username.strip())

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Fetch user by unique email address."""
        return self._fetch_user_by_field("email", email.strip().lower())

    def get_user_by_username_or_email(self, identifier: str) -> Optional[User]:
        """Fetch user by either username or email address."""
        if not identifier:
            return None

        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor(dictionary=True)

            ident = identifier.strip()
            sql = """
            SELECT id, username, email, password_hash, role, is_active,
                   created_at, updated_at, last_login
            FROM users
            WHERE username = %s OR email = %s
            LIMIT 1;
            """
            cursor.execute(sql, (ident, ident.lower()))
            row = cursor.fetchone()
            if not row:
                return None

            return User(
                id=row["id"],
                username=row["username"],
                email=row["email"],
                password_hash=row["password_hash"],
                role=row["role"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                last_login=row["last_login"],
            )

        except Exception as e:
            logger.error(f"Error fetching user by identifier `{identifier}`: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _fetch_user_by_field(self, field_name: str, value: any) -> Optional[User]:
        """Internal helper to retrieve a single user record by a specific column."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor(dictionary=True)

            sql = f"""
            SELECT id, username, email, password_hash, role, is_active,
                   created_at, updated_at, last_login
            FROM users
            WHERE {field_name} = %s
            LIMIT 1;
            """
            cursor.execute(sql, (value,))
            row = cursor.fetchone()
            if not row:
                return None

            return User(
                id=row["id"],
                username=row["username"],
                email=row["email"],
                password_hash=row["password_hash"],
                role=row["role"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                last_login=row["last_login"],
            )
        except Exception as e:
            logger.error(f"Error fetching user by {field_name}={value}: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_password(self, user_id: int, new_password_hash: str) -> Tuple[bool, Optional[str]]:
        """Update password hash for a user."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
                (new_password_hash, user_id),
            )
            conn.commit()
            logger.info(f"Password updated for user ID {user_id}.")
            return True, None
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to update password for user {user_id}: {e}")
            return False, str(e)
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_last_login(self, user_id: int):
        """Update last_login timestamp on successful authentication."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s;",
                (user_id,),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to update last_login for user {user_id}: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def count_active_admins(self) -> int:
        """Return the number of active administrator accounts in the database."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN' AND is_active = TRUE;")
            res = cursor.fetchone()
            return res[0] if res else 0
        except Exception as e:
            logger.error(f"Error counting active admins: {e}")
            return 0
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def has_any_admin(self) -> bool:
        """Check whether any active administrator account exists."""
        return self.count_active_admins() > 0

    def set_user_active_status(self, user_id: int, is_active: bool) -> Tuple[bool, Optional[str]]:
        """Activate or deactivate a user account with Last-Admin protection."""
        target_user = self.get_user_by_id(user_id)
        if not target_user:
            return False, "User not found."

        # Last-Admin protection guard: do not deactivate the last active admin
        if not is_active and target_user.is_admin and target_user.is_active:
            if self.count_active_admins() <= 1:
                return False, "Cannot deactivate the last active administrator."

        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_active = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
                (is_active, user_id),
            )
            conn.commit()
            logger.info(f"User {user_id} active status set to {is_active}.")
            return True, None
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error setting user active status: {e}")
            return False, str(e)
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def set_user_role(self, user_id: int, new_role: str) -> Tuple[bool, Optional[str]]:
        """Update a user's role (USER or ADMIN) with Last-Admin protection."""
        role_upper = new_role.upper()
        if role_upper not in ("USER", "ADMIN"):
            return False, "Invalid role specified."

        target_user = self.get_user_by_id(user_id)
        if not target_user:
            return False, "User not found."

        # Last-Admin protection guard: do not demote the last active admin
        if target_user.is_admin and role_upper != "ADMIN" and target_user.is_active:
            if self.count_active_admins() <= 1:
                return False, "Cannot remove the last active administrator."

        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET role = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
                (role_upper, user_id),
            )
            conn.commit()
            logger.info(f"User {user_id} role updated to {role_upper}.")
            return True, None
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error updating user role: {e}")
            return False, str(e)
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def list_users(
        self,
        search_term: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[User], int]:
        """Search and list users with pagination."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor(dictionary=True)

            where_clause = ""
            params = []

            if search_term and search_term.strip():
                term = f"%{search_term.strip()}%"
                where_clause = "WHERE username LIKE %s OR email LIKE %s OR role LIKE %s"
                params = [term, term, term]

            count_sql = f"SELECT COUNT(*) as total FROM users {where_clause};"
            cursor.execute(count_sql, tuple(params))
            total_count = cursor.fetchone()["total"]

            offset = max(0, (page - 1) * page_size)
            query_sql = f"""
            SELECT id, username, email, password_hash, role, is_active,
                   created_at, updated_at, last_login
            FROM users
            {where_clause}
            ORDER BY id ASC
            LIMIT %s OFFSET %s;
            """
            cursor.execute(query_sql, tuple(params + [page_size, offset]))
            rows = cursor.fetchall()

            users = [
                User(
                    id=r["id"],
                    username=r["username"],
                    email=r["email"],
                    password_hash=r["password_hash"],
                    role=r["role"],
                    is_active=bool(r["is_active"]),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    last_login=r["last_login"],
                )
                for r in rows
            ]
            return users, total_count

        except Exception as e:
            logger.error(f"Error listing users: {e}")
            return [], 0
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
