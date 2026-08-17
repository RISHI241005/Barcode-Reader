"""Repository layer for barcode scan CRUD operations, filtering, pagination, and export (Part 6 with User Scoping)."""

import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import List, Optional, Tuple
from mysql.connector import Error as MySQLError

from src.database import DatabaseManager
from src.models import ScanRecord, User
from src.utils import get_logger

logger = get_logger()


class ScanRepository:
    """Repository handling all database operations for barcode scan records with user-level data isolation."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager or DatabaseManager()

    def save_scan(self, scan: ScanRecord) -> Tuple[bool, Optional[int], Optional[str]]:
        """Insert a single scan record associated with a user ID with duplicate click prevention."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            # Prevent duplicate insertion if the same barcode was saved for the same user within 5 seconds
            check_dup_sql = """
            SELECT id FROM barcode_scans 
            WHERE barcode_type = %s 
              AND barcode_data = %s 
              AND (image_name = %s OR (image_name IS NULL AND %s IS NULL))
              AND (user_id = %s OR (user_id IS NULL AND %s IS NULL))
              AND scan_date >= DATE_SUB(NOW(), INTERVAL 5 SECOND)
            LIMIT 1;
            """
            cursor.execute(
                check_dup_sql,
                (
                    scan.barcode_type,
                    scan.barcode_data,
                    scan.image_name,
                    scan.image_name,
                    scan.user_id,
                    scan.user_id,
                ),
            )
            existing = cursor.fetchone()
            if existing:
                logger.info(f"Duplicate scan save skipped for record ID {existing[0]}")
                return True, existing[0], "Already saved."

            insert_sql = """
            INSERT INTO barcode_scans (
                barcode_type, barcode_data, image_name, validation_status,
                x_position, y_position, width, height,
                processing_method, processing_time_ms, source, user_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            params = (
                scan.barcode_type,
                scan.barcode_data,
                scan.image_name,
                scan.validation_status,
                scan.x_position,
                scan.y_position,
                scan.width,
                scan.height,
                scan.processing_method,
                scan.processing_time_ms,
                scan.source or "image",
                scan.user_id,
            )
            cursor.execute(insert_sql, params)
            inserted_id = cursor.lastrowid
            conn.commit()

            logger.info(
                f"Scan record #{inserted_id} ({scan.barcode_type}, source={scan.source}, user_id={scan.user_id}) saved successfully."
            )
            return True, inserted_id, None

        except MySQLError as e:
            if conn:
                conn.rollback()
            err_msg = f"Database error saving scan: {e.msg}"
            logger.error(err_msg)
            return False, None, err_msg
        except Exception as e:
            if conn:
                conn.rollback()
            err_msg = f"Failed to save scan: {str(e)}"
            logger.error(err_msg)
            return False, None, err_msg
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def save_scans(self, scans: List[ScanRecord]) -> Tuple[bool, int, Optional[str]]:
        """Atomically insert multiple scan records with user scoping within a single transaction."""
        if not scans:
            return True, 0, None

        conn = None
        cursor = None
        saved_count = 0
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            insert_sql = """
            INSERT INTO barcode_scans (
                barcode_type, barcode_data, image_name, validation_status,
                x_position, y_position, width, height,
                processing_method, processing_time_ms, source, user_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """

            for scan in scans:
                # Check recent duplicate within transaction
                check_dup_sql = """
                SELECT id FROM barcode_scans 
                WHERE barcode_type = %s 
                  AND barcode_data = %s 
                  AND (image_name = %s OR (image_name IS NULL AND %s IS NULL))
                  AND (user_id = %s OR (user_id IS NULL AND %s IS NULL))
                  AND scan_date >= DATE_SUB(NOW(), INTERVAL 5 SECOND)
                LIMIT 1;
                """
                cursor.execute(
                    check_dup_sql,
                    (
                        scan.barcode_type,
                        scan.barcode_data,
                        scan.image_name,
                        scan.image_name,
                        scan.user_id,
                        scan.user_id,
                    ),
                )
                if cursor.fetchone():
                    continue

                params = (
                    scan.barcode_type,
                    scan.barcode_data,
                    scan.image_name,
                    scan.validation_status,
                    scan.x_position,
                    scan.y_position,
                    scan.width,
                    scan.height,
                    scan.processing_method,
                    scan.processing_time_ms,
                    scan.source or "image",
                    scan.user_id,
                )
                cursor.execute(insert_sql, params)
                saved_count += 1

            conn.commit()
            logger.info(f"Batch saved {saved_count} scan records.")
            return True, saved_count, None

        except MySQLError as e:
            if conn:
                conn.rollback()
            err_msg = f"Database error in batch save: {e.msg}"
            logger.error(err_msg)
            return False, 0, err_msg
        except Exception as e:
            if conn:
                conn.rollback()
            err_msg = f"Batch save error: {str(e)}"
            logger.error(err_msg)
            return False, 0, err_msg
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_scans(
        self,
        page: int = 1,
        page_size: int = 50,
        search_term: Optional[str] = None,
        barcode_type: Optional[str] = None,
        date_filter: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Tuple[List[ScanRecord], int]:
        """Fetch paginated, filtered scan records with optional user scoping."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor(dictionary=True)

            where_clauses = []
            params = []

            # 1. User isolation filter
            if user_id is not None:
                where_clauses.append("s.user_id = %s")
                params.append(user_id)

            # 2. Search term filter (partial matching on data, type, or image_name)
            if search_term and search_term.strip():
                term = f"%{search_term.strip()}%"
                where_clauses.append(
                    "(s.barcode_data LIKE %s OR s.barcode_type LIKE %s OR s.image_name LIKE %s)"
                )
                params.extend([term, term, term])

            # 3. Barcode type filter
            if barcode_type and barcode_type.strip() and barcode_type.strip().lower() != "all":
                where_clauses.append("s.barcode_type = %s")
                params.append(barcode_type.strip())

            # 4. Date range filter
            if date_filter and date_filter.strip().lower() != "all":
                df = date_filter.strip().lower()
                if df == "today":
                    where_clauses.append("s.scan_date >= CURDATE()")
                elif df == "yesterday":
                    where_clauses.append(
                        "s.scan_date >= DATE_SUB(CURDATE(), INTERVAL 1 DAY) AND s.scan_date < CURDATE()"
                    )
                elif df in ("last 7 days", "7 days"):
                    where_clauses.append("s.scan_date >= DATE_SUB(NOW(), INTERVAL 7 DAY)")
                elif df in ("last 30 days", "30 days"):
                    where_clauses.append("s.scan_date >= DATE_SUB(NOW(), INTERVAL 30 DAY)")

            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            # Count total matching records
            count_sql = f"SELECT COUNT(*) as total FROM barcode_scans s {where_sql};"
            cursor.execute(count_sql, tuple(params))
            count_res = cursor.fetchone()
            total_count = count_res["total"] if count_res else 0

            # Query paginated rows (left join users to populate username)
            offset = max(0, (page - 1) * page_size)
            query_sql = f"""
            SELECT s.id, s.barcode_type, s.barcode_data, s.image_name, s.scan_date,
                   s.validation_status, s.x_position, s.y_position, s.width, s.height,
                   s.processing_method, s.processing_time_ms, s.source, s.user_id,
                   u.username
            FROM barcode_scans s
            LEFT JOIN users u ON s.user_id = u.id
            {where_sql}
            ORDER BY s.scan_date DESC, s.id DESC
            LIMIT %s OFFSET %s;
            """
            query_params = list(params) + [page_size, offset]
            cursor.execute(query_sql, tuple(query_params))
            rows = cursor.fetchall()

            records = [
                ScanRecord(
                    id=row["id"],
                    barcode_type=row["barcode_type"],
                    barcode_data=row["barcode_data"],
                    image_name=row["image_name"],
                    scan_date=row["scan_date"],
                    validation_status=row["validation_status"] or "Not Available",
                    x_position=row["x_position"] or 0,
                    y_position=row["y_position"] or 0,
                    width=row["width"] or 0,
                    height=row["height"] or 0,
                    processing_method=row["processing_method"] or "Original Image",
                    processing_time_ms=row["processing_time_ms"] or 0.0,
                    source=row.get("source") or "image",
                    user_id=row.get("user_id"),
                    username=row.get("username") or ("Anonymous" if row.get("user_id") is None else "User"),
                )
                for row in rows
            ]

            return records, total_count

        except MySQLError as e:
            logger.error(f"Database error fetching scans: {e.msg}")
            return [], 0
        except Exception as e:
            logger.error(f"Error fetching scans: {e}")
            return [], 0
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def delete_scan(self, scan_id: int, current_user: Optional[User] = None) -> Tuple[bool, Optional[str]]:
        """Delete a single scan record with database-level ownership authorization check."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            # If user is admin, allow deleting any scan; otherwise restrict to user's own scans
            if current_user and current_user.is_admin:
                cursor.execute("DELETE FROM barcode_scans WHERE id = %s;", (scan_id,))
            elif current_user:
                cursor.execute(
                    "DELETE FROM barcode_scans WHERE id = %s AND user_id = %s;",
                    (scan_id, current_user.id),
                )
            else:
                cursor.execute("DELETE FROM barcode_scans WHERE id = %s;", (scan_id,))

            if cursor.rowcount == 0:
                conn.rollback()
                return False, "Scan record not found or unauthorized deletion attempt."

            conn.commit()
            logger.info(f"Deleted scan record #{scan_id}")
            return True, None
        except MySQLError as e:
            if conn:
                conn.rollback()
            err_msg = f"Database error deleting scan #{scan_id}: {e.msg}"
            logger.error(err_msg)
            return False, err_msg
        except Exception as e:
            if conn:
                conn.rollback()
            err_msg = f"Failed to delete scan: {str(e)}"
            logger.error(err_msg)
            return False, err_msg
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def delete_all_scans(self, current_user: Optional[User] = None) -> Tuple[bool, Optional[str]]:
        """Delete scans with role-aware scoping (admin clears all, normal user clears own)."""
        conn = None
        cursor = None
        try:
            conn = self.db_manager.get_connection(include_database=True)
            cursor = conn.cursor()

            if current_user and not current_user.is_admin:
                cursor.execute("DELETE FROM barcode_scans WHERE user_id = %s;", (current_user.id,))
            else:
                cursor.execute("DELETE FROM barcode_scans;")

            conn.commit()
            logger.warning("Scan records cleared by user action.")
            return True, None
        except MySQLError as e:
            if conn:
                conn.rollback()
            err_msg = f"Database error clearing scans: {e.msg}"
            logger.error(err_msg)
            return False, err_msg
        except Exception as e:
            if conn:
                conn.rollback()
            err_msg = f"Failed to clear scans: {str(e)}"
            logger.error(err_msg)
            return False, err_msg
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def export_scans_to_file(
        self,
        output_file_path: Path,
        search_term: Optional[str] = None,
        barcode_type: Optional[str] = None,
        date_filter: Optional[str] = None,
        export_format: str = "csv",
        user_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Export filtered scan records with user-level authorization scoping."""
        try:
            records, total = self.get_scans(
                page=1,
                page_size=100000,
                search_term=search_term,
                barcode_type=barcode_type,
                date_filter=date_filter,
                user_id=user_id,
            )

            if not records:
                return False, "No matching records to export."

            output_path = Path(output_file_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if export_format.lower() == "json":
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump([r.to_dict() for r in records], f, indent=2, ensure_ascii=False)
            else:
                fieldnames = [
                    "id",
                    "barcode_type",
                    "barcode_data",
                    "source",
                    "user_id",
                    "username",
                    "image_name",
                    "scan_date",
                    "validation_status",
                    "x_position",
                    "y_position",
                    "width",
                    "height",
                    "processing_method",
                    "processing_time_ms",
                ]
                with open(output_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    for r in records:
                        writer.writerow(r.to_dict())

            logger.info(f"Exported {len(records)} records to {output_path}")
            return True, f"Successfully exported {len(records)} record(s) to {output_path.name}"

        except Exception as e:
            err_msg = f"Export failed: {str(e)}"
            logger.error(err_msg)
            return False, err_msg
