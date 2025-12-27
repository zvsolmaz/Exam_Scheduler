from __future__ import annotations
from typing import List, Tuple
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QMessageBox, QFrame, QSizePolicy, QComboBox
)

from db import get_connection
from auth import get_department_name


# ───────────── DB yardımcıları ─────────────
def _find_student_with_courses(student_no_input: str) -> List[Tuple]:
    """
    Öğrenci numarasına göre öğrenciyi ve derslerini getirir.
    INT / NVARCHAR farkına takılmadan eşleşir.
    Dönüş: [(StudentNo, FullName, CourseCode, CourseName)]
    """
    raw = (student_no_input or "").strip()
    if not raw:
        return []

    try:
        as_int = int(raw)
    except ValueError:
        as_int = None

    conn = get_connection()
    cur = conn.cursor()

    if as_int is not None:
        cur.execute(
            """
            SELECT s.StudentNo, s.FullName, c.Code, c.Name
            FROM dbo.Students s
            LEFT JOIN dbo.StudentCourses sc ON sc.StudentNo = s.StudentNo
            LEFT JOIN dbo.Courses c          ON c.CourseID   = sc.CourseID
            WHERE CAST(s.StudentNo AS NVARCHAR(64)) = ? OR s.StudentNo = ?
            ORDER BY c.Code
            """,
            (raw, as_int)
        )
    else:
        cur.execute(
            """
            SELECT s.StudentNo, s.FullName, c.Code, c.Name
            FROM dbo.Students s
            LEFT JOIN dbo.StudentCourses sc ON sc.StudentNo = s.StudentNo
            LEFT JOIN dbo.Courses c          ON c.CourseID   = sc.CourseID
            WHERE CAST(s.StudentNo AS NVARCHAR(64)) = ?
            ORDER BY c.Code
            """,
            (raw,)
        )

    rows = cur.fetchall()
    conn.close()
    return rows


