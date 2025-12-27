# issue_dialog.py
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QPushButton
)
import os, sys, subprocess

class IssuesDialog(QDialog):
    def __init__(self, issues, csv_path: str | None = None, parent=None, title="Excel Hata Listesi"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.csv_path = csv_path

        self.setStyleSheet("""
            QDialog { background:#FFFFFF; }
            QLabel#Title { font-size:18px; font-weight:800; color:#991B1B; }
            QLabel#Subtitle { color:#6B7280; }
            QPushButton#Primary {
                background:#16A34A; color:white; border:none; border-radius:10px;
                font-weight:700; padding:10px 16px;
            }
            QPushButton#Ghost {
                background:#F3F4F6; color:#111827; border:1px solid #E5E7EB;
                border-radius:10px; padding:8px 12px; font-weight:600;
            }
            QTableWidget { gridline-color:#E5E7EB; alternate-background-color:#FAFAFB; }
            QHeaderView::section { background:#FEE2E2; color:#7F1D1D; border:none; padding:8px; font-weight:800; }
        """)

        v = QVBoxLayout(self); v.setContentsMargins(14,12,14,12); v.setSpacing(8)

        t = QLabel("İçe aktarma yapılamadı"); t.setObjectName("Title")
        s = QLabel("Excel’de düzeltilmesi gereken satırlar var. Lütfen hataları düzeltip tekrar yükleyin.")
        s.setObjectName("Subtitle")
        v.addWidget(t); v.addWidget(s)

        tbl = QTableWidget(len(issues), 3, self)
        tbl.setHorizontalHeaderLabels(["Sayfa", "Satır", "Açıklama"])
        tbl.setAlternatingRowColors(True)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for i, it in enumerate(issues):
            tbl.setItem(i, 0, QTableWidgetItem(str(getattr(it, "sheet", ""))))
            tbl.setItem(i, 1, QTableWidgetItem(str(getattr(it, "row", ""))))
            tbl.setItem(i, 2, QTableWidgetItem(str(getattr(it, "reason", ""))))
        v.addWidget(tbl)

        btns = QHBoxLayout(); btns.addStretch(1)
        if csv_path:
            btn_open = QPushButton("CSV’yi Aç"); btn_open.setObjectName("Ghost")
            btn_open.clicked.connect(self._open_csv)
            btns.addWidget(btn_open)
        btn_ok = QPushButton("Kapat"); btn_ok.setObjectName("Primary")
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_ok)
        v.addLayout(btns)

        self.resize(820, 540)

    def _open_csv(self):
        if not self.csv_path: return
        p = self.csv_path
        if sys.platform.startswith("win"):
            os.startfile(p)  # nosec - yerel dosya
        elif sys.platform == "darwin":
            subprocess.call(["open", p])
        else:
            subprocess.call(["xdg-open", p])