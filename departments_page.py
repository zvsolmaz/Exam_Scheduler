# departments_page.py
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame
)
from PyQt6.QtCore import Qt

from db import get_connection


class DepartmentsPage(QWidget):
    """
    Admin görünümünde bölümleri listeler.
    Tablo: DepartmentID | Bölüm Adı | Ders Sayısı | Öğrenci Sayısı
    """
    def __init__(self, user: dict):
        super().__init__()
        self.user = user or {}
        self._build_ui()
        self._load_departments()

    # ───────── UI
    def _build_ui(self):
        self.setStyleSheet("""
            QLabel#Title { font-size:22px; font-weight:800; color:#0B1324; }
            QLabel#Subtitle { color:#6B7280; }
            QFrame#Card { background:#FFFFFF; border:1px solid #E5E7EB; border-radius:12px; }
            QPushButton#Primary { background:#1E7C45; color:white; border:none; border-radius:10px; padding:8px 14px; font-weight:700; }
            QPushButton#Ghost { background:#EEF2F7; color:#0F172A; border:1px solid #E5E7EB; border-radius:10px; padding:8px 12px; font-weight:600; }
            QLineEdit { border:1px solid #E1E7EF; border-radius:10px; padding:8px 10px; background:#FAFBFD; }
            QLineEdit:focus { border:1px solid #1E7C45; background:#FFFFFF; }
        """)

        root = QVBoxLayout(self); root.setContentsMargins(12,12,12,12); root.setSpacing(10)

        title = QLabel("Bölümler"); title.setObjectName("Title")
        sub   = QLabel("Sistemde kayıtlı tüm bölümler."); sub.setObjectName("Subtitle")
        head  = QVBoxLayout(); head.addWidget(title); head.addWidget(sub)
        root.addLayout(head)

        card = QFrame(); card.setObjectName("Card")
        cv   = QVBoxLayout(card); cv.setContentsMargins(12,12,12,12); cv.setSpacing(10)

        # üst araç çubuğu
        tools = QHBoxLayout()
        self.ed_search = QLineEdit(); self.ed_search.setPlaceholderText("Bölüm adı içinde ara…")
        btn_search = QPushButton("Ara"); btn_search.setObjectName("Ghost")
        btn_search.clicked.connect(self._filter_table)
        btn_clear  = QPushButton("Temizle"); btn_clear.setObjectName("Ghost")
        btn_clear.clicked.connect(lambda: (self.ed_search.clear(), self._filter_table()))
        btn_refresh = QPushButton("Yenile"); btn_refresh.setObjectName("Primary")
        btn_refresh.clicked.connect(self._load_departments)
        tools.addWidget(self.ed_search, 1)
        tools.addWidget(btn_search)
        tools.addWidget(btn_clear)
        tools.addStretch(1)
        tools.addWidget(btn_refresh)
        cv.addLayout(tools)

        # tablo
        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["ID", "Bölüm Adı", "Ders Sayısı", "Öğrenci Sayısı"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tbl.setSelectionBehavior(self.tbl.SelectionBehavior.SelectRows)
        cv.addWidget(self.tbl)

        root.addWidget(card)

    # ───────── Data
    def _load_departments(self):
        self._all_rows = []  # filtreleme için cache
        self.tbl.setRowCount(0)
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT D.DepartmentID,
                       D.Name,
                       ISNULL(Cc.TotalCourses, 0)  AS CourseCount,
                       ISNULL(Sc.TotalStudents, 0) AS StudentCount
                FROM dbo.Departments D
                LEFT JOIN (SELECT DepartmentID, COUNT(*) AS TotalCourses
                           FROM dbo.Courses GROUP BY DepartmentID) Cc
                       ON Cc.DepartmentID = D.DepartmentID
                LEFT JOIN (SELECT DepartmentID, COUNT(*) AS TotalStudents
                           FROM dbo.Students GROUP BY DepartmentID) Sc
                       ON Sc.DepartmentID = D.DepartmentID
                ORDER BY D.DepartmentID
            """)
            rows = cur.fetchall()

        for r in rows:
            self._all_rows.append((r.DepartmentID, r.Name, r.CourseCount, r.StudentCount))

        self._render_rows(self._all_rows)

    def _render_rows(self, rows):
        self.tbl.setRowCount(0)
        for dep_id, name, course_cnt, stu_cnt in rows:
            i = self.tbl.rowCount()
            self.tbl.insertRow(i)
            self.tbl.setItem(i, 0, self._cell(dep_id, center=True))
            self.tbl.setItem(i, 1, self._cell(name))
            self.tbl.setItem(i, 2, self._cell(course_cnt, center=True))
            self.tbl.setItem(i, 3, self._cell(stu_cnt, center=True))

    def _filter_table(self):
        q = (self.ed_search.text() or "").strip().lower()
        if not q:
            self._render_rows(self._all_rows); return
        filt = [row for row in self._all_rows if q in (row[1] or "").lower()]
        self._render_rows(filt)

    # helpers
    def _cell(self, value, center=False):
        it = QTableWidgetItem("" if value is None else str(value))
        if center:
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return it
