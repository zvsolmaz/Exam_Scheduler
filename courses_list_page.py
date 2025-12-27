
# courses_list_page.py
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame
)
from auth import get_connection

ROLE_ADMIN = 1
ROLE_COORD  = 2

class CoursesListPage(QWidget):
    def __init__(self, user: dict):
        super().__init__()
        self.user = user or {}
        self.role = int(self.user.get("role_id") or self.user.get("RoleID") or ROLE_COORD)
        self.dept = self.user.get("department_id") or self.user.get("DepartmentID")

        self.setStyleSheet("""
            QLabel#Title    { font-size:22px; font-weight:800; color:#0B1324; }
            QLabel#Subtitle { color:#6B7280; }
            QFrame#Card     { background:#FFFFFF; border-radius:16px; border:1px solid #E5E7EB; }
            QTableWidget {
                background:#FFFFFF; border:1px solid #E5E7EB; border-radius:12px;
                gridline-color:#EEF1F4; alternate-background-color:#FAFAFB;
            }
            QHeaderView::section {
                background:#F3F4F6; border:none; padding:10px; font-weight:800; font-size:13px;
            }
        """)

        root = QVBoxLayout(self); root.setSpacing(12); root.setContentsMargins(12,12,12,12)
        t = QLabel("Ders Listesi"); t.setObjectName("Title")
        s = QLabel("Excel’den gelen dersler burada listelenir. Bir derse tıklayınca dersi alan öğrenciler gösterilir.")
        s.setObjectName("Subtitle")
        root.addWidget(t); root.addWidget(s)

        card = QFrame(); card.setObjectName("Card")
        hl = QHBoxLayout(card); hl.setContentsMargins(14,14,14,14); hl.setSpacing(12)

        # Sol: Dersler
        self.tbl_courses = QTableWidget(0, 2)
        self.tbl_courses.setHorizontalHeaderLabels(["Ders Kodu", "Ders Adı"])
        self.tbl_courses.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_courses.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_courses.setAlternatingRowColors(True)
        self.tbl_courses.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_courses.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl_courses.itemSelectionChanged.connect(self._on_course_selected)
        self.tbl_courses.verticalHeader().setVisible(False)  # ← EK: satır numarasını gizle
        hl.addWidget(self.tbl_courses, 1)

        # Sağ: Öğrenciler
        right = QVBoxLayout(); right.setSpacing(8)
        self.lbl_right = QLabel("Dersi Alan Öğrenciler: —")
        right.addWidget(self.lbl_right)

        self.tbl_students = QTableWidget(0, 2)
        self.tbl_students.setHorizontalHeaderLabels(["Öğrenci No", "Ad Soyad"])
        self.tbl_students.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_students.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_students.setAlternatingRowColors(True)
        self.tbl_students.verticalHeader().setVisible(False)  # ← EK: satır numarasını gizle
        right.addWidget(self.tbl_students, 1)

        hl.addLayout(right, 1)
        root.addWidget(card, 1)

        # İlk yükleme
        self._load_courses()

    # sayfaya her gelişte dersleri tazele (excel yüklemeden sonra işe yarar)
    def showEvent(self, e):
        super().showEvent(e)
        self._load_courses()

    # ---------------- DB ----------------
    def _load_courses(self):
        self.tbl_courses.setRowCount(0)
        q = "SELECT CourseID, DepartmentID, Code, Name FROM dbo.Courses"
        params = ()
        if self.role != ROLE_ADMIN and self.dept:
            q += " WHERE DepartmentID = ?"
            params = (int(self.dept),)
        q += " ORDER BY DepartmentID, Code"

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(q, params)
            rows = cur.fetchall()

        for r in rows:
            row = self.tbl_courses.rowCount()
            self.tbl_courses.insertRow(row)

            it_code = QTableWidgetItem(r.Code or "")
            it_code.setData(Qt.ItemDataRole.UserRole, int(r.CourseID))  # CourseID’yi sakla
            it_name = QTableWidgetItem(r.Name or "")

            # hizalama
            it_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_courses.setItem(row, 0, it_code)
            self.tbl_courses.setItem(row, 1, it_name)

        # otomatik ilk satırı seç
        if self.tbl_courses.rowCount() > 0:
            self.tbl_courses.selectRow(0)
            self._on_course_selected()
        else:
            self.lbl_right.setText("Dersi Alan Öğrenciler: —")
            self.tbl_students.setRowCount(0)

    def _on_course_selected(self):
        r = self.tbl_courses.currentRow()
        if r < 0:
            self.tbl_students.setRowCount(0)
            self.lbl_right.setText("Dersi Alan Öğrenciler: —")
            return

        code = (self.tbl_courses.item(r, 0).text() if self.tbl_courses.item(r, 0) else "")
        name = (self.tbl_courses.item(r, 1).text() if self.tbl_courses.item(r, 1) else "")
        course_id = self.tbl_courses.item(r, 0).data(Qt.ItemDataRole.UserRole)

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT sc.StudentNo, ISNULL(s.FullName,'') AS FullName
                  FROM dbo.StudentCourses sc
                  LEFT JOIN dbo.Students s ON s.StudentNo = sc.StudentNo
                 WHERE sc.CourseID = ?
                 ORDER BY sc.StudentNo
            """, (int(course_id),))
            rows = cur.fetchall()

        # EK: başlığı öğrenci sayısıyla güncelle
        self.lbl_right.setText(f"Dersi Alan Öğrenciler: {code} — {name} (Toplam: {len(rows)})")

        self.tbl_students.setRowCount(0)
        for rr in rows:
            row = self.tbl_students.rowCount()
            self.tbl_students.insertRow(row)

            # EK: Öğrenci no'yu güvenli biçimde stringe çevir
            no_text = str(getattr(rr, "StudentNo", "") or "")
            it_no = QTableWidgetItem(no_text)
            it_no.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tbl_students.setItem(row, 0, it_no)
            self.tbl_students.setItem(row, 1, QTableWidgetItem(rr.FullName or ""))
