# seat_plan_page.py — slot bazlı UI (CourseID + StartDT) • 3’lü bench (kenarlar dolu)
from __future__ import annotations
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import hashlib

from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QPageLayout, QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox,
    QSplitter, QScrollArea, QHeaderView, QFileDialog, QListWidget, QListWidgetItem,
    QComboBox, QSlider, QSizePolicy, QCheckBox
)
from PyQt6.QtPrintSupport import QPrinter

from db import get_connection
from seat_plan_repo import (
    list_exam_slots, build_plan_for_slot,
    PlanResult, Placement, RoomLayout
)

# ────────── Tema / Renkler ──────────
ACCENT      = "#2563EB"
BORDER      = "#E5E7EB"
TEXT_DARK   = "#0B1324"
MUTED       = "#6B7280"

CANVAS_BG   = "#FFFFFF"
CARD_BG     = "#FFFFFF"
CARD_SHADOW = (0, 0, 0, 22)
PILL_BG     = "#F3F4F6"
PILL_TXT    = "#374151"

# Oturma renkleri
SEAT_BG     = "#E3F2FD"   # mask=0 (kullanılamaz)
SEAT_EMPTY  = "#BBDEFB"   # boş ama oturulabilir
SEAT_FILL   = "#1E88E5"   # dolu (öğrenci)
SEAT_LINE   = "#90CAF9"

# ────────── Bench maskesi ──────────
def _mask_for_bench(bench_size: int) -> List[int]:
    # 4’lü: dolu-boş-boş-dolu, 3’lü: kenarlar dolu, 2’li: sağ koltuk dolu
    if bench_size == 4: return [1, 0, 0, 1]
    if bench_size == 3: return [1, 0, 1]
    if bench_size == 2: return [1, 0]
    return [1]

# isim kısaltma (A. SOYAD)
def _short_name(full: str) -> str:
    parts = [p for p in (full or "").split() if p]
    if not parts: return ""
    last = parts[-1].upper()
    first = parts[0][0].upper() + "."
    return f"{first} {last}"

# ────────── Liste öğesi ──────────
@dataclass
class SlotItem:
    course_id: int
    start_dt: datetime
    info: str  # "INS101 – Matematik I | 20.10 09:00 | Amfi, 301, 303"

