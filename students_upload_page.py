from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QFrame, QProgressBar, QMessageBox, QSizePolicy
)
from excel_import import parse_student_enrollments_xlsx, import_student_enrollments


class StudentsUploadPage(QWidget):
    def __init__(self, user: dict):
        super().__init__()
        self.user = user or {}
        self._picked_path = None
        self.setAcceptDrops(True)

        self.setStyleSheet("""
            QLabel#Title    { font-size:22px; font-weight:800; color:#0B1324; }
            QLabel#Subtitle { color:#6B7280; }
            QFrame#DropZone { background:#F9FAFB; border:2px dashed #C7CDD4; border-radius:14px; }
            QFrame#Banner   { background:#ECFDF5; border:1px solid #D1FAE5; border-radius:12px; }
            QLabel#BannerText { color:#065F46; }
            QPushButton#Primary {
                background:#16A34A; color:white; border:none; border-radius:10px;
                font-weight:700; padding:10px 16px;
            }
            QPushButton#Primary:hover   { background:#19b254; }
            QPushButton#Primary:pressed { background:#138a43; }
            QPushButton#Ghost {
                background:#EEF2F7; color:#0F172A; border:1px solid #E5E7EB;
                border-radius:10px; padding:10px 14px; font-weight:600;
            }
        """)

        root = QVBoxLayout(self); root.setContentsMargins(12,12,12,12); root.setSpacing(12)

        # Başlık
        t = QLabel("Öğrenci Listesi Yükleme"); t.setObjectName("Title")
        s = QLabel("Excel parser ile öğrenci yükleme."); s.setObjectName("Subtitle")
        root.addWidget(t); root.addWidget(s)

        # Banner
        self.banner = QFrame(); self.banner.setObjectName("Banner"); self.banner.setVisible(False)
        bl = QHBoxLayout(self.banner); bl.setContentsMargins(12,8,12,8)
        self.banner_lbl = QLabel("Hazır"); self.banner_lbl.setObjectName("BannerText")
        close_btn = QPushButton("Kapat"); close_btn.setObjectName("Ghost")
        close_btn.clicked.connect(lambda: self.banner.setVisible(False))
        bl.addWidget(QLabel("✅")); bl.addWidget(self.banner_lbl, 1); bl.addWidget(close_btn)
        root.addWidget(self.banner)

        # Drop-zone (merkezlenmiş)
        center = QVBoxLayout(); center.addStretch(1)
        row_center = QHBoxLayout(); row_center.addStretch(1)

        self.drop = QFrame(); self.drop.setObjectName("DropZone")
        self.drop.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.drop.setMinimumSize(640, 160)

        dz = QVBoxLayout(self.drop); dz.setContentsMargins(18,24,18,24); dz.setSpacing(8)
        self.dz_title = QLabel("Dosyanızı buraya sürükleyip bırakın (.xlsx / .xls)")
        self.dz_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sel_lbl = QLabel("Seçili dosya: —"); self.sel_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pick_btn = QPushButton("Dosya Seç…"); pick_btn.setObjectName("Ghost")
        pick_btn.clicked.connect(self._pick_file)
        dz.addWidget(self.dz_title); dz.addWidget(self.sel_lbl); dz.addWidget(pick_btn, 0, Qt.AlignmentFlag.AlignCenter)

        row_center.addWidget(self.drop); row_center.addStretch(1)
        center.addLayout(row_center); center.addStretch(1)
        root.addLayout(center)

        # Alt satır: Yükle + Progress
        row = QHBoxLayout(); row.addStretch(1)
        self.upload_btn = QPushButton("Excel'den Öğrenci Listesi Yükle"); self.upload_btn.setObjectName("Primary")
        self.upload_btn.clicked.connect(self._start_import_clicked)
        row.addWidget(self.upload_btn); root.addLayout(row)

        self.prg = QProgressBar(); self.prg.setVisible(False); self.prg.setRange(0, 0)
        root.addWidget(self.prg)

    # Drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            for u in e.mimeData().urls():
                if u.toLocalFile().lower().endswith((".xlsx", ".xls")):
                    e.acceptProposedAction(); return
        e.ignore()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith((".xlsx", ".xls")):
                self._set_file(p); break

    # Helpers
    def _set_file(self, path: str):
        self._picked_path = path
        self.sel_lbl.setText(f"Seçili dosya: {path}")

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Öğrenci Excel'i Seç", "", "Excel (*.xlsx *.xls)")
        if path: self._set_file(path)

    def _busy(self, on: bool):
        self.prg.setVisible(on)
        self.upload_btn.setEnabled(not on)
        self.drop.setEnabled(not on)

    # Import
    def _start_import_clicked(self):
        if not self._picked_path:
            QMessageBox.information(self, "Dosya Seçilmedi", "Lütfen bir Excel dosyası seçin ya da sürükleyin.")
            return
        dept_id = (self.user or {}).get("department_id")
        if dept_id is None:
            QMessageBox.warning(self, "Bölüm Seçilmedi", "İçe aktarmadan önce bölüm belirlenmeli.")
            return
        self._start_import(self._picked_path, int(dept_id))

    def _start_import(self, path: str, department_id: int):
        try:
            self._busy(True)
            df = parse_student_enrollments_xlsx(path)
            if df.empty:
                QMessageBox.information(self, "Öğrenci Yükleme", "Excel'de öğrenci verisi bulunamadı.")
                return

            stu_up, sc_ins, miss = import_student_enrollments(df, department_id)

            self.banner_lbl.setText(
                f"Tamamlandı • Yeni öğrenci: {stu_up} • Kayıt: {sc_ins} • Eşleşmeyen ders: {miss}"
            )
            self.banner.setVisible(True)
            QMessageBox.information(
                self, "Öğrenci Yükleme",
                f"Tamamlandı.\nÖğrenci (ilk eklenen): {stu_up}\n"
                f"Kayıt (StudentCourses eklenen): {sc_ins}\n"
                f"Eşleşmeyen ders kodu: {miss}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Öğrenci listesi yüklenemedi:\n{e}")
        finally:
            self._busy(False)
