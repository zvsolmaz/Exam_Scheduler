# classrooms_page.py
# Koordinatör: sadece kendi bölümünün dersliklerini görür/işler.
# - Listeleme + Ekle/Düzenle/Sil
# - Sağda oturma düzeni önizlemesi (Cols x Rows + grup çizgileri)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QLineEdit, QSpinBox, QLabel, QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPen
from auth import get_connection, get_department_name

ROLE_ADMIN = 1
ROLE_COORDINATOR = 2

def warn(parent, m): QMessageBox.warning(parent, "Uyarı", m)
def info(parent, m): QMessageBox.information(parent, "Bilgi", m)

# ----------------------------- Oturma Önizleme -----------------------------
class SeatPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cols = 0; self.rows = 0; self.group = 0
        self.setMinimumWidth(420)

    def set_layout(self, cols:int, rows:int, group:int):
        self.cols = max(0, int(cols or 0))
        self.rows = max(0, int(rows or 0))
        self.group = max(0, int(group or 0))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad = 16
        rect = self.rect().adjusted(pad, pad, -pad, -pad)
        p.fillRect(rect, self.palette().base())
        if self.cols and self.rows:
            cell_w = rect.width() / self.cols
            cell_h = rect.height() / self.rows
            pen = QPen(self.palette().mid().color()); pen.setWidthF(1); p.setPen(pen)
            for c in range(self.cols + 1):
                x = rect.left() + c * cell_w
                p.drawLine(int(x), rect.top(), int(x), rect.bottom())
            for r in range(self.rows + 1):
                y = rect.top() + r * cell_h
                p.drawLine(rect.left(), int(y), rect.right(), int(y))
            if self.group and self.group > 1:
                thick = QPen(self.palette().dark().color()); thick.setWidth(2); p.setPen(thick)
                for c in range(self.group, self.cols, self.group):
                    x = rect.left() + c * cell_w
                    p.drawLine(int(x), rect.top(), int(x), rect.bottom())

# ------------------------------ Ekle/Düzenle Dialog ------------------------------
class ClassroomDialog(QDialog):
    """Ekle/Düzenle. Koordinatör bölümünü değiştiremez."""
    def __init__(self, parent, user, record=None):
        super().__init__(parent)
        self.user = user or {}
        self.role = self.user.get("RoleID") or self.user.get("role_id")
        self.my_dept = self.user.get("DepartmentID") or self.user.get("department_id")
        self.record = record
        self.setWindowTitle("Derslik " + ("Düzenle" if record else "Ekle"))

        lay = QVBoxLayout(self)

        # Bölüm
        self.cb_dept = QComboBox()
        if self.role == ROLE_ADMIN:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT DepartmentID, Name FROM dbo.Departments ORDER BY Name")
                for r in cur.fetchall():
                    self.cb_dept.addItem(r.Name, r.DepartmentID)
        else:
            self.cb_dept.addItem("(Bölümünüz)", int(self.my_dept))
            self.cb_dept.setEnabled(False)

        # Alanlar
        self.ed_code = QLineEdit()
        self.ed_name = QLineEdit()
        self.sp_capacity = QSpinBox(); self.sp_capacity.setRange(1, 10000)
        self.sp_cols = QSpinBox(); self.sp_cols.setRange(1, 1000)
        self.sp_rows = QSpinBox(); self.sp_rows.setRange(1, 1000)
        self.sp_group = QSpinBox(); self.sp_group.setRange(1, 50)

        def row(lbl, w):
            h = QHBoxLayout(); h.addWidget(QLabel(lbl)); h.addWidget(w); lay.addLayout(h)

        row("Bölüm", self.cb_dept)
        row("Kod", self.ed_code)
        row("Ad", self.ed_name)
        row("Kapasite", self.sp_capacity)
        row("Sütun (Cols)", self.sp_cols)
        row("Satır (Rows)", self.sp_rows)
        row("Sıra Grup", self.sp_group)

        # Butonlar
        btns = QHBoxLayout(); lay.addLayout(btns)
        btn_cancel = QPushButton("İptal"); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Kaydet"); btn_ok.clicked.connect(self.accept)
        btns.addStretch(1); btns.addWidget(btn_cancel); btns.addWidget(btn_ok)

        if record:
            self.cb_dept.setCurrentIndex(max(0, self.cb_dept.findData(int(record["DepartmentID"]))))
            self.ed_code.setText(record["Code"] or "")
            self.ed_name.setText(record["Name"] or "")
            self.sp_capacity.setValue(int(record["Capacity"] or 1))
            self.sp_cols.setValue(int(record["Cols"] or 1))
            self.sp_rows.setValue(int(record["Rows"] or 1))
            self.sp_group.setValue(int(record.get("DeskGroupSize") or 1))

    def values(self):
        code = self.ed_code.text().strip()
        name = self.ed_name.text().strip()
        if not code or not name:
            warn(self, "Kod ve Ad zorunludur."); return None
        dept_data = self.cb_dept.currentData()
        return {
            "DepartmentID": int(dept_data) if dept_data is not None else None,
            "Code": code,
            "Name": name,
            "Capacity": int(self.sp_capacity.value()),
            "Cols": int(self.sp_cols.value()),
            "Rows": int(self.sp_rows.value()),
            "DeskGroupSize": int(self.sp_group.value()),
        }

