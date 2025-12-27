# exam_program_page.py
from __future__ import annotations

from typing import List, Dict, Any, Set, Optional
from datetime import date
from PyQt6.QtCore import Qt, QDate, QSize
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox,
    QDateEdit, QCheckBox, QListWidget, QListWidgetItem, QSpinBox,
    QFileDialog, QComboBox, QLineEdit, QAbstractSpinBox
)

# DB
from db import get_connection

# Planlama & dışa aktarma + ayrıntılı hata sınıfları
from scheduler_core import (
    generate_schedule, Constraints,
    SchedulingError, DateRangeError, ClassroomNotFoundError,
    CapacityError, StudentOverlapError
)
from export_excel import export_schedule_to_excel
from exams_repo import overwrite_and_insert_scoped

ACCENT     = "#2F6FED"
CARD_BG    = "#FFFFFF"
BORDER     = "#E5E7EB"
TEXT_DARK  = "#0B1324"
MUTED      = "#6B7280"
SUCCESS_BG = "#ECFDF5"
SUCCESS_BR = "#A7F3D0"

# Liste satırı yüksekliği (px)
ROW_H = 46


def _h1(text: str) -> QLabel:
    l = QLabel(text)
    l.setProperty("class", "h1")
    return l


def _muted(text: str) -> QLabel:
    l = QLabel(text)
    l.setProperty("class", "muted")
    return l


