"""Repository layer for scan analytics, aggregations, and dashboard metrics with user & system scoping (Part 6)."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from mysql.connector import Error as MySQLError

from src.database import DatabaseManager
from src.utils import get_logger

logger = get_logger()


class AnalyticsRepository:
    """Repository executing aggregated SQL analytics queries with user-level and system-level scoping."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager or DatabaseManager()

    def _build_where_clause(
        self, date_range: Optional[str] = "All", user_id: Optional[int] = None
    ) -> Tuple[str, List[Any]]:
        """Construct parameterized SQL WHERE clause for time interval and optional user scoping."""
        clauses = []
        params = []

        if user_id is not None:
            clauses.append("user_id = %s")
            params.append(user_id)

        if date_range and date_range.strip().lower() not in ("all", "all time"):
            dr = date_range.strip().lower()
            if dr == "today":
                clauses.append("scan_date >= CURDATE()")
            elif dr == "yesterday":
                clauses.append("scan_date >= DATE_SUB(CURDATE(), INTERVAL 1 DAY) AND scan_date < CURDATE()")
            elif dr in ("last 7 days", "7 days", "7d"):
                clauses.append("scan_date >= DATE_SUB(NOW(), INTERVAL 7 DAY)")
            elif dr in ("last 30 days", "30 days", "30d"):
                clauses.append("scan_date >= DATE_SUB(NOW(), INTERVAL 30 DAY)")
            elif dr in ("this month", "month"):
                clauses.append("scan_date >= DATE_FORMAT(NOW(), '%Y-%m-01')")

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return where_sql, params

    def get_summary_metrics(
        self, date_range: Optional[str] = "All", user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Fetch summary KPI metrics (scoped to a single user or system-wide for admin)."""
        conn = None
        cursor = None
        metrics = {
            "total_scans": 0,
            "unique_barcodes": 0,
            "total_products": 0,
            "today_scans": 0,
            "total_users": 0,
            "active_users": 0,
            "lookup_rate": 0.0,
        }

        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor(dictionary=True)

            where_clause, params = self._build_where_clause(date_range, user_id)

            # 1. Total Scans & Unique Barcodes for date range and user scope
            scan_query = f"""
            SELECT 
                COUNT(*) as total_scans,
                COUNT(DISTINCT barcode_data) as unique_barcodes
            FROM barcode_scans
            {where_clause};
            """
            cursor.execute(scan_query, tuple(params))
            res = cursor.fetchone()
            if res:
                metrics["total_scans"] = res["total_scans"] or 0
                metrics["unique_barcodes"] = res["unique_barcodes"] or 0

            # 2. Today's scans count (scoped)
            today_where, today_params = self._build_where_clause("today", user_id)
            today_query = f"SELECT COUNT(*) as today_count FROM barcode_scans {today_where};"
            cursor.execute(today_query, tuple(today_params))
            today_res = cursor.fetchone()
            if today_res:
                metrics["today_scans"] = today_res["today_count"] or 0

            # 3. Total cached products
            prod_query = "SELECT COUNT(*) as prod_count FROM products;"
            cursor.execute(prod_query)
            prod_res = cursor.fetchone()
            if prod_res:
                metrics["total_products"] = prod_res["prod_count"] or 0

            # 4. Total and active users (for system dashboard)
            if user_id is None:
                user_query = """
                SELECT 
                    COUNT(*) as total_users,
                    SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) as active_users
                FROM users;
                """
                cursor.execute(user_query)
                u_res = cursor.fetchone()
                if u_res:
                    metrics["total_users"] = u_res["total_users"] or 0
                    metrics["active_users"] = u_res["active_users"] or 0

            # 5. Coverage rate
            if metrics["unique_barcodes"] > 0:
                rate = (metrics["total_products"] / metrics["unique_barcodes"]) * 100.0
                metrics["lookup_rate"] = min(100.0, round(rate, 1))

            return metrics

        except MySQLError as e:
            logger.error(f"Database error querying summary analytics: {e.msg}")
            return metrics
        except Exception as e:
            logger.error(f"Error querying summary analytics: {e}")
            return metrics
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_barcode_type_distribution(
        self,
        date_range: Optional[str] = "All",
        user_id: Optional[int] = None,
        limit: int = 8,
    ) -> List[Tuple[str, int]]:
        """Return list of (barcode_type, scan_count) pairs ordered by count descending."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            where_clause, params = self._build_where_clause(date_range, user_id)
            sql = f"""
            SELECT barcode_type, COUNT(*) as cnt
            FROM barcode_scans
            {where_clause}
            GROUP BY barcode_type
            ORDER BY cnt DESC
            LIMIT %s;
            """
            cursor.execute(sql, tuple(params + [limit]))
            rows = cursor.fetchall()
            return [(r[0], int(r[1])) for r in rows]

        except Exception as e:
            logger.error(f"Error fetching barcode type distribution: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_source_distribution(
        self, date_range: Optional[str] = "All", user_id: Optional[int] = None
    ) -> Dict[str, int]:
        """Return scan count broken down by source (Camera vs Image)."""
        conn = None
        cursor = None
        dist = {"camera": 0, "image": 0}
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            where_clause, params = self._build_where_clause(date_range, user_id)
            sql = f"""
            SELECT COALESCE(source, 'image') as src, COUNT(*) as cnt
            FROM barcode_scans
            {where_clause}
            GROUP BY src;
            """
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            for src_name, cnt in rows:
                key = str(src_name).strip().lower()
                dist[key] = dist.get(key, 0) + int(cnt)

            return dist

        except Exception as e:
            logger.error(f"Error fetching source distribution: {e}")
            return dist
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_daily_scan_counts(
        self, days: int = 7, user_id: Optional[int] = None
    ) -> List[Tuple[str, int]]:
        """Return daily scan counts for the past N days."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            user_filter = "AND user_id = %s" if user_id is not None else ""
            params = [days, user_id] if user_id is not None else [days]

            sql = f"""
            SELECT DATE_FORMAT(scan_date, '%m-%d') as day_label, COUNT(*) as cnt
            FROM barcode_scans
            WHERE scan_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY) {user_filter}
            GROUP BY day_label
            ORDER BY MIN(scan_date) ASC;
            """
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            return [(r[0], int(r[1])) for r in rows]

        except Exception as e:
            logger.error(f"Error fetching daily scan counts: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_top_barcodes(
        self,
        limit: int = 5,
        date_range: Optional[str] = "All",
        user_id: Optional[int] = None,
    ) -> List[Tuple[str, str, int]]:
        """Return most frequently scanned barcodes."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            where_clause, params = self._build_where_clause(date_range, user_id)
            sql = f"""
            SELECT barcode_data, barcode_type, COUNT(*) as cnt
            FROM barcode_scans
            {where_clause}
            GROUP BY barcode_data, barcode_type
            ORDER BY cnt DESC
            LIMIT %s;
            """
            cursor.execute(sql, tuple(params + [limit]))
            rows = cursor.fetchall()
            return [(r[0], r[1], int(r[2])) for r in rows]

        except Exception as e:
            logger.error(f"Error fetching top barcodes: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
