# app.py — Uygulama yaşam döngüsü kontrolcüsü (login <-> main arasında güvenli geçiş)
from __future__ import annotations
import sys
from typing import Optional
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QMessageBox

from login_dialog import LoginDialog
from main_window import MainWindow


class AppController(QObject):
    """
    LoginDialog <-> MainWindow arasında geçişi yönetir.
    - Giriş iptal edilirse (hiç ana pencere yokken): uygulamayı kapatır.
    - Çıkış'a basılırsa: ana pencere kapanır ve login ekranına geri döner.
    - MainWindow oluşturulurken/başlarken hata olursa uygulama kapanmaz, login'e döner.
    """
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self._login: Optional[LoginDialog] = None
        self._main: Optional[MainWindow] = None

    # ---- public api ----
    def run(self) -> int:
        self._show_login()
        return self.app.exec()

    # ---- flow ----
    def _show_login(self):
        # Ana pencere açıksa kapat
        if self._main is not None:
            try:
                self._main.logged_out.disconnect(self._on_logout)
            except Exception:
                pass
            self._main.close()
            self._main = None

        # Login'i oluştur ve göster
        self._login = LoginDialog()
        result = self._login.exec()

        if result == LoginDialog.DialogCode.Accepted:
            user = None
            try:
                # LoginDialog.get_user() varsa onu kullan, yoksa .user alanı
                user = self._login.get_user() if hasattr(self._login, "get_user") else getattr(self._login, "user", None)
            except Exception:
                user = getattr(self._login, "user", None)

            if not user:
                QMessageBox.critical(None, "Hata", "Kullanıcı bilgisi alınamadı.")
                # Geri login’e dön
                self._show_login()
                return

            # Login penceresini kapat ve main'e geç
            self._login = None
            self._show_main(user)
        else:
            # Giriş iptal: hiç ana pencere yoksa uygulamayı kapat
            if self._main is None:
                self.app.quit()

    def _show_main(self, user: dict):
        # Her ihtimale karşı eski main'i kapat
        if self._main is not None:
            try:
                self._main.logged_out.disconnect(self._on_logout)
            except Exception:
                pass
            self._main.close()
            self._main = None

        # Ana pencereyi güvenli oluştur
        try:
            self._main = MainWindow(user)
            # Çıkış butonu bu sinyali yolluyor (main_window.py: self.logged_out.emit())
            self._main.logged_out.connect(self._on_logout)
            # Ekran boyutu tercihi: istersen showFullScreen() de kullanabilirsin
            self._main.showMaximized()
        except Exception as e:
            # Örn. main init içinde DB erişimi patlarsa:
            self._main = None
            QMessageBox.critical(None, "Hata", f"Ana pencere açılamadı:\n{e}")
            # Login'e geri dön
            self._show_login()

    def _on_logout(self):
        """
        MainWindow'dan 'Çıkış' sinyali gelince:
        - Main kapanır
        - Login ekranı yeniden açılır
        """
        if self._main is not None:
            try:
                self._main.logged_out.disconnect(self._on_logout)
            except Exception:
                pass
            self._main.close()
            self._main = None
        self._show_login()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    controller = AppController(app)
    sys.exit(controller.run())