class ExamProgramPage(QWidget):
    """
    Sınav Programı Oluştur — başlık butonları ile açılan bölümler:
      1) Ders Seçimi / Süre İstisnaları
         ├─ Süre İstisnaları (Tüm Dersler)
         └─ Program Dışı (Hariç)
      2) Tarih/Gün
      3) Tür
      4) Süre / Bekleme
    """

    # ───────────────────────── init / UI ─────────────────────────
    def __init__(self, user: dict):
        super().__init__()
        self.user = user or {}

        # Rol bilgisi (admin=1, koordinatör=2 varsayım)
        self._role_id = int(self.user.get("role_id") or self.user.get("RoleID") or 2)
        self._is_admin = (self._role_id == 1)

        self.setObjectName("ExamProgramPage")
        self.setStyleSheet(f"""
            QLabel[class="h1"] {{
                font-size:22px; font-weight:800; color:{TEXT_DARK};
            }}
            QLabel[class="muted"] {{ color:{MUTED}; }}

            QFrame#Card {{
                background:{CARD_BG}; border:1px solid {BORDER}; border-radius:12px;
            }}

            /* Bölüm başlığı (accordion) */
            QPushButton.Section {{
                text-align:left; padding:12px 14px; border:none; border-radius:10px;
                background:#F6FAFF; font-weight:800; color:{TEXT_DARK};
            }}
            QPushButton.Section:hover {{ background:#ECF3FF; }}
            QPushButton.Section:checked {{ background:#E7F0FF; }}

            /* Alt panel kartı */
            QFrame#SubCard {{
                background:#F9FAFB; border:1px solid {BORDER}; border-radius:12px;
            }}

            /* Küçük açıklamalar */
            QLabel[counter] {{ color:{MUTED}; }}

            QLineEdit {{
                border:1px solid #E1E7EF; border-radius:10px; padding:8px 10px; background:#FAFBFD;
            }}
            QLineEdit:focus {{ border:1px solid {ACCENT}; background:#FFFFFF; }}

            QListWidget {{
                background:#FFFFFF; border:1px solid {BORDER}; border-radius:10px;
            }}

            QPushButton#Primary {{
                background:{ACCENT}; color:white; border:none; border-radius:10px;
                padding:10px 16px; font-weight:700;
            }}
            QPushButton#Ghost {{
                background:#EEF2F7; color:#0F172A; border:1px solid #E5E7EB;
                border-radius:10px; padding:10px 14px; font-weight:600;
            }}

            QTableWidget {{ background:#FFFFFF; border:1px solid {BORDER}; border-radius:12px; }}
            QHeaderView::section {{
                background:#F5F7FB; color:{TEXT_DARK}; border:none; padding:10px; font-weight:800;
            }}

            /* Süre istisna satırı */
            QFrame#DurRow {{
                background:#FFFFFF; border:1px solid {BORDER};
                border-radius:10px; padding:8px; min-height:{ROW_H}px;
            }}
            QFrame#DurRow[active="true"] {{
                background:{SUCCESS_BG}; border:1px solid {SUCCESS_BR};
            }}
            QLabel#DurLbl {{ color:{TEXT_DARK}; }}

            /* Geniş ve okunaklı spinbox */
            QSpinBox#DurSpin {{
                min-width:130px;
                border:1px solid {SUCCESS_BR}; border-radius:8px; padding:2px 6px;
                background:#FFFFFF;
            }}
            QSpinBox#DurSpin:focus {{ border:1px solid #10B981; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(_h1("Sınav Programı Oluştur"))
        root.addWidget(_muted("Bölüm başlıklarına tıklayarak paneli aç/kapatın. İşlemler sonunda ‘Programı Oluştur’ deyin."))

        # ── Bölüm kartı
        card = QFrame(); card.setObjectName("Card")
        cv = QVBoxLayout(card); cv.setContentsMargins(12, 12, 12, 12); cv.setSpacing(10)

        # (YENİ) Admin'e bölüm seçici
        self.cmb_dept: Optional[QComboBox] = None
        if self._is_admin:
            top = QHBoxLayout()
            top.addWidget(QLabel("Bölüm:"))
            self.cmb_dept = QComboBox()
            self._load_departments_for_admin()
            top.addWidget(self.cmb_dept, 1)
            cv.addLayout(top)

        # 1) Ders / Süre
        self.btn_sec1 = self._mk_section_button("Ders Seçimi / Süre İstisnaları")
        self.pnl_sec1 = self._mk_section_container()
        cv.addWidget(self.btn_sec1); cv.addWidget(self.pnl_sec1)

        sec1v = QVBoxLayout(self.pnl_sec1); sec1v.setContentsMargins(10, 10, 10, 10); sec1v.setSpacing(10)

        # 1a) Süre İstisnaları (tüm dersler)
        self.btn_dur = self._mk_section_button("▸ Süre İstisnaları (Tüm Dersler)", small=True)
        self.pnl_dur = self._mk_subcard()
        sec1v.addWidget(self.btn_dur); sec1v.addWidget(self.pnl_dur)

        dur = QVBoxLayout(self.pnl_dur); dur.setContentsMargins(12, 12, 12, 12); dur.setSpacing(8)
        self.lbl_counter = QLabel(); self.lbl_counter.setProperty("counter", True)
        self.lbl_counter.setText("Dahil: 0 • Hariç: 0 • İstisna: 0")
        dur.addWidget(self.lbl_counter)

        srow = QHBoxLayout()
        self.ed_search_dur = QLineEdit(placeholderText="Süre panelinde ara (kod/ad)…")
        self.btn_clear_over = QPushButton("İstisnaları Temizle"); self.btn_clear_over.setObjectName("Ghost")
        self.btn_clear_over.clicked.connect(self._clear_overrides)
        srow.addWidget(self.ed_search_dur, 1); srow.addWidget(self.btn_clear_over, 0)
        dur.addLayout(srow)

        self.list_durations = QListWidget()
        self.list_durations.setUniformItemSizes(False)
        self.list_durations.setSpacing(6)
        dur.addWidget(self.list_durations)

        # 1b) Program Dışı (alt)
        self.btn_exc = self._mk_section_button("▸ Program Dışı (Hariç)", small=True)
        self.pnl_exc = self._mk_subcard()
        sec1v.addWidget(self.btn_exc); sec1v.addWidget(self.pnl_exc)

        exc = QVBoxLayout(self.pnl_exc); exc.setContentsMargins(12, 12, 12, 12); exc.setSpacing(8)

        ed_row = QHBoxLayout()
        self.ed_search_exc = QLineEdit(placeholderText="Hariç panelinde ara (kod/ad)…")
        self.btn_all_ex = QPushButton("Tümünü Hariç"); self.btn_all_ex.setObjectName("Ghost")
        self.btn_all_in = QPushButton("Tümünü Dahil"); self.btn_all_in.setObjectName("Ghost")
        self.btn_all_ex.clicked.connect(lambda: self._set_all_excluded(True))
        self.btn_all_in.clicked.connect(lambda: self._set_all_excluded(False))
        ed_row.addWidget(self.ed_search_exc, 1)
        ed_row.addWidget(self.btn_all_ex)
        ed_row.addWidget(self.btn_all_in)
        exc.addLayout(ed_row)

        self.list_excludes = QListWidget()
        self.list_excludes.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list_excludes.setUniformItemSizes(True)
        exc.addWidget(self.list_excludes)

        # 2) Tarih / Gün
        self.btn_sec2 = self._mk_section_button("Sınav Tarihleri ve Günleri")
        self.pnl_sec2 = self._mk_section_container()
        cv.addWidget(self.btn_sec2); cv.addWidget(self.pnl_sec2)

        dlay = QHBoxLayout(self.pnl_sec2); dlay.setContentsMargins(10, 6, 10, 6)
        dlay.addWidget(QLabel("Tarih aralığı:"))
        self.start_date = QDateEdit(); self.start_date.setCalendarPopup(True)
        self.end_date   = QDateEdit(); self.end_date.setCalendarPopup(True)
        today = QDate.currentDate()
        self.start_date.setDate(today)
        self.end_date.setDate(today.addDays(7))
        dlay.addWidget(self.start_date); dlay.addWidget(QLabel("—")); dlay.addWidget(self.end_date)

        dlay.addSpacing(14)
        dlay.addWidget(QLabel("Dahil olmayan günler:"))

        # ▼▼▼ TÜM GÜNLER (Pzt=0 ... Paz=6) — İşaretli olanlar programa ALINMAZ ▼▼▼
        self.chk_days: Dict[int, QCheckBox] = {}
        day_labels = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
        for wd, name in enumerate(day_labels):  # Monday=0 .. Sunday=6
            cb = QCheckBox(name)
            self.chk_days[wd] = cb
            dlay.addWidget(cb)

        dlay.addStretch(1)

        # 3) Tür
        self.btn_sec3 = self._mk_section_button("Sınav Türü")
        self.pnl_sec3 = self._mk_section_container()
        cv.addWidget(self.btn_sec3); cv.addWidget(self.pnl_sec3)
        tlay = QHBoxLayout(self.pnl_sec3); tlay.setContentsMargins(10, 6, 10, 6)
        tlay.addWidget(QLabel("Sınav Türü:"))
        self.cmb_exam_type = QComboBox(); self.cmb_exam_type.addItems(["Vize", "Final", "Bütünleme"])
        tlay.addWidget(self.cmb_exam_type); tlay.addStretch(1)

        # 4) Süre / Bekleme / Global overlap
        self.btn_sec4 = self._mk_section_button("Sınav Süresi • Bekleme")
        self.pnl_sec4 = self._mk_section_container()
        cv.addWidget(self.btn_sec4); cv.addWidget(self.pnl_sec4)
        blay = QHBoxLayout(self.pnl_sec4); blay.setContentsMargins(10, 6, 10, 6)
        blay.addWidget(QLabel("Varsayılan sınav süresi (dk):"))
        self.sp_duration = QSpinBox(); self.sp_duration.setRange(30, 240); self.sp_duration.setValue(75)
        blay.addWidget(self.sp_duration)
        blay.addSpacing(12); blay.addWidget(QLabel("Bekleme süresi (dk):"))
        self.sp_buffer = QSpinBox(); self.sp_buffer.setRange(0, 180); self.sp_buffer.setValue(15)
        blay.addWidget(self.sp_buffer)
        blay.addSpacing(12)
        self.chk_no_overlap = QCheckBox("Sınavlar aynı anda başlamasın (global tek sınav)")
        blay.addWidget(self.chk_no_overlap); blay.addStretch(1)

        # actions
        act = QHBoxLayout()
        self.btn_load = QPushButton("Dersleri / Derslikleri Yükle"); self.btn_load.setObjectName("Ghost")
        self.btn_gen  = QPushButton("Programı Oluştur"); self.btn_gen.setObjectName("Primary")
        self.btn_xls  = QPushButton("Excel'e Aktar"); self.btn_xls.setObjectName("Ghost"); self.btn_xls.setEnabled(False)
        act.addWidget(self.btn_load); act.addStretch(1); act.addWidget(self.btn_gen); act.addWidget(self.btn_xls)
        cv.addLayout(act)

        root.addWidget(card)

        # Sonuç tablosu
        self.tbl = QTableWidget(0, 8)
        self.tbl.setHorizontalHeaderLabels(["Tarih", "Başlangıç", "Bitiş", "Ders Kodu", "Ders Adı", "Derslik", "Sınav Türü", "Süre (dk)"])
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        root.addWidget(self.tbl)

        # Sinyaller
        self.btn_load.clicked.connect(self._load_data)
        self.btn_gen.clicked.connect(self._generate)
        self.btn_xls.clicked.connect(self._export_excel)
        self.ed_search_dur.textChanged.connect(self._filter_dur)
        self.ed_search_exc.textChanged.connect(self._filter_exc)

        # State
        self._courses_cache: List[Dict[str, Any]] = []
        self._classrooms_cache: List[Dict[str, Any]] = []
        self._schedule: List[Dict[str, Any]] = []
        self._sp_by_cid: Dict[int, QSpinBox] = {}      # ders -> spin
        self._row_by_cid: Dict[int, QFrame] = {}       # ders -> satır widget
        self._excluded_ids: Set[int] = set()

        # Başlangıçta açık kalsın
        self.btn_sec1.setChecked(True); self.pnl_sec1.setVisible(True)
        self.btn_dur.setChecked(True);  self.pnl_dur.setVisible(True)
        self.btn_exc.setChecked(True);  self.pnl_exc.setVisible(True)

    # ───────────────────────── helpers (UI) ─────────────────────────
    def _mk_section_button(self, title: str, small: bool = False) -> QPushButton:
        b = QPushButton(title)
        b.setCheckable(True)
        b.setChecked(False)
        b.setProperty("class", "Section")
        b.setMinimumHeight(40 if not small else 36)
        b.clicked.connect(lambda s, w=b: self._toggle_section(w))
        return b

    def _toggle_section(self, btn: QPushButton):
        parent = btn.parentWidget()
        lay = parent.layout()
        for i in range(lay.count()):
            if lay.itemAt(i).widget() is btn:
                pnl = lay.itemAt(i + 1).widget()
                pnl.setVisible(btn.isChecked())
                break

    def _mk_section_container(self) -> QFrame:
        f = QFrame(); f.setObjectName("SectionBody")
        f.setVisible(False)
        return f

    def _mk_subcard(self) -> QFrame:
        f = QFrame(); f.setObjectName("SubCard")
        f.setVisible(False)
        return f

    # ───────────────────────── DB LOAD ─────────────────────────
    def _selected_dept_id(self) -> Optional[int]:
        """Koordinatörde kullanıcıdan, admin ise combobox'tan bölüm alır."""
        if self._is_admin:
            if not self.cmb_dept or self.cmb_dept.count() == 0:
                return None
            val = self.cmb_dept.currentData()
            return int(val) if val is not None else None
        # koordinatör — kullanıcıdaki DepartmentID
        u = (self.user or {})
        val = u.get("department_id") or u.get("DepartmentID") or u.get("department")
        try:
            return int(val) if val is not None else None
        except Exception:
            return None

    def _load_departments_for_admin(self):
        self.cmb_dept.clear()
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT DepartmentID, Name FROM dbo.Departments ORDER BY DepartmentID")
            for r in cur.fetchall():
                self.cmb_dept.addItem(f"{r.Name} (#{r.DepartmentID})", int(r.DepartmentID))

    def _load_data(self):
        dept_id = self._selected_dept_id()
        if not dept_id:
            QMessageBox.warning(self, "Uyarı", "Bir bölüm seçin.")
            return
        try:
            conn = get_connection(); cur = conn.cursor()

            # Courses
            cur.execute("""
                SELECT CourseID, Code AS CourseCode, Name AS CourseName, ClassYear
                FROM dbo.Courses
                WHERE DepartmentID = ?
                ORDER BY Code
            """, (dept_id,))
            self._courses_cache = [
                {"CourseID": int(r[0]), "CourseCode": r[1], "CourseName": r[2], "ClassYear": int(r[3] or 0)}
                for r in cur.fetchall()
            ]

            # Classrooms
            cur.execute("""
                SELECT ClassroomID, Code, Name, Capacity, Cols, Rows, DeskGroupSize
                FROM dbo.Classrooms
                WHERE DepartmentID = ?
                ORDER BY Code
            """, (dept_id,))
            self._classrooms_cache = [
                {"ClassroomID": int(r[0]), "Code": r[1], "Name": r[2], "Capacity": int(r[3] or 0),
                 "Cols": int(r[4] or 0), "Rows": int(r[5] or 0), "DeskGroupSize": int(r[6] or 0)}
                for r in cur.fetchall()
            ]
            conn.close()

            # Panelleri doldur
            self._fill_durations_panel()
            self._fill_excludes_panel()
            self._refresh_counters()

            QMessageBox.information(self, "Yüklendi",
                                    f"Ders: {len(self._courses_cache)} • Derslik: {len(self._classrooms_cache)}")

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"DB yüklenemedi:\n{e}")

    # ───────────────────────── panels ─────────────────────────
    def _mk_duration_row(self, text: str, cid: int) -> QFrame:
        row = QFrame(); row.setObjectName("DurRow"); row.setProperty("active", False)
        row.setFixedHeight(ROW_H)

        h = QHBoxLayout(row); h.setContentsMargins(8, 4, 8, 4); h.setSpacing(10)

        lbl = QLabel(text); lbl.setObjectName("DurLbl"); lbl.setWordWrap(False)

        sp  = QSpinBox(); sp.setObjectName("DurSpin")
        sp.setRange(0, 240)
        sp.setValue(0)                         # 0 → varsayılan
        sp.setSuffix(" dk")
        sp.setSpecialValueText("varsayılan")
        sp.setFixedWidth(130)
        sp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sp.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        sp.setKeyboardTracking(False)
        sp.setToolTip("0 = Varsayılan süre • >0 girerseniz bu ders için özel süre uygulanır")

        sp.valueChanged.connect(lambda v, r=row, ccid=cid: self._on_override_changed(ccid, v, r))

        h.addWidget(lbl, 1)
        h.addStretch(0)
        h.addWidget(sp, 0, Qt.AlignmentFlag.AlignRight)

        self._sp_by_cid[cid]  = sp
        self._row_by_cid[cid] = row
        return row

    def _on_override_changed(self, cid: int, val: int, row: QFrame):
        row.setProperty("active", bool(val > 0))
        row.style().unpolish(row); row.style().polish(row); row.update()
        self._refresh_counters()

    def _fill_durations_panel(self):
        self.list_durations.clear()
        self._sp_by_cid.clear()
        self._row_by_cid.clear()

        for c in self._courses_cache:
            cid = int(c["CourseID"])
            text = f"{c['CourseCode']} — {c['CourseName']}"
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, cid)

            row = self._mk_duration_row(text, cid)
            it.setSizeHint(QSize(0, ROW_H))
            self.list_durations.addItem(it)
            self.list_durations.setItemWidget(it, row)

    # Boyama yardımcıları (Hariç listesi)
    def _paint_selected(self, it: QListWidgetItem, selected: bool):
        if selected:
            it.setBackground(QColor("#90EE90"))
            it.setForeground(QColor("#000000"))
        else:
            it.setBackground(QColor("#FFFFFF"))
            it.setForeground(QColor("#000000"))

    def _fill_excludes_panel(self):
        self.list_excludes.clear()
   
        existing = set(self._excluded_ids)

        for c in self._courses_cache:
            cid = int(c["CourseID"])
            text = f"{c['CourseCode']} — {c['CourseName']}"
            it = QListWidgetItem(text)
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            it.setData(Qt.ItemDataRole.UserRole, cid)
            self.list_excludes.addItem(it)
            self._paint_selected(it, cid in existing)

    # 🔧 ÖNEMLİ: önce eski bağlantıyı kopar, sonra bağla (yoksa çift çağrılır)
        try:
            self.list_excludes.itemClicked.disconnect()
        except TypeError:
            pass
        self.list_excludes.itemClicked.connect(self._on_exclude_clicked)

    # state'i geri yaz
        self._excluded_ids = existing


    def _on_exclude_clicked(self, it: QListWidgetItem):
        cid = int(it.data(Qt.ItemDataRole.UserRole))
        if cid in self._excluded_ids:
            self._excluded_ids.remove(cid); self._paint_selected(it, False)
        else:
            self._excluded_ids.add(cid); self._paint_selected(it, True)
        self._refresh_counters()

    def _set_all_excluded(self, yes: bool):
        self._excluded_ids.clear()
        for i in range(self.list_excludes.count()):
            it = self.list_excludes.item(i)
            cid = int(it.data(Qt.ItemDataRole.UserRole))
            if yes:
                self._excluded_ids.add(cid); self._paint_selected(it, True)
            else:
                self._paint_selected(it, False)
        self._refresh_counters()

    def _clear_overrides(self):
        for sp in self._sp_by_cid.values():
            sp.setValue(0)

    def _filter_dur(self, s: str):
        q = (s or "").strip().lower()
        for i in range(self.list_durations.count()):
            it = self.list_durations.item(i)
            it.setHidden(q not in it.text().lower())

    def _filter_exc(self, s: str):
        q = (s or "").strip().lower()
        for i in range(self.list_excludes.count()):
            it = self.list_excludes.item(i)
            it.setHidden(q not in it.text().lower())

    def _refresh_counters(self):
        total = len(self._courses_cache)
        excluded = len(self._excluded_ids)
        included = max(0, total - excluded)
        overrides = sum(1 for sp in self._sp_by_cid.values() if int(sp.value()) > 0)
        self.lbl_counter.setText(f"Dahil: {included} • Hariç: {excluded} • İstisna: {overrides}")

    # ───────────────────────── generate & save ─────────────────────────
    def _included_courses(self) -> List[Dict[str, Any]]:
        excl = set(self._excluded_ids)
        return [c for c in self._courses_cache if int(c["CourseID"]) not in excl]

    def _gather_constraints(self) -> Optional[Constraints]:
        dept_id = self._selected_dept_id()
        if not dept_id:
            QMessageBox.warning(self, "Uyarı", "Bir bölüm seçin.")
            return None

        sd = self.start_date.date().toPyDate()
        ed = self.end_date.date().toPyDate()
        if ed < sd:
            QMessageBox.warning(self, "Uyarı", "Bitiş tarihi başlangıçtan önce olamaz.")
            return None

        # Tüm günlerden işaretlenenleri program dışına al
        excl_days: Set[int] = {wd for wd, cb in self.chk_days.items() if cb.isChecked()}

        chosen = self._included_courses()
        if not chosen:
            QMessageBox.warning(self, "Uyarı", "En az bir dersi dahil bırakmalısınız.")
            return None

        # spinbox'lardan istisnaları oku (0 → varsayılan değil)
        overrides: Dict[int, int] = {}
        for cid, sp in self._sp_by_cid.items():
            v = int(sp.value())
            if v > 0:
                overrides[int(cid)] = v

        return Constraints(
            department_id=int(dept_id),
            date_start=sd, date_end=ed,
            exclude_weekdays=excl_days,
            default_duration_min=self.sp_duration.value(),
            buffer_min=self.sp_buffer.value(),
            global_no_overlap=self.chk_no_overlap.isChecked(),
            chosen_courses=chosen,
            exam_type=self.cmb_exam_type.currentText(),
            per_course_durations=overrides
        )

    def _generate(self):
        if not self._courses_cache or not self._classrooms_cache:
            QMessageBox.information(self, "Bilgi", "Önce 'Dersleri / Derslikleri Yükle' butonuna tıklayın.")
            return

        cons = self._gather_constraints()
        if not cons:
            return

        try:
            # scheduler_core beklediği şekilde çağrılıyor
            sched = generate_schedule(cons, self._classrooms_cache)

            self._schedule = sched
            self._render_table(sched)
            self.btn_xls.setEnabled(len(sched) > 0)

            if sched:
                dept_id = int(self._selected_dept_id() or 0)
                reply = QMessageBox.question(
                    self,
                    "Veritabanı Kaydı",
                    (f"Oluşturulan {cons.exam_type} programını veritabanına kaydedeyim mi?\n"
                     f"Not: SADECE bu bölüm için {cons.date_start}–{cons.date_end} aralığındaki "
                     f"{cons.exam_type} kayıtları silinip yeniden yazılacak."),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    inserted = overwrite_and_insert_scoped(
                        department_id=dept_id,
                        exam_type=cons.exam_type,
                        date_start=cons.date_start,
                        date_end=cons.date_end,
                        rows=sched,
                    )
                    QMessageBox.information(self, "Kayıt",
                                            f"Veritabanına yazıldı: {inserted} satır (diğer bölümlere dokunulmadı).")

            # Özet
            unique_courses = {int(r["CourseID"]) for r in sched}
            total_rows = len(sched)

            multi_room_map: Dict[tuple, int] = {}
            for r in sched:
                key = (r["Date"], r["Start"], int(r["CourseID"]))
                multi_room_map[key] = multi_room_map.get(key, 0) + 1
            multi_course_ids = {cid for (_, _, cid), cnt in multi_room_map.items() if cnt > 1}

            msg_lines = [
                f"{len(unique_courses)} dersin sınavı planlandı.",
                f"Toplam {total_rows} salon (satır) kullanıldı.",
            ]
            if multi_course_ids:
                lookup = {int(c["CourseID"]): f"{c['CourseCode']} — {c['CourseName']}" for c in self._courses_cache}
                names = [lookup.get(cid, str(cid)) for cid in sorted(multi_course_ids)]
                msg_lines.append("Çoklu salona bölünen dersler:")
                msg_lines.extend([f"  • {n}" for n in names])

            QMessageBox.information(self, "Sonuç", "\n".join(msg_lines))

        except StudentOverlapError as e:
            lines = [str(e)]
            ex = (getattr(e, "details", None) or {}).get("examples") or []
            if ex:
                lines.append("")
                lines.append("Örnek çakışmalar:")
                for item in ex:
                    st = item.get("student")
                    typ = "Aynı saat" if item.get("type") == "same-time" else "Bekleme süresi"
                    withs = ", ".join([c for c in item.get("conflict_with", []) if c])
                    if withs:
                        lines.append(f"  • Öğrenci {st}: {typ} — {withs}")
                    else:
                        lines.append(f"  • Öğrenci {st}: {typ}")
                if len(ex) >= 10:
                    lines.append("  • … (liste kısaltıldı)")
            QMessageBox.critical(self, "Hata", "\n".join(lines))
            self._schedule = []; self._render_table([]); self.btn_xls.setEnabled(False)

        except CapacityError as e:
            d = getattr(e, "details", None) or {}
            extra = []
            if d.get("course_code"):
                extra.append(f"Ders: {d['course_code']}")
            if "need" in d and "total_capacity" in d:
                extra.append(f"Gerekli: {d['need']} • Toplam kapasite: {d['total_capacity']}")
            msg = str(e) + (("\n\n" + " / ".join(extra)) if extra else "")
            QMessageBox.critical(self, "Hata", msg)
            self._schedule = []; self._render_table([]); self.btn_xls.setEnabled(False)

        except ClassroomNotFoundError as e:
            reason_map = {
                "global_no_overlap_occupied": "Global tek sınav kısıtı yüzünden tüm slotlar dolu.",
                "no_compatible_slot": "Seçilen tarih/günler ve süreler içinde uygun slot yok.",
                "no_room_bundle": "Derslik kapasite demeti oluşturulamadı.",
            }
            d = getattr(e, "details", None) or {}
            reason = reason_map.get(d.get("reason", ""), "")
            msg = str(e) + (("\n\n" + reason) if reason else "")
            QMessageBox.critical(self, "Hata", msg)
            self._schedule = []; self._render_table([]); self.btn_xls.setEnabled(False)

        except DateRangeError as e:
            QMessageBox.critical(self, "Hata", str(e))
            self._schedule = []; self._render_table([]); self.btn_xls.setEnabled(False)

        except SchedulingError as e:
            QMessageBox.critical(self, "Hata", str(e))
            self._schedule = []; self._render_table([]); self.btn_xls.setEnabled(False)

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Program oluşturulamadı:\n{e}")
            self._schedule = []; self._render_table([]); self.btn_xls.setEnabled(False)

    # ───────────────────────── render & export ─────────────────────────
    def _render_table(self, rows: List[Dict[str, Any]]):
        self.tbl.setRowCount(0)
        for r in rows:
            i = self.tbl.rowCount()
            self.tbl.insertRow(i)
            self.tbl.setItem(i, 0, QTableWidgetItem(r["Date"].strftime("%Y-%m-%d")))
            self.tbl.setItem(i, 1, QTableWidgetItem(r["Start"].strftime("%H:%M")))
            self.tbl.setItem(i, 2, QTableWidgetItem(r["End"].strftime("%H:%M")))
            self.tbl.setItem(i, 3, QTableWidgetItem(r["CourseCode"]))
            self.tbl.setItem(i, 4, QTableWidgetItem(r["CourseName"]))
            self.tbl.setItem(i, 5, QTableWidgetItem(r["ClassroomName"]))
            self.tbl.setItem(i, 6, QTableWidgetItem(r.get("ExamType", "Vize")))
            self.tbl.setItem(i, 7, QTableWidgetItem(str(r.get("DurationMin", ""))))
        self.tbl.resizeColumnsToContents()

    def _export_excel(self):
        if not self._schedule:
            QMessageBox.information(self, "Bilgi", "Önce program oluşturun.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Excel'e Aktar", "sinav_programi.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            export_schedule_to_excel(self._schedule, path)
            QMessageBox.information(self, "Tamam", f"Excel kaydedildi:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Excel yazılamadı:\n{e}")
