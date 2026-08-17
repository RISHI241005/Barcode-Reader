"""Modern CustomTkinter desktop interface for Barcode Reader (Part 6 with Authentication, User Management & Security)."""

from datetime import datetime
import os
from pathlib import Path
import queue
import threading
import time
from typing import Optional, List, Dict, Any
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image
import cv2
import numpy as np

from src.models import BarcodeResult, DetectionReport, ImageMetrics, Product, ScanRecord, User, AuditLog
from src.image_processor import ImageProcessor, SUPPORTED_EXTENSIONS
from src.barcode_detector import BarcodeDetector
from src.camera_scanner import CameraScanner, CameraState, detect_available_cameras
from src.database import DatabaseManager
from src.scan_repository import ScanRepository
from src.product_repository import ProductRepository
from src.product_service import ProductService
from src.analytics_repository import AnalyticsRepository
from src.user_repository import UserRepository
from src.audit_repository import AuditRepository
from src.session_manager import SessionManager
from src.auth_service import AuthService
from src.authorization_service import AuthorizationService, Permission
from src.utils import get_logger, copy_to_clipboard

logger = get_logger()

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class ProfileModal(ctk.CTkToplevel):
    """Modal displaying active user profile and password change interface."""

    def __init__(self, parent, current_user: User, auth_service: AuthService):
        super().__init__(parent)
        self.current_user = current_user
        self.auth_service = auth_service
        self.parent_app = parent

        self.title("My Profile & Security — Barcode Reader")
        self.geometry("520x540")
        self.minsize(480, 480)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=20, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        # 1. Profile Title
        ctk.CTkLabel(
            scroll,
            text="👤 User Profile",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        # 2. Profile Info Card
        card = ctk.CTkFrame(scroll, corner_radius=8, fg_color=("gray90", "#27272a"))
        card.pack(fill="x", pady=(0, 16))
        card.grid_columnconfigure((0, 1), weight=1)

        def add_row(p, label, val, row):
            ctk.CTkLabel(
                p,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=("gray40", "#a1a1aa"),
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=14, pady=4)
            ctk.CTkLabel(
                p,
                text=str(val),
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=("gray10", "#f4f4f5"),
                anchor="w",
            ).grid(row=row, column=1, sticky="w", padx=14, pady=4)

        add_row(card, "Username", self.current_user.username, 0)
        add_row(card, "Email", self.current_user.email, 1)
        add_row(card, "Role", self.current_user.role, 2)
        add_row(card, "Account Created", self.current_user.formatted_created_at, 3)
        add_row(card, "Last Login", self.current_user.formatted_last_login, 4)

        # 3. Change Password Card
        ctk.CTkLabel(
            scroll,
            text="🔒 Change Password",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
            anchor="w",
        ).pack(fill="x", pady=(8, 8))

        pwd_card = ctk.CTkFrame(scroll, corner_radius=8, fg_color=("gray90", "#27272a"))
        pwd_card.pack(fill="x", pady=(0, 14))

        self.cur_pwd_entry = ctk.CTkEntry(
            pwd_card,
            placeholder_text="Current Password",
            show="•",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            height=34,
        )
        self.cur_pwd_entry.pack(fill="x", padx=14, pady=(12, 6))

        self.new_pwd_entry = ctk.CTkEntry(
            pwd_card,
            placeholder_text="New Password (min. 6 characters)",
            show="•",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            height=34,
        )
        self.new_pwd_entry.pack(fill="x", padx=14, pady=6)

        self.confirm_pwd_entry = ctk.CTkEntry(
            pwd_card,
            placeholder_text="Confirm New Password",
            show="•",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            height=34,
        )
        self.confirm_pwd_entry.pack(fill="x", padx=14, pady=(6, 12))

        change_btn = ctk.CTkButton(
            pwd_card,
            text="Update Password",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#2563eb",
            height=32,
            command=self._on_change_password_click,
        )
        change_btn.pack(fill="x", padx=14, pady=(0, 12))

        # Close button
        ctk.CTkButton(
            scroll,
            text="Close",
            width=80,
            height=30,
            fg_color=("gray75", "#3f3f46"),
            command=self.destroy,
        ).pack(side="right", pady=4)

    def _on_change_password_click(self):
        cur = self.cur_pwd_entry.get().strip()
        new_p = self.new_pwd_entry.get().strip()
        conf = self.confirm_pwd_entry.get().strip()

        ok, err = self.auth_service.change_password(self.current_user.id, cur, new_p, conf)
        if ok:
            messagebox.showinfo("Success", "Password changed successfully.", parent=self)
            self.cur_pwd_entry.delete(0, "end")
            self.new_pwd_entry.delete(0, "end")
            self.confirm_pwd_entry.delete(0, "end")
        else:
            messagebox.showerror("Error", err or "Failed to change password.", parent=self)


class AdminPanelWindow(ctk.CTkToplevel):
    """Administrative management window for user management, system scan history, audit logs, and analytics."""

    def __init__(
        self,
        parent,
        user_repo: UserRepository,
        scan_repo: ScanRepository,
        audit_repo: AuditRepository,
        analytics_repo: AnalyticsRepository,
        auth_service: AuthService,
    ):
        super().__init__(parent)
        self.user_repo = user_repo
        self.scan_repo = scan_repo
        self.audit_repo = audit_repo
        self.analytics_repo = analytics_repo
        self.auth_service = auth_service
        self.parent_app = parent

        self.title("Administrator Control Panel — Barcode Reader")
        self.geometry("1060x700")
        self.minsize(940, 580)

        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Top Header
        top_bar = ctk.CTkFrame(self, height=48, corner_radius=0, fg_color=("gray90", "#18181b"))
        top_bar.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        ctk.CTkLabel(
            top_bar,
            text="🛡️ Administrator Control Panel",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        ).pack(side="left", padx=20, pady=10)

        # Tabview
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=16, pady=10)

        self.tab_users = self.tabview.add("👥 User Management")
        self.tab_scans = self.tabview.add("📜 System Scan History")
        self.tab_audit = self.tabview.add("📋 Security Audit Logs")
        self.tab_stats = self.tabview.add("🌐 System Statistics")

        self._setup_users_tab()
        self._setup_scans_tab()
        self._setup_audit_tab()
        self._setup_stats_tab()

    # -------------------------------------------------------------------------
    # Tab 1: User Management
    # -------------------------------------------------------------------------
    def _setup_users_tab(self):
        tab = self.tab_users
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        ctrl_bar = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl_bar.grid(row=0, column=0, sticky="ew", padx=4, pady=6)

        self.user_search_entry = ctk.CTkEntry(
            ctrl_bar,
            placeholder_text="Search users by username, email, role...",
            width=320,
            height=32,
        )
        self.user_search_entry.pack(side="left", padx=(0, 8))
        self.user_search_entry.bind("<Return>", lambda e: self.load_users())

        ctk.CTkButton(
            ctrl_bar,
            text="🔍 Search",
            width=75,
            height=32,
            fg_color="#2563eb",
            command=self.load_users,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            ctrl_bar,
            text="🔄 Refresh",
            width=75,
            height=32,
            fg_color=("gray75", "#27272a"),
            command=self.load_users,
        ).pack(side="right")

        self.users_container = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.users_container.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.users_container.grid_columnconfigure(0, weight=1)

        self.load_users()

    def load_users(self):
        for w in self.users_container.winfo_children():
            w.destroy()

        search_txt = self.user_search_entry.get().strip()
        users, total = self.user_repo.list_users(search_term=search_txt)

        if not users:
            ctk.CTkLabel(
                self.users_container,
                text="No users found.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=("gray50", "#71717a"),
            ).pack(pady=40)
            return

        for u in users:
            self._render_user_card(u)

    def _render_user_card(self, u: User):
        card = ctk.CTkFrame(
            self.users_container,
            corner_radius=8,
            fg_color=("gray90", "#27272a"),
            border_width=1,
            border_color=("gray80", "#3f3f46"),
        )
        card.pack(fill="x", padx=2, pady=4)
        card.grid_columnconfigure(1, weight=1)

        # ID & Role Badge
        id_lbl = ctk.CTkLabel(
            card,
            text=f"#{u.id}",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=("gray50", "#71717a"),
            width=35,
        )
        id_lbl.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        info_f = ctk.CTkFrame(card, fg_color="transparent")
        info_f.grid(row=0, column=1, padx=4, pady=8, sticky="w")

        u_title = ctk.CTkLabel(
            info_f,
            text=f"{u.username}   •   {u.email}",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
            anchor="w",
        )
        u_title.pack(anchor="w")

        status_txt = "🟢 Active" if u.is_active else "🔴 Deactivated"
        meta_txt = f"Role: {u.role}   •   Status: {status_txt}   •   Created: {u.formatted_created_at}   •   Last Login: {u.formatted_last_login}"
        ctk.CTkLabel(
            info_f,
            text=meta_txt,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("gray50", "#a1a1aa"),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        # Actions
        btn_f = ctk.CTkFrame(card, fg_color="transparent")
        btn_f.grid(row=0, column=2, padx=10, pady=8, sticky="e")

        # Activate/Deactivate Toggle
        if u.is_active:
            status_btn = ctk.CTkButton(
                btn_f,
                text="Deactivate",
                width=80,
                height=28,
                fg_color=("#fee2e2", "#7f1d1d"),
                text_color=("#991b1b", "#fca5a5"),
                hover_color="#991b1b",
                command=lambda user=u: self._on_toggle_user_status(user, False),
            )
        else:
            status_btn = ctk.CTkButton(
                btn_f,
                text="Activate",
                width=80,
                height=28,
                fg_color="#059669",
                hover_color="#047857",
                command=lambda user=u: self._on_toggle_user_status(user, True),
            )
        status_btn.pack(side="left", padx=(0, 6))

        # Promote/Demote Role Toggle
        new_role = "USER" if u.is_admin else "ADMIN"
        role_btn_text = "Make USER" if u.is_admin else "Make ADMIN"
        role_btn = ctk.CTkButton(
            btn_f,
            text=role_btn_text,
            width=85,
            height=28,
            fg_color=("gray75", "#3f3f46"),
            command=lambda user=u, r=new_role: self._on_change_user_role(user, r),
        )
        role_btn.pack(side="left")

    def _on_toggle_user_status(self, user: User, is_active: bool):
        action_verb = "activate" if is_active else "deactivate"
        if not messagebox.askyesno(
            f"Confirm {action_verb.title()}",
            f"Are you sure you want to {action_verb} account `{user.username}`?",
            parent=self,
        ):
            return

        ok, err = self.user_repo.set_user_active_status(user.id, is_active)
        if ok:
            self.audit_repo.log_action(
                action="USER_ACTIVATED" if is_active else "USER_DEACTIVATED",
                user_id=self.parent_app.session_manager.user_id,
                username=self.parent_app.session_manager.username,
                description=f"User `{user.username}` (ID {user.id}) status set to {is_active}",
                target_type="User",
                target_id=str(user.id),
            )
            self.load_users()
        else:
            messagebox.showerror("Action Rejected", err or f"Failed to {action_verb} user.", parent=self)

    def _on_change_user_role(self, user: User, new_role: str):
        if not messagebox.askyesno(
            "Confirm Role Change",
            f"Are you sure you want to change `{user.username}`'s role to {new_role}?",
            parent=self,
        ):
            return

        ok, err = self.user_repo.set_user_role(user.id, new_role)
        if ok:
            self.audit_repo.log_action(
                action="USER_ROLE_CHANGED",
                user_id=self.parent_app.session_manager.user_id,
                username=self.parent_app.session_manager.username,
                description=f"User `{user.username}` role changed to {new_role}",
                target_type="User",
                target_id=str(user.id),
            )
            self.load_users()
        else:
            messagebox.showerror("Action Rejected", err or "Failed to change user role.", parent=self)

    # -------------------------------------------------------------------------
    # Tab 2: System Scan History
    # -------------------------------------------------------------------------
    def _setup_scans_tab(self):
        tab = self.tab_scans
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        ctrl_bar = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl_bar.grid(row=0, column=0, sticky="ew", padx=4, pady=6)

        self.sys_scan_search = ctk.CTkEntry(
            ctrl_bar,
            placeholder_text="Search all scans by barcode, type, image, user...",
            width=320,
            height=32,
        )
        self.sys_scan_search.pack(side="left", padx=(0, 8))
        self.sys_scan_search.bind("<Return>", lambda e: self.load_system_scans())

        ctk.CTkButton(
            ctrl_bar,
            text="🔍 Search",
            width=75,
            height=32,
            fg_color="#2563eb",
            command=self.load_system_scans,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            ctrl_bar,
            text="🔄 Refresh",
            width=75,
            height=32,
            fg_color=("gray75", "#27272a"),
            command=self.load_system_scans,
        ).pack(side="right")

        self.sys_scans_container = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.sys_scans_container.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.sys_scans_container.grid_columnconfigure(0, weight=1)

        self.load_system_scans()

    def load_system_scans(self):
        for w in self.sys_scans_container.winfo_children():
            w.destroy()

        search_txt = self.sys_scan_search.get().strip()
        scans, total = self.scan_repo.get_scans(search_term=search_txt, user_id=None, page_size=100)

        if not scans:
            ctk.CTkLabel(
                self.sys_scans_container,
                text="No system scans recorded.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=("gray50", "#71717a"),
            ).pack(pady=40)
            return

        for s in scans:
            row_f = ctk.CTkFrame(self.sys_scans_container, corner_radius=6, fg_color=("gray90", "#27272a"))
            row_f.pack(fill="x", padx=2, pady=3)
            row_f.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                row_f,
                text=f"#{s.id}",
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color=("gray50", "#71717a"),
                width=35,
            ).grid(row=0, column=0, padx=8, pady=8, sticky="w")

            info = f"📦 {s.barcode_data}  ({s.barcode_type})   •   👤 {s.username or 'Anonymous'}   •   📷 {s.source}   •   📅 {s.formatted_date}"
            ctk.CTkLabel(
                row_f,
                text=info,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=("gray10", "#f4f4f5"),
                anchor="w",
            ).grid(row=0, column=1, padx=4, sticky="w")

            del_btn = ctk.CTkButton(
                row_f,
                text="🗑️",
                width=36,
                height=26,
                fg_color=("gray75", "#3f3f46"),
                hover_color="#991b1b",
                command=lambda scan_id=s.id: self._on_delete_system_scan(scan_id),
            )
            del_btn.grid(row=0, column=2, padx=8, pady=8, sticky="e")

    def _on_delete_system_scan(self, scan_id: int):
        ok, err = self.scan_repo.delete_scan(scan_id, current_user=self.parent_app.session_manager.current_user)
        if ok:
            self.load_system_scans()
        else:
            messagebox.showerror("Error", err or "Failed to delete scan.", parent=self)

    # -------------------------------------------------------------------------
    # Tab 3: Security Audit Logs
    # -------------------------------------------------------------------------
    def _setup_audit_tab(self):
        tab = self.tab_audit
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        ctrl_bar = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl_bar.grid(row=0, column=0, sticky="ew", padx=4, pady=6)

        ctk.CTkLabel(
            ctrl_bar,
            text="Security & Administrative Audit Trail",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        ).pack(side="left")

        ctk.CTkButton(
            ctrl_bar,
            text="🔄 Refresh Logs",
            width=100,
            height=32,
            fg_color=("gray75", "#27272a"),
            command=self.load_audit_logs,
        ).pack(side="right")

        self.audit_container = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.audit_container.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.audit_container.grid_columnconfigure(0, weight=1)

        self.load_audit_logs()

    def load_audit_logs(self):
        for w in self.audit_container.winfo_children():
            w.destroy()

        logs, total = self.audit_repo.get_audit_logs(page_size=100)
        if not logs:
            ctk.CTkLabel(
                self.audit_container,
                text="No audit events recorded yet.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=("gray50", "#71717a"),
            ).pack(pady=40)
            return

        for log in logs:
            row_f = ctk.CTkFrame(self.audit_container, corner_radius=6, fg_color=("gray90", "#27272a"))
            row_f.pack(fill="x", padx=2, pady=3)
            row_f.grid_columnconfigure(1, weight=1)

            # Action Badge
            act_badge = ctk.CTkLabel(
                row_f,
                text=log.action,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                fg_color="#1e3a8a",
                text_color="#93c5fd",
                corner_radius=4,
                padx=8,
                pady=2,
            )
            act_badge.grid(row=0, column=0, padx=8, pady=8, sticky="w")

            detail_txt = f"👤 {log.username}   •   {log.description or ''}   •   📅 {log.formatted_created_at}"
            ctk.CTkLabel(
                row_f,
                text=detail_txt,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=("gray20", "#d4d4d8"),
                anchor="w",
            ).grid(row=0, column=1, padx=6, sticky="w")

    # -------------------------------------------------------------------------
    # Tab 4: System Statistics
    # -------------------------------------------------------------------------
    def _setup_stats_tab(self):
        tab = self.tab_stats
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        scroll.grid_columnconfigure((0, 1, 2, 3), weight=1)

        summary = self.analytics_repo.get_summary_metrics(date_range="All Time", user_id=None)

        kpi_defs = [
            ("👥 Total Users", str(summary.get("total_users", 0)), "#2563eb"),
            ("🟢 Active Users", str(summary.get("active_users", 0)), "#059669"),
            ("📈 System Scans", str(summary.get("total_scans", 0)), "#7c3aed"),
            ("📦 Cached Products", str(summary.get("total_products", 0)), "#d97706"),
        ]

        for idx, (title, val, col) in enumerate(kpi_defs):
            card = ctk.CTkFrame(scroll, corner_radius=8, fg_color=("gray90", "#27272a"))
            card.grid(row=0, column=idx, sticky="nsew", padx=6, pady=6)
            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=("gray40", "#a1a1aa"),
            ).pack(anchor="w", padx=12, pady=(10, 2))
            ctk.CTkLabel(
                card,
                text=val,
                font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
                text_color=col,
            ).pack(anchor="w", padx=12, pady=(0, 10))