# ────────── Sayfa ──────────
class SeatPlanPage(QWidget):
    def __init__(self, user: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.user = user or {}
        self.role_id = int(self.user.get("role_id") or self.user.get("RoleID") or 2)
        self.department_id = self.user.get("department_id") or self.user.get("DepartmentID")

        self.setWindowTitle("Oturma Planı")
        self._plan: PlanResult | None = None
        self._rooms_for_slot: List[RoomLayout] = []
        self._placement_by_room: Dict[int, List[Placement]] = {}

        # Program fingerprint (değişiklik algılama)
        self._schedule_fingerprint: Optional[str] = None

        root = QVBoxLayout(self); root.setSpacing(10)

        # Üst başlık ve (admin ise) bölüm filtresi
        top = QHBoxLayout()
        title = QLabel("Derse Ait Oturma Düzeni")
        title.setStyleSheet(f"font-size:18px;font-weight:800;color:{TEXT_DARK};")
        top.addWidget(title); top.addStretch(1)

        self.cmb_department: Optional[QComboBox] = None
        if self.role_id == 1:  # Admin
            top.addWidget(QLabel("Bölüm:"))
            self.cmb_department = QComboBox(); self.cmb_department.setMinimumWidth(260)
            top.addWidget(self.cmb_department)
        root.addLayout(top)

        # Üst kontrol şeridi
        ctrl = QHBoxLayout(); ctrl.setSpacing(10)
        self.chk_names = QPushButton("İsimleri Göster"); self.chk_names.setCheckable(True); self.chk_names.setChecked(True)
        self.chk_grid  = QPushButton("Izgarayı Göster"); self.chk_grid.setCheckable(True); self.chk_grid.setChecked(False)
        self.zoom = QSlider(Qt.Orientation.Horizontal); self.zoom.setMinimum(70); self.zoom.setMaximum(160); self.zoom.setSingleStep(5); self.zoom.setValue(95)
        zoom_lbl = QLabel("Yakınlaştırma")
        for w in (self.chk_names, self.chk_grid): w.setCursor(Qt.CursorShape.PointingHandCursor)

        # Program Yenile + Otomatik
        self.btn_refresh = QPushButton("Programı Yenile")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_auto = QCheckBox("Otomatik Yenile")
        self.chk_auto.setChecked(True)

        ctrl.addWidget(self.btn_refresh)
        ctrl.addWidget(self.chk_auto)
        ctrl.addStretch(1)
        ctrl.addWidget(self.chk_names); ctrl.addWidget(self.chk_grid)
        ctrl.addSpacing(12); ctrl.addWidget(zoom_lbl); ctrl.addWidget(self.zoom)
        root.addLayout(ctrl)

        # Ana splitter
        main = QSplitter(Qt.Orientation.Horizontal); root.addWidget(main, 1)

        # Sol panel (slot listesi)
        left = QFrame()
        lv = QVBoxLayout(left); lv.setContentsMargins(8,8,8,8); lv.setSpacing(8)
        cap = QLabel("Sınav Slotları (Ders + Saat)"); cap.setStyleSheet(f"color:{MUTED}; font-weight:600;")
        self.slot_list = QListWidget()
        self.slot_list.setStyleSheet(f"""
            QListWidget {{
                background: #FFFFFF; border: 1px solid {BORDER}; border-radius: 14px; padding: 6px;
            }}
            QListWidget::item {{ height: 36px; border-radius: 10px; padding-left: 10px; color: {TEXT_DARK}; }}
            QListWidget::item:hover {{ background: #F3F4F6; }}
            QListWidget::item:selected {{ background: {ACCENT}; color: #FFFFFF; }}
        """)
        self.btn_build = QPushButton("Seçilen Slot İçin Oturma Düzeni Oluştur")
        self.btn_build.setStyleSheet(f"""
            QPushButton {{
                background:{ACCENT}; color:#fff; border:none; border-radius:12px; padding:10px 12px; font-weight:700;
            }}
            QPushButton:hover  {{ background:#2b6be0; }}
            QPushButton:pressed{{ background:#1f56c4; }}
        """)
        lv.addWidget(cap); lv.addWidget(self.slot_list, 1); lv.addWidget(self.btn_build)
        main.addWidget(left)

        # Sağ panel: çizim + tablo
        right = QSplitter(Qt.Orientation.Vertical); main.addWidget(right)

        # Kanvas: yatay scroll aktif — genişliği içerik belirlesin
        self.canvas_area = QScrollArea()
        self.canvas_area.setWidgetResizable(False)
        self.canvas_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.canvas_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.canvas = _SeatCanvas()
        self.canvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.canvas_area.setWidget(self.canvas)
        right.addWidget(self.canvas_area)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Öğrenci", "No", "Derslik", "Sıra,Sütun"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        right.addWidget(self.table)

        # Lejand + PDF
        legend = QLabel("● Dolu   ○ Boş   ◌ Kullanılamaz"); legend.setStyleSheet(f"color:{MUTED};")
        root.addWidget(legend)
        bottom = QHBoxLayout()
        self.btn_pdf = QPushButton("PDF İndir")
        self.btn_pdf.setStyleSheet("""
            QPushButton {
                background:#111827; color:#fff; border:none; border-radius:10px; padding:8px 12px; font-weight:700;
            }
            QPushButton:hover  { background:#1f2432; }
            QPushButton:pressed{ background:#0c1723; }
        """)
        self.btn_pdf.clicked.connect(self._export_pdf)
        bottom.addStretch(1); bottom.addWidget(self.btn_pdf)
        root.addLayout(bottom)

        # Sinyaller
        self.slot_list.itemSelectionChanged.connect(self._on_selected)
        self.btn_build.clicked.connect(self._build_for_selected)
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        self.chk_names.toggled.connect(lambda v: self.canvas.set_options(show_names=v))
        self.chk_grid.toggled.connect(lambda v: self.canvas.set_options(show_grid=v))

        def _on_zoom(v: int):
            self.canvas.set_options(zoom=v / 100.0)
            self._sync_canvas_width()

        self.zoom.valueChanged.connect(_on_zoom)

        # Veriyi yükle
        if self.cmb_department:
            self._load_departments()
            self.cmb_department.currentIndexChanged.connect(self._load_slots)
        self._load_slots(initial=True)

    # ----------------- Departmanlar (Admin) -----------------
    def _load_departments(self):
        assert self.cmb_department is not None
        self.cmb_department.clear()
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SELECT DepartmentID, Name FROM Departments ORDER BY Name;")
        for dep_id, name in cur.fetchall():
            self.cmb_department.addItem(str(name), int(dep_id))
        conn.close()

    # ----------------- Slot listesi -----------------
    def _current_dep_id(self) -> Optional[int]:
        if self.role_id == 1 and self.cmb_department is not None:
            val = self.cmb_department.currentData()
            return int(val) if val is not None else None
        elif self.role_id != 1:
            return int(self.department_id) if self.department_id else None
        return None

    def _load_slots(self, initial: bool = False):
        # Var olan seçimi (course_id, start_dt) ile sakla
        prev_key: Optional[Tuple[int, datetime]] = None
        it = self.slot_list.currentItem()
        if it:
            s: SlotItem = it.data(Qt.ItemDataRole.UserRole)
            prev_key = (s.course_id, s.start_dt)

        self.slot_list.clear()
        dep_id = self._current_dep_id()
        for course_id, start_dt, info in list_exam_slots(dep_id):
            slot = SlotItem(course_id=course_id, start_dt=start_dt, info=info)
            item = QListWidgetItem(info); item.setData(Qt.ItemDataRole.UserRole, slot)
            self.slot_list.addItem(item)

        # fingerprint’i güncelle ve ilk yüklemede set et
        try:
            fp = self._compute_schedule_fingerprint(dep_id)
            if initial or self._schedule_fingerprint is None:
                self._schedule_fingerprint = fp
        except Exception:
            # fingerprint okunamazsa sessiz geç
            pass

        # Eski seçim hâlâ varsa geri seç
        if prev_key:
            for i in range(self.slot_list.count()):
                s: SlotItem = self.slot_list.item(i).data(Qt.ItemDataRole.UserRole)
                if (s.course_id, s.start_dt) == prev_key:
                    self.slot_list.setCurrentRow(i)
                    break

    # Çizim için slotun salonları
    def _fetch_rooms_for_slot(self, course_id: int, start_dt: datetime) -> List[RoomLayout]:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT cl.ClassroomID, cl.Name, cl.Rows, cl.Cols, cl.DeskGroupSize
            FROM Exams e
            JOIN ExamRooms er ON er.ExamID = e.ExamID
            JOIN Classrooms cl ON cl.ClassroomID = er.ClassroomID
            WHERE e.CourseID = ? AND e.StartDT = ?
            ORDER BY cl.Name
        """, course_id, start_dt)
        rows = cur.fetchall(); conn.close()
        return [RoomLayout(int(r[0]), r[1], int(r[2]), int(r[3]), int(r[4])) for r in rows]

    # --------------- Program Yenile ---------------
    def _compute_schedule_fingerprint(self, dep_id: Optional[int]) -> str:
        """
        Exams + ExamRooms + Classrooms satırlarından deterministik fingerprint üretir.
        Bitiş zamanı EndDT yerine StartDT + DurationMin’den hesaplanır.
        """
        conn = get_connection(); cur = conn.cursor()

        # Ortak SELECT: EndDT türet
        base_sql = """
            SELECT
                E.ExamID,
                E.CourseID,
                E.ExamType,
                E.StartDT,
                DATEADD(MINUTE, E.DurationMin, E.StartDT) AS EndDT,
                E.DurationMin,
                ISNULL(E.Notes, '') AS Notes,
                ER.ClassroomID,
                C.Rows,
                C.Cols,
                C.DeskGroupSize
            FROM Exams E
            JOIN ExamRooms ER ON ER.ExamID = E.ExamID
            JOIN Classrooms C ON C.ClassroomID = ER.ClassroomID
            {dep_filter}
            ORDER BY E.StartDT, E.ExamID, ER.ClassroomID
        """

        if dep_id:
            sql = base_sql.format(dep_filter="WHERE C.DepartmentID = ?")
            cur.execute(sql, dep_id)
        else:
            sql = base_sql.format(dep_filter="")
            cur.execute(sql)

        rows = cur.fetchall()
        conn.close()

        import hashlib
        h = hashlib.sha256()
        for r in rows:
            h.update(("|".join(str(x) for x in r)).encode("utf-8"))
        return h.hexdigest()


    def _on_refresh_clicked(self):
        dep_id = self._current_dep_id()
        try:
            new_fp = self._compute_schedule_fingerprint(dep_id)
        except Exception as e:
            QMessageBox.warning(self, "Uyarı", f"Program okunamadı:\n{e}")
            # yine de listeyi yenilemeyi dene
            self._load_slots()
            return

        changed = (new_fp != self._schedule_fingerprint)
        self._schedule_fingerprint = new_fp

        self._load_slots()  # listeyi tazele

        if changed:
            # Seçim varsa ve otomatik açıksa, planı yeniden üret
            if self.chk_auto.isChecked():
                self._build_for_selected()
            QMessageBox.information(self, "Güncellendi", "Sınav programındaki değişiklikler algılandı.")
        else:
            QMessageBox.information(self, "Güncel", "Sınav programında değişiklik yok.")

    # --------------- Olaylar ---------------
    def _on_selected(self):
        self.canvas.set_rooms([]); self.table.setRowCount(0)
        self._plan = None; self._placement_by_room.clear(); self._rooms_for_slot = []

    def _build_for_selected(self):
        item = self.slot_list.currentItem()
        if not item:
            QMessageBox.information(self, "Seçim Yok", "Lütfen bir sınav slotu seçin.")
            return
        slot: SlotItem = item.data(Qt.ItemDataRole.UserRole)

        plan: PlanResult = build_plan_for_slot(
            course_id=slot.course_id,
            start_dt=slot.start_dt,
            forbidden_pairs=set(),
            prefer_front_student_nos=[]
        )
        self._plan = plan
        if plan.errors:
            QMessageBox.critical(self, "Plan Oluşturulamadı", "\n".join(plan.errors)); return
        if plan.warnings:
            QMessageBox.warning(self, "Uyarılar", "\n".join(plan.warnings))

        self._rooms_for_slot = self._fetch_rooms_for_slot(slot.course_id, slot.start_dt)
        if not self._rooms_for_slot:
            QMessageBox.warning(self, "Derslik Yok", "Bu slot için derslik atanmamış."); return

        by_room: Dict[int, List[Placement]] = {}
        for p in plan.placements:
            by_room.setdefault(p.classroom_id, []).append(p)
        self._placement_by_room = by_room
        self.canvas.set_rooms(self._rooms_for_slot, by_room)
        self._sync_canvas_width()
        self._fill_table(plan.placements)

    def _sync_canvas_width(self):
        """Yatay scrollbar için içerik genişliğini, en geniş salonun sütununa göre ayarla."""
        if not self._rooms_for_slot:
            self.canvas.setFixedWidth(900); return
        cols_max = max(r.cols for r in self._rooms_for_slot)
        z = self.canvas.zoom
        est = int(40*z + (cols_max * (46*z + 3*z)) + 80)  # sol/sağ padding dahil
        self.canvas.setFixedWidth(max(900, est))

    def _fill_table(self, placements: List[Placement]):
        self.table.setRowCount(len(placements))
        placements_sorted = sorted(placements, key=lambda x: (x.classroom_name, x.pos.row, x.pos.col, x.student.no))
        for i, p in enumerate(placements_sorted):
            self.table.setItem(i, 0, QTableWidgetItem(p.student.name))
            self.table.setItem(i, 1, QTableWidgetItem(p.student.no))
            self.table.setItem(i, 2, QTableWidgetItem(p.classroom_name))
            self.table.setItem(i, 3, QTableWidgetItem(f"{p.pos.row+1}, {p.pos.col+1}"))

    # ----------------- PDF Dışa Aktar -----------------
    def _export_pdf(self):
        if not self._rooms_for_slot or not self._placement_by_room:
            QMessageBox.information(self, "Plan Yok", "Önce bir plan oluşturun.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "PDF olarak kaydet", "oturma_plani.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        
        old_show = self.canvas._show_names
        self.canvas._show_names = True

        # 1) Canvas'ı tam boy render et (ekrandakiyle birebir)
        old_size = self.canvas.size()
        full_w   = self.canvas.width()                    # yatay genişlik zaten ayarlanıyor
        full_h   = self.canvas.sizeHint().height()        # tüm salonları kapsayan yükseklik
        self.canvas.resize(full_w, full_h)                # geçici olarak büyüt

        scale_factor = 2.0                                # daha keskin görüntü için 2x çözünürlük
        img = QImage(int(full_w*scale_factor), int(full_h*scale_factor), QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p_img = QPainter(img)
        p_img.scale(scale_factor, scale_factor)           # mantıksal boyut ~ canvas boyutu
        self.canvas.render(p_img)
        p_img.end()

        # 2) PDF’e sayfa sayfa bas
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setFullPage(True)
        printer.setPageOrientation(QPageLayout.Orientation.Portrait)
        printer.setResolution(300)

        p_pdf = QPainter()
        if not p_pdf.begin(printer):
            QMessageBox.critical(self, "Hata", "PDF yazıcı başlatılamadı.")
            self.canvas.resize(old_size)
            return

        try:
            page_px   = printer.pageLayout().paintRectPixels(printer.resolution())
            page_rect = QRectF(page_px)

            margin = 32.0
            target = QRectF(
                page_rect.x() + margin,
                page_rect.y() + margin,
                page_rect.width() - 2*margin,
                page_rect.height() - 2*margin,
            )

            # Görüntüyü sayfa genişliğine sığdır; yükseklik kadar dilimle
            s = target.width() / img.width()  # ölçek: kaynak→hedef
            slice_h_src = int(target.height() / s)  # kaynakta bir sayfada sığacak yükseklik

            y0 = 0
            while y0 < img.height():
                if y0 > 0:
                    printer.newPage()

                src_h = min(slice_h_src, img.height() - y0)
                src   = img.copy(0, y0, img.width(), src_h)

                # hedefin yüksekliğini orana göre ayarla (boşluk kalmasın)
                dst = QRectF(target.x(), target.y(), target.width(), src_h * s)
                p_pdf.drawImage(dst, src)
                y0 += slice_h_src

        except Exception as e:
            p_pdf.end()
            self.canvas.resize(old_size)
            self.canvas._show_names = old_show
            QMessageBox.critical(self, "PDF Hatası", str(e))
            return
        finally:
            p_pdf.end()
            self.canvas.resize(old_size)
            self.canvas._show_names = old_show

        QMessageBox.information(self, "Hazır", "PDF dışa aktarıldı (ekrandakiyle birebir).")

# ────────── Çizim widget’ı ──────────
class _SeatCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self._rooms: List[RoomLayout] = []
        self._by_room: Dict[int, List[Placement]] = {}
        self._show_names = True
        self._show_grid  = False
        self._zoom       = 0.95
        self.setMinimumSize(QSize(900, 640))
        self.setStyleSheet("background: %s;" % CANVAS_BG)

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_options(self, show_names: Optional[bool] = None, show_grid: Optional[bool] = None, zoom: Optional[float] = None):
        if show_names is not None: self._show_names = show_names
        if show_grid  is not None: self._show_grid  = show_grid
        if zoom       is not None: self._zoom       = max(0.6, min(2.0, zoom))
        self.updateGeometry(); self.update()

    def set_rooms(self, rooms: List[RoomLayout], by_room: Dict[int, List[Placement]] | None = None):
        self._rooms = rooms
        self._by_room = by_room or {}
        self.updateGeometry(); self.update()

    def sizeHint(self):
        # dinamik yükseklik: blok boşlukları hesaplanır
        total = 40
        for room in self._rooms:
            z = self._zoom
            per_row = 18 * z
            mlen = len(_mask_for_bench(room.bench_size))
            block_count = (room.rows - 1) // mlen
            block_gap = 2.0 * z * block_count
            rows_h = room.rows * per_row + (room.rows - 1) * (3.0 * z) + block_gap

            min_h   = 150 * z
            max_h   = 280 * z
            card_h  = min(max_h, max(min_h, rows_h + 90 * z))
            total += card_h + 22
        return QSize(max(900, self.width()), max(640, int(total)))

    def paintEvent(self, ev):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = 20; card_gap = 22
        for room in self._rooms:
            z = self._zoom
            per_row = 18 * z
            mlen = len(_mask_for_bench(room.bench_size))
            block_count = (room.rows - 1) // mlen
            block_gap = 2.0 * z * block_count
            rows_h = room.rows * per_row + (room.rows - 1) * (3.0 * z) + block_gap

            min_h   = 150 * z
            max_h   = 280 * z
            card_h  = min(max_h, max(min_h, rows_h + 90 * z))

            rect = QRectF(20, y, self.width()-40, card_h)
            self._drop_shadow(p, rect, radius=14)
            self._rounded_rect(p, rect, fill=CARD_BG, border=BORDER, radius=14)

            header_rect = QRectF(rect.x()+16, rect.y()+10, rect.width()-32, 24*z)
            self._draw_header(p, header_rect, room)

            area = QRectF(rect.x()+16, header_rect.bottom()+8, rect.width()-32, rect.height()-(header_rect.height()+24))
            self.draw_single_room(p, room, self._by_room.get(room.classroom_id, []), area, for_pdf=False)
            y += card_h + card_gap

    # ---- yardımcı çizimler ----
    def _rounded_rect(self, p: QPainter, r: QRectF, fill: str, border: str, radius: float = 12.0):
        p.setPen(QPen(QColor(border))); p.setBrush(QColor(fill)); p.drawRoundedRect(r, radius, radius)

    def _drop_shadow(self, p: QPainter, r: QRectF, radius: float = 12.0):
        r2 = QRectF(r.x()+2, r.y()+4, r.width(), r.height())
        p.save(); p.setPen(Qt.PenStyle.NoPen)
        r_, g_, b_, a_ = CARD_SHADOW
        p.setBrush(QColor(r_, g_, b_, a_)); p.drawRoundedRect(r2, radius, radius); p.restore()

    def _draw_header(self, p: QPainter, rect: QRectF, room: RoomLayout):
        p.save()
        title_f = QFont(); title_f.setPointSize(int(10*self._zoom)); title_f.setBold(True)
        p.setFont(title_f); p.setPen(QColor(TEXT_DARK))
        p.drawText(rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), room.classroom_name)

        pill = QRectF(rect.right()-170*self._zoom, rect.y()+2, 160*self._zoom, rect.height()-4)
        p.setBrush(QColor(PILL_BG)); p.setPen(Qt.PenStyle.NoPen); p.drawRoundedRect(pill, 10, 10)
        p.setPen(QColor(PILL_TXT))
        small = QFont(); small.setPointSize(int(9*self._zoom)); p.setFont(small)
        txt = f"{room.cols}×{room.rows}  •  bench {room.bench_size}"
        p.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), txt)
        p.restore()

    def draw_single_room(self, p: QPainter, room: RoomLayout, placements: List[Placement],
                         rect: QRectF, for_pdf: bool=False):
        z = 1.0 if for_pdf else self._zoom

        # Aralıklar
        gap_x = 3.0 * z
        gap_y = 3.0 * z
        group_gap_y = 2.0 * z  # bloklar (3’lü/4’lü) arasında ekstra boşluk

        cols = max(1, room.cols)
        rows = max(1, room.rows)

        # Hücre ölçüleri
        cell_w = (rect.width()  - gap_x * (cols - 1)) / cols
        bench = _mask_for_bench(room.bench_size)
        mlen  = len(bench)

        # Yükseklik, her satır için gap + blok boşlukları ile birlikte
        block_count = (rows - 1) // mlen
        usable_h = rect.height() - block_count * group_gap_y - (rows - 1) * gap_y
        cell_h = usable_h / rows

        posmap: Dict[Tuple[int,int], Placement] = {(pl.pos.row, pl.pos.col): pl for pl in placements}

        # Renkler
        seat_fill  = QColor(SEAT_FILL)
        seat_empty = QColor(SEAT_EMPTY)
        seat_bg    = QColor(SEAT_BG)
        seat_line  = QColor(SEAT_LINE)

        # Fontlar
        base     = max(10.0, min(cell_w, cell_h))
        # PDF’te biraz daha küçük tut
        name_pt  = int(max(6, base * (0.22 if for_pdf else 0.28)))
        small_pt = int(max(5, base * 0.20))
        name_font  = QFont(); name_font.setPointSize(name_pt); name_font.setBold(True)
        small_font = QFont(); small_font.setPointSize(small_pt)

        # Görsel yoğunluk eşikleri
        show_indices    = (cell_w >= 22 and cell_h >= 14)
        show_full_name  = (cell_w >= 52 and cell_h >= 26)

        for r in range(rows):
            y = rect.y() + r * (cell_h + gap_y) + (r // mlen) * group_gap_y
            x = rect.x()
            for c in range(cols):
                cell = QRectF(x, y, cell_w, cell_h)
                x += cell_w + gap_x

                inner = 2.5 * z
                capsule = QRectF(cell.x()+inner, cell.y()+inner,
                                 cell.width()-2*inner, cell.height()-2*inner)

                allowed = bench[r % mlen] == 1       # desen BOYUNA (satır yönünde)
                filled  = (r, c) in posmap

                brush = seat_bg
                if allowed and not filled: brush = seat_empty
                if allowed and filled:      brush = seat_fill

                pen = QPen(seat_line)
                pen.setWidthF(0.6 if for_pdf else 1.1 * z)
                p.setPen(pen); p.setBrush(brush)
                p.drawRoundedRect(capsule, 7*z, 7*z)

                # Izgara (isteğe bağlı)
                if self._show_grid and not for_pdf:
                    p.save()
                    p.setPen(QPen(QColor("#E5E7EB")))
                    p.drawRect(cell)
                    p.restore()

                # Sol üst sıra,sütun etiketi
                if show_indices:
                    p.save()
                    p.setFont(small_font)
                    p.setPen(QColor("#546E7A") if not filled else QColor("#E0F2F1"))
                    lt = QRectF(capsule.x()+2*z, capsule.y()+0.8*z, 30*z, 10*z)
                    p.drawText(lt, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                               f"{r+1},{c+1}")
                    p.restore()

                # Öğrenci
                if filled and (self._show_names or for_pdf):
                    st = posmap[(r, c)].student
                    p.save()
                    p.setFont(name_font); p.setPen(QColor("#FFFFFF"))
                    txt = f"{_short_name(st.name)}\n{st.no}" if show_full_name else st.no
                    p.drawText(capsule, int(Qt.AlignmentFlag.AlignCenter), txt)
                    p.restore()