def _list_students_with_courses_by_department(department_id: int, limit: int = 1000) -> List[Tuple]:
    """
    Bölüm bazında öğrenci + derslerini getirir.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT TOP (?) s.StudentNo, s.FullName, c.Code, c.Name
        FROM dbo.Students s
        LEFT JOIN dbo.StudentCourses sc ON sc.StudentNo = s.StudentNo
        LEFT JOIN dbo.Courses c          ON c.CourseID   = sc.CourseID
        WHERE s.DepartmentID = ?
        ORDER BY s.StudentNo, c.Code
        """,
        (int(limit), int(department_id))
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# ───────────── Sayfa ─────────────
class StudentsListPage(QWidget):
    """
    Öğrenci Listesi Sayfası:
      - Öğrenci No ile arama
      - Koordinatör: kendi bölümünü listeleyebilir
      - Admin: istediği bölümü seçip listeleyebilir
    """
    def __init__(self, user: dict):
        super().__init__()
        self.user = user or {}
        self._role_id = int(self.user.get("role_id") or self.user.get("RoleID") or 2)
        self._dept_id = self.user.get("department_id") or self.user.get("DepartmentID")
        try:
            self._dept_id = int(self._dept_id) if self._dept_id is not None else None
        except Exception:
            self._dept_id = None

        self._build_ui()

    # ───────────────── UI ─────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Başlık
        title = QLabel("Öğrenci Listesi"); title.setObjectName("Title")
        subtitle = QLabel("Öğrenci numarasına göre ara veya bölümdeki öğrencileri listele.")
        subtitle.setObjectName("Subtitle")

        head = QVBoxLayout(); head.addWidget(title); head.addWidget(subtitle)
        root.addLayout(head)

        self.setStyleSheet("""
            QLabel#Title { font-size:22px; font-weight:800; color:#0B1324; }
            QLabel#Subtitle { color:#6B7280; }
            QFrame#Card { background:#FFFFFF; border:1px solid #E5E7EB; border-radius:12px; }
            QPushButton#Primary { background:#1E7C45; color:white; border:none; border-radius:10px; padding:8px 14px; font-weight:700; }
            QPushButton#Ghost { background:#EEF2F7; color:#0F172A; border:1px solid #E5E7EB; border-radius:10px; padding:8px 12px; font-weight:600; }
            QLineEdit { border:1px solid #E1E7EF; border-radius:10px; padding:8px 10px; background:#FAFBFD; }
            QLineEdit:focus { border:1px solid #1E7C45; background:#FFFFFF; }
        """)

        # Ana kart
        card = QFrame(); card.setObjectName("Card")
        cv = QVBoxLayout(card); cv.setContentsMargins(12, 12, 12, 12); cv.setSpacing(10)

        # Arama satırı
        row = QHBoxLayout()
        self.ed_search = QLineEdit(placeholderText="Öğrenci No girin (örn: 210059017)")
        self.ed_search.returnPressed.connect(self._do_search)
        btn_search = QPushButton("Ara"); btn_search.setObjectName("Primary"); btn_search.clicked.connect(self._do_search)
        row.addWidget(QLabel("Ara:")); row.addWidget(self.ed_search, 1); row.addWidget(btn_search)

        # Bölüm seçici
        row2 = QHBoxLayout()
        if self._role_id == 1:
            # Admin için: tüm bölümleri dropdown’dan yükle
            self.cmb_dept = QComboBox()
            self.cmb_dept.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._load_departments()
            btn_list = QPushButton("Seçili Bölümü Listele")
            btn_list.setObjectName("Ghost")
            btn_list.clicked.connect(self._list_department_students)
            row2.addWidget(QLabel("Bölüm:"))
            row2.addWidget(self.cmb_dept, 1)
            row2.addWidget(btn_list, 0)
        else:
            # Koordinatör: sadece kendi bölümü
            name = get_department_name(self._dept_id) or f"Bölüm #{self._dept_id or '—'}"
            lbl = QLabel(f"Bu sayfa bölümünüzü listeler:  {name}")
            lbl.setStyleSheet("color:#374151;")
            btn_list = QPushButton("Bölümümü Listele")
            btn_list.setObjectName("Ghost")
            btn_list.clicked.connect(self._list_department_students)
            row2.addWidget(lbl, 1)
            row2.addStretch(1)
            row2.addWidget(btn_list)

        cv.addLayout(row)
        cv.addLayout(row2)

        # Tablo
        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["Öğrenci No", "Ad Soyad", "Ders Kodu", "Ders Adı"])
        self.tbl.setSelectionBehavior(self.tbl.SelectionBehavior.SelectRows)
        cv.addWidget(self.tbl)

        root.addWidget(card)

    # ───────────── yardımcılar ─────────────
    def _load_departments(self):
        """Admin görünümünde combobox’a tüm bölümleri yükler."""
        self.cmb_dept.clear()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT DepartmentID, Name FROM dbo.Departments ORDER BY DepartmentID")
        rows = cur.fetchall()
        conn.close()

        if not rows:
            self.cmb_dept.addItem("Bölüm bulunamadı", -1)
        else:
            for dep in rows:
                self.cmb_dept.addItem(f"{dep.Name} (#{dep.DepartmentID})", dep.DepartmentID)

    # ───────────── actions ─────────────
    def _do_search(self):
        q = (self.ed_search.text() or "").strip()
        if not q:
            QMessageBox.information(self, "Bilgi", "Lütfen bir öğrenci numarası girin.")
            return

        rows = _find_student_with_courses(q)
        self._fill_table(rows)
        if not rows:
            QMessageBox.warning(self, "Bulunamadı", f"Öğrenci bulunamadı: {q}")

    def _list_department_students(self):
        """Seçili bölüm veya mevcut bölümdeki öğrencileri listeler."""
        if self._role_id == 1:
            if hasattr(self, "cmb_dept") and self.cmb_dept.count() > 0:
                dept_id = int(self.cmb_dept.currentData())
                if dept_id < 0:
                    QMessageBox.information(self, "Bilgi", "Geçerli bir bölüm seçin.")
                    return
            else:
                QMessageBox.warning(self, "Uyarı", "Hiç bölüm bulunamadı.")
                return
        else:
            dept_id = self._dept_id

        if not dept_id:
            QMessageBox.information(self, "Bilgi", "Bölüm bilgisi bulunamadı.")
            return

        rows = _list_students_with_courses_by_department(int(dept_id), limit=1000)
        self._fill_table(rows)
        if not rows:
            QMessageBox.information(self, "Bilgi", "Bu bölümde kayıtlı öğrenci/ders bulunamadı.")

    def _fill_table(self, rows: List[Tuple]):
        """Tabloyu doldurur."""
        self.tbl.setRowCount(0)
        for (stu_no, full_name, code, name) in rows:
            i = self.tbl.rowCount()
            self.tbl.insertRow(i)
            self.tbl.setItem(i, 0, QTableWidgetItem(str(stu_no)))
            self.tbl.setItem(i, 1, QTableWidgetItem(full_name or ""))
            self.tbl.setItem(i, 2, QTableWidgetItem(code or "—"))
            self.tbl.setItem(i, 3, QTableWidgetItem(name or "—"))
        self.tbl.resizeColumnsToContents()
