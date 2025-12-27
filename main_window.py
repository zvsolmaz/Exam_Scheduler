# main_window.py
from __future__ import annotations
import os
from typing import Optional, Dict

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QStackedWidget, QLabel, QStatusBar, QFrame, QPushButton, QSizePolicy, QMessageBox,
    QComboBox, QTabWidget
)

# Sayfalar
from classrooms_page import ClassroomsPage
from users_coordinators_page import CoordinatorsPage
from departments_page import DepartmentsPage
from students_list_page import StudentsListPage
from courses_list_page import CoursesListPage
from courses_upload_page import CoursesUploadPage
from students_upload_page import StudentsUploadPage
from exam_program_page import ExamProgramPage
from seat_plan_page import SeatPlanPage  # parent=QWidget bekler

# Yardımcılar
from auth import get_department_name, get_coordinator_profile
from db import get_connection

# ──────────────────────────────────────────────────────────────────────────────
# Küçük yardımcılar
# ──────────────────────────────────────────────────────────────────────────────

def _u(user: Dict, *keys, default=None):
    """Kullanıcı sözlüğünde role_id/RoleID gibi anahtar varyantlarını güvenle al."""
    for k in keys:
        if k in user and user[k] not in (None, ""):
            return user[k]
    return default


class Placeholder(QWidget):
    """Basit boş sayfa başlığı + açıklama."""
    def __init__(self, title: str, desc: str = ""):
        super().__init__()
        v = QVBoxLayout(self)
        h1 = QLabel(title); h1.setObjectName("PageTitle")
        p  = QLabel(desc or ""); p.setObjectName("PageDesc"); p.setWordWrap(True)
        v.addWidget(h1); v.addWidget(p); v.addStretch(1)


class AdminExcelImportPage(QWidget):
    """
    Admin için bölüm seçip hem Ders hem Öğrenci Excel içe aktarımı.
    Koordinatör sayfalarını, seçilen bölüme "sahte user" geçirerek yeniden kullanır.
    """
    def __init__(self, admin_user: dict):
        super().__init__()
        self.admin_user = admin_user
        root = QVBoxLayout(self); root.setSpacing(12)

        title = QLabel("Excel İçe Aktarım"); title.setObjectName("PageTitle")
        desc  = QLabel("Admin, bölüm seçip ders/öğrenci listelerini yükleyebilir.")
        desc.setObjectName("PageDesc"); desc.setWordWrap(True)

        # Üst şerit: Bölüm seçimi
        top = QHBoxLayout(); top.setSpacing(8)
        top.addWidget(QLabel("Bölüm:"))
        self.cmb_department = QComboBox()
        self.cmb_department.setMinimumWidth(320)
        top.addWidget(self.cmb_department)
        top.addStretch(1)

        # Sekmeler: Ders / Öğrenci
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setDocumentMode(True)

        # İlk yüklemede doldurulacak
        self._courses_page: Optional[QWidget] = None
        self._students_page: Optional[QWidget] = None

        root.addWidget(title); root.addWidget(desc); root.addLayout(top)
        root.addWidget(self.tabs, 1)

        self._load_departments()
        self.cmb_department.currentIndexChanged.connect(self._reload_pages)
        self._reload_pages()

    def _load_departments(self):
        self.cmb_department.clear()
        try:
            conn = get_connection(); cur = conn.cursor()
            cur.execute("SELECT DepartmentID, Name FROM dbo.Departments ORDER BY Name;")
            for dep_id, name in cur.fetchall():
                self.cmb_department.addItem(str(name), int(dep_id))
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Bölümler alınamadı:\n{e}")

    def _fake_user_for(self, department_id: int) -> dict:
        """Koordinatör sayfalarını yeniden kullanmak için bölüm sabitli sahte user."""
        return {
            "role_id": 2,  # koordinatör gibi davransın
            "department_id": department_id,
            "email": _u(self.admin_user, "email", "Email", default="admin@uni.edu"),
            "name": "Admin (yetkili aktarım)"
        }

    def _reload_pages(self):
        dep_id = int(self.cmb_department.currentData()) if self.cmb_department.currentData() is not None else None
        if dep_id is None:
            self.tabs.clear()
            return

        user_for_dep = self._fake_user_for(dep_id)

        # Sekmeleri baştan kur
        self.tabs.clear()
        self._courses_page = CoursesUploadPage(user_for_dep)
        self._students_page = StudentsUploadPage(user_for_dep)

        self.tabs.addTab(self._courses_page, "Ders Listesi Yükle")
        self.tabs.addTab(self._students_page, "Öğrenci Listesi Yükle")


