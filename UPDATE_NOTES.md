# 📝 UPDATE NOTES — версия 2.0

Что нового в версии 2.0 по сравнению с 1.0: исправления багов, новые функции,
обновлённая документация и скрипты установки.

---

## 🐛 Исправленные баги

1. **Команда `/set` реализована** — раньше была заявлена в `/help`, но не существовала.
   Теперь работает: `/set свет 50` → яркость 50% (через корректный сервис
   `light.turn_on` с `brightness` 0–255, а не несуществующий `light.set_brightness`),
   `/set термостат 22` → `climate.set_temperature`. Значения `>100` для света
   трактуются как сырое 0–255.
2. **Таймеры** — ключ изменён с пользователя на пару `(пользователь + устройство)`:
   можно несколько таймеров одновременно, повторный запуск для того же устройства
   отменяет старый с уведомлением. Добавлена валидация диапазона 1–1440 мин.
3. **Комнаты** — настоящие area из Home Assistant через
   `area_registry` / `device_registry` / `entity_registry` (раньше искались
   только несуществующие по умолчанию атрибуты). Fallback на атрибуты
   `room_name`/`area`/`area_name`/`location` сохранён, список атрибутов унифицирован.
4. **Callback-data** — вместо обрезания до 64 байт введён маппинг коротких токенов:
   длинные `entity_id` и имена комнат больше не ломают inline-кнопки.
   Устаревшая кнопка показывает понятное сообщение.
5. **HTML** — обрезка списков по границам строк (теги не рвутся), fallback на
   plain text при ошибке парсинга, сообщения длиннее 4096 отправляются новым
   сообщением вместо падения.
6. **Текстовый ввод** — больше не выключает устройство по умолчанию. Совпадение
   показывает карточку: статус + кнопки Вкл/Выкл/Переключить.
7. **`/state` без аргументов** — показывает живые данные из `/api/states`,
   а не устаревший на 60 секунд кеш.
8. `/scene` проверяет, что найденная сущность действительно `scene.*`.

## ✨ Новые функции

9. **Несколько пользователей** — `ALLOWED_USER_IDS=111,222,333` (через запятую).
   Старый `ALLOWED_USER_ID` продолжает работать. Пустой список = предупреждение
   в логе «доступ разрешён всем».
10. **Уведомления из HA → Telegram** — встроенный HTTP-приёмник (aiohttp):
    `NOTIFY_PORT`, `NOTIFY_HOST`, `NOTIFY_TOKEN`. Home Assistant шлёт сообщения
    через `rest_command` (пример ниже). Поддержка `parse_mode` и `chat_ids`.
11. **Поиск устройств** — ввод части имени показывает список совпадений
    (до 20, точное совпадение открывается сразу).
12. **`/alloff`** — выключение всех `light`/`switch`/`fan`/`cover` с подтверждением
    и отчётом о количестве.
13. **Таймеры переживают перезапуск** — сохраняются в `data/timers.json` при
    штатной остановке, восстанавливаются с оставшимся временем при старте.
14. **Логирование запросов** — каждое обращение фиксируется:
    `Запрос user=123456789: /on свет`.
15. `/help` обновлён (все команды + подсказка про поиск).

## 📦 Изменения в файлах

- `bot.py` — полностью переработан (v2.0)
- `requirements.txt` — добавлен `aiohttp>=3.9`
- `Dockerfile` — `DATA_DIR=/app/data`, `VOLUME /app/data`, `EXPOSE 8099`, версия 2.0
- `.sh`-скрипты — обновлены: создание `data/`, новый шаблон `.env`,
  мягкая остановка (сохранение таймеров), `install_service.sh` подхватывает
  `NOTIFY_PORT` в комментарий юнита
- **Новые `.bat`-скрипты для Windows:** `install.bat`, `start.bat`,
  `start_log.bat`, `stop.bat` (аналоги Linux-скриптов)

## 📚 Документация

- `README.md` / `README_LINUX.md` — обновлены до v2.0, добавлены разделы
  «Уведомления из Home Assistant», новые пункты troubleshooting
- `README_DOCKER.md` — **новый**: docker run и docker-compose
- `README_WINDOWS.md` — **новый**: установка на Windows 10/11
- `README_WINDOWS_SERVICE.md` — **новый**: служба Windows (NSSM / Планировщик задач)
- Перекрёстные ссылки между всеми инструкциями

---

## ⚙️ Новые / изменённые переменные окружения (.env)

```env
# Вместо одного ALLOWED_USER_ID — список через запятую:
ALLOWED_USER_IDS=123456789,987654321

# --- Приёмник уведомлений из Home Assistant ---
NOTIFY_PORT=8099        # 0 = выключен
NOTIFY_HOST=0.0.0.0
NOTIFY_TOKEN=секрет     # обязателен, если NOTIFY_PORT != 0
```

## 🚨 Уведомления из Home Assistant

1. В `configuration.yaml` HA:

```yaml
rest_command:
  telegram_notify:
    url: "http://<IP_сервера_с_ботом>:8099/notify"
    method: POST
    headers:
      Authorization: "Bearer <NOTIFY_TOKEN_из_.env>"
    content_type: application/json
    payload: '{"text": "{{ message }}"}'
```

2. В автоматизациях:

```yaml
- service: rest_command.telegram_notify
  data:
    message: "🚨 Датчик дыма в гараже сработал!"
```

Опционально в payload: `"parse_mode": "HTML"`, `"chat_ids": [123456789]`.

---

## ⬆️ Обновление с версии 1.0

```bash
cd /opt/ha-telegram-bot
git pull
sudo systemctl stop ha-telegram-bot
source venv/bin/activate
pip install --upgrade -r requirements.txt   # подтянется aiohttp
deactivate
sudo systemctl start ha-telegram-bot
```

После обновления:

- перенесите `user_langs.json` из корня проекта в `data/` (если хотите
  сохранить языки пользователей);
- добавьте в `.env` `ALLOWED_USER_IDS` (формат с ID через запятую);
- активные таймеры на момент обновления будут потеряны (создадутся заново
  при следующих запросах);
- inline-кнопки в старых сообщениях перестанут работать — отправьте `/menu`.

## ✅ Проверка после обновления

1. `sudo systemctl status ha-telegram-bot` — служба активна
2. `sudo journalctl -u ha-telegram-bot -n 30` — в логе
   `Загружено устройств: N`
3. В Telegram: `/status` → «Home Assistant: онлайн»
4. `/set свет 50` → подтверждение установки значения
5. Уведомление: `curl -X POST -H "Authorization: Bearer <NOTIFY_TOKEN>" \
   -H "Content-Type: application/json" \
   -d '{"text":"test"}' http://localhost:8099/notify`
