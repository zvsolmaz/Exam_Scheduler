# login_dialog.py — KOÜ Sınav Takvimi Oluşturma Uygulaması
from PyQt6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QRect, QPoint
from PyQt6.QtGui import QPixmap, QIcon, QColor, QPainter, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QMessageBox, QCheckBox, QSizePolicy, QSpacerItem
)

# auth tarafı
try:
    from auth import verify_user
except ImportError:
    from auth import check_credentials as verify_user

APP_TITLE = "Sınav Takvimi Oluşturma Uygulaması"
WINDOW_TITLE = "Kocaeli Üniversitesi • " + APP_TITLE
ACCENT    = "#1E7C45"
TEXT_DARK = "#1C2B3A"
MUTED     = "#6B7A90"

def load_logo_pixmap(size: int = 56) -> QPixmap:
    try:
        pm = QPixmap("assets/kou_logo.png")
        if not pm.isNull():
            return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    except Exception:
        pass
    # yedek basit logo
    pm = QPixmap(size, size); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHints(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(ACCENT)); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(0, 0, size, size)
    p.setBrush(QColor("white")); w, h = size*0.58, size*0.38; x, y = (size-w)/2, (size-h)/2
    p.drawRoundedRect(int(x), int(y), int(w), int(h), 6, 6)
    p.end()
    return pm