class ScanHistoryWindow(ctk.CTkToplevel):
    """Scan History window supporting personal and system-wide scan history with search, filtering, and export."""

    def __init__(
        self,
        parent,
        db_manager: DatabaseManager,
        scan_repo: ScanRepository,
        current_user: Optional[User] = None,
    ):
        super().__init__(parent)
        self.db_manager = db_manager
        self.scan_repo = scan_repo
        self.current_user = current_user
        self.parent_app = parent

        self.title("Scan History — Barcode Reader")
        self.geometry("960x620")
        self.minsize(820, 500)

        self.current_page = 1
        self.page_size = 25
        self.total_scans = 0

        self._build_ui()
        self.load_history_data()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 1. Top Controls Bar
        top_bar = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "#18181b"))
        top_bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        self.search_entry = ctk.CTkEntry(
            top_bar,
            placeholder_text="Search barcode data or filename...",
            width=260,
            height=32,
        )
        self.search_entry.pack(side="left", padx=10, pady=8)
        self.search_entry.bind("<Return>", lambda e: self.on_search())

        self.search_btn = ctk.CTkButton(
            top_bar,
            text="🔍 Search",
            width=75,
            height=32,
            fg_color="#2563eb",
            command=self.on_search,
        )
        self.search_btn.pack(side="left", padx=(0, 8))

        self.type_menu = ctk.CTkOptionMenu(
            top_bar,
            values=["All", "EAN-13", "QR Code", "Code 128", "UPC-A", "Code 39", "DataBar"],
            width=100,
            height=32,
            command=lambda v: self.on_search(),
        )
        self.type_menu.pack(side="left", padx=(0, 8))

        self.export_btn = ctk.CTkButton(
            top_bar,
            text="📥 Export CSV",
            width=90,
            height=32,
            fg_color="#059669",
            hover_color="#047857",
            command=self.on_export,
        )
        self.export_btn.pack(side="right", padx=10)

        self.refresh_btn = ctk.CTkButton(
            top_bar,
            text="🔄 Refresh",
            width=75,
            height=32,
            fg_color=("gray75", "#27272a"),
            command=self.load_history_data,
        )
        self.refresh_btn.pack(side="right", padx=(0, 6))

        # 2. Scrollable Cards
        self.cards_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.cards_container.grid(row=1, column=0, sticky="nsew", padx=16, pady=4)
        self.cards_container.grid_columnconfigure(0, weight=1)

        # 3. Bottom Pagination
        self.pagination_frame = ctk.CTkFrame(self, height=40, fg_color="transparent")
        self.pagination_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 10))

        self.count_lbl = ctk.CTkLabel(
            self.pagination_frame,
            text="Loading scans...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("gray50", "#71717a"),
        )
        self.count_lbl.pack(side="left", padx=6)

        self.next_btn = ctk.CTkButton(
            self.pagination_frame,
            text="Next ▶",
            width=70,
            height=28,
            fg_color=("gray75", "#27272a"),
            command=self.on_next_page,
        )
        self.next_btn.pack(side="right", padx=(4, 0))

        self.page_info_lbl = ctk.CTkLabel(
            self.pagination_frame,
            text="Page 1 / 1",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("gray40", "#a1a1aa"),
        )
        self.page_info_lbl.pack(side="right", padx=8)

        self.prev_btn = ctk.CTkButton(
            self.pagination_frame,
            text="◀ Prev",
            width=70,
            height=28,
            fg_color=("gray75", "#27272a"),
            command=self.on_prev_page,
        )
        self.prev_btn.pack(side="right", padx=(0, 4))

    def on_search(self):
        self.current_page = 1
        self.load_history_data()

    def on_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_history_data()

    def on_next_page(self):
        max_p = max(1, (self.total_scans + self.page_size - 1) // self.page_size)
        if self.current_page < max_p:
            self.current_page += 1
            self.load_history_data()

    def load_history_data(self):
        for w in self.cards_container.winfo_children():
            w.destroy()

        search_txt = self.search_entry.get().strip()
        b_type = self.type_menu.get()

        # Normal user sees only own scans; admin sees all
        u_id = None if (self.current_user and self.current_user.is_admin) else (self.current_user.id if self.current_user else None)

        scans, total = self.scan_repo.get_scans(
            page=self.current_page,
            page_size=self.page_size,
            search_term=search_txt,
            barcode_type=b_type,
            user_id=u_id,
        )
        self.total_scans = total

        max_p = max(1, (total + self.page_size - 1) // self.page_size)
        self.page_info_lbl.configure(text=f"Page {self.current_page} of {max_p}")
        start_idx = (self.current_page - 1) * self.page_size + 1 if total > 0 else 0
        end_idx = min(total, self.current_page * self.page_size)
        self.count_lbl.configure(text=f"Showing {start_idx}–{end_idx} of {total} scan(s)")

        self.prev_btn.configure(state="normal" if self.current_page > 1 else "disabled")
        self.next_btn.configure(state="normal" if self.current_page < max_p else "disabled")

        if not scans:
            ctk.CTkLabel(
                self.cards_container,
                text="No scan records found.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=("gray50", "#71717a"),
            ).pack(pady=50)
            return

        for s in scans:
            self._render_scan_card(s)

    def _render_scan_card(self, s: ScanRecord):
        card = ctk.CTkFrame(
            self.cards_container,
            corner_radius=8,
            fg_color=("gray90", "#27272a"),
            border_width=1,
            border_color=("gray80", "#3f3f46"),
        )
        card.pack(fill="x", padx=2, pady=4)
        card.grid_columnconfigure(1, weight=1)

        type_badge = ctk.CTkLabel(
            card,
            text=s.barcode_type,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#1e3a8a",
            text_color="#93c5fd",
            corner_radius=6,
            padx=8,
            pady=3,
            width=90,
        )
        type_badge.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        info_f = ctk.CTkFrame(card, fg_color="transparent")
        info_f.grid(row=0, column=1, padx=4, pady=8, sticky="ew")

        ctk.CTkLabel(
            info_f,
            text=s.barcode_data,
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
            anchor="w",
        ).pack(anchor="w")

        meta = f"📅 {s.formatted_date}   •   📷 {s.source}   •   👤 {s.username or 'Anonymous'}"
        ctk.CTkLabel(
            info_f,
            text=meta,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("gray50", "#71717a"),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        # Actions
        act_f = ctk.CTkFrame(card, fg_color="transparent")
        act_f.grid(row=0, column=2, padx=10, pady=8, sticky="e")

        copy_btn = ctk.CTkButton(
            act_f,
            text="📋",
            width=34,
            height=28,
            fg_color="#2563eb",
            command=lambda d=s.barcode_data: copy_to_clipboard(d, self),
        )
        copy_btn.pack(side="left", padx=(0, 4))

        del_btn = ctk.CTkButton(
            act_f,
            text="🗑️",
            width=34,
            height=28,
            fg_color=("gray75", "#3f3f46"),
            hover_color="#991b1b",
            command=lambda scan_id=s.id: self._on_delete_scan(scan_id),
        )
        del_btn.pack(side="left")

    def _on_delete_scan(self, scan_id: int):
        ok, err = self.scan_repo.delete_scan(scan_id, current_user=self.current_user)
        if ok:
            self.load_history_data()
        else:
            messagebox.showerror("Error", err or "Failed to delete scan.", parent=self)

    def on_export(self):
        file_path = filedialog.asksaveasfilename(
            title="Export Scan History",
            defaultextension=".csv",
            filetypes=[("CSV File", "*.csv"), ("JSON File", "*.json")],
            initialfile=f"scans_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            parent=self,
        )
        if not file_path:
            return

        u_id = None if (self.current_user and self.current_user.is_admin) else (self.current_user.id if self.current_user else None)
        fmt = "json" if str(file_path).lower().endswith(".json") else "csv"
        ok, msg = self.scan_repo.export_scans_to_file(Path(file_path), export_format=fmt, user_id=u_id)
        if ok:
            messagebox.showinfo("Export Successful", msg, parent=self)
        else:
            messagebox.showerror("Export Failed", msg, parent=self)


class ProductDetailsModal(ctk.CTkToplevel):
    """Modal displaying comprehensive product information and nutrition/ingredients metadata."""

    def __init__(self, parent, product: Product):
        super().__init__(parent)
        self.product = product
        self.title(f"Product Details — {product.name or product.barcode}")
        self.geometry("640x560")
        self.minsize(560, 440)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=20, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        title_lbl = ctk.CTkLabel(
            scroll,
            text=self.product.name or "Unnamed Product",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
            wraplength=560,
            justify="left",
            anchor="w",
        )
        title_lbl.pack(fill="x", pady=(0, 4))

        brand_txt = f"Brand: {self.product.brand or 'Not available'}"
        ctk.CTkLabel(
            scroll,
            text=brand_txt,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#93c5fd",
            anchor="w",
        ).pack(fill="x", pady=(0, 12))

        attr_card = ctk.CTkFrame(scroll, corner_radius=8, fg_color=("gray90", "#27272a"))
        attr_card.pack(fill="x", pady=(0, 14))
        attr_card.grid_columnconfigure((0, 1), weight=1)

        def add_attr_row(parent, label, value, row):
            ctk.CTkLabel(
                parent,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=("gray40", "#a1a1aa"),
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=14, pady=4)
            ctk.CTkLabel(
                parent,
                text=str(value),
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=("gray10", "#f4f4f5"),
                anchor="w",
            ).grid(row=row, column=1, sticky="w", padx=14, pady=4)

        add_attr_row(attr_card, "Barcode", self.product.barcode, 0)
        add_attr_row(attr_card, "Category", self.product.category, 1)
        add_attr_row(attr_card, "Quantity", self.product.quantity, 2)
        add_attr_row(attr_card, "Data Source", self.product.source, 3)
        add_attr_row(attr_card, "Last Updated", self.product.formatted_updated_at, 4)

        if self.product.ingredients and self.product.ingredients != "Not available":
            ing_card = ctk.CTkFrame(scroll, corner_radius=8, fg_color=("gray90", "#27272a"))
            ing_card.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(
                ing_card,
                text="🥗 Ingredients",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=("gray10", "#f4f4f5"),
            ).pack(anchor="w", padx=14, pady=(10, 4))
            ctk.CTkLabel(
                ing_card,
                text=self.product.ingredients,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=("gray30", "#d4d4d8"),
                wraplength=540,
                justify="left",
            ).pack(anchor="w", padx=14, pady=(0, 10))

        if self.product.allergens and self.product.allergens != "Not available":
            all_card = ctk.CTkFrame(
                scroll,
                corner_radius=8,
                fg_color=("#fee2e2", "#3b1717"),
                border_width=1,
                border_color=("#f87171", "#7f1d1d"),
            )
            all_card.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(
                all_card,
                text="⚠️ Allergens Notice",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=("#b91c1c", "#f87171"),
            ).pack(anchor="w", padx=14, pady=(10, 4))
            ctk.CTkLabel(
                all_card,
                text=self.product.allergens,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=("#991b1b", "#fca5a5"),
                wraplength=540,
                justify="left",
            ).pack(anchor="w", padx=14, pady=(0, 10))

        ctk.CTkButton(
            scroll,
            text="Close",
            width=100,
            height=32,
            fg_color=("gray75", "#3f3f46"),
            command=self.destroy,
        ).pack(side="right", pady=10)


class ProductCatalogWindow(ctk.CTkToplevel):
    """Dedicated Products Catalog window."""

    def __init__(self, parent, product_service: ProductService, product_repo: ProductRepository, current_user: Optional[User] = None):
        super().__init__(parent)
        self.product_service = product_service
        self.product_repo = product_repo
        self.current_user = current_user
        self.parent_app = parent

        self.title("Product Catalog — Barcode Reader")
        self.geometry("980x640")
        self.minsize(860, 520)

        self.current_page = 1
        self.page_size = 20
        self.total_products = 0

        self._build_ui()
        self.load_products_data()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        top_bar = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "#18181b"))
        top_bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        self.search_entry = ctk.CTkEntry(
            top_bar,
            placeholder_text="Search product name, brand, category, barcode...",
            width=380,
            height=34,
        )
        self.search_entry.pack(side="left", padx=12, pady=10)
        self.search_entry.bind("<Return>", lambda e: self.on_search())

        self.search_btn = ctk.CTkButton(
            top_bar,
            text="🔍 Search",
            width=80,
            height=34,
            fg_color="#2563eb",
            command=self.on_search,
        )
        self.search_btn.pack(side="left", padx=(0, 10))

        self.refresh_btn = ctk.CTkButton(
            top_bar,
            text="🔄 Refresh",
            width=80,
            height=34,
            fg_color=("gray75", "#27272a"),
            command=self.load_products_data,
        )
        self.refresh_btn.pack(side="right", padx=12)

        self.cards_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.cards_container.grid(row=1, column=0, sticky="nsew", padx=16, pady=4)
        self.cards_container.grid_columnconfigure(0, weight=1)

        self.pagination_frame = ctk.CTkFrame(self, height=44, fg_color="transparent")
        self.pagination_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 10))

        self.count_lbl = ctk.CTkLabel(
            self.pagination_frame,
            text="Loading products...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("gray50", "#71717a"),
        )
        self.count_lbl.pack(side="left", padx=6)

        self.next_btn = ctk.CTkButton(
            self.pagination_frame,
            text="Next ▶",
            width=70,
            height=30,
            fg_color=("gray75", "#27272a"),
            command=self.on_next_page,
        )
        self.next_btn.pack(side="right", padx=(4, 0))

        self.page_info_lbl = ctk.CTkLabel(
            self.pagination_frame,
            text="Page 1 / 1",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("gray40", "#a1a1aa"),
        )
        self.page_info_lbl.pack(side="right", padx=8)

        self.prev_btn = ctk.CTkButton(
            self.pagination_frame,
            text="◀ Previous",
            width=75,
            height=30,
            fg_color=("gray75", "#27272a"),
            command=self.on_prev_page,
        )
        self.prev_btn.pack(side="right", padx=(0, 4))

    def on_search(self):
        self.current_page = 1
        self.load_products_data()

    def on_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_products_data()

    def on_next_page(self):
        max_p = max(1, (self.total_products + self.page_size - 1) // self.page_size)
        if self.current_page < max_p:
            self.current_page += 1
            self.load_products_data()

    def load_products_data(self):
        for w in self.cards_container.winfo_children():
            w.destroy()

        search_txt = self.search_entry.get().strip()
        products, total = self.product_repo.search_products(
            search_term=search_txt,
            page=self.current_page,
            page_size=self.page_size,
        )
        self.total_products = total

        max_p = max(1, (total + self.page_size - 1) // self.page_size)
        self.page_info_lbl.configure(text=f"Page {self.current_page} of {max_p}")
        start_idx = (self.current_page - 1) * self.page_size + 1 if total > 0 else 0
        end_idx = min(total, self.current_page * self.page_size)
        self.count_lbl.configure(text=f"Showing {start_idx}–{end_idx} of {total} product(s)")

        self.prev_btn.configure(state="normal" if self.current_page > 1 else "disabled")
        self.next_btn.configure(state="normal" if self.current_page < max_p else "disabled")

        if not products:
            empty_frame = ctk.CTkFrame(self.cards_container, fg_color="transparent")
            empty_frame.pack(fill="both", expand=True, pady=60)
            ctk.CTkLabel(
                empty_frame,
                text="📦\n\nNo products found in local cache.",
                font=ctk.CTkFont(family="Segoe UI", size=14),
                text_color=("gray50", "#71717a"),
                justify="center",
            ).pack()
            return

        for prod in products:
            self._render_product_card(prod)

    def _render_product_card(self, product: Product):
        card = ctk.CTkFrame(
            self.cards_container,
            corner_radius=8,
            fg_color=("gray90", "#27272a"),
            border_width=1,
            border_color=("gray80", "#3f3f46"),
        )
        card.pack(fill="x", expand=True, padx=2, pady=4)
        card.grid_columnconfigure(1, weight=1)

        bc_badge = ctk.CTkLabel(
            card,
            text=product.barcode,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            fg_color="#1e3a8a",
            text_color="#93c5fd",
            corner_radius=6,
            padx=10,
            pady=4,
            width=130,
        )
        bc_badge.grid(row=0, column=0, padx=12, pady=12, sticky="w")

        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=1, padx=6, pady=8, sticky="ew")

        ctk.CTkLabel(
            info_frame,
            text=product.name or "Unnamed Product",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
            anchor="w",
        ).pack(anchor="w")

        meta = f"🏷️ {product.brand or 'N/A'}   •   📁 {product.category or 'N/A'}   •   ⚖️ {product.quantity or 'N/A'}"
        ctk.CTkLabel(
            info_frame,
            text=meta,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("gray50", "#71717a"),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=0, column=2, padx=12, pady=12, sticky="e")

        details_btn = ctk.CTkButton(
            actions,
            text="📄 Details",
            width=70,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#2563eb",
            command=lambda p=product: ProductDetailsModal(self, p),
        )
        details_btn.pack(side="left", padx=(0, 6))

        # Only Admin can delete cached products
        if self.current_user and self.current_user.is_admin:
            del_btn = ctk.CTkButton(
                actions,
                text="🗑️ Delete",
                width=65,
                height=28,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                fg_color=("gray75", "#3f3f46"),
                hover_color="#991b1b",
                command=lambda p=product: self._on_delete_product(p),
            )
            del_btn.pack(side="left")

    def _on_delete_product(self, product: Product):
        confirm = messagebox.askyesno(
            "Delete Product Cache",
            f"Are you sure you want to delete cached product for barcode:\n{product.barcode} ({product.name})?\n\n(Scan history will remain intact.)",
            parent=self,
        )
        if confirm:
            ok, err = self.product_repo.delete_product(product.barcode)
            if ok:
                self.load_products_data()
            else:
                messagebox.showerror("Error", f"Failed to delete product: {err}", parent=self)


class AnalyticsDashboardWindow(ctk.CTkToplevel):
    """Dedicated Analytics Dashboard window presenting personal or system-wide statistics."""

    def __init__(self, parent, analytics_repo: AnalyticsRepository, current_user: Optional[User] = None):
        super().__init__(parent)
        self.analytics_repo = analytics_repo
        self.current_user = current_user
        self.parent_app = parent

        scope_title = "System Analytics" if (current_user and current_user.is_admin) else "My Personal Analytics"
        self.title(f"{scope_title} — Barcode Reader")
        self.geometry("1020x680")
        self.minsize(900, 560)

        self._build_ui()
        self.refresh_dashboard()

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        top_bar = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "#18181b"))
        top_bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        heading = "🌐 System-Wide Analytics" if (self.current_user and self.current_user.is_admin) else "👤 My Personal Dashboard"
        ctk.CTkLabel(
            top_bar,
            text=heading,
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        ).pack(side="left", padx=14, pady=10)

        self.refresh_btn = ctk.CTkButton(
            top_bar,
            text="🔄 Refresh",
            width=100,
            height=32,
            fg_color="#059669",
            hover_color="#047857",
            command=self.refresh_dashboard,
        )
        self.refresh_btn.pack(side="right", padx=14)

        self.date_range_menu = ctk.CTkOptionMenu(
            top_bar,
            values=["All Time", "Today", "Last 7 Days", "Last 30 Days", "This Month"],
            width=130,
            height=32,
            command=lambda v: self.refresh_dashboard(),
        )
        self.date_range_menu.pack(side="right", padx=(0, 10))

        self.scroll_content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_content.grid(row=1, column=0, sticky="nsew", padx=16, pady=4)
        self.scroll_content.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.kpi_cards: Dict[str, ctk.CTkLabel] = {}
        kpi_defs = [
            ("total_scans", "📈 Total Scans", "0", "#2563eb"),
            ("unique_barcodes", "🏷️ Unique Codes", "0", "#7c3aed"),
            ("total_products", "📦 Cached Products", "0", "#059669"),
            ("today_scans", "📅 Today's Scans", "0", "#d97706"),
        ]

        for idx, (key, title, default_val, color) in enumerate(kpi_defs):
            card = ctk.CTkFrame(
                self.scroll_content,
                corner_radius=10,
                fg_color=("gray90", "#18181b"),
                border_width=1,
                border_color=("gray80", "#27272a"),
            )
            card.grid(row=0, column=idx, sticky="nsew", padx=6, pady=6)
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=("gray40", "#a1a1aa"),
            ).pack(anchor="w", padx=12, pady=(10, 2))

            v_lbl = ctk.CTkLabel(
                card,
                text=default_val,
                font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
                text_color=color,
            )
            v_lbl.pack(anchor="w", padx=12, pady=(0, 10))
            self.kpi_cards[key] = v_lbl

        charts_row = ctk.CTkFrame(self.scroll_content, fg_color="transparent")
        charts_row.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=(10, 6))
        charts_row.grid_columnconfigure(0, weight=6)
        charts_row.grid_columnconfigure(1, weight=4)

        self.daily_activity_frame = ctk.CTkFrame(
            charts_row,
            corner_radius=10,
            fg_color=("gray90", "#18181b"),
            border_width=1,
            border_color=("gray80", "#27272a"),
        )
        self.daily_activity_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)

        ctk.CTkLabel(
            self.daily_activity_frame,
            text="📅 Daily Scan Activity (Last 7 Days)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        ).pack(anchor="w", padx=14, pady=(12, 6))

        self.daily_bars_container = ctk.CTkFrame(self.daily_activity_frame, fg_color="transparent")
        self.daily_bars_container.pack(fill="both", expand=True, padx=14, pady=(4, 12))

        self.dist_frame = ctk.CTkFrame(
            charts_row,
            corner_radius=10,
            fg_color=("gray90", "#18181b"),
            border_width=1,
            border_color=("gray80", "#27272a"),
        )
        self.dist_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=0)

        ctk.CTkLabel(
            self.dist_frame,
            text="🏷️ Format & Source Distribution",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        ).pack(anchor="w", padx=14, pady=(12, 6))

        self.dist_bars_container = ctk.CTkFrame(self.dist_frame, fg_color="transparent")
        self.dist_bars_container.pack(fill="both", expand=True, padx=14, pady=(4, 12))

        self.top_codes_frame = ctk.CTkFrame(
            self.scroll_content,
            corner_radius=10,
            fg_color=("gray90", "#18181b"),
            border_width=1,
            border_color=("gray80", "#27272a"),
        )
        self.top_codes_frame.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=6)

        ctk.CTkLabel(
            self.top_codes_frame,
            text="🏆 Most Scanned Barcodes",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        ).pack(anchor="w", padx=14, pady=(12, 6))

        self.top_codes_container = ctk.CTkFrame(self.top_codes_frame, fg_color="transparent")
        self.top_codes_container.pack(fill="both", expand=True, padx=14, pady=(4, 12))

    def refresh_dashboard(self):
        date_range = self.date_range_menu.get()
        u_id = None if (self.current_user and self.current_user.is_admin) else (self.current_user.id if self.current_user else None)

        summary = self.analytics_repo.get_summary_metrics(date_range, user_id=u_id)
        self.kpi_cards["total_scans"].configure(text=f"{summary['total_scans']:,}")
        self.kpi_cards["unique_barcodes"].configure(text=f"{summary['unique_barcodes']:,}")
        self.kpi_cards["total_products"].configure(text=f"{summary['total_products']:,}")
        self.kpi_cards["today_scans"].configure(text=f"{summary['today_scans']:,}")

        for w in self.daily_bars_container.winfo_children():
            w.destroy()

        daily_data = self.analytics_repo.get_daily_scan_counts(days=7, user_id=u_id)
        if not daily_data:
            ctk.CTkLabel(
                self.daily_bars_container,
                text="No scan activity recorded in the past 7 days.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=("gray50", "#71717a"),
            ).pack(pady=20)
        else:
            max_cnt = max(cnt for _, cnt in daily_data) if daily_data else 1
            max_cnt = max(max_cnt, 1)

            grid_f = ctk.CTkFrame(self.daily_bars_container, fg_color="transparent")
            grid_f.pack(fill="x", expand=True)

            for d_idx, (day_lbl, cnt) in enumerate(daily_data):
                col_f = ctk.CTkFrame(grid_f, fg_color="transparent")
                col_f.pack(side="left", fill="both", expand=True, padx=4)

                ctk.CTkLabel(
                    col_f,
                    text=str(cnt),
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color=("gray30", "#34d399"),
                ).pack()

                bar_h = max(8, int((cnt / max_cnt) * 90))
                ctk.CTkFrame(
                    col_f,
                    height=bar_h,
                    corner_radius=4,
                    fg_color="#059669" if cnt > 0 else ("gray80", "#27272a"),
                ).pack(fill="x", pady=4)

                ctk.CTkLabel(
                    col_f,
                    text=day_lbl,
                    font=ctk.CTkFont(family="Segoe UI", size=10),
                    text_color=("gray50", "#71717a"),
                ).pack()

        for w in self.dist_bars_container.winfo_children():
            w.destroy()

        types_data = self.analytics_repo.get_barcode_type_distribution(date_range, user_id=u_id, limit=4)
        sources_data = self.analytics_repo.get_source_distribution(date_range, user_id=u_id)

        cam_cnt = sources_data.get("camera", 0)
        img_cnt = sources_data.get("image", 0)
        tot_src = max(1, cam_cnt + img_cnt)
        cam_pct = round((cam_cnt / tot_src) * 100)
        img_pct = 100 - cam_pct

        ctk.CTkLabel(
            self.dist_bars_container,
            text=f"📷 Camera: {cam_cnt} ({cam_pct}%)  •  📁 Image: {img_cnt} ({img_pct}%)",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("gray40", "#a1a1aa"),
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        if not types_data:
            ctk.CTkLabel(
                self.dist_bars_container,
                text="No barcode type data available.",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=("gray50", "#71717a"),
            ).pack(pady=10)
        else:
            tot_types = sum(c for _, c in types_data) or 1
            for btype, cnt in types_data:
                row_f = ctk.CTkFrame(self.dist_bars_container, fg_color="transparent")
                row_f.pack(fill="x", pady=2)
                pct = round((cnt / tot_types) * 100)
                ctk.CTkLabel(
                    row_f,
                    text=f"{btype}: {cnt} ({pct}%)",
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color=("gray10", "#f4f4f5"),
                    anchor="w",
                ).pack(side="left")

        for w in self.top_codes_container.winfo_children():
            w.destroy()

        top_codes = self.analytics_repo.get_top_barcodes(limit=5, date_range=date_range, user_id=u_id)
        if not top_codes:
            ctk.CTkLabel(
                self.top_codes_container,
                text="No scans recorded yet.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=("gray50", "#71717a"),
            ).pack(pady=10)
        else:
            for rank, (code_data, code_type, count) in enumerate(top_codes, start=1):
                row_f = ctk.CTkFrame(self.top_codes_container, fg_color="transparent")
                row_f.pack(fill="x", pady=3)
                row_f.grid_columnconfigure(1, weight=1)

                ctk.CTkLabel(
                    row_f,
                    text=f"#{rank}",
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color=("gray50", "#71717a"),
                    width=30,
                ).grid(row=0, column=0, sticky="w", padx=(0, 6))

                ctk.CTkLabel(
                    row_f,
                    text=f"{code_data}  ({code_type})",
                    font=ctk.CTkFont(family="Consolas", size=12),
                    text_color=("gray10", "#f4f4f5"),
                    anchor="w",
                ).grid(row=0, column=1, sticky="w")

                ctk.CTkLabel(
                    row_f,
                    text=f"{count} scan(s)",
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color="#34d399",
                ).grid(row=0, column=2, sticky="e")


class LoginWindow(ctk.CTkToplevel):
    """Dedicated modal for User Login, Registration, and First-Time Administrator Setup."""

    def __init__(self, app_parent, auth_service: AuthService, user_repo: UserRepository):
        super().__init__(app_parent)
        self.app_parent = app_parent
        self.auth_service = auth_service
        self.user_repo = user_repo

        self.title("Authentication — Barcode Reader")
        self.geometry("460x520")
        self.minsize(440, 480)
        self.resizable(False, False)
        self.grab_set()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Check if first-time admin setup is required
        self.is_first_admin_mode = not self.user_repo.has_any_admin()
        self.mode = "first_admin" if self.is_first_admin_mode else "login"

        self._build_ui()

    def _on_close(self):
        if not self.app_parent.session_manager.is_authenticated():
            self.app_parent.destroy()
        else:
            self.destroy()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.main_card = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray95", "#18181b"))
        self.main_card.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.main_card.grid_columnconfigure(0, weight=1)

        self._render_view()

    def _render_view(self):
        for w in self.main_card.winfo_children():
            w.destroy()

        if self.mode == "first_admin":
            self._render_first_admin_view()
        elif self.mode == "register":
            self._render_register_view()
        else:
            self._render_login_view()

    def _render_first_admin_view(self):
        ctk.CTkLabel(
            self.main_card,
            text="🛡️ Initial Administrator Setup",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        ).pack(pady=(20, 4))

        ctk.CTkLabel(
            self.main_card,
            text="No administrator account found.\nPlease create the initial administrator to secure the system.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("gray40", "#a1a1aa"),
            justify="center",
        ).pack(pady=(0, 16))

        self.adm_user_entry = ctk.CTkEntry(self.main_card, placeholder_text="Admin Username", height=36)
        self.adm_user_entry.pack(fill="x", padx=24, pady=6)

        self.adm_email_entry = ctk.CTkEntry(self.main_card, placeholder_text="Admin Email Address", height=36)
        self.adm_email_entry.pack(fill="x", padx=24, pady=6)

        self.adm_pwd_entry = ctk.CTkEntry(self.main_card, placeholder_text="Password (min. 6 chars)", show="•", height=36)
        self.adm_pwd_entry.pack(fill="x", padx=24, pady=6)

        self.adm_conf_entry = ctk.CTkEntry(self.main_card, placeholder_text="Confirm Password", show="•", height=36)
        self.adm_conf_entry.pack(fill="x", padx=24, pady=6)

        ctk.CTkButton(
            self.main_card,
            text="Create Administrator",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=38,
            command=self._handle_first_admin_create,
        ).pack(fill="x", padx=24, pady=(16, 12))

    def _render_login_view(self):
        ctk.CTkLabel(
            self.main_card,
            text="Barcode Reader",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        ).pack(pady=(24, 2))

        ctk.CTkLabel(
            self.main_card,
            text="Sign in to your account",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("gray40", "#a1a1aa"),
        ).pack(pady=(0, 20))

        self.login_ident_entry = ctk.CTkEntry(
            self.main_card,
            placeholder_text="Username or Email",
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.login_ident_entry.pack(fill="x", padx=24, pady=8)
        self.login_ident_entry.focus()

        self.login_pwd_entry = ctk.CTkEntry(
            self.main_card,
            placeholder_text="Password",
            show="•",
            height=38,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.login_pwd_entry.pack(fill="x", padx=24, pady=8)
        self.login_pwd_entry.bind("<Return>", lambda e: self._handle_login())

        self.login_btn = ctk.CTkButton(
            self.main_card,
            text="Sign In",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=38,
            command=self._handle_login,
        )
        self.login_btn.pack(fill="x", padx=24, pady=(16, 12))

        ctk.CTkButton(
            self.main_card,
            text="Don't have an account? Create Account",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="transparent",
            text_color="#93c5fd",
            hover=False,
            command=lambda: self._set_mode("register"),
        ).pack(pady=(4, 10))

    def _render_register_view(self):
        ctk.CTkLabel(
            self.main_card,
            text="Create New Account",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        ).pack(pady=(16, 2))

        ctk.CTkLabel(
            self.main_card,
            text="Register a standard user account",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("gray40", "#a1a1aa"),
        ).pack(pady=(0, 14))

        self.reg_user_entry = ctk.CTkEntry(self.main_card, placeholder_text="Username", height=34)
        self.reg_user_entry.pack(fill="x", padx=24, pady=5)

        self.reg_email_entry = ctk.CTkEntry(self.main_card, placeholder_text="Email Address", height=34)
        self.reg_email_entry.pack(fill="x", padx=24, pady=5)

        self.reg_pwd_entry = ctk.CTkEntry(self.main_card, placeholder_text="Password (min. 6 chars)", show="•", height=34)
        self.reg_pwd_entry.pack(fill="x", padx=24, pady=5)

        self.reg_conf_entry = ctk.CTkEntry(self.main_card, placeholder_text="Confirm Password", show="•", height=34)
        self.reg_conf_entry.pack(fill="x", padx=24, pady=5)

        ctk.CTkButton(
            self.main_card,
            text="Create Account",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#2563eb",
            height=36,
            command=self._handle_register,
        ).pack(fill="x", padx=24, pady=(14, 10))

        ctk.CTkButton(
            self.main_card,
            text="Already have an account? Sign In",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="transparent",
            text_color="#93c5fd",
            hover=False,
            command=lambda: self._set_mode("login"),
        ).pack(pady=(0, 8))

    def _set_mode(self, mode: str):
        self.mode = mode
        self._render_view()

    def _handle_first_admin_create(self):
        u = self.adm_user_entry.get().strip()
        e = self.adm_email_entry.get().strip()
        p = self.adm_pwd_entry.get().strip()
        c = self.adm_conf_entry.get().strip()

        ok, user, err = self.auth_service.register(u, e, p, c, role="ADMIN")
        if ok:
            messagebox.showinfo("Setup Complete", "Administrator account created successfully!\nPlease log in.", parent=self)
            self._set_mode("login")
        else:
            messagebox.showerror("Error", err or "Failed to create administrator account.", parent=self)

    def _handle_register(self):
        u = self.reg_user_entry.get().strip()
        e = self.reg_email_entry.get().strip()
        p = self.reg_pwd_entry.get().strip()
        c = self.reg_conf_entry.get().strip()

        ok, user, err = self.auth_service.register(u, e, p, c, role="USER")
        if ok:
            messagebox.showinfo("Registration Successful", "Account created successfully!\nPlease log in with your credentials.", parent=self)
            self._set_mode("login")
        else:
            messagebox.showerror("Registration Error", err or "Failed to create account.", parent=self)

    def _handle_login(self):
        ident = self.login_ident_entry.get().strip()
        pwd = self.login_pwd_entry.get().strip()

        ok, user, err = self.auth_service.login(ident, pwd)
        if ok and user:
            self.app_parent._on_user_authenticated(user)
            self.destroy()
        else:
            messagebox.showerror("Authentication Failed", err or "Invalid username/email or password.", parent=self)


class BarcodeReaderApp(ctk.CTk):
    """Main application window for Barcode Reader supporting Image & Camera scanning, Multi-User RBAC, Products & Analytics."""

    def __init__(self):
        super().__init__()

        # Window Configuration
        self.title("Barcode Reader — Multi-User Intelligence & Analytics System")
        self.geometry("1200x780")
        self.minsize(1040, 700)

        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self._msg_queue: queue.Queue = queue.Queue()

        # Database & Repositories
        self.db_manager = DatabaseManager()
        self.scan_repository = ScanRepository(self.db_manager)
        self.product_repository = ProductRepository(self.db_manager)
        self.product_service = ProductService(repository=self.product_repository)
        self.analytics_repository = AnalyticsRepository(self.db_manager)
        self.user_repository = UserRepository(self.db_manager)
        self.audit_repository = AuditRepository(self.db_manager)

        # Security & Session
        self.session_manager = SessionManager()
        self.auth_service = AuthService(
            user_repo=self.user_repository,
            session_mgr=self.session_manager,
            audit_repo=self.audit_repository,
        )

        # Sub-windows
        self.history_window: Optional[ScanHistoryWindow] = None
        self.catalog_window: Optional[ProductCatalogWindow] = None
        self.dashboard_window: Optional[AnalyticsDashboardWindow] = None
        self.admin_panel_window: Optional[AdminPanelWindow] = None
        self.profile_window: Optional[ProfileModal] = None
        self.login_window: Optional[LoginWindow] = None
        self.is_db_connected = False

        # Detection & Camera Engine
        self.detector = BarcodeDetector()
        self.camera_scanner = CameraScanner(detector=self.detector)
        self.camera_scanner.on_frame_ready = self._on_camera_frame_ready
        self.camera_scanner.on_barcode_confirmed = self._on_camera_barcode_confirmed
        self.camera_scanner.on_state_changed = self._on_camera_state_changed

        # State Variables
        self.active_mode = "image"
        self.current_image_path: Optional[Path] = None
        self.original_image: Optional[np.ndarray] = None
        self.annotated_image: Optional[np.ndarray] = None
        self.current_report: Optional[DetectionReport] = None
        self.is_processing = False

        # Build UI layout
        self._create_layout()
        self._set_mode("image")

        # Start periodic tasks
        self._schedule_queue_check()
        self._schedule_session_check()
        self._init_database_and_auth()

        logger.info("Barcode Reader Desktop Application initialized successfully.")

    def _schedule_queue_check(self):
        try:
            while not self._msg_queue.empty():
                callback = self._msg_queue.get_nowait()
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error executing queued UI callback: {e}")
        finally:
            self.after(30, self._schedule_queue_check)

    def _schedule_session_check(self):
        """Periodically inspect active session for inactivity timeout."""
        if self.session_manager.current_user and self.session_manager.is_expired():
            self._on_session_timeout()
        self.after(5000, self._schedule_session_check)

    def _on_session_timeout(self):
        logger.warning("User session timed out due to inactivity.")
        if self.camera_scanner.state != CameraState.STOPPED:
            self.camera_scanner.stop()
        self.session_manager.clear_session()
        self._update_auth_ui()
        messagebox.showwarning("Session Expired", "Your session has expired due to inactivity.\nPlease log in again.", parent=self)
        self._prompt_login()

    def _dispatch_to_main_thread(self, callback):
        self._msg_queue.put(callback)

    def _on_window_close(self):
        logger.info("Application shutdown requested. Releasing camera and DB resources...")
        if self.camera_scanner.state != CameraState.STOPPED:
            self.camera_scanner.stop()
        self.destroy()

    def _init_database_and_auth(self):
        """Asynchronously connect to DB, run safe migrations, and prompt for login."""
        self._update_db_indicator("Connecting...", state="busy")

        def worker():
            ok, msg = self.db_manager.initialize_database()
            if ok:
                self.is_db_connected = True
                self._dispatch_to_main_thread(
                    lambda: self._update_db_indicator("Connected", state="normal")
                )
                self._dispatch_to_main_thread(self._prompt_login)
            else:
                self.is_db_connected = False
                logger.warning(f"MySQL unavailable at startup: {msg}")
                self._dispatch_to_main_thread(
                    lambda: self._update_db_indicator("Disconnected", state="error")
                )
                self._dispatch_to_main_thread(self._prompt_login)

        threading.Thread(target=worker, daemon=True).start()

    def _prompt_login(self):
        """Open the modal login/registration dialog."""
        if self.login_window is None or not self.login_window.winfo_exists():
            self.login_window = LoginWindow(self, self.auth_service, self.user_repository)
        else:
            self.login_window.focus()

    def _on_user_authenticated(self, user: User):
        """Callback when user successfully logs in."""
        logger.info(f"User `{user.username}` authenticated into application (Role: {user.role}).")
        self._update_auth_ui()
        self._set_status(f"Logged in as {user.username} ({user.role})", state="normal")

    def _update_auth_ui(self):
        """Update top bar profile badge, permissions, and Admin Panel visibility."""
        user = self.session_manager.current_user
        if user:
            self.user_badge_btn.configure(
                text=f"👤 {user.username} ({user.role})",
                state="normal",
            )
            self.user_badge_btn.pack(side="left", padx=(0, 6))
            self.logout_btn.pack(side="left")

            if user.is_admin:
                self.admin_panel_btn.pack(side="left", padx=(0, 6))
            else:
                self.admin_panel_btn.pack_forget()
        else:
            self.user_badge_btn.configure(text="🔒 Not Signed In", state="disabled")
            self.user_badge_btn.pack_forget()
            self.admin_panel_btn.pack_forget()
            self.logout_btn.pack_forget()

    def _on_logout_click(self):
        """Handle user logout."""
        if self.camera_scanner.state != CameraState.STOPPED:
            self.camera_scanner.stop()
        self.auth_service.logout()
        self._reset_to_initial_state()
        self._update_auth_ui()
        self._set_status("Logged out.", state="normal")
        self._prompt_login()

    def _update_db_indicator(self, text: str, state: str = "normal"):
        color_map = {"normal": "#10b981", "busy": "#3b82f6", "error": "#ef4444"}
        self.db_status_badge.configure(
            text=f"Database: ● {text}",
            text_color=color_map.get(state, "#10b981"),
        )
        if state == "error":
            self.db_retry_btn.grid(row=0, column=1, sticky="w", padx=(4, 10), pady=6)
        else:
            self.db_retry_btn.grid_forget()

    def _on_retry_db_click(self):
        self.db_manager.reload_config()
        self._init_database_and_auth()

    def _create_layout(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 1. Header Section
        self.header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray90", "#18181b"))
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        self.header_frame.grid_columnconfigure(1, weight=1)

        title_container = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_container.grid(row=0, column=0, sticky="w", padx=20, pady=12)

        self.title_label = ctk.CTkLabel(
            title_container,
            text="Barcode Reader",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        )
        self.title_label.pack(anchor="w")

        self.subtitle_label = ctk.CTkLabel(
            title_container,
            text="Enterprise Multi-User Barcode Intelligence & Analytics Platform",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=("gray40", "#a1a1aa"),
        )
        self.subtitle_label.pack(anchor="w", pady=(2, 0))

        # Main Navigation Bar
        nav_container = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        nav_container.grid(row=0, column=1, sticky="e", padx=20, pady=12)

        self.mode_switcher = ctk.CTkSegmentedButton(
            nav_container,
            values=["📁 Image Scanner", "📷 Camera Scanner"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            selected_color="#2563eb",
            command=self._on_mode_change,
            height=34,
        )
        self.mode_switcher.set("📁 Image Scanner")
        self.mode_switcher.pack(side="left", padx=(0, 10))

        self.history_btn = ctk.CTkButton(
            nav_container,
            text="📜 History",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=("gray75", "#27272a"),
            hover_color=("gray65", "#3f3f46"),
            height=34,
            width=85,
            command=self._on_history_click,
        )
        self.history_btn.pack(side="left", padx=(0, 6))

        self.products_btn = ctk.CTkButton(
            nav_container,
            text="📦 Products",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=("gray75", "#27272a"),
            hover_color=("gray65", "#3f3f46"),
            height=34,
            width=85,
            command=self._on_products_click,
        )
        self.products_btn.pack(side="left", padx=(0, 6))

        self.dashboard_btn = ctk.CTkButton(
            nav_container,
            text="📊 Dashboard",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=34,
            width=95,
            command=self._on_dashboard_click,
        )
        self.dashboard_btn.pack(side="left", padx=(0, 8))

        # Admin Panel Button (visible only to admins)
        self.admin_panel_btn = ctk.CTkButton(
            nav_container,
            text="🛡️ Admin Panel",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            height=34,
            width=110,
            command=self._on_admin_panel_click,
        )

        # Profile / User Badge Button
        self.user_badge_btn = ctk.CTkButton(
            nav_container,
            text="👤 User",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=("gray75", "#27272a"),
            hover_color=("gray65", "#3f3f46"),
            height=34,
            command=self._on_profile_click,
        )

        # Logout Button
        self.logout_btn = ctk.CTkButton(
            nav_container,
            text="🚪",
            width=36,
            height=34,
            fg_color=("gray75", "#27272a"),
            hover_color="#991b1b",
            command=self._on_logout_click,
        )

        # 2. Main Content Split View (Preview Left, Results Right)
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(12, 6))
        self.main_content.grid_columnconfigure(0, weight=6)
        self.main_content.grid_columnconfigure(1, weight=5)
        self.main_content.grid_rowconfigure(0, weight=1)

        # Left Panel
        self.preview_panel = ctk.CTkFrame(self.main_content, corner_radius=12, fg_color=("gray95", "#18181b"))
        self.preview_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
        self.preview_panel.grid_rowconfigure(2, weight=1)
        self.preview_panel.grid_columnconfigure(0, weight=1)

        self.preview_header = ctk.CTkFrame(self.preview_panel, fg_color="transparent")
        self.preview_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        self.preview_header.grid_columnconfigure(1, weight=1)

        self.preview_title = ctk.CTkLabel(
            self.preview_header,
            text="Image Preview",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        )
        self.preview_title.grid(row=0, column=0, sticky="w")

        self.upload_btn = ctk.CTkButton(
            self.preview_header,
            text="📁 Upload Image",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=30,
            width=120,
            command=self._on_upload_click,
        )

        self.camera_ctrl_bar = ctk.CTkFrame(self.preview_header, fg_color="transparent")
        self.camera_select_menu = ctk.CTkOptionMenu(
            self.camera_ctrl_bar,
            values=["Camera 0"],
            width=110,
            height=28,
            command=self._on_camera_select,
        )
        self.camera_select_menu.pack(side="left", padx=(0, 6))

        self.camera_toggle_btn = ctk.CTkButton(
            self.camera_ctrl_bar,
            text="▶ Start Camera",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=28,
            width=100,
            command=self._on_camera_toggle_click,
        )
        self.camera_toggle_btn.pack(side="left", padx=(0, 6))

        self.snapshot_btn = ctk.CTkButton(
            self.camera_ctrl_bar,
            text="📸 Capture",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=("gray75", "#27272a"),
            hover_color=("gray65", "#3f3f46"),
            height=28,
            width=80,
            command=self._on_snapshot_click,
        )
        self.snapshot_btn.pack(side="left", padx=(0, 6))

        self.auto_save_switch = ctk.CTkSwitch(
            self.camera_ctrl_bar,
            text="Auto-Save",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=self._on_auto_save_toggle,
        )
        self.auto_save_switch.pack(side="left", padx=(4, 0))

        self.warning_banner = ctk.CTkFrame(
            self.preview_panel,
            fg_color=("#fef3c7", "#451a03"),
            corner_radius=6,
            border_width=1,
            border_color=("#f59e0b", "#78350f"),
        )
        self.warning_label = ctk.CTkLabel(
            self.warning_banner,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("#92400e", "#fde68a"),
            wraplength=480,
            justify="left",
        )
        self.warning_label.pack(anchor="w", padx=10, pady=4)

        self.preview_display_box = ctk.CTkFrame(
            self.preview_panel,
            corner_radius=8,
            fg_color=("gray90", "#09090b"),
            border_width=1,
            border_color=("gray80", "#27272a"),
        )
        self.preview_display_box.grid(row=2, column=0, sticky="nsew", padx=16, pady=(6, 14))
        self.preview_display_box.grid_rowconfigure(0, weight=1)
        self.preview_display_box.grid_columnconfigure(0, weight=1)

        self.placeholder_label = ctk.CTkLabel(
            self.preview_display_box,
            text="📷\n\nNo image uploaded\nClick 'Upload Image' to begin",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=("gray50", "#71717a"),
            justify="center",
        )
        self.placeholder_label.grid(row=0, column=0, sticky="nsew")
        self.preview_image_label = ctk.CTkLabel(self.preview_display_box, text="")

        # Right Panel: Results
        self.results_panel = ctk.CTkFrame(self.main_content, corner_radius=12, fg_color=("gray95", "#18181b"))
        self.results_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)
        self.results_panel.grid_rowconfigure(2, weight=1)
        self.results_panel.grid_columnconfigure(0, weight=1)

        results_header = ctk.CTkFrame(self.results_panel, fg_color="transparent")
        results_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))

        self.results_title = ctk.CTkLabel(
            results_header,
            text="Detection Results",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        )
        self.results_title.pack(side="left")

        self.save_all_btn = ctk.CTkButton(
            results_header,
            text="💾 Save All",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            width=85,
            height=28,
            corner_radius=6,
            command=self._on_save_all_click,
        )

        self.count_badge = ctk.CTkLabel(
            results_header,
            text="0 detected",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=("gray80", "#27272a"),
            text_color=("gray20", "#a1a1aa"),
            corner_radius=6,
            padx=8,
            pady=2,
        )
        self.count_badge.pack(side="right")

        self.summary_card = ctk.CTkFrame(
            self.results_panel,
            fg_color=("gray90", "#27272a"),
            corner_radius=8,
            border_width=1,
            border_color=("gray80", "#3f3f46"),
        )
        self.summary_card.grid_columnconfigure((0, 1), weight=1)

        self.summary_left_lbl = ctk.CTkLabel(
            self.summary_card,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("gray40", "#a1a1aa"),
            justify="left",
        )
        self.summary_left_lbl.grid(row=0, column=0, sticky="w", padx=12, pady=6)

        self.summary_right_lbl = ctk.CTkLabel(
            self.summary_card,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("gray40", "#a1a1aa"),
            justify="right",
        )
        self.summary_right_lbl.grid(row=0, column=1, sticky="e", padx=12, pady=6)

        self.results_scrollable = ctk.CTkScrollableFrame(self.results_panel, fg_color="transparent")
        self.results_scrollable.grid(row=2, column=0, sticky="nsew", padx=14, pady=(6, 12))
        self.results_scrollable.grid_columnconfigure(0, weight=1)

        # 3. Status Bar
        self.status_bar = ctk.CTkFrame(self, height=36, corner_radius=0, fg_color=("gray90", "#18181b"))
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        self.status_bar.grid_columnconfigure(2, weight=1)

        self.db_status_badge = ctk.CTkLabel(
            self.status_bar,
            text="Database: ● Connecting...",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#3b82f6",
        )
        self.db_status_badge.grid(row=0, column=0, sticky="w", padx=(20, 4), pady=6)

        self.db_retry_btn = ctk.CTkButton(
            self.status_bar,
            text="🔄 Reconnect",
            width=75,
            height=24,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=("gray75", "#27272a"),
            hover_color=("gray65", "#3f3f46"),
            command=self._on_retry_db_click,
        )

        self.status_text = ctk.CTkLabel(
            self.status_bar,
            text="Ready for image upload",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("gray40", "#a1a1aa"),
        )
        self.status_text.grid(row=0, column=2, sticky="w", padx=10, pady=6)

        self.pipeline_info_label = ctk.CTkLabel(
            self.status_bar,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("gray50", "#71717a"),
        )
        self.pipeline_info_label.grid(row=0, column=3, sticky="e", padx=(0, 20), pady=6)

    def _on_mode_change(self, selected_mode: str):
        self.session_manager.touch()
        mode_key = "camera" if "Camera" in selected_mode else "image"
        self._set_mode(mode_key)

    def _set_mode(self, mode: str):
        self.active_mode = mode
        if mode == "image":
            if self.camera_scanner.state != CameraState.STOPPED:
                self.camera_scanner.stop()
            self.preview_title.configure(text="Image Preview")
            self.camera_ctrl_bar.grid_forget()
            self.upload_btn.grid(row=0, column=1, sticky="e")
            self._reset_to_initial_state()
            self._set_status("Ready for image upload", state="normal")
        elif mode == "camera":
            self.upload_btn.grid_forget()
            self.preview_title.configure(text="Live Camera Preview")
            self.camera_ctrl_bar.grid(row=0, column=1, sticky="e")
            cams = detect_available_cameras()
            cam_options = [f"Camera {idx}" for idx in cams]
            self.camera_select_menu.configure(values=cam_options)
            self.camera_select_menu.set(cam_options[0])
            self._reset_to_initial_state()
            self.placeholder_label.configure(text="📹\n\nCamera Idle\nClick '▶ Start Camera' to begin live scanning")
            self._set_status("Camera Scanner ready", state="normal")

    def _on_camera_toggle_click(self):
        self.session_manager.touch()
        if self.camera_scanner.state in (CameraState.RUNNING, CameraState.STARTING):
            self.camera_scanner.stop()
        else:
            selected_cam_str = self.camera_select_menu.get()
            cam_idx = int(selected_cam_str.replace("Camera", "").strip())
            ok, err = self.camera_scanner.start(camera_index=cam_idx)
            if not ok:
                messagebox.showerror("Camera Error", f"Unable to start camera: {err}", parent=self)

    def _on_camera_select(self, choice: str):
        cam_idx = int(choice.replace("Camera", "").strip())
        if self.camera_scanner.state == CameraState.RUNNING:
            self.camera_scanner.switch_camera(cam_idx)
        else:
            self.camera_scanner.camera_index = cam_idx

    def _on_auto_save_toggle(self):
        self.session_manager.touch()
        self.camera_scanner.auto_save_enabled = bool(self.auto_save_switch.get())

    def _on_snapshot_click(self):
        self.session_manager.touch()
        frame = self.camera_scanner.capture_snapshot()
        if frame is None:
            messagebox.showinfo("Notice", "No active camera frame available to capture.", parent=self)
            return

        file_types = [("PNG Image", "*.png"), ("JPEG Image", "*.jpg"), ("All Files", "*.*")]
        save_path = filedialog.asksaveasfilename(
            title="Save Camera Snapshot",
            defaultextension=".png",
            filetypes=file_types,
            initialfile=f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            parent=self,
        )
        if save_path:
            try:
                cv2.imwrite(str(save_path), frame)
                messagebox.showinfo("Snapshot Saved", f"Snapshot saved successfully to:\n{save_path}", parent=self)
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save snapshot: {e}", parent=self)

    def _on_camera_state_changed(self, new_state: CameraState, error: Optional[str]):
        def update_ui():
            if new_state == CameraState.RUNNING:
                self.camera_toggle_btn.configure(text="⏹ Stop Camera", fg_color="#7f1d1d", hover_color="#991b1b")
                self._set_status(f"Camera Active ({self.camera_scanner.actual_resolution[0]}×{self.camera_scanner.actual_resolution[1]})", state="normal")
            elif new_state in (CameraState.STOPPED, CameraState.STOPPING):
                self.camera_toggle_btn.configure(text="▶ Start Camera", fg_color="#059669", hover_color="#047857")
                self.placeholder_label.configure(text="📹\n\nCamera Idle\nClick '▶ Start Camera' to begin live scanning")
                self.preview_image_label.grid_forget()
                self.placeholder_label.grid(row=0, column=0, sticky="nsew")
                self._set_status("Camera stopped.", state="normal")
                self.pipeline_info_label.configure(text="")
            elif new_state == CameraState.ERROR:
                self.camera_toggle_btn.configure(text="▶ Start Camera", fg_color="#059669", hover_color="#047857")
                self.placeholder_label.configure(text=f"⚠️ Camera Access Failed\n\n{error or 'Device unavailable'}")
                self.preview_image_label.grid_forget()
                self.placeholder_label.grid(row=0, column=0, sticky="nsew")
                self._set_status("Camera error", state="error")

        self._dispatch_to_main_thread(update_ui)

    def _on_camera_frame_ready(self, frame: np.ndarray, results: List[BarcodeResult]):
        def update_frame():
            if self.active_mode != "camera":
                return

            self._display_preview_image(frame)
            fps = self.camera_scanner.fps
            res_w, res_h = self.camera_scanner.actual_resolution
            self.pipeline_info_label.configure(text=f"Resolution: {res_w}×{res_h} | {fps} FPS")

            if results:
                count = len(results)
                plural = "barcode" if count == 1 else "barcodes"
                self._set_status(f"✓ {count} {plural} detected live", state="normal")
                self.count_badge.configure(text=f"{count} detected", fg_color="#065f46", text_color="#34d399")
                if count > 1:
                    self.save_all_btn.configure(text=f"💾 Save All ({count})")
                    self.save_all_btn.pack(side="right", padx=(0, 8))
                else:
                    self.save_all_btn.pack_forget()

                report = DetectionReport(
                    success=True,
                    results=results,
                    stage_used="Live Camera Stream",
                    processing_time_ms=round(1000.0 / max(1.0, fps), 1),
                    engine_used="ZXing-C++" if self.detector.has_zxing else "PyZBar",
                )
                self.current_report = report
                self._render_results(report)
            else:
                self.count_badge.configure(text="Scanning...", fg_color=("gray80", "#27272a"), text_color=("gray20", "#a1a1aa"))
                self.save_all_btn.pack_forget()

        self._dispatch_to_main_thread(update_frame)

    def _on_camera_barcode_confirmed(self, result: BarcodeResult):
        def on_confirmed():
            self._set_status(f"✓ Confirmed {result.barcode_type}: {result.data}", state="normal")
            if self.camera_scanner.auto_save_enabled:
                self._auto_save_camera_barcode(result)

        self._dispatch_to_main_thread(on_confirmed)

    def _auto_save_camera_barcode(self, result: BarcodeResult):
        if not self.is_db_connected:
            return

        u_id = self.session_manager.user_id
        scan_record = ScanRecord(
            barcode_type=result.barcode_type,
            barcode_data=result.data,
            image_name="camera_scan",
            validation_status=result.validation_status,
            x_position=result.x,
            y_position=result.y,
            width=result.width,
            height=result.height,
            processing_method=result.processing_method,
            processing_time_ms=0.0,
            source="camera",
            user_id=u_id,
        )
        self.scan_repository.save_scan(scan_record)

    def _set_status(self, text: str, state: str = "normal"):
        self.status_text.configure(text=text)

    def _on_history_click(self):
        self.session_manager.touch()
        if self.history_window is None or not self.history_window.winfo_exists():
            self.history_window = ScanHistoryWindow(
                self, self.db_manager, self.scan_repository, current_user=self.session_manager.current_user
            )
        else:
            self.history_window.focus()
            self.history_window.load_history_data()

    def _on_products_click(self):
        self.session_manager.touch()
        if self.catalog_window is None or not self.catalog_window.winfo_exists():
            self.catalog_window = ProductCatalogWindow(
                self, self.product_service, self.product_repository, current_user=self.session_manager.current_user
            )
        else:
            self.catalog_window.focus()
            self.catalog_window.load_products_data()

    def _on_dashboard_click(self):
        self.session_manager.touch()
        if self.dashboard_window is None or not self.dashboard_window.winfo_exists():
            self.dashboard_window = AnalyticsDashboardWindow(
                self, self.analytics_repository, current_user=self.session_manager.current_user
            )
        else:
            self.dashboard_window.focus()
            self.dashboard_window.refresh_dashboard()

    def _on_admin_panel_click(self):
        self.session_manager.touch()
        if not AuthorizationService.has_permission(self.session_manager.current_user, Permission.ACCESS_ADMIN_PANEL):
            messagebox.showerror("Access Denied", "Administrator privileges are required to access this panel.", parent=self)
            return

        if self.admin_panel_window is None or not self.admin_panel_window.winfo_exists():
            self.admin_panel_window = AdminPanelWindow(
                self,
                self.user_repository,
                self.scan_repository,
                self.audit_repository,
                self.analytics_repository,
                self.auth_service,
            )
        else:
            self.admin_panel_window.focus()

    def _on_profile_click(self):
        self.session_manager.touch()
        user = self.session_manager.current_user
        if not user:
            self._prompt_login()
            return

        if self.profile_window is None or not self.profile_window.winfo_exists():
            self.profile_window = ProfileModal(self, user, self.auth_service)
        else:
            self.profile_window.focus()

    def _on_upload_click(self):
        self.session_manager.touch()
        if self.is_processing:
            return

        file_types = [
            ("Supported Image Files", "*.jpg;*.jpeg;*.png;*.bmp;*.webp"),
            ("JPEG Images", "*.jpg;*.jpeg"),
            ("PNG Images", "*.png"),
            ("Bitmap Images", "*.bmp"),
            ("WebP Images", "*.webp"),
            ("All Files", "*.*"),
        ]

        initial_dir = str(Path(__file__).resolve().parent.parent / "sample_images")
        if not os.path.exists(initial_dir):
            initial_dir = os.path.expanduser("~")

        selected_file = filedialog.askopenfilename(
            title="Select Barcode or QR Code Image",
            filetypes=file_types,
            initialdir=initial_dir,
        )

        if not selected_file:
            return

        file_path = Path(selected_file)
        self._process_image_async(file_path)

    def _process_image_async(self, file_path: Path):
        self.is_processing = True
        self.upload_btn.configure(state="disabled")
        self._set_status("Analyzing image...", state="busy")
        self._show_analyzing_state()

        def worker():
            try:
                is_valid, err_msg = ImageProcessor.validate_file(file_path)
                if not is_valid:
                    self._dispatch_to_main_thread(lambda: self._on_processing_error(err_msg or "Invalid file selected."))
                    return

                image = ImageProcessor.load_image(file_path)
                if image is None:
                    self._dispatch_to_main_thread(
                        lambda: self._on_processing_error("Unable to read image.\nPlease select another image.")
                    )
                    return

                self.original_image = image
                self.current_image_path = file_path

                report = self.detector.detect_and_decode(image)
                self.current_report = report

                if report.success:
                    self.annotated_image = ImageProcessor.draw_bounding_boxes(image, report.results)
                else:
                    self.annotated_image = image.copy()

                self._dispatch_to_main_thread(lambda: self._on_processing_success(file_path, report))

            except Exception as e:
                logger.exception(f"Unexpected error during processing: {e}")
                self._dispatch_to_main_thread(lambda: self._on_processing_error(f"Processing error: {str(e)}"))
            finally:
                self._dispatch_to_main_thread(self._cleanup_processing_state)

        threading.Thread(target=worker, daemon=True).start()

    def _cleanup_processing_state(self):
        self.is_processing = False
        self.upload_btn.configure(state="normal")

    def _on_processing_success(self, file_path: Path, report: DetectionReport):
        self._display_preview_image(self.annotated_image)
        h, w = self.original_image.shape[:2]

        if report.image_metrics and report.image_metrics.warnings:
            warn_msg = " • " + "\n • ".join(report.image_metrics.warnings)
            self.warning_label.configure(text=f"Quality Notice:\n{warn_msg}")
            self.warning_banner.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))
        else:
            self.warning_banner.grid_forget()

        time_sec = report.processing_time_ms / 1000.0
        if report.success:
            count = report.count
            plural = "barcode" if count == 1 else "barcodes"
            self._set_status(f"{count} {plural} detected in {time_sec:.2f}s", state="normal")
            self.pipeline_info_label.configure(text=f"Engine: {report.engine_used} | {report.processing_time_ms} ms")
            self.count_badge.configure(text=f"{count} detected", fg_color="#065f46", text_color="#34d399")
            if count > 1:
                self.save_all_btn.configure(text=f"💾 Save All ({count})")
                self.save_all_btn.pack(side="right", padx=(0, 8))
            else:
                self.save_all_btn.pack_forget()
        else:
            self._set_status(f"No barcode detected ({time_sec:.2f}s)", state="warning")
            self.pipeline_info_label.configure(text=f"Engine: {report.engine_used} | {report.processing_time_ms} ms")
            self.count_badge.configure(text="0 detected", fg_color=("gray80", "#27272a"), text_color=("gray20", "#a1a1aa"))
            self.save_all_btn.pack_forget()

        self.summary_left_lbl.configure(text=f"📊 Barcodes: {report.count}\n⏱️ Time: {time_sec:.2f}s ({report.processing_time_ms}ms)")
        self.summary_right_lbl.configure(text=f"📐 Size: {w}×{h} px\n⚙️ Method: {report.stage_used}")
        self.summary_card.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))

        self._render_results(report)

    def _on_processing_error(self, message: str):
        self._set_status("Unable to process image.", state="error")
        self.pipeline_info_label.configure(text="")
        self.count_badge.configure(text="Error", fg_color="#7f1d1d", text_color="#f87171")
        self.summary_card.grid_forget()
        self.warning_banner.grid_forget()
        self.save_all_btn.pack_forget()

        for widget in self.results_scrollable.winfo_children():
            widget.destroy()

        error_card = ctk.CTkFrame(
            self.results_scrollable,
            corner_radius=8,
            fg_color=("#fee2e2", "#2d1515"),
            border_width=1,
            border_color=("#f87171", "#7f1d1d"),
        )
        error_card.pack(fill="x", expand=True, padx=4, pady=8)

        ctk.CTkLabel(
            error_card,
            text="⚠️ Processing Notice",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=("#b91c1c", "#f87171"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        ctk.CTkLabel(
            error_card,
            text=message,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=("#991b1b", "#fca5a5"),
            wraplength=380,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _display_preview_image(self, img_array: np.ndarray):
        box_w = max(360, self.preview_display_box.winfo_width() - 20)
        box_h = max(280, self.preview_display_box.winfo_height() - 20)

        pil_img = ImageProcessor.resize_for_preview(img_array, max_width=box_w, max_height=box_h)
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)

        self.placeholder_label.grid_forget()
        self.preview_image_label.configure(image=ctk_img)
        self.preview_image_label.image = ctk_img
        self.preview_image_label.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def _show_analyzing_state(self):
        for widget in self.results_scrollable.winfo_children():
            widget.destroy()

        self.summary_card.grid_forget()
        self.warning_banner.grid_forget()
        self.save_all_btn.pack_forget()

        loading_frame = ctk.CTkFrame(self.results_scrollable, fg_color="transparent")
        loading_frame.pack(fill="both", expand=True, pady=40)

        ctk.CTkLabel(loading_frame, text="🔍", font=ctk.CTkFont(size=32)).pack(pady=(10, 8))
        ctk.CTkLabel(
            loading_frame,
            text="Analyzing image and detecting barcodes...",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=("gray40", "#a1a1aa"),
        ).pack()

    def _render_results(self, report: DetectionReport):
        for widget in self.results_scrollable.winfo_children():
            widget.destroy()

        if not report.success or len(report.results) == 0:
            no_code_card = ctk.CTkFrame(
                self.results_scrollable,
                corner_radius=10,
                fg_color=("gray90", "#27272a"),
                border_width=1,
                border_color=("gray80", "#3f3f46"),
            )
            no_code_card.pack(fill="x", expand=True, padx=4, pady=8)

            ctk.CTkLabel(
                no_code_card,
                text="🔍 No Barcode Detected",
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                text_color=("gray10", "#f4f4f5"),
            ).pack(anchor="w", padx=18, pady=(16, 8))

            reason_text = (
                "Tips for clear detection:\n"
                "  • Position the barcode inside the central frame\n"
                "  • Hold steady and avoid harsh glares or reflections\n"
                "  • Move closer if barcode is small or low resolution"
            )
            ctk.CTkLabel(
                no_code_card,
                text=reason_text,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=("gray30", "#d4d4d8"),
                justify="left",
            ).pack(anchor="w", padx=18, pady=(0, 16))
            return

        for idx, result in enumerate(report.results, start=1):
            self._create_barcode_card(idx, result)

    def _create_barcode_card(self, idx: int, result: BarcodeResult):
        card = ctk.CTkFrame(
            self.results_scrollable,
            corner_radius=10,
            fg_color=("gray90", "#27272a"),
            border_width=1,
            border_color=("gray80", "#3f3f46"),
        )
        card.pack(fill="x", expand=True, padx=4, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)

        # Header
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            header_frame,
            text=f"Barcode #{idx}",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=("gray10", "#f4f4f5"),
        ).pack(side="left")

        badges_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        badges_container.pack(side="right")

        if result.validation_status == "Valid":
            val_bg, val_fg, val_txt = "#065f46", "#34d399", "✓ Valid"
        elif result.validation_status == "Invalid":
            val_bg, val_fg, val_txt = "#7f1d1d", "#f87171", "✕ Invalid"
        else:
            val_bg, val_fg, val_txt = ("gray75", "#3f3f46"), ("gray30", "#a1a1aa"), "ℹ Checksum N/A"

        ctk.CTkLabel(
            badges_container,
            text=val_txt,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=val_bg,
            text_color=val_fg,
            corner_radius=6,
            padx=8,
            pady=2,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            badges_container,
            text=result.barcode_type,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#1e3a8a",
            text_color="#93c5fd",
            corner_radius=6,
            padx=10,
            pady=3,
        ).pack(side="left")

        # Decoded Data Entry + Buttons
        data_container = ctk.CTkFrame(
            card,
            corner_radius=6,
            fg_color=("gray85", "#18181b"),
            border_width=1,
            border_color=("gray75", "#3f3f46"),
        )
        data_container.pack(fill="x", padx=16, pady=(0, 8))
        data_container.grid_columnconfigure(0, weight=1)

        data_entry = ctk.CTkEntry(
            data_container,
            font=ctk.CTkFont(family="Consolas", size=13),
            fg_color="transparent",
            border_width=0,
            text_color=("gray10", "#f4f4f5"),
        )
        data_entry.insert(0, result.data)
        data_entry.configure(state="readonly")
        data_entry.grid(row=0, column=0, sticky="ew", padx=(10, 8), pady=8)

        btns_frame = ctk.CTkFrame(data_container, fg_color="transparent")
        btns_frame.grid(row=0, column=1, sticky="e", padx=(0, 8), pady=6)

        copy_btn = ctk.CTkButton(
            btns_frame,
            text="📋 Copy",
            width=64,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            corner_radius=6,
        )

        def on_copy():
            if copy_to_clipboard(result.data, self):
                copy_btn.configure(text="✓ Copied", fg_color="#059669")
                self._set_status("Barcode data copied to clipboard.", state="normal")
                self.after(2000, lambda: copy_btn.configure(text="📋 Copy", fg_color="#2563eb"))

        copy_btn.configure(command=on_copy)
        copy_btn.pack(side="left", padx=(0, 4))

        save_btn = ctk.CTkButton(
            btns_frame,
            text="💾 Save",
            width=64,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            corner_radius=6,
            command=lambda r=result: self._on_save_single_barcode(r),
        )
        save_btn.pack(side="left", padx=(0, 4))

        lookup_btn = ctk.CTkButton(
            btns_frame,
            text="🔎 Product",
            width=76,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            corner_radius=6,
        )

        def on_lookup_click(b_code=result.data, btn=lookup_btn, parent_card=card):
            self._handle_product_lookup(b_code, btn, parent_card)

        lookup_btn.configure(command=on_lookup_click)
        lookup_btn.pack(side="left")

        # Footer Coordinates
        footer_frame = ctk.CTkFrame(card, fg_color="transparent")
        footer_frame.pack(fill="x", padx=16, pady=(0, 10))

        loc_text = f"📍 Location: ({result.x}, {result.y})  •  Size: {result.width}×{result.height} px"
        if result.rotation != 0:
            loc_text += f"  •  Rotated: {result.rotation}°"

        ctk.CTkLabel(
            footer_frame,
            text=loc_text,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=("gray50", "#71717a"),
        ).pack(side="left")

        if result.validation_details:
            ctk.CTkLabel(
                footer_frame,
                text=result.validation_details,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=("gray50", "#a1a1aa"),
            ).pack(side="right")

    def _handle_product_lookup(self, barcode: str, btn: ctk.CTkButton, card: ctk.CTkFrame):
        self.session_manager.touch()
        btn.configure(text="⌛ Looking up...", state="disabled")
        self._set_status("Querying product information...", state="busy")

        def worker():
            product, msg, is_cached = self.product_service.lookup_product(barcode)

            def on_complete():
                btn.configure(text="🔎 Product", state="normal")
                if product:
                    self._set_status(f"✓ Product found: {product.name}", state="normal")
                    ProductDetailsModal(self, product)
                else:
                    self._set_status("Product not found.", state="warning")
                    messagebox.showinfo(
                        "Product Lookup",
                        f"Product Not Found\n\nNo product information is available in the product database for barcode:\n{barcode}\n\n(The barcode itself was successfully decoded.)",
                        parent=self,
                    )

            self._dispatch_to_main_thread(on_complete)

        threading.Thread(target=worker, daemon=True).start()

    def _on_save_single_barcode(self, result: BarcodeResult):
        self.session_manager.touch()
        if not self.is_db_connected:
            messagebox.showwarning("Database Unavailable", "Database unavailable.\nPlease check MySQL Server.", parent=self)
            return

        source = "camera" if self.active_mode == "camera" else "image"
        img_name = "camera_scan" if self.active_mode == "camera" else (
            self.current_image_path.name if self.current_image_path else "uploaded_image"
        )
        u_id = self.session_manager.user_id

        scan_record = ScanRecord(
            barcode_type=result.barcode_type,
            barcode_data=result.data,
            image_name=img_name,
            validation_status=result.validation_status,
            x_position=result.x,
            y_position=result.y,
            width=result.width,
            height=result.height,
            processing_method=result.processing_method,
            processing_time_ms=self.current_report.processing_time_ms if self.current_report else 0.0,
            source=source,
            user_id=u_id,
        )

        ok, rec_id, err = self.scan_repository.save_scan(scan_record)
        if ok:
            self._set_status("Scan saved successfully.", state="normal")
            messagebox.showinfo("Saved", "Scan saved successfully to MySQL.", parent=self)
        else:
            self._set_status("Failed to save scan.", state="error")
            messagebox.showerror("Save Error", f"Unable to save scan:\n{err}", parent=self)

    def _on_save_all_click(self):
        self.session_manager.touch()
        if not self.current_report or not self.current_report.results:
            return

        if not self.is_db_connected:
            messagebox.showwarning("Database Unavailable", "Database unavailable.\nPlease check MySQL Server.", parent=self)
            return

        source = "camera" if self.active_mode == "camera" else "image"
        img_name = "camera_scan" if self.active_mode == "camera" else (
            self.current_image_path.name if self.current_image_path else "uploaded_image"
        )
        time_ms = self.current_report.processing_time_ms
        u_id = self.session_manager.user_id

        scans_to_save = [
            ScanRecord(
                barcode_type=r.barcode_type,
                barcode_data=r.data,
                image_name=img_name,
                validation_status=r.validation_status,
                x_position=r.x,
                y_position=r.y,
                width=r.width,
                height=r.height,
                processing_method=r.processing_method,
                processing_time_ms=time_ms,
                source=source,
                user_id=u_id,
            )
            for r in self.current_report.results
        ]

        ok, saved_count, err = self.scan_repository.save_scans(scans_to_save)
        if ok:
            msg = f"{saved_count} barcode scan(s) saved successfully."
            self._set_status(msg, state="normal")
            messagebox.showinfo("Batch Save Complete", msg, parent=self)
        else:
            self._set_status("Batch save failed.", state="error")
            messagebox.showerror("Save Error", f"Unable to save scans:\n{err}", parent=self)

    def _reset_to_initial_state(self):
        self.current_image_path = None
        self.original_image = None
        self.annotated_image = None
        self.current_report = None

        self.preview_image_label.grid_forget()
        self.preview_image_label.configure(image=None)
        self.placeholder_label.grid(row=0, column=0, sticky="nsew")
        self.warning_banner.grid_forget()

        self.summary_card.grid_forget()
        self.save_all_btn.pack_forget()
        for widget in self.results_scrollable.winfo_children():
            widget.destroy()

        self.count_badge.configure(
            text="0 detected",
            fg_color=("gray80", "#27272a"),
            text_color=("gray20", "#a1a1aa"),
        )
        self._set_status("Ready", state="normal")
        self.pipeline_info_label.configure(text="")
