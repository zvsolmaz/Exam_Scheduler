from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QMessageBox
from auth import check_credentials
from main_window import MainWindow
import sys

class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sınav Takvimi - Giriş")
        self.resize(300, 150)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("E-posta")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Şifre")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.login_button = QPushButton("Giriş Yap")
        self.login_button.clicked.connect(self.login)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("E-posta:"))
        layout.addWidget(self.email_input)
        layout.addWidget(QLabel("Şifre:"))
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)
        self.setLayout(layout)

    def login(self):
        email = self.email_input.text().strip()
        password = self.password_input.text().strip()
        result = check_credentials(email, password)

        if result:
            self.close()
            self.main_window = MainWindow(result["role"], result["department"])
            self.main_window.show()
        else:
            QMessageBox.warning(self, "Hata", "E-posta veya şifre hatalı!")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = LoginWindow()
    win.show()
    sys.exit(app.exec())