class TitleBar(QFrame):
    """Özel başlık çubuğu: simge + metin + window kontrol butonları"""
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(40)
        self._drag_pos: QPoint | None = None

        h = QHBoxLayout(self); h.setContentsMargins(10, 0, 8, 0); h.setSpacing(8)

        icon = QLabel(); icon.setPixmap(load_logo_pixmap(22))
        title = QLabel(WINDOW_TITLE); title.setObjectName("WindowTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        h.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(title, 1)

        # Sağ kontrol butonları
        self.btn_min = QPushButton("—");   self.btn_min.setObjectName("WinBtn")
        self.btn_max = QPushButton("▢");   self.btn_max.setObjectName("WinBtn")
        self.btn_full= QPushButton("⛶");  self.btn_full.setObjectName("WinBtn")
        self.btn_close = QPushButton("✕"); self.btn_close.setObjectName("WinBtnClose")

        for b in (self.btn_min, self.btn_max, self.btn_full, self.btn_close):
            b.setFixedSize(36, 28)
            h.addWidget(b, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # sinyaller
        self.btn_min.clicked.connect(lambda: parent.showMinimized())
        self.btn_max.clicked.connect(self._toggle_max_restore)
        self.btn_full.clicked.connect(self._toggle_fullscreen)
        self.btn_close.clicked.connect(lambda: (parent.reject(), QApplication.instance().quit()))

        self._is_full = False

    def _toggle_max_restore(self):
        w = self.window()
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()

    def _toggle_fullscreen(self):
        w = self.window()
        if self._is_full:
            self._is_full = False
            w.showNormal()
        else:
            self._is_full = True
            w.showFullScreen()

    # sürükleyerek taşıma
    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._drag_pos is not None and not self.window().isFullScreen():
            self.window().move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._drag_pos = None
        e.accept()

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        icon_pm = load_logo_pixmap(32)
        if not icon_pm.isNull():
            self.setWindowIcon(QIcon(icon_pm))

        # Klasik çerçeveyi kapatıp kendi başlığımızı kullanacağız
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # responsive
        screen_geo = self.screen().availableGeometry() if self.screen() else QRect(0,0,1280,720)
        sw = screen_geo.width()
        self.CARD_W = max(420, min(560, int(sw * 0.30)))
        self.OUTER_GAP = max(12, min(40, int(sw * 0.02)))

        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # ======= ÖZEL BAŞLIK =======
        titlebar = TitleBar(self)

        # ======= GÖVDE =======
        body = QFrame(); body.setObjectName("Body")
        body_v = QVBoxLayout(body)
        body_v.setContentsMargins(self.OUTER_GAP, self.OUTER_GAP, self.OUTER_GAP, self.OUTER_GAP)
        body_v.setSpacing(self.OUTER_GAP)

        # Büyük amblem (girişin üstünde)
        big_logo = QLabel(); big_logo.setPixmap(load_logo_pixmap(110))
        big_logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # --- Giriş kartı ---
        card = QFrame(); card.setObjectName("Card")
        card.setMaximumWidth(self.CARD_W)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        cv = QVBoxLayout(card); cv.setContentsMargins(34, 30, 34, 30); cv.setSpacing(14)

        card_title = QLabel("Kullanıcı Girişi"); card_title.setObjectName("CardTitle")

        self.email = QLineEdit(placeholderText="E-posta")
        self.email.setMinimumHeight(44); self.email.setClearButtonEnabled(True)

        self.password = QLineEdit(placeholderText="Şifre")
        self.password.setMinimumHeight(44); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setClearButtonEnabled(True)

        self.showPw = QCheckBox("Şifreyi göster")
        self.showPw.toggled.connect(
            lambda s: self.password.setEchoMode(QLineEdit.EchoMode.Normal if s else QLineEdit.EchoMode.Password)
        )

        self.btn = QPushButton("Giriş"); self.btn.setObjectName("PrimaryButton")
        self.btn.setMinimumHeight(46); self.btn.clicked.connect(self.try_login)

        info = QLabel("Admin: tüm bölümler  •  Koordinatör: kendi bölümü")
        info.setObjectName("Info"); info.setWordWrap(True); info.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        cv.addWidget(card_title)
        cv.addWidget(self.email)
        cv.addWidget(self.password)
        cv.addWidget(self.showPw)
        cv.addSpacing(6)
        cv.addWidget(self.btn)
        cv.addWidget(info)

        # gölge
        shadow = QGraphicsDropShadowEffect(self); shadow.setBlurRadius(38); shadow.setOffset(0, 16); shadow.setColor(QColor(0,0,0,70))
        card.setGraphicsEffect(shadow)

        # dikey yerleşim: logo -> kart
        body_v.addStretch(1)
        body_v.addWidget(big_logo, 0, Qt.AlignmentFlag.AlignHCenter)
        row = QHBoxLayout(); row.addStretch(1); row.addWidget(card); row.addStretch(1)
        body_v.addLayout(row)
        body_v.addStretch(2)

        root.addWidget(titlebar)   # beyaz başlık
        root.addWidget(body, 1)    # gradient gövde

        # ======= STİL =======
        self.setStyleSheet(f"""
            /* Başlık çubuğu */
            QFrame#TitleBar {{
                background: #FFFFFF;
                border-bottom: 1px solid #E6E6E6;
            }}
            QLabel#WindowTitle {{
                color: #1A202C; font-size: 14px; font-weight: 700;
            }}
            QPushButton#WinBtn, QPushButton#WinBtnClose {{
                background: transparent; border: none; color: #2D3748;
                border-radius: 6px; font-size: 14px; font-weight: 800;
            }}
            QPushButton#WinBtn:hover {{ background: #F2F2F2; }}
            QPushButton#WinBtnClose:hover {{ background: #FEE2E2; color: #B00020; }}

            /* Gövde */
            QFrame#Body {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0F223A, stop:1 #0B182B);
            }}

            QFrame#Card {{ background: #FFFFFF; border-radius: 18px; }}
            QLabel#CardTitle {{ color: {TEXT_DARK}; font-size: 22px; font-weight: 800; }}

            QLineEdit {{
                border: 1px solid #E1E7EF; border-radius: 12px; padding: 10px 12px;
                font-size: 14px; color: {TEXT_DARK}; background: #FAFBFD;
            }}
            QLineEdit:focus {{ border: 1px solid {ACCENT}; background: #FFFFFF; }}
            QCheckBox {{ color: {TEXT_DARK}; }}

            QPushButton#PrimaryButton {{
                background: {ACCENT}; color: #FFFFFF; border-radius: 12px;
                font-weight: 700; font-size: 15px;
            }}
            QPushButton#PrimaryButton:hover   {{ background: #219157; }}  /* #1E7C45'tan biraz açık */
            QPushButton#PrimaryButton:pressed {{ background: #177747; }}  /* biraz koyu */

            QLabel#Info {{ color: {MUTED}; font-size: 12px; }}
        """)

        # animasyon
        self._fade_in(card)

        # Enter ile login
        self.email.returnPressed.connect(self.password.setFocus)
        self.password.returnPressed.connect(self.try_login)
        self.email.setFocus()

        # başlangıç: normal pencere (kullanıcı isterse tam ekran tuşundan)
        self.resize(1100, 700)
        self.user = None

    def _fade_in(self, w: QWidget):
        w.setWindowOpacity(0.0)
        anim = QPropertyAnimation(w, b"windowOpacity", self)
        anim.setStartValue(0.0); anim.setEndValue(1.0)
        anim.setDuration(420); anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def try_login(self):
        email = self.email.text().strip()
        pw    = self.password.text()
        if not email or not pw:
            QMessageBox.warning(self, "Eksik Bilgi", "E-posta ve şifre zorunludur."); return

        result = verify_user(email, pw)
        ok, payload = (result if isinstance(result, tuple) else (bool(result), result))
        if not ok:
            QMessageBox.critical(self, "Hatalı Giriş", "E-posta veya şifre hatalı."); return

        self.user = payload or {}
        self.accept()
