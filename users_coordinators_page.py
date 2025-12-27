# users_coordinators_page.py
# PyQt6 — Koordinatör yönetimi (Admin)
# Özellikler:
#  - Ekle: Ad/Ünvan + E-posta + Bölüm + (opsiyonel) Foto → Users + Instructors (upsert)
#  - Düzenle: Seçileni güncelle (ad, e-posta, bölüm, foto)
#  - Sil: Users ve eşleşen Instructors kaydını kaldır
#  - Şifre Sıfırla: 4 haneli PIN üret, bcrypt ile güncelle ve ekrana göster
#  - Tüm e-posta alanları normalize (trim + lower)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QPushButton,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QTextEdit,
    QApplication, QFrame, QLabel, QSizePolicy, QSpacerItem, QFileDialog
)
from PyQt6.QtCore import Qt
from passlib.hash import bcrypt
import random, string, os, shutil

from db import get_connection   # ✅ DOĞRU: DB bağlantısı

ROLE_COORDINATOR = 2  # sabit rol id (koordinatör)

def warn(msg, parent=None): QMessageBox.warning(parent, "Uyarı", msg)
def info(msg, parent=None): QMessageBox.information(parent, "Bilgi", msg)

def _slugify_filename(email: str, default="instructor"):
    name = (email or "").split("@")[0].strip().replace(" ", "_")
    return name or default

# -------------------- Düzenleme Diyaloğu --------------------
class EditCoordinatorDialog(QDialog):
    def __init__(self, parent, name, email, dept_id, photo_url):
        super().__init__(parent)
        self.setWindowTitle("Koordinatör Düzenle")
        self._src_photo = None

        v = QVBoxLayout(self)
        def row(lbl, w):
            h = QHBoxLayout(); h.addWidget(QLabel(lbl)); h.addWidget(w); v.addLayout(h)

        self.ed_name  = QLineEdit(name or "")
        self.ed_email = QLineEdit(email or "")
        self.cb_dept  = QComboBox(); self._load_departments()
        if dept_id is not None:
            idx = self.cb_dept.findData(int(dept_id))
            if idx >= 0: self.cb_dept.setCurrentIndex(idx)

        self.ed_photo = QLineEdit(photo_url or ""); self.ed_photo.setReadOnly(True)
        btn_browse = QPushButton("Foto Seç"); btn_browse.clicked.connect(self._pick_photo)

        row("Ad / Ünvan", self.ed_name)
        row("E-posta",     self.ed_email)
        row("Bölüm",       self.cb_dept)
        hh = QHBoxLayout(); hh.addWidget(self.ed_photo, 1); hh.addWidget(btn_browse, 0); v.addLayout(hh)

        btns = QHBoxLayout(); btns.addStretch(1)
        btn_cancel = QPushButton("İptal"); btn_ok = QPushButton("Kaydet")
        btn_cancel.clicked.connect(self.reject); btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_cancel); btns.addWidget(btn_ok); v.addLayout(btns)

    def _load_departments(self):
        self.cb_dept.clear()
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT DepartmentID, Name FROM dbo.Departments ORDER BY DepartmentID")
            for r in cur.fetchall():
                self.cb_dept.addItem(r.Name, r.DepartmentID)

    def _pick_photo(self):
        pth, _ = QFileDialog.getOpenFileName(self, "Fotoğraf Seç", "", "Resimler (*.png *.jpg *.jpeg)")
        if pth:
            self._src_photo = pth
            self.ed_photo.setText(pth)

    def values(self):
        name  = (self.ed_name.text()  or "").strip()
        email = (self.ed_email.text() or "").strip().lower()
        dept  = self.cb_dept.currentData()
        return name, email, int(dept) if dept is not None else None, self._src_photo

