# welcome_dialog.py
from PyQt6.QtCore import Qt, QEasingCurve, QPropertyAnimation
from PyQt6.QtGui import QPixmap, QColor, QPainter
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QSpacerItem
)

ACCENT = "#1E7C45"

def load_logo_pixmap(size: int) -> QPixmap:
    try:
        pm = QPixmap("assets/kou_logo.png")
        if not pm.isNull():
            return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    except Exception:
        pass
    pm = QPixmap(size, size); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHints(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(ACCENT)); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(0, 0, size, size)
    p.setBrush(QColor("white")); w, h = size*0.58, size*0.38; x, y = (size-w)/2, (size-h)/2
    p.drawRoundedRect(int(x), int(y), int(w), int(h), 6, 6)
    p.end()
    return pm

class WelcomeDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kocaeli Üniversitesi • Sınav Takvimi")
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bg = QFrame(); bg.setObjectName("BG")
        bg_l = QVBoxLayout(bg); bg_l.setContentsMargins(0, 0, 0, 0); bg_l.setSpacing(0)

        topbar = QHBoxLayout(); topbar.setContentsMargins(18, 14, 18, 0)
        topbar.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        closeBtn = QPushButton("×"); closeBtn.setObjectName("CloseBtn"); closeBtn.setFixedSize(44, 44)
        closeBtn.clicked.connect(self.reject)
        topbar.addWidget(closeBtn)

        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(18)
        center.addStretch(1)

        scr = self.screen().availableGeometry() if self.screen() else None
        w = scr.width() if scr else 1920
        logo_size = max(150, min(220, int(w * 0.12)))
        title_size = max(40,  min(64,  int(w * 0.034)))
        btn_height = max(64,  min(86,  int(w * 0.045)))
        btn_width  = max(320, min(460, int(w * 0.24)))

        logo = QLabel(); logo.setPixmap(load_logo_pixmap(logo_size))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Sınav Takvimi"); title.setObjectName("HeroTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size:{title_size}px;")

        goBtn = QPushButton("Giriş"); goBtn.setObjectName("GoBtn")
        goBtn.setFixedHeight(btn_height); goBtn.setFixedWidth(btn_width)
        goBtn.clicked.connect(self.accept)

        center.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        center.addWidget(title, 0, Qt.AlignmentFlag.AlignHCenter)
        center.addSpacing(10)
        center.addWidget(goBtn, 0, Qt.AlignmentFlag.AlignHCenter)
        center.addStretch(2)

        bg_l.addLayout(topbar)
        bg_l.addLayout(center)

        root.addWidget(bg)

        self.setStyleSheet(f"""
            QFrame#BG {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0F223A, stop:1 #0B182B);
            }}
            QLabel#HeroTitle {{
                color: #FFFFFF; font-weight: 900; letter-spacing: .5px;
            }}
            QPushButton#GoBtn {{
                background: {ACCENT}; color: #fff; font-weight: 800;
                border-radius: 16px; font-size: 20px; padding: 8px 24px;
            }}
            QPushButton#GoBtn:hover   {{ background:#19b254; }}
            QPushButton#GoBtn:pressed {{ background:#138a43; }}

            QPushButton#CloseBtn {{
                background: rgba(255,255,255,.14); color: #fff; border: none;
                border-radius: 22px; font-size: 24px; font-weight: 900;
            }}
            QPushButton#CloseBtn:hover {{ background: rgba(255,255,255,.22); }}
            QPushButton#CloseBtn:pressed {{ background: rgba(255,255,255,.10); }}
        """)

        self._fade_in(bg)
        self.showFullScreen()

    def _fade_in(self, w):
        w.setWindowOpacity(0.0)
        anim = QPropertyAnimation(w, b"windowOpacity", self)
        anim.setStartValue(0.0); anim.setEndValue(1.0)
        anim.setDuration(420); anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