# ──────────────────────────────────────────────────────────────────────────────
# Ana Pencere
# ──────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    logged_out = pyqtSignal()  # Çıkış sinyali

    ACCENT    = "#1E7C45"
    BG_START  = "#0F223A"
    BG_END    = "#0B182B"
    TEXT_DARK = "#1C2B3A"
    MUTED     = "#6B7A90"
    CARD_BG   = "#FFFFFF"
    BORDER    = "#E6E6E6"

    def __init__(self, user: dict):
        super().__init__()
        self.user = user or {}
        self.setWindowTitle("Sınav Takvimi")
        self.resize(1200, 760)
        try:
            self.setWindowIcon(QIcon("assets/kou_logo.png"))
        except Exception:
            pass

        # Kullanıcı bilgileri
        self.role_id = int(_u(self.user, "role_id", "RoleID", default=2))
        self.dept_id = _u(self.user, "department_id", "DepartmentID", default=None)
        self.email   = _u(self.user, "email", "Email", default="")

        dept_name = get_department_name(self.dept_id) if self.dept_id else None

        # Profil verisi
        if self.role_id == 1:
            prof = {
                "name": "Yönetici",
                "email": self.email or "admin@uni.edu",
                "department_name": "Admin",
                "photo": _u(self.user, "photo", "PhotoPath", default=None)
            }
        else:
            prof = get_coordinator_profile(self.email) if self.email else {}
            prof.setdefault("name", _u(self.user, "name", "Name", default="Koordinatör"))
            prof.setdefault("email", self.email)
            prof.setdefault("department_name", dept_name or "Bölüm")
            prof.setdefault("photo", _u(self.user, "photo", "PhotoPath", default=None))

        # ── ÜST BAR
        top_widget = QWidget()
        tv = QVBoxLayout(top_widget); tv.setContentsMargins(0,0,0,0); tv.setSpacing(0)

        bar = QFrame(); bar.setObjectName("TopBar"); bar.setFixedHeight(50)
        hl = QHBoxLayout(bar); hl.setContentsMargins(14, 0, 14, 0); hl.setSpacing(10)

        title = QLabel("Kocaeli Üniversitesi • Sınav Takvimi")
        title.setStyleSheet("font-weight:800; color:#FFFFFF; font-size:15px; letter-spacing:.3px;")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        hl.addWidget(title)
        hl.addStretch(1)

        btn_logout = QPushButton("Çıkış")
        btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_logout.setStyleSheet("""
            QPushButton {
                background: #EF4444; color:#fff; border:none; border-radius:8px;
                padding:6px 12px; font-weight:700;
            }
            QPushButton:hover { background:#DC2626; }
        """)
        btn_logout.clicked.connect(self._logout)
        hl.addWidget(btn_logout)

        btn_min = QPushButton("—"); btn_close = QPushButton("✕")
        for b in (btn_min, btn_close):
            b.setFixedSize(34, 28); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton { background: transparent; border: none; color: #FFFFFF;
                               font-size:16px; font-weight:800; border-radius:6px; }
                QPushButton:hover { background: rgba(255,255,255,0.16); }
            """)
            hl.addWidget(b)
        btn_close.setStyleSheet(btn_close.styleSheet() + "QPushButton:hover {background:#B91C1C; color:#FFFFFF;}")
        btn_min.clicked.connect(self.showMinimized)
        btn_close.clicked.connect(self.close)

        bar.setStyleSheet("""
            QFrame#TopBar { background: #0B1324; border-bottom: 1px solid #0F223A; }
        """)

        # ── PROFİL PANELİ
        prof_card = QFrame(); prof_card.setObjectName("ProfileCard")
        ph = QHBoxLayout(prof_card); ph.setContentsMargins(24,10,24,10); ph.setSpacing(14)

        avatar = QLabel(); avatar.setFixedSize(72, 72)
        avatar.setStyleSheet("border-radius:36px; background:#E5E7EB;")
        photo_path = prof.get("photo")
        if photo_path and os.path.exists(photo_path):
            pm = QPixmap(photo_path).scaled(
                72, 72, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            avatar.setPixmap(pm)
        ph.addWidget(avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        info_col = QVBoxLayout(); info_col.setSpacing(4)
        dept_badge = QLabel(prof.get("department_name") or dept_name or "Bölüm")
        dept_badge.setObjectName("DeptBadge")
        dept_badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        dept_badge.adjustSize()
        name_lbl = QLabel(f"<b>{prof.get('name','')}</b>")
        email_lbl = QLabel(f"<span style='color:{self.MUTED}'>{prof.get('email','')}</span>")
        info_col.addWidget(dept_badge); info_col.addWidget(name_lbl); info_col.addWidget(email_lbl)
        ph.addLayout(info_col, 0)

        prof_card.setStyleSheet(f"""
            QFrame#ProfileCard {{
                background: #FFFFFF; border-bottom: 1px solid {self.BORDER};
            }}
            QLabel#DeptBadge {{
                background: #DCFCE7; color: #065F46; font-weight: 800;
                border-radius: 10px; padding: 3px 10px; font-size: 12px;
            }}
            QLabel {{ color: {self.TEXT_DARK}; font-size: 13px; }}
        """)

        tv.addWidget(bar); tv.addWidget(prof_card)
        self.setMenuWidget(top_widget)

        # ── STATUS BAR
        sb = QStatusBar(); self.setStatusBar(sb)
        role_name = "Admin" if self.role_id == 1 else "Bölüm Koordinatörü"
        dept_text = "Tüm Bölümler" if self.role_id == 1 else (dept_name or (f"Bölüm ID: {self.dept_id}" if self.dept_id else "Bölüm atanmadı"))
        sb.showMessage(f"Giriş: {self.email}  |  Rol: {role_name}  |  Yetki: {dept_text}")

        # ── MENÜ & SAYFALAR
        self.left = QListWidget()
        self.stack = QStackedWidget()

        def add_page(title: str, widget: QWidget):
            item = QListWidgetItem(title)
            self.left.addItem(item)
            self.stack.addWidget(widget)

        add_page("Dashboard", Placeholder("Dashboard", "Sistem özeti ve istatistikler."))

        if self.role_id == 1:
            # Admin görünümü
            add_page("Kullanıcılar", CoordinatorsPage(self.user))
            add_page("Bölümler", DepartmentsPage(self.user))
            add_page("Dersler (Tüm Bölümler)", CoursesListPage(self.user))
            add_page("Öğrenciler (Tüm Bölümler)", StudentsListPage(self.user))
            add_page("Excel İçe Aktarım", AdminExcelImportPage(self.user))
            add_page("Sınav Programı (Genel)", ExamProgramPage(self.user))
            add_page("Oturma Planı", SeatPlanPage(user=self.user, parent=self))
            self._gated_titles = set()  # admin kısıtlanmaz
        else:
            # Koordinatör görünümü
            self._classrooms_title = f"Derslikler — {dept_name or 'Bölümünüz'}"
            add_page(self._classrooms_title, ClassroomsPage(self.user))
            add_page("Ders Listesi Yükle", CoursesUploadPage(self.user))
            add_page("Öğrenci Listesi Yükle", StudentsUploadPage(self.user))
            add_page("Öğrenci Listesi", StudentsListPage(self.user))
            add_page("Ders Listesi", CoursesListPage(self.user))
            add_page("Sınav Programı Oluştur", ExamProgramPage(self.user))
            add_page("Oturma Planı", SeatPlanPage(user=self.user, parent=self))
            # Hoca notuna göre: derslik yoksa bu sayfalar kilitli olsun
            self._gated_titles = {
                "Ders Listesi Yükle",
                "Öğrenci Listesi Yükle",
                "Öğrenci Listesi",
                "Ders Listesi",
                "Sınav Programı Oluştur",
                "Oturma Planı",
            }

        # ── ANA YERLEŞİM
        central = QWidget(); self.setCentralWidget(central)
        outer = QHBoxLayout(central); outer.setContentsMargins(18,18,18,18); outer.setSpacing(18)

        content_card = QFrame(); content_card.setObjectName("ContentCard")
        content_v = QVBoxLayout(content_card); content_v.setContentsMargins(22,18,22,18); content_v.setSpacing(12)
        content_v.addWidget(self.stack, 1)

        # Sol menü davranışı (gate ile)
        self.left.currentRowChanged.connect(self._on_menu_change)
        self.left.setFixedWidth(260); self.left.setCurrentRow(0)

        # Başlangıçta görsel disable yapmak istersen (opsiyonel)
        self._apply_gate_visual()

        outer.addWidget(self.left); outer.addWidget(content_card, 1)
        self._apply_theme()

    # ── Gate: Derslik var mı?
    def _has_any_classrooms(self) -> bool:
        """Koordinatör için kendi bölümünde derslik var mı? (Admin için her zaman True)"""
        if self.role_id == 1:
            return True
        if not self.dept_id:
            return False
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT COUNT(*) FROM dbo.Classrooms WHERE DepartmentID = ?",
                    (int(self.dept_id),)
                )
                cnt = cur.fetchone()[0] or 0
                return cnt > 0
        except Exception:
            return False

    def _apply_gate_visual(self):
        """İsteyene: Derslik yoksa gated itemları görsel olarak devre dışı göster."""
        if self.role_id == 1:
            return
        has_cls = self._has_any_classrooms()
        for i in range(self.left.count()):
            title = self.left.item(i).text()
            if title in getattr(self, "_gated_titles", set()):
                flags = self.left.item(i).flags()
                if has_cls:
                    self.left.item(i).setFlags(flags | Qt.ItemFlag.ItemIsEnabled)
                else:
                    self.left.item(i).setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled)

    def _on_menu_change(self, idx: int):
        """Seçim değişince: derslik yoksa gated menülere geçişi engelle ve uyar."""
        # Admin kısıtlanmaz:
        if self.role_id == 1:
            self.stack.setCurrentIndex(idx); return

        item = self.left.item(idx)
        title = item.text() if item else ""

        if title in getattr(self, "_gated_titles", set()):
            if not self._has_any_classrooms():
                QMessageBox.information(
                    self, "Bilgi",
                    "Önce en az bir derslik ekleyin. Derslik olmadan bu alan açılamaz."
                )
                # Derslikler sayfasına dön
                for i in range(self.left.count()):
                    if "Derslikler" in self.left.item(i).text():
                        self.left.setCurrentRow(i)
                        self.stack.setCurrentIndex(i)
                        self._apply_gate_visual()
                        return
                # Fallback: ilk sayfa
                self.left.setCurrentRow(0)
                self.stack.setCurrentIndex(0)
                self._apply_gate_visual()
                return

        # izin ver
        self.stack.setCurrentIndex(idx)
        # durum değişmiş olabilir; görünümü tazele
        self._apply_gate_visual()

    # ── Tema
    def _apply_theme(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {self.BG_START}, stop:1 {self.BG_END});
            }}
            QWidget#ContentCard {{
                background: {self.CARD_BG}; border-radius: 18px;
            }}
            QLabel#PageTitle {{ color: {self.TEXT_DARK}; font-size: 22px; font-weight: 800; }}
            QLabel#PageDesc  {{ color: {self.MUTED}; font-size: 13px; }}
            QListWidget {{
                background: #FFFFFF; border-right: 1px solid {self.BORDER}; font-size: 14px;
            }}
            QListWidget::item {{ height: 40px; padding-left: 12px; color: {self.TEXT_DARK}; }}
            QListWidget::item:hover {{ background: #F4F7FB; }}
            QListWidget::item:selected {{
                background: {self.ACCENT}; color: #FFFFFF; border-radius: 6px; margin: 2px 6px;
            }}
            QStatusBar {{ background: #FFFFFF; border-top: 1px solid {self.BORDER}; }}
            QStatusBar QLabel {{ color: {self.TEXT_DARK}; }}
        """)

    # ── Çıkış
    def _logout(self):
        reply = QMessageBox.question(
            self, "Çıkış", "Oturumu kapatıp giriş ekranına dönmek istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.logged_out.emit()
            self.close()
