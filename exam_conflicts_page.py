# exam_conflicts_page.py — Öğrenci sınav çakışmalarını listeleme
from __future__ import annotations
from typing import List, Tuple
from datetime import datetime, timedelta
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QDateEdit, QComboBox, QSpinBox, QMessageBox, QSizePolicy
)

from db import get_connection
from auth import get_department_name

ROLE_ADMIN = 1

class ExamConflictsPage(QWidget):
    """
    Seçilen tarih aralığı + sınav türü + (gerekirse) bölüm için
    öğrencilerin sınav çakışmalarını listeler.

    - Zaman çakışması: A.EndDT > B.StartDT
    - Bekleme kuralı ihlali: (B.StartDT - A.EndDT) < buffer_min (dk)
    """
    def __init__(self, user: dict):
        super().__init__()
        self.user = user or {}
        self.role_id = int(self.user.get("role_id") or self.user.get("RoleID") or 2)
        self.dept_id = self.user.get("department_id") or self.user.get("DepartmentID")
        try:
            self.dept_id = int(self.dept_id) if self.dept_id is not None else None
        except Exception:
            self.dept_id = None

        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        self.setStyleSheet("""
            QLabel#Title { font-size:22px; font-weight:800; color:#0B1324; }
            QLabel#Subtitle { color:#6B7280; }
            QFrame#Card { background:#FFFFFF; border:1px solid #E5E7EB; border-radius:12px; }
            QPushButton#Primary { background:#2F6FED; color:white; border:none; border-radius:10px; padding:8px 14px; font-weight:700; }
            QPushButton#Ghost { background:#EEF2F7; color:#0F172A; border:1px solid #E5E7EB; border-radius:10px; padding:8px 12px; font-weight:600; }
            QTableWidget { background:#FFFFFF; border:1px solid #E5E7EB; border-radius:12px;
                           gridline-color:#EEF1F4; alternate-background-color:#FAFAFB; }
            QHeaderView::section { background:#F3F4F6; border:none; padding:10px; font-weight:800; font-size:13px; }
        """)

        root = QVBoxLayout(self); root.setContentsMargins(12,12,12,12); root.setSpacing(10)
        title = QLabel("Sınav Çakışmaları"); title.setObjectName("Title")
        subtitle = QLabel("Seçili aralıkta aynı öğrencinin çakışan veya bekleme süresi ihlal edilen sınavlarını gösterir.")
        subtitle.setObjectName("Subtitle")
        root.addWidget(title); root.addWidget(subtitle)

        # Kart: filtreler + butonlar
        card = QFrame(); card.setObjectName("Card")
        cv = QVBoxLayout(card); cv.setContentsMargins(12,12,12,12); cv.setSpacing(8)

        # Üst satır: Tarih aralığı + Tür + Buffer + Bölüm (admin ise seçilebilir)
        row = QHBoxLayout(); row.setSpacing(10)

        row.addWidget(QLabel("Tarih aralığı:"))
        self.start_date = QDateEdit(); self.start_date.setCalendarPopup(True)
        self.end_date   = QDateEdit(); self.end_date.setCalendarPopup(True)
        today = QDate.currentDate()
        self.start_date.setDate(today)
        self.end_date.setDate(today.addDays(14))
        row.addWidget(self.start_date); row.addWidget(QLabel("—")); row.addWidget(self.end_date)

        row.addSpacing(12)
        row.addWidget(QLabel("Sınav Türü:"))
        self.cmb_exam_type = QComboBox(); self.cmb_exam_type.addItems(["Vize", "Final", "Bütünleme"])
        row.addWidget(self.cmb_exam_type)

        row.addSpacing(12)
        row.addWidget(QLabel("Bekleme (dk):"))
        self.sp_buffer = QSpinBox(); self.sp_buffer.setRange(0, 240); self.sp_buffer.setValue(15)
        row.addWidget(self.sp_buffer)

        row.addSpacing(12)
        if self.role_id == ROLE_ADMIN:
            row.addWidget(QLabel("Bölüm:"))
            self.cmb_dept = QComboBox(); self._load_departments()
            self.cmb_dept.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            row.addWidget(self.cmb_dept)
        else:
            dept_name = get_department_name(self.dept_id) if self.dept_id is not None else None
            display   = dept_name if dept_name else (f"#{self.dept_id}" if self.dept_id else "—")
            lbl = QLabel(f"Bölümünüz: {display}")
            row.addWidget(lbl)

        row.addStretch(1)

        self.btn_check = QPushButton("Çakışmaları Kontrol Et"); self.btn_check.setObjectName("Primary")
        self.btn_check.clicked.connect(self._run_check)
        row.addWidget(self.btn_check)

        cv.addLayout(row)
        root.addWidget(card)

        # Tablo
        self.tbl = QTableWidget(0, 9)
        self.tbl.setHorizontalHeaderLabels([
            "Öğrenci No", "Ad Soyad", "Tarih",
            "A Başlangıç", "A Bitiş", "Ders A (Kod — Ad)",
            "B Başlangıç", "B Bitiş", "Ders B (Kod — Ad)"
        ])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.tbl, 1)

        # Alt özet
        self.lbl_summary = QLabel("—"); self.lbl_summary.setObjectName("Subtitle")
        root.addWidget(self.lbl_summary)

    def _load_departments(self):
        self.cmb_dept.clear()
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT DepartmentID, Name FROM dbo.Departments ORDER BY Name")
            for r in cur.fetchall():
                self.cmb_dept.addItem(r.Name, int(r.DepartmentID))
        # varsa kullanıcı bölümünü seç
        if self.dept_id:
            idx = self.cmb_dept.findData(int(self.dept_id))
            if idx >= 0: self.cmb_dept.setCurrentIndex(idx)

    # ---------- Actions ----------
    def _run_check(self):
        # tarih doğrulama
        sd = self.start_date.date().toPyDate()
        ed = self.end_date.date().toPyDate()
        if ed < sd:
            QMessageBox.warning(self, "Uyarı", "Bitiş tarihi başlangıçtan önce olamaz."); return

        dept_id = self._get_dept_id()
        if not dept_id:
            QMessageBox.warning(self, "Uyarı", "Bölüm bilgisi yok."); return

        exam_type = self.cmb_exam_type.currentText()
        buffer_min = int(self.sp_buffer.value())
        try:
            rows = self._fetch_conflicts(dept_id, exam_type, sd, ed, buffer_min)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kontrol yapılamadı:\n{e}")
            return

        self._fill_table(rows)
        if not rows:
            self.lbl_summary.setText("Çakışma bulunmadı.")
        else:
            uniq_students = len({r[0] for r in rows})
            self.lbl_summary.setText(f"Toplam {len(rows)} çakışma • {uniq_students} öğrenci")

    def _get_dept_id(self) -> int | None:
        if self.role_id == ROLE_ADMIN and hasattr(self, "cmb_dept"):
            data = self.cmb_dept.currentData()
            return int(data) if data is not None else None
        return self.dept_id

    # ---------- DB ----------
    def _fetch_conflicts(self, department_id: int, exam_type: str,
                         date_start, date_end, buffer_min: int) -> List[Tuple]:
        """
        Dönüş: list of tuples:
          (StudentNo, FullName, Date, AStart, AEnd, CodeA, NameA, BStart, BEnd, CodeB, NameB)
        A: daha erken başlayan sınav, B: sonra başlayan.
        Çakışma koşulu: DATEDIFF(min, A.EndDT, B.StartDT) < buffer_min
        (negatif ise gerçek zaman çakışması; 0..buffer-1 ise bekleme ihlali)
        """
        end_exclusive = datetime.combine(date_end, datetime.min.time()) + timedelta(days=1)

        conn = get_connection(); cur = conn.cursor()
        # A: öğrenciye ait sınav atamaları
        # Not: Hem Students hem Courses ile bölüm filtresi (veri tutarlılığı için)
        q = f"""
        WITH Assignments AS (
            SELECT
                sc.StudentNo,
                ISNULL(s.FullName, '') AS FullName,
                c.CourseID,
                c.Code AS CourseCode,
                c.Name AS CourseName,
                e.ExamType,
                e.StartDT,
                DATEADD(MINUTE, e.DurationMin, e.StartDT) AS EndDT
            FROM dbo.StudentCourses sc
            INNER JOIN dbo.Students  s ON s.StudentNo = sc.StudentNo
            INNER JOIN dbo.Courses   c ON c.CourseID  = sc.CourseID
            INNER JOIN dbo.Exams     e ON e.CourseID  = c.CourseID AND e.ExamType = ?
            WHERE s.DepartmentID = ? AND c.DepartmentID = ?
              AND e.StartDT >= ? AND e.StartDT < ?
        )
        SELECT
            a.StudentNo, a.FullName,
            CAST(a.StartDT AS date) AS TheDate,
            a.StartDT AS AStart, a.EndDT AS AEnd, a.CourseCode AS CodeA, a.CourseName AS NameA,
            b.StartDT AS BStart, b.EndDT AS BEnd, b.CourseCode AS CodeB, b.CourseName AS NameB
        FROM Assignments a
        INNER JOIN Assignments b
            ON a.StudentNo = b.StudentNo
           AND a.StartDT < b.StartDT  -- çift sayım olmasın
        WHERE DATEDIFF(MINUTE, a.EndDT, b.StartDT) < ?
        ORDER BY a.StudentNo, a.StartDT, b.StartDT
        """
        cur.execute(q, (exam_type, int(department_id), int(department_id),
                        date_start, end_exclusive, int(buffer_min)))
        rows = cur.fetchall()
        conn.close()

        # PyQt tabloda rahat göstermek için tuple'a dönüştür
        out = []
        for r in rows:
            out.append((
                str(r.StudentNo),
                r.FullName or "",
                r.TheDate,                      # date
                r.AStart, r.AEnd,               # datetimes
                r.CodeA, r.NameA,
                r.BStart, r.BEnd,               # datetimes
                r.CodeB, r.NameB,
            ))
        return out

    # ---------- Fill table ----------
    def _fill_table(self, rows: List[Tuple]):
        self.tbl.setRowCount(0)
        for (stu_no, full_name, d, a_start, a_end, code_a, name_a, b_start, b_end, code_b, name_b) in rows:
            i = self.tbl.rowCount()
            self.tbl.insertRow(i)

            def dt_str(dt): return (dt.strftime("%H:%M") if isinstance(dt, datetime) else "")
            def date_str(x): return x.strftime("%Y-%m-%d")

            self.tbl.setItem(i, 0, self._center_item(stu_no))
            self.tbl.setItem(i, 1, QTableWidgetItem(full_name))
            self.tbl.setItem(i, 2, self._center_item(date_str(d)))
            self.tbl.setItem(i, 3, self._center_item(dt_str(a_start)))
            self.tbl.setItem(i, 4, self._center_item(dt_str(a_end)))
            self.tbl.setItem(i, 5, QTableWidgetItem(f"{code_a} — {name_a}"))
            self.tbl.setItem(i, 6, self._center_item(dt_str(b_start)))
            self.tbl.setItem(i, 7, self._center_item(dt_str(b_end)))
            self.tbl.setItem(i, 8, QTableWidgetItem(f"{code_b} — {name_b}"))

        # genişlik ve hizalar
        self.tbl.resizeColumnsToContents()
        self.tbl.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)

    def _center_item(self, text) -> QTableWidgetItem:
        it = QTableWidgetItem("" if text is None else str(text))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return it
