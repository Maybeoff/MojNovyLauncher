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
    message_signal = pyqtSignal(str, str)

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

        def is_version_installed(version_id: str) -> bool:
            version_dir = os.path.join(minecraft_directory, 'versions', version_id)
            version_json = os.path.join(version_dir, f"{version_id}.json")
            version_jar = os.path.join(version_dir, f"{version_id}.jar")
            return os.path.isdir(version_dir) and os.path.isfile(version_json)

        try:
            if not is_version_installed(self.version_id):
                # Пытаемся установить только если нет локальной установки
                install_minecraft_version(
                    versionid=self.version_id,
                    minecraft_directory=minecraft_directory,
                    callback={
                        'setStatus': self.update_progress_label,
                        'setProgress': self.update_progress,
                        'setMax': self.update_progress_max
                    }
                )
        except Exception:
            # Сообщаем пользователю и выходим из запуска, если не удалось установить (например, оффлайн)
            self.message_signal.emit(
                'Оффлайн режим',
                'Эта версия не установлена локально и не может быть скачана без интернета.'
            )
            self.state_update_signal.emit(False)
            return

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

        # Путь к конфигу лаунчера
        self.config_path = os.path.join(
            os.getenv('APPDATA'), '.MjnLauncher', 'client', 'config.json'
        )

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
        self.version_filter = QComboBox(self.centralwidget)
        self.version_filter.addItems(['Релизы', 'Снапшоты', 'Все'])
        self.version_filter.currentIndexChanged.connect(self.on_version_filter_changed)

        self.version_select = QComboBox(self.centralwidget)
        self.all_versions = []

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
        layout.addWidget(self.version_filter)
        layout.addWidget(self.version_select)
        layout.addWidget(self.start_progress_label)
        layout.addWidget(self.start_progress)
        layout.addWidget(self.time_label)
        layout.addWidget(self.start_button)

        self.setCentralWidget(self.centralwidget)

        self.load_accounts()
        self.load_config()
        self.load_versions()

        # Поток для запуска игры
        self.launch_thread = LaunchThread()
        self.launch_thread.state_update_signal.connect(self.state_update)
        self.launch_thread.progress_update_signal.connect(self.update_progress)
        self.launch_thread.message_signal.connect(self.show_message)

    def load_accounts(self):
        self.account_type.clear()
        try:
            with open(self.users_path, 'r', encoding='utf-8') as f:
                users = json.load(f)
                for user in users:
                    self.account_type.addItem(user.get('nickname', 'Unknown'))
        except Exception:
            self.account_type.addItem('Player')

    def load_config(self):
        self._config = {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
        except Exception:
            self._config = {}

        # Восстанавливаем фильтр версий, если сохранён
        saved_filter = self._config.get('version_filter')
        if isinstance(saved_filter, str):
            self.version_filter.blockSignals(True)
            idx = self.version_filter.findText(saved_filter)
            if idx >= 0:
                self.version_filter.setCurrentIndex(idx)
            self.version_filter.blockSignals(False)

        # Сохраняем желаемую версию для установки после загрузки списка
        self._desired_version = self._config.get('selected_version')

    def load_versions(self):
        # Пытаемся получить список доступных версий из сети
        try:
            self.all_versions = get_version_list()
            self.offline_mode = False
        except Exception:
            # Оффлайн-режим: берём только локально установленные версии
            self.all_versions = self.get_installed_versions()
            self.offline_mode = True

        # В оффлайне отключаем фильтр типов, в онлайне включаем
        self.version_filter.setDisabled(self.offline_mode)

        self.apply_version_filter()

        # Восстанавливаем выбранную версию из конфигурации, если она есть в списке
        if getattr(self, '_desired_version', None):
            idx = self.version_select.findText(self._desired_version)
            if idx >= 0:
                self.version_select.setCurrentIndex(idx)
            self._desired_version = None

    def apply_version_filter(self):
        # Сохраняем текущий выбор, чтобы попытаться восстановить после фильтрации
        previous_selection = self.version_select.currentText() if self.version_select.count() > 0 else ''

        # Определяем режим фильтра
        if getattr(self, 'offline_mode', False):
            # В офлайне типы неизвестны, показываем все установленное
            allowed_types = None
        else:
            mode = self.version_filter.currentText()
            if mode == 'Релизы':
                allowed_types = {'release'}
            elif mode == 'Снапшоты':
                allowed_types = {'snapshot'}
            else:
                allowed_types = None  # Все

        # Перезаполняем список версий
        self.version_select.blockSignals(True)
        self.version_select.clear()

        versions = self.all_versions
        if allowed_types is not None:
            versions = [v for v in versions if v.get('type') in allowed_types]

        for version in versions:
            vid = version.get('id')
            if vid:
                self.version_select.addItem(vid)

        # Восстанавливаем выбор, если возможно
        if previous_selection:
            idx = self.version_select.findText(previous_selection)
            if idx >= 0:
                self.version_select.setCurrentIndex(idx)
        self.version_select.blockSignals(False)

    def get_installed_versions(self):
        versions_dir = os.path.join(minecraft_directory, 'versions')
        result = []
        try:
            if not os.path.isdir(versions_dir):
                return result
            for entry in os.listdir(versions_dir):
                entry_path = os.path.join(versions_dir, entry)
                if not os.path.isdir(entry_path):
                    continue
                # Установленная версия обычно имеет файл <version>/<version>.json
                json_manifest = os.path.join(entry_path, f"{entry}.json")
                if os.path.isfile(json_manifest):
                    result.append({'id': entry})
        except Exception:
            pass
        return result

    def on_version_filter_changed(self):
        self.apply_version_filter()
        self.save_config()

    def save_config(self):
        cfg = dict(self._config) if hasattr(self, '_config') else {}
        cfg['version_filter'] = self.version_filter.currentText()
        # Текущая выбранная версия
        if self.version_select.count() > 0:
            cfg['selected_version'] = self.version_select.currentText()
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
            self._config = cfg
        except Exception:
            pass

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
        # Сохраняем выбранную версию на момент запуска
        try:
            self.save_config()
        except Exception:
            pass

    def show_message(self, title: str, text: str):
        QMessageBox.information(self, title, text)


if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(argv)
    window = MainWindow()
    window.show()
    exit(app.exec_())