# --------------------------------- Sayfa ---------------------------------
class ClassroomsPage(QWidget):
    """Koordinatör: sadece kendi bölümünün dersliklerini görür/işler. Admin: tümü."""
    def __init__(self, user):
        super().__init__()
        self.user = user or {}
        self.role = self.user.get("RoleID") or self.user.get("role_id")
        self.my_dept = self.user.get("DepartmentID") or self.user.get("department_id")
        self.email   = self.user.get("Email") or self.user.get("email") or ""

        # Sol: kontrol butonları + tablo  |  Sağ: önizleme
        root = QHBoxLayout(self)

        left_container = QVBoxLayout(); left_container.setSpacing(10)
        root.addLayout(left_container, 3)

        # Üst araç satırı + tablo
        inner = QVBoxLayout(); left_container.addLayout(inner, 1)

        btns = QHBoxLayout()
        self.btn_add  = QPushButton("Ekle");    self.btn_add.clicked.connect(self.add_classroom)
        self.btn_edit = QPushButton("Düzenle"); self.btn_edit.clicked.connect(self.edit_selected)
        self.btn_del  = QPushButton("Sil");     self.btn_del.clicked.connect(self.delete_selected)
        btns.addStretch(1); btns.addWidget(self.btn_add); btns.addWidget(self.btn_edit); btns.addWidget(self.btn_del)
        inner.addLayout(btns)

        self.tbl = QTableWidget(0, 8)
        self.tbl.setHorizontalHeaderLabels(["ID","DepartmentID","Kod","Ad","Kapasite","Cols","Rows","Grup"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.itemSelectionChanged.connect(self._update_preview)
        inner.addWidget(self.tbl, 1)

        if self.role == ROLE_COORDINATOR:
            self.tbl.setColumnHidden(1, True)  # DepartmentID koordinatörde gizli

        # Sağ: Oturma Önizleme
        self.preview = SeatPreview(); root.addWidget(self.preview, 2)

        self.refresh()

    # ---------- Helpers ----------
    def _center_item(self, v):
        it = QTableWidgetItem("" if v is None else str(v))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return it

    def _selected_id(self):
        r = self.tbl.currentRow()
        if r < 0: return None
        it = self.tbl.item(r, 0)
        if not it: return None
        try:
            return int((it.text() or "").strip())
        except ValueError:
            return None

    def _load_rows(self):
        with get_connection() as conn:
            cur = conn.cursor()
            if self.role == ROLE_COORDINATOR and self.my_dept:
                cur.execute("""
                    SELECT ClassroomID, DepartmentID, Code, Name, Capacity, Cols, Rows, DeskGroupSize
                    FROM dbo.Classrooms
                    WHERE DepartmentID = ?
                    ORDER BY ClassroomID
                """, (int(self.my_dept),))
            else:
                cur.execute("""
                    SELECT ClassroomID, DepartmentID, Code, Name, Capacity, Cols, Rows, DeskGroupSize
                    FROM dbo.Classrooms
                    ORDER BY ClassroomID
                """)
            return cur.fetchall()

    def refresh(self):
        rows = self._load_rows()
        self.tbl.setRowCount(0)
        for r in rows:
            row = self.tbl.rowCount(); self.tbl.insertRow(row)
            vals = [r.ClassroomID, r.DepartmentID, r.Code, r.Name, r.Capacity, r.Cols, r.Rows, r.DeskGroupSize]
            for c, v in enumerate(vals):
                self.tbl.setItem(row, c, self._center_item(v))

        if rows:
            self.tbl.selectRow(0)
            self._update_preview()
        else:
            self.preview.set_layout(0,0,0)

    def _fetch_record(self, classroom_id):
        with get_connection() as conn:
            cur = conn.cursor()
            if self.role == ROLE_COORDINATOR and self.my_dept:
                cur.execute("""
                    SELECT ClassroomID, DepartmentID, Code, Name, Capacity, Cols, Rows, DeskGroupSize
                    FROM dbo.Classrooms
                    WHERE ClassroomID=? AND DepartmentID=?
                """, (classroom_id, int(self.my_dept)))
            else:
                cur.execute("""
                    SELECT ClassroomID, DepartmentID, Code, Name, Capacity, Cols, Rows, DeskGroupSize
                    FROM dbo.Classrooms
                    WHERE ClassroomID=?
                """, (classroom_id,))
            return cur.fetchone()

    # ---------- Önizleme Güncelle ----------
    def _update_preview(self):
        r = self.tbl.currentRow()
        if r < 0 or self.tbl.rowCount() == 0:
            self.preview.set_layout(0, 0, 0)
            return

        def safe_int(col):
            item = self.tbl.item(r, col)
            if not item: return 0
            txt = (item.text() or "").strip()
            try: return int(txt)
            except ValueError: return 0

        cols = safe_int(5); rows = safe_int(6); grp = safe_int(7)
        self.preview.set_layout(cols, rows, grp)

    # ---------- Actions ----------
    def add_classroom(self):
        dlg = ClassroomDialog(self, self.user)
        if dlg.exec():
            data = dlg.values()
            if not data: return
            with get_connection() as conn:
                cur = conn.cursor()
                dept_id = data["DepartmentID"]
                if self.role == ROLE_COORDINATOR and self.my_dept:
                    dept_id = int(self.my_dept)  # güvenlik
                cur.execute("""
                    INSERT INTO dbo.Classrooms(DepartmentID, Code, Name, Capacity, Cols, Rows, DeskGroupSize)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (dept_id, data["Code"], data["Name"], data["Capacity"],
                      data["Cols"], data["Rows"], data["DeskGroupSize"]))
                conn.commit()
            info(self, "Derslik eklendi."); self.refresh()

    def edit_selected(self):
        cid = self._selected_id()
        if not cid: warn(self, "Bir satır seçin."); return
        r = self._fetch_record(cid)
        if not r: warn(self, "Bu dersliği düzenleme yetkiniz yok."); return

        rec = dict(ClassroomID=r.ClassroomID, DepartmentID=r.DepartmentID, Code=r.Code, Name=r.Name,
                   Capacity=r.Capacity, Cols=r.Cols, Rows=r.Rows, DeskGroupSize=r.DeskGroupSize)
        dlg = ClassroomDialog(self, self.user, rec)
        if dlg.exec():
            data = dlg.values()
            if not data: return
            with get_connection() as conn:
                cur = conn.cursor()
                if self.role == ROLE_COORDINATOR and self.my_dept:
                    cur.execute("""
                        UPDATE dbo.Classrooms
                        SET Code=?, Name=?, Capacity=?, Cols=?, Rows=?, DeskGroupSize=?
                        WHERE ClassroomID=? AND DepartmentID=?
                    """, (data["Code"], data["Name"], data["Capacity"], data["Cols"], data["Rows"],
                          data["DeskGroupSize"], cid, int(self.my_dept)))
                else:
                    cur.execute("""
                        UPDATE dbo.Classrooms
                        SET DepartmentID=?, Code=?, Name=?, Capacity=?, Cols=?, Rows=?, DeskGroupSize=?
                        WHERE ClassroomID=?
                    """, (data["DepartmentID"], data["Code"], data["Name"], data["Capacity"],
                          data["Cols"], data["Rows"], data["DeskGroupSize"], cid))
                if cur.rowcount == 0: warn(self, "Güncelleme başarısız veya yetkisiz."); return
                conn.commit()
            info(self, "Derslik güncellendi."); self.refresh()

    def delete_selected(self):
        cid = self._selected_id()
        if not cid: warn(self, "Bir satır seçin."); return
        if QMessageBox.question(self, "Onay", "Seçili derslik silinsin mi?") != QMessageBox.StandardButton.Yes:
            return

        with get_connection() as conn:
            cur = conn.cursor()
            if self.role == ROLE_COORDINATOR and self.my_dept:
                cur.execute("DELETE FROM dbo.Classrooms WHERE ClassroomID=? AND DepartmentID=?",
                            (cid, int(self.my_dept)))
            else:
                cur.execute("DELETE FROM dbo.Classrooms WHERE ClassroomID=?", (cid,))
            if cur.rowcount == 0: warn(self, "Silme başarısız veya yetkiniz yok."); return
            conn.commit()
        info(self, "Derslik silindi."); self.refresh()