# -------------------- Ana Sayfa --------------------
class CoordinatorsPage(QWidget):
    def __init__(self, user):
        super().__init__()
        self.user = user or {}
        self.photo_src_path = None  # ekle formu için seçilen foto

        # — Stil —
        self.setStyleSheet("""
            QWidget { font-size: 14px; color:#0F172A; }
            QLabel#PageTitle { font-size: 22px; font-weight: 800; color:#0B1324; }

            QFrame#Card {
                background:#FFFFFF; border-radius:16px;
                border:1px solid #E5E7EB;
            }

            QPushButton#Primary {
                background:#16A34A; color:#FFFFFF; border:none; border-radius:12px;
                font-weight:700; padding:10px 16px;
            }
            QPushButton#Primary:hover  { background:#19b254; }
            QPushButton#Primary:pressed{ background:#138a43; }

            QPushButton#Ghost {
                background:#F3F4F6; color:#111827; border:1px solid #E5E7EB;
                border-radius:10px; padding:8px 12px; font-weight:600;
            }
            QPushButton#Ghost:hover { background:#ECEEF1; }

            QLineEdit, QComboBox {
                border:1px solid #E5E7EB; border-radius:12px; padding:10px 12px;
                font-size:14px; background:#FAFBFC; min-height:40px;
            }
            QLineEdit:focus, QComboBox:focus { border:1px solid #16A34A; background:#FFFFFF; }

            QTableWidget {
                background:#FFFFFF; border:1px solid #E5E7EB; border-radius:12px;
                gridline-color:#EEF1F4; alternate-background-color:#FAFAFB;
            }
            QHeaderView::section {
                background:#F0FDF4; color:#0B1324; border:none; padding:10px;
                font-weight:800; font-size:13px;
            }
            QTableWidget::item { padding:8px; }
            QTableWidget::item:selected { background:#DCFCE7; color:#0B1324; }

            QFrame#Banner { background:#ECFDF5; border:1px solid #D1FAE5; border-radius:12px; }
            QLabel#BannerIcon { color:#059669; font-weight:900; }
            QLabel#BannerText { color:#065F46; }
        """)

        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(14)

        # Başlık
        title = QLabel("Koordinatörler"); title.setObjectName("PageTitle")
        trow = QHBoxLayout(); trow.addWidget(title); trow.addStretch(1); root.addLayout(trow)

        # Üst bilgi şeridi (gizli)
        self.banner = QFrame(); self.banner.setObjectName("Banner"); self.banner.setVisible(False)
        bl = QHBoxLayout(self.banner); bl.setContentsMargins(12,8,12,8); bl.setSpacing(10)
        bicon = QLabel("✓"); bicon.setObjectName("BannerIcon")
        self.btext = QLabel(); self.btext.setObjectName("BannerText")
        bclose = QPushButton("Kapat"); bclose.setObjectName("Ghost")
        bclose.clicked.connect(lambda: self.banner.setVisible(False))
        bl.addWidget(bicon); bl.addWidget(self.btext, 1); bl.addWidget(bclose)
        root.addWidget(self.banner)

        # Kart: Ekle formu
        card = QFrame(); card.setObjectName("Card")
        cv = QVBoxLayout(card); cv.setContentsMargins(18,16,18,16); cv.setSpacing(10)

        crow = QHBoxLayout(); crow.setSpacing(10)
        self.ed_name = QLineEdit(); self.ed_name.setPlaceholderText("Ad Soyad / Ünvan")
        self.ed_email = QLineEdit(); self.ed_email.setPlaceholderText("Koordinatör e-posta adresi")
        self.cb_dept = QComboBox(); self._load_departments()

        self.ed_photo = QLineEdit(); self.ed_photo.setPlaceholderText("Fotoğraf yolu (seçiniz)")
        self.ed_photo.setReadOnly(True)
        btn_browse = QPushButton("Foto Seç"); btn_browse.setObjectName("Ghost")
        btn_browse.clicked.connect(self._pick_photo)

        btn_add = QPushButton("Ekle"); btn_add.setObjectName("Primary"); btn_add.setFixedWidth(130)
        btn_add.clicked.connect(self._create_coordinator)

        crow.addWidget(self.ed_name, 2)
        crow.addWidget(self.ed_email, 2)
        crow.addWidget(self.cb_dept, 1)
        crow.addWidget(self.ed_photo, 2)
        crow.addWidget(btn_browse, 0)
        crow.addItem(QSpacerItem(10,10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        crow.addWidget(btn_add, 0, Qt.AlignmentFlag.AlignRight)
        cv.addLayout(crow)

        # Form altı: tablo aksiyon butonları
        actions = QHBoxLayout()
        self.btn_edit = QPushButton("Düzenle");       self.btn_edit.setObjectName("Ghost")
        self.btn_reset= QPushButton("Şifre Sıfırla"); self.btn_reset.setObjectName("Ghost")
        self.btn_del  = QPushButton("Sil");           self.btn_del.setObjectName("Ghost")
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_reset.clicked.connect(self._resetpw_selected)
        self.btn_del.clicked.connect(self._delete_selected)
        actions.addStretch(1)
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_reset)
        actions.addWidget(self.btn_del)
        cv.addLayout(actions)

        root.addWidget(card)

        # Tablo
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["ID", "Ad Soyad", "E-posta", "Rol", "Bölüm"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setHighlightSections(False)
        self.tbl.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setMinimumHeight(360)
        root.addWidget(self.tbl, 1)

        self._load_coordinators()

    # ---------- helpers ----------
    def _pick_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Fotoğraf Seç", "", "Resimler (*.png *.jpg *.jpeg)")
        if path:
            self.photo_src_path = path
            self.ed_photo.setText(path)

    def _load_departments(self):
        self.cb_dept.clear()
        self.cb_dept.addItem("Bölüm", None)
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT DepartmentID, Name FROM dbo.Departments ORDER BY DepartmentID")
            for r in cur.fetchall():
                self.cb_dept.addItem(r.Name, r.DepartmentID)
        self.cb_dept.setCurrentIndex(0)

    def _center_item(self, value) -> QTableWidgetItem:
        it = QTableWidgetItem("" if value is None else str(value))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return it

    def _load_coordinators(self):
        self.tbl.setRowCount(0)
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT U.UserID,
                       ISNULL(I.Name, '') AS IName,
                       U.Email,
                       R.Name AS RoleName,
                       D.Name AS DeptName
                FROM dbo.Users U
                LEFT JOIN dbo.Roles R ON R.RoleID = U.RoleID
                LEFT JOIN dbo.Departments D ON D.DepartmentID = U.DepartmentID
                LEFT JOIN dbo.Instructors I ON LOWER(LTRIM(RTRIM(I.Email))) = LOWER(LTRIM(RTRIM(U.Email)))
                WHERE U.RoleID = ?
                ORDER BY U.UserID
            """, (ROLE_COORDINATOR,))
            rows = cur.fetchall()

        if not rows:
            self.tbl.setRowCount(1)
            for c, txt in enumerate(["—", "Henüz koordinatör yok", "—", "coordinator", "—"]):
                self.tbl.setItem(0, c, self._center_item(txt))
            self.tbl.setDisabled(True)
        else:
            self.tbl.setDisabled(False)
            for r in rows:
                row = self.tbl.rowCount()
                self.tbl.insertRow(row)
                vals = [r.UserID, (r.IName or "—"), r.Email, (r.RoleName or ""), (r.DeptName or "—")]
                for c, val in enumerate(vals):
                    self.tbl.setItem(row, c, self._center_item(val))

    def _email_exists(self, email_norm: str) -> bool:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM dbo.Users WHERE LOWER(RTRIM(LTRIM(Email)))=?", (email_norm,))
            return cur.fetchone() is not None

    def _gen_temp_pin(self) -> str:
        # 4 farklı rakamdan oluşan PIN
        return "".join(random.sample(list(string.digits), 4))

    def _ensure_assets_dir(self) -> str:
        target_dir = os.path.join("assets", "instructors")
        os.makedirs(target_dir, exist_ok=True)
        return target_dir

    def _copy_photo(self, email: str, src_path: str | None = None) -> str | None:
        """Belirtilen resmi assets/instructors altına kopyalar, göreli yolu döndürür."""
        src = src_path or self.photo_src_path
        if not src:
            return None
        target_dir = self._ensure_assets_dir()
        name = _slugify_filename(email)
        ext = os.path.splitext(src)[1].lower() or ".jpg"
        dest = os.path.join(target_dir, f"{name}{ext}")
        try:
            shutil.copyfile(src, dest)
            return dest.replace("\\", "/")  # Windows ayıracı → /
        except Exception as e:
            warn(f"Fotoğraf kopyalanamadı: {e}", self)
            return None

    def _upsert_instructor(self, name: str, email: str, dept_id: int, photo_relpath: str | None):
        """E-posta ile Instructors üzerinde insert/update yapar."""
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT InstructorID FROM dbo.Instructors
                WHERE LOWER(LTRIM(RTRIM(Email))) = LOWER(LTRIM(RTRIM(?)))
            """, (email,))
            row = cur.fetchone()
            if row:
                cur.execute("""
                    UPDATE dbo.Instructors
                       SET Name = ?, DepartmentID = ?, PhotoUrl = ?
                     WHERE InstructorID = ?
                """, (name, dept_id, photo_relpath, row.InstructorID))
            else:
                cur.execute("""
                    INSERT INTO dbo.Instructors(Name, Email, DepartmentID, PhotoUrl)
                    VALUES (?, ?, ?, ?)
                """, (name, email, dept_id, photo_relpath))
            conn.commit()

    def _sel_row_info(self):
        r = self.tbl.currentRow()
        if r < 0: return None
        def txt(c):
            it = self.tbl.item(r, c)
            return (it.text() if it else "").strip()
        try:
            uid = int(txt(0))
        except ValueError:
            return None
        return {
            "user_id": uid,
            "name": txt(1),
            "email": txt(2).lower(),
            "role_name": txt(3),
            "dept_name": txt(4)
        }

    # ---------- actions ----------
    def _create_coordinator(self):
        name = (self.ed_name.text() or "").strip()
        email = (self.ed_email.text() or "").strip().lower()
        dept_id = self.cb_dept.currentData()

        if not name or len(name) < 3:
            warn("Lütfen geçerli bir ad/ünvan girin.", self); return
        if "@" not in email or "." not in email.split("@")[-1]:
            warn("Geçerli bir e-posta giriniz.", self); return
        if not dept_id:
            warn("Lütfen bir bölüm seçin.", self); return

        if self._email_exists(email):
            warn("Bu e-posta ile bir kullanıcı zaten var.", self); return

        temp_pw = self._gen_temp_pin()
        pw_hash = bcrypt.hash(temp_pw)

        photo_rel = self._copy_photo(email)

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO dbo.Users(Email, PasswordHash, RoleID, DepartmentID)
                VALUES (?, ?, ?, ?)
            """, (email, pw_hash, ROLE_COORDINATOR, int(dept_id)))
            conn.commit()

        self._upsert_instructor(name, email, int(dept_id), photo_rel)

        # UI refresh
        self._load_coordinators()
        self.ed_name.clear(); self.ed_email.clear(); self.cb_dept.setCurrentIndex(0)
        self.ed_photo.clear(); self.photo_src_path = None

        # Üst bilgi şeridi + diyalog
        self.btext.setText(f"Koordinatör eklendi: {name} • {email} • Geçici şifre: {temp_pw}")
        self.banner.setVisible(True)
        self._show_pw_dialog(name, email, temp_pw)

    def _show_pw_dialog(self, name: str, email: str, pw: str):
        dlg = QDialog(self); dlg.setWindowTitle("Koordinatör Oluşturuldu")
        lay = QVBoxLayout(dlg); lay.setContentsMargins(14,12,14,12); lay.setSpacing(10)

        head = QLabel("Koordinatör oluşturuldu"); head.setObjectName("PageTitle"); lay.addWidget(head)
        txt = QTextEdit(readOnly=True)
        txt.setPlainText(
            f"Ad Soyad: {name}\n"
            f"E-posta: {email}\n"
            f"Geçici Şifre (4 hane): {pw}\n\n"
            f"Kullanıcı bu şifre ile giriş yapabilir.\n"
            f"İlk girişten sonra şifre değişimi önerilir."
        )
        lay.addWidget(txt)

        row = QHBoxLayout()
        btn_copy = QPushButton("Şifreyi Kopyala"); btn_copy.setObjectName("Ghost")
        btn_ok   = QPushButton("Kapat");          btn_ok.setObjectName("Primary")
        row.addWidget(btn_copy); row.addStretch(1); row.addWidget(btn_ok)
        lay.addLayout(row)

        btn_copy.clicked.connect(lambda: (QApplication.clipboard().setText(pw), info("Şifre kopyalandı.", dlg)))
        btn_ok.clicked.connect(dlg.accept)
        dlg.resize(520, 300)
        dlg.exec()

    def _edit_selected(self):
        sel = self._sel_row_info()
        if not sel:
            warn("Lütfen bir satır seçin.", self); return

        # mevcut verileri çek
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT U.UserID, U.Email, U.DepartmentID,
                       ISNULL(I.Name,''), ISNULL(I.PhotoUrl,'')
                FROM dbo.Users U
                LEFT JOIN dbo.Instructors I
                  ON LOWER(LTRIM(RTRIM(I.Email)))=LOWER(LTRIM(RTRIM(U.Email)))
                WHERE U.UserID=?""", (sel["user_id"],))
            r = cur.fetchone()
            if not r: 
                warn("Kayıt bulunamadı.", self); return
            user_id, old_email, dept_id, name, photo = r.UserID, r.Email, r.DepartmentID, r[3], r[4]

        dlg = EditCoordinatorDialog(self, name, old_email, dept_id, photo)
        if not dlg.exec(): return
        new_name, new_email, new_dept, src_photo = dlg.values()
        if not new_name or "@" not in new_email:
            warn("Ad ve geçerli e-posta zorunludur.", self); return
        if new_dept is None:
            warn("Bölüm seçiniz.", self); return

        # e-posta çakışması
        if new_email != (old_email or "").lower():
            with get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT 1 FROM dbo.Users WHERE LOWER(LTRIM(RTRIM(Email)))=?", (new_email,))
                if c.fetchone():
                    warn("Bu e-posta zaten kullanımda.", self); return

        # foto kopyala (varsa)
        photo_rel = self._copy_photo(new_email, src_photo) if src_photo else None

        # veritabanı güncelle
        with get_connection() as conn:
            cur = conn.cursor()
            # Users
            cur.execute("""
                UPDATE dbo.Users
                   SET Email = ?, DepartmentID = ?
                 WHERE UserID = ?""", (new_email, int(new_dept), user_id))

            # Instructors upsert & email değişimi
            cur.execute("SELECT InstructorID FROM dbo.Instructors WHERE LOWER(LTRIM(RTRIM(Email)))=?", (old_email,))
            inst = cur.fetchone()
            if inst:
                cur.execute("""
                    UPDATE dbo.Instructors
                       SET Name=?, Email=?, DepartmentID=?, PhotoUrl=ISNULL(?, PhotoUrl)
                     WHERE InstructorID=?""",
                    (new_name, new_email, int(new_dept), photo_rel, inst.InstructorID))
            else:
                cur.execute("""
                    INSERT INTO dbo.Instructors(Name, Email, DepartmentID, PhotoUrl)
                    VALUES(?,?,?,?)""",
                    (new_name, new_email, int(new_dept), photo_rel))
            conn.commit()

        info("Koordinatör güncellendi.", self)
        self._load_coordinators()

    def _delete_selected(self):
        sel = self._sel_row_info()
        if not sel:
            warn("Lütfen bir satır seçin.", self); return
        if QMessageBox.question(self, "Onay",
            f"{sel['email']} kullanıcısını silmek istiyor musunuz?") != QMessageBox.StandardButton.Yes:
            return

        with get_connection() as conn:
            cur = conn.cursor()
            # Instructors'ı e-postadan sil
            cur.execute("DELETE FROM dbo.Instructors WHERE LOWER(LTRIM(RTRIM(Email)))=?", (sel["email"],))
            # Users'ı ID'den sil
            cur.execute("DELETE FROM dbo.Users WHERE UserID=?", (sel["user_id"],))
            conn.commit()

        info("Koordinatör silindi.", self)
        self._load_coordinators()

    def _resetpw_selected(self):
        sel = self._sel_row_info()
        if not sel:
            warn("Lütfen bir satır seçin.", self); return
        pin = self._gen_temp_pin()
        pw_hash = bcrypt.hash(pin)
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE dbo.Users SET PasswordHash=? WHERE UserID=?", (pw_hash, sel["user_id"]))
            conn.commit()
        info(f"Yeni geçici şifre: {pin}\nKullanıcı girişten sonra değiştirmeli.", self)

    def _gen_temp_pin(self) -> str:
        # 4 farklı rakamdan oluşan PIN
        return "".join(random.sample(list(string.digits), 4))
