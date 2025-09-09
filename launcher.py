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
try:
    from minecraft_launcher_lib.fabric import install_fabric as mll_install_fabric  # type: ignore
except Exception:
    mll_install_fabric = None
 

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

        def find_installed_mod_version(base_version: str, loader: str) -> str:
            versions_dir = os.path.join(minecraft_directory, 'versions')
            try:
                candidates = []
                for entry in os.listdir(versions_dir):
                    if not os.path.isdir(os.path.join(versions_dir, entry)):
                        continue
                    name_lower = entry.lower()
                    if base_version in entry and loader in name_lower:
                        # проверяем наличие json
                        if os.path.isfile(os.path.join(versions_dir, entry, f"{entry}.json")):
                            candidates.append(entry)
                if candidates:
                    # Приоритет fabric-loader-* (реальная сборка), затем алиасы
                    def candidate_key(e: str) -> tuple:
                        is_loader = e.startswith('fabric-loader-')
                        return (0 if is_loader else 1, e)
                    candidates.sort(key=candidate_key)
                    return candidates[0]
            except Exception:
                pass
            return ''

        def install_modded_if_needed(base_version: str, loader: str) -> str:
            # Возвращает реальный id установленной модифицированной версии (или пусто при неуспехе)
            try:
                # Установка базовой версии перед модлоадером
                if not is_version_installed(base_version):
                    install_minecraft_version(
                        versionid=base_version,
                        minecraft_directory=minecraft_directory,
                        callback={
                            'setStatus': self.update_progress_label,
                            'setProgress': self.update_progress,
                            'setMax': self.update_progress_max
                        }
                    )
                if loader == 'fabric' and mll_install_fabric is not None:
                    mll_install_fabric(
                        minecraft_version=base_version,
                        minecraft_directory=minecraft_directory,
                        callback={
                            'setStatus': self.update_progress_label,
                            'setProgress': self.update_progress,
                            'setMax': self.update_progress_max
                        }
                    )
                else:
                    pass
            except Exception:
                # Игнорируем, попробуем найти локально установленную
                pass
            return find_installed_mod_version(base_version, loader)

        # Поддержка синтаксиса отображаемых версий: "<base> <loader>" или просто "<base>"
        version_to_launch = self.version_id
        game_dir_override = None
        loader = ''
        if ' ' in self.version_id:
            parts = self.version_id.split()
            if len(parts) >= 2 and parts[-1].lower() in {'fabric'}:
                loader = parts[-1].lower()
                base_version = ' '.join(parts[:-1])
                # Пытаемся найти уже установленную мод-версию
                version_to_launch = find_installed_mod_version(base_version, loader)
                if not version_to_launch:
                    # Пытаемся установить мод-версию (если есть интернет/установщик)
                    version_to_launch = install_modded_if_needed(base_version, loader)
                if not version_to_launch:
                    self.message_signal.emit('Ошибка установки', f'Не удалось установить {loader} для {base_version}. Проверьте интернет или совместимость версии.')
                    self.state_update_signal.emit(False)
                    return
                # Создаём алиас-версию с читаемым названием, например "1.21.8 fabric"
                if 'fabric' in version_to_launch.lower():
                    alias_id = f"{base_version} {loader}"
                    try:
                        alias_dir = os.path.join(minecraft_directory, 'versions', alias_id)
                        alias_json_path = os.path.join(alias_dir, f"{alias_id}.json")
                        if not os.path.isfile(alias_json_path):
                            os.makedirs(alias_dir, exist_ok=True)
                            alias_data = {
                                'id': alias_id,
                                'inheritsFrom': version_to_launch,
                                'type': 'release'
                            }
                            with open(alias_json_path, 'w', encoding='utf-8') as f:
                                json.dump(alias_data, f, indent=4, ensure_ascii=False)
                        # Алиас нужен для отображения в списке; запуск оставим на реальный fabric id
                    except Exception:
                        pass
                # Для модовой версии используем отдельную папку профиля
                game_dir_override = os.path.join(minecraft_directory, 'profiles', f"{base_version}-fabric")
                try:
                    os.makedirs(game_dir_override, exist_ok=True)
                    for sub in ['mods', 'config', 'resourcepacks', 'saves']:
                        os.makedirs(os.path.join(game_dir_override, sub), exist_ok=True)
                except Exception:
                    pass
        else:
            # Обычная ванильная версия
            try:
                if not is_version_installed(version_to_launch):
                    install_minecraft_version(
                        versionid=version_to_launch,
                        minecraft_directory=minecraft_directory,
                        callback={
                            'setStatus': self.update_progress_label,
                            'setProgress': self.update_progress,
                            'setMax': self.update_progress_max
                        }
                    )
            except Exception:
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
        if game_dir_override:
            options['gameDirectory'] = game_dir_override

        cmd = get_minecraft_command(
            version=version_to_launch,
            minecraft_directory=minecraft_directory,
            options=options
        )
        call(cmd)

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

        # Кнопка обновления списка версий
        self.refresh_versions_button = QPushButton("🔄 Обновить", self.centralwidget)
        self.refresh_versions_button.clicked.connect(self.refresh_versions)
        
        # Лэйаут для фильтра и кнопки обновления
        self.version_layout = QHBoxLayout()
        self.version_layout.addWidget(self.version_filter, 3)
        self.version_layout.addWidget(self.refresh_versions_button, 1)

        self.version_select = QComboBox(self.centralwidget)
        self.all_versions = []
        self.offline_mode = False

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
        layout.addLayout(self.version_layout)
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
        self.refresh_versions()

    def refresh_versions(self):
        """Обновляет список доступных версий из интернета"""
        # Показываем прогресс загрузки
        self.refresh_versions_button.setEnabled(False)
        self.refresh_versions_button.setText("🔄 Загрузка...")
        
        # Пытаемся получить список доступных версий из сети
        try:
            self.all_versions = get_version_list()
            self.offline_mode = False
            self.refresh_versions_button.setText("🔄 Обновить")
            self.refresh_versions_button.setEnabled(True)
        except Exception as e:
            # Оффлайн-режим: берём только локально установленные версии
            self.all_versions = self.get_installed_versions()
            self.offline_mode = True
            self.refresh_versions_button.setText("🔄 Обновить (офлайн)")
            self.refresh_versions_button.setEnabled(True)
            # Показываем сообщение об ошибке только если это не первая загрузка
            if hasattr(self, '_first_load_done'):
                QMessageBox.warning(self, "Ошибка сети", 
                    f"Не удалось загрузить список версий из интернета.\n"
                    f"Показываются только установленные версии.\n"
                    f"Ошибка: {str(e)}")

        # В оффлайне отключаем фильтр типов, в онлайне включаем
        self.version_filter.setDisabled(self.offline_mode)

        self.apply_version_filter()

        # Восстанавливаем выбранную версию из конфигурации, если она есть в списке
        if getattr(self, '_desired_version', None):
            # Ищем версию по чистому имени (без иконки)
            for i in range(self.version_select.count()):
                item_text = self.version_select.itemText(i)
                clean_text = item_text.replace("✅ ", "").replace("⬇️ ", "")
                if clean_text == self._desired_version:
                    self.version_select.setCurrentIndex(i)
                    break
            self._desired_version = None
        
        # Отмечаем, что первая загрузка завершена
        self._first_load_done = True

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
            if not vid:
                continue
            
            # Проверяем, установлена ли версия
            is_installed = self.is_version_installed(vid)
            status_icon = "✅" if is_installed else "⬇️"
            
            # Добавляем базовую версию с индикатором статуса
            display_name = f"{status_icon} {vid}"
            self.version_select.addItem(display_name)
            
            # В онлайне добавляем «виртуальные» записи: только fabric (если поддерживается)
            if not getattr(self, 'offline_mode', False):
                if self.is_fabric_supported_for(vid):
                    fabric_display = f"{status_icon} {vid} fabric"
                    self.version_select.addItem(fabric_display)

        # Восстанавливаем выбор, если возможно
        if previous_selection:
            # Ищем по чистому имени (без иконки)
            clean_previous = previous_selection.replace("✅ ", "").replace("⬇️ ", "")
            for i in range(self.version_select.count()):
                item_text = self.version_select.itemText(i)
                clean_text = item_text.replace("✅ ", "").replace("⬇️ ", "")
                if clean_text == clean_previous:
                    self.version_select.setCurrentIndex(i)
                    break
        self.version_select.blockSignals(False)

    def is_version_installed(self, version_id: str) -> bool:
        """Проверяет, установлена ли версия локально"""
        version_dir = os.path.join(minecraft_directory, 'versions', version_id)
        version_json = os.path.join(version_dir, f"{version_id}.json")
        return os.path.isdir(version_dir) and os.path.isfile(version_json)

    def is_fabric_supported_for(self, mc_version: str) -> bool:
        # Грубая эвристика: Fabric официально поддерживает 1.14+; более точно можно опросить fabric-meta
        try:
            parts = mc_version.split('.')
            # Ожидаем формат X.Y[.Z]
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            return (major > 1) or (major == 1 and minor >= 14)
        except Exception:
            return False

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
        # Текущая выбранная версия (без иконки)
        if self.version_select.count() > 0:
            display_text = self.version_select.currentText()
            clean_version = display_text.replace("✅ ", "").replace("⬇️ ", "")
            cfg['selected_version'] = clean_version
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
        
        # Извлекаем чистую версию из отображаемого имени (убираем иконку)
        display_text = self.version_select.currentText()
        version_id = display_text.replace("✅ ", "").replace("⬇️ ", "")
        
        self.launch_thread.launch_setup_signal.emit(version_id, nick)
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
