import os
import json
from subprocess import call
from sys import argv, exit

from PyQt5.QtCore import QThread, pyqtSignal, QSize, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QProgressBar,
    QPushButton, QApplication, QMainWindow, QHBoxLayout,
    QInputDialog, QMessageBox
)

from minecraft_launcher_lib.utils import get_minecraft_directory, get_version_list
from minecraft_launcher_lib.install import install_minecraft_version
from minecraft_launcher_lib.command import get_minecraft_command

# Путь установки Minecraft для MjnLauncher
minecraft_directory = get_minecraft_directory().replace('minecraft', 'mjnlauncher')


class LaunchThread(QThread):
    launch_setup_signal = pyqtSignal(str, str)
    progress_update_signal = pyqtSignal(int, int, str)
    state_update_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.launch_setup_signal.connect(self.launch_setup)
        self.version_id = ''
        self.username = ''
        self.progress = 0
        self.progress_max = 0
        self.progress_label = ''

    def launch_setup(self, version_id, username):
        self.version_id = version_id
        self.username = username

    def update_progress_label(self, value):
        self.progress_label = value
        self.progress_update_signal.emit(self.progress, self.progress_max, self.progress_label)

    def update_progress(self, value):
        self.progress = value
        self.progress_update_signal.emit(self.progress, self.progress_max, self.progress_label)

    def update_progress_max(self, value):
        self.progress_max = value
        self.progress_update_signal.emit(self.progress, self.progress_max, self.progress_label)

    def run(self):
        self.state_update_signal.emit(True)

        # Установка выбранной версии Minecraft
        install_minecraft_version(
            versionid=self.version_id,
            minecraft_directory=minecraft_directory,
            callback={
                'setStatus': self.update_progress_label,
                'setProgress': self.update_progress,
                'setMax': self.update_progress_max
            }
        )

        # Запуск игры с ником (offline-режим)
        options = {
            'username': self.username,
            'uuid': '',
            'token': ''
        }

        call(get_minecraft_command(
            version=self.version_id,
            minecraft_directory=minecraft_directory,
            options=options
        ))

        self.state_update_signal.emit(False)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('MJNL')
        self.resize(300, 200)
        self.centralwidget = QWidget(self)

        # Путь к файлу с аккаунтами
        self.users_path = os.path.join(
            os.getenv('APPDATA'), '.MjnLauncher', 'client', 'users.json'
        )
        os.makedirs(os.path.dirname(self.users_path), exist_ok=True)

        # Логотип
        self.logo = QLabel(self.centralwidget)
        self.logo.setMaximumSize(QSize(256, 37))
        self.logo.setPixmap(QPixmap('assets/title.png'))
        self.logo.setScaledContents(True)

        # Список аккаунтов и кнопка добавления
        self.account_type = QComboBox(self.centralwidget)
        self.add_account_button = QPushButton("+", self.centralwidget)
        self.add_account_button.setFixedWidth(30)
        self.add_account_button.clicked.connect(self.add_account)

        self.account_layout = QHBoxLayout()
        self.account_layout.addWidget(self.account_type, 4)
        self.account_layout.addWidget(self.add_account_button, 1)

        # Список версий Minecraft
        self.version_select = QComboBox(self.centralwidget)
        for version in get_version_list():
            self.version_select.addItem(version['id'])

        # Прогресс-бар и метка
        self.start_progress_label = QLabel(self.centralwidget)
        self.start_progress_label.setVisible(False)
        self.start_progress = QProgressBar(self.centralwidget)
        self.start_progress.setVisible(False)

        self.time_label = QLabel(self.centralwidget)
        self.time_label.setVisible(False)

        # Кнопка запуска игры
        self.start_button = QPushButton('Play', self.centralwidget)
        self.start_button.clicked.connect(self.launch_game)

        # Основной вертикальный лэйаут
        layout = QVBoxLayout(self.centralwidget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.addWidget(self.logo, alignment=Qt.AlignHCenter)
        layout.addLayout(self.account_layout)
        layout.addWidget(self.version_select)
        layout.addWidget(self.start_progress_label)
        layout.addWidget(self.start_progress)
        layout.addWidget(self.time_label)
        layout.addWidget(self.start_button)

        self.setCentralWidget(self.centralwidget)

        self.load_accounts()

        # Поток для запуска игры
        self.launch_thread = LaunchThread()
        self.launch_thread.state_update_signal.connect(self.state_update)
        self.launch_thread.progress_update_signal.connect(self.update_progress)

    def load_accounts(self):
        self.account_type.clear()
        try:
            with open(self.users_path, 'r', encoding='utf-8') as f:
                users = json.load(f)
                for user in users:
                    self.account_type.addItem(user.get('nickname', 'Unknown'))
        except Exception:
            self.account_type.addItem('Player')

    def add_account(self):
        nick, ok = QInputDialog.getText(self, "Добавить аккаунт", "Введите никнейм:")
        if ok and nick.strip():
            nick = nick.strip()
            try:
                with open(self.users_path, 'r', encoding='utf-8') as f:
                    users = json.load(f)
            except Exception:
                users = []

            if any(u.get('nickname') == nick for u in users):
                QMessageBox.warning(self, "Ошибка", "Такой аккаунт уже существует.")
                return

            users.append({'nickname': nick})

            with open(self.users_path, 'w', encoding='utf-8') as f:
                json.dump(users, f, indent=4, ensure_ascii=False)

            self.load_accounts()
            index = self.account_type.findText(nick)
            if index >= 0:
                self.account_type.setCurrentIndex(index)

    def state_update(self, value: bool):
        self.start_button.setDisabled(value)
        self.start_progress.setVisible(value)
        self.start_progress_label.setVisible(value)
        self.time_label.setVisible(False)

    def update_progress(self, progress: int, max_progress: int, label: str):
        self.start_progress.setMaximum(max_progress)
        self.start_progress.setValue(progress)
        self.start_progress_label.setText(label)

    def launch_game(self):
        nick = self.account_type.currentText()
        if not nick:
            nick = 'Player'
        self.launch_thread.launch_setup_signal.emit(self.version_select.currentText(), nick)
        self.launch_thread.start()


if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(argv)
    window = MainWindow()
    window.show()
    exit(app.exec_())
