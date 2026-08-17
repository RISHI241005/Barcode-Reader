"""Repository layer for audit logs and security event tracking in MySQL (Part 6)."""

from typing import List, Optional, Tuple
from src.database import DatabaseManager
from src.models import AuditLog
from src.utils import get_logger

logger = get_logger()


class AuditRepository:
    """Repository handling logging and retrieval of administrative and security events."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager or DatabaseManager()

    def log_action(
        self,
        action: str,
        user_id: Optional[int] = None,
        username: Optional[str] = "system",
        description: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
    ) -> bool:
        """Record an administrative or security audit event in MySQL."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            sql = """
            INSERT INTO audit_logs (user_id, username, action, target_type, target_id, description)
            VALUES (%s, %s, %s, %s, %s, %s);
            """
            cursor.execute(
                sql,
                (
                    user_id,
                    username or "system",
                    action.upper(),
                    target_type,
                    str(target_id) if target_id is not None else None,
                    description,
                ),
            )
            conn.commit()
            logger.info(f"Audit event logged: {action} by {username} ({description})")
            return True
        except Exception as e:
            logger.error(f"Failed to record audit log: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_audit_logs(
        self,
        page: int = 1,
        page_size: int = 50,
        action_filter: Optional[str] = None,
    ) -> Tuple[List[AuditLog], int]:
        """Fetch audit log entries with pagination and optional action filtering."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor(dictionary=True)

            where_clause = ""
            params = []

            if action_filter and action_filter.strip() and action_filter.upper() != "ALL":
                where_clause = "WHERE action = %s"
                params = [action_filter.strip().upper()]

            count_sql = f"SELECT COUNT(*) as total FROM audit_logs {where_clause};"
            cursor.execute(count_sql, tuple(params))
            total_count = cursor.fetchone()["total"]

            offset = max(0, (page - 1) * page_size)
            query_sql = f"""
            SELECT id, user_id, username, action, target_type, target_id, description, created_at
            FROM audit_logs
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s;
            """
            cursor.execute(query_sql, tuple(params + [page_size, offset]))
            rows = cursor.fetchall()

            logs = [
                AuditLog(
                    id=r["id"],
                    user_id=r["user_id"],
                    username=r["username"],
                    action=r["action"],
                    target_type=r["target_type"],
                    target_id=r["target_id"],
                    description=r["description"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]
            return logs, total_count

        except Exception as e:
            logger.error(f"Error retrieving audit logs: {e}")
            return [], 0
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
