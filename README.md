## MojNovyLauncher (MJNL)

Лёгкий оффлайн-лаунчер Minecraft на PyQt5 с установкой и запуском версий через `minecraft_launcher_lib`.

### Возможности
- Фильтр списка версий: «Релизы», «Снапшоты», «Все».
- Автосохранение настроек (фильтр и выбранная версия) в конфиг.
- Полноценный офлайн-режим:
  - при отсутствии сети отображаются только локально установленные версии;
  - попытка установить неустановленную версию без интернета блокируется с понятным сообщением.
- Список никнеймов-аккаунтов в оффлайн-режиме, хранится локально.

### Установка зависимостей
```bash
pip install PyQt5 minecraft_launcher_lib
```

### Запуск
```bash
python MojNovyLauncher/launcher.py
```

### Где хранятся данные
- Директория Minecraft для лаунчера: `%APPDATA%/.mjnlauncher` (Windows).
- Аккаунты (ники): `%APPDATA%/.MjnLauncher/client/users.json`.
- Конфиг лаунчера: `%APPDATA%/.MjnLauncher/client/config.json`.

### Примечания
- В офлайне фильтр типов версий отключается, так как у локальных версий нет метки `type`.
- При запуске без интернета лаунчер не будет скачивать JRE/артефакты — запустятся только уже установленные версии.

### Скриншоты
<img width="302" height="232" alt="image" src="https://github.com/user-attachments/assets/b848c604-b831-42a1-9cf5-e00db455f37c" />
<img width="202" height="122" alt="image" src="https://github.com/user-attachments/assets/f7485ea4-b203-4963-809d-a9c03ff6fee1" />
