# 🤖 V1PER IT Solutions | CRM Group Manager: Управление группами в Telegram и Мессенджере МАКС

[![Tests](https://img.shields.io/badge/Tests-6%2F6%20Passed%20(100%25)-brightgreen.svg)](tests/)
[![Security Audit: Hardened](https://img.shields.io/badge/Security%20Audit-0%20Vulnerabilities%20(Hardened)-brightgreen.svg)](audit_stress_test.py)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Studio](https://img.shields.io/badge/Studio-V1PER_IT_Solutions-emerald.svg)]()
[![Architecture: Clean Zero--Pip](https://img.shields.io/badge/Architecture-Clean%20Zero--Pip-blueviolet.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Автономный промышленный REST API микросервис студии **V1PER IT Solutions** на **Python**, реализующий автоматическое создание, тонкую настройку политик безопасности, администрирование и удаление проектных рабочих групп в мессенджерах **Telegram** (MTProto) и **Мессенджер МАКС** по вебхукам из корпоративных CRM-систем (Битрикс24, amoCRM, Custom ERP).

> [!IMPORTANT]
> **🚀 Корпоративная интеграция и внедрение CRM-менеджера под ключ:**  
> В данном репозитории представлена базовая открытая архитектура микросервиса. Студия **V1PER IT Solutions** выполняет разработку и интеграцию решения под ключ в IT-контур вашей компании:
> - 🏢 **Связка с вашей CRM/ERP:** интеграция с Битрикс24, amoCRM, 1С, RetailCRM или собственной базой через REST API и вебхуки.
> - 👥 **Автоматизация чатов сделок:** создание групп, приглашение ответственных сотрудников и клиентов, выдача и отзыв прав.
> - 💬 **Сквозная синхронизация:** двустороннее зеркалирование переписки между Telegram и Мессенджером МАКС.
> - 🛡️ **Безопасность и аудит:** предотвращение утечек данных, скрытие номеров и детальный аудит всех действий.
>
> 📩 **Заказать корпоративную интеграцию:** [Заказать на Kwork (Безопасная сделка)](https://kwork.ru/user/V1PER86RUS) • [Создать заявку (Issue)](https://github.com/viper86rus-arch/CRM_Group_Manager/issues) • [Профиль студии](https://github.com/viper86rus-arch)



---

## 📋 Реализованные сценарии ТЗ

```mermaid
flowchart TD
    CRM["🏢 Корпоративная ЦРМ"] -->|1. Webhook: Создать заказ| SVR["⚡ CRM Group Manager (REST API)"]
    SVR -->|2. Определение мессенджера| ROUTER{"Выбор мессенджера"}

    subgraph Telegram ["Модуль Telegram (MTProto)"]
        ROUTER -->|telegram| TG1["Создать супергруппу (Заказ.Название / Описание / Аватар)"]
        TG1 --> TG2["Политики: Reactions=No, ChangeInfo=Off, History=Hidden"]
        TG2 --> TG3["Добавить Система.ТГ_бот и выдать Администратора"]
        TG3 --> TG4["Отправить сервисную команду /task [Заказ.Номер]"]
        TG4 --> TG5["Добавить Заказ.Подрядчик.ID"]
    end

    subgraph Max ["Модуль Мессенджера Макс (REST API)"]
        ROUTER -->|max| MX1["Создать чат (Заказ.Название / Описание / Аватар)"]
        MX1 --> MX2["Политики: Reactions=off, Edit=off, Call in chat=off"]
        MX2 --> MX3["Добавить Система.Макс_бот и выдать Администратора"]
        MX3 --> MX4["Добавить Заказ.Подрядчик.Идентификатор_в_Максе"]
    end

    TG5 --> DB[("💾 Локальная БД (SQLite)")]:::db
    MX4 --> DB

    CRM -->|3. Webhook: Заказ завершен| DEL["🗑️ Автоудаление группы из мессенджера"]
    DEL --> DB

    classDef db fill:#0d1117,stroke:#58a6ff,stroke-width:2px,color:#fff;
```

---

## 🚀 Архитектурные особенности

1. **Zero-Pip Baseline (Чистый Python)**:
   * Ядро сервера построено на стандартных библиотеках Python (`http.server`, `asyncio`, `sqlite3`, `urllib`).
   * Встроенный режим изоляции `--demo` позволяет запускать и тестировать 100% сценариев ТЗ без внешних API-ключей и сторонних зависимостей.
2. **MTProto-оркестрация Telegram**:
   * Обычный Telegram Bot API запрещает ботам создавать супергруппы с нуля.
   * Данный микросервис решает проблему через надежный клиент MTProto (`Telethon`), который программно поднимает чат, передает права администратора корпоративному боту и закрепляет задачу через `/task [Номер]`.
3. **Единый коннектор к мессенджеру Макс**:
   * Взаимодействие с корпоративным сервером Макс через защищенный REST API с Bearer-авторизацией.
4. **Гарантированная дедупликация**:
   * Локальная база данных SQLite предотвращает повторное создание дублирующих групп при повторных вебхуках от CRM.

---

## 🛠️ Спецификация REST API

### 1. Проверка работоспособности (Healthcheck)
```http
GET /health
```
**Ответ `200 OK`:**
```json
{
  "status": "healthy",
  "service": "CRM Group Manager",
  "version": "1.0.0",
  "author": "V1PER (viper86rus-arch)",
  "active_messengers": ["telegram", "max"],
  "demo_mode": true
}
```

---

### 2. Создание группы под новый Заказ
```http
POST /api/v1/groups/create
Content-Type: application/json
```
**Тело запроса (Telegram):**
```json
{
  "order_id": "ORD-1082",
  "title": "Заказ #1082: Поставка серверного оборудования",
  "description": "Рабочая группа проекта ЦОД. Заказчик: ООО Вектор",
  "contractor_id": "@network_specialist",
  "messenger": "telegram",
  "avatar_url": "https://company.ru/avatars/order_1082.png",
  "task_number": "1082"
}
```

**Тело запроса (Макс):**
```json
{
  "order_id": "ORD-1083",
  "title": "Заказ #1083: Аудит информационной безопасности",
  "description": "Закрытая группа аудита инфраструктуры",
  "contractor_id": "max_user_99120",
  "messenger": "max"
}
```

**Ответ `200 OK`:**
```json
{
  "success": true,
  "order_id": "ORD-1082",
  "message": "Группа в Telegram успешно создана и сконфигурирована по ТЗ",
  "group_id": "-1001001001",
  "invite_link": "https://t.me/c/1001001/1",
  "error": null
}
```

---

### 3. Завершение заказа и автоудаление группы
```http
POST /api/v1/groups/delete
Content-Type: application/json
```
```json
{
  "order_id": "ORD-1082",
  "reason": "Работы приняты заказчиком"
}
```

---

## 💻 Установка и запуск

### Быстрый запуск в демонстрационном режиме
Для проверки всех сценариев создания, настройки и удаления групп:
```bash
python3 server.py --demo
```

### Запуск постоянного фонового сервера
```bash
python3 server.py --host 0.0.0.0 --port 8000
```

### Запуск набора модульных тестов
```bash
python3 -m unittest discover -s tests -v
```

### Запуск автономного аудита безопасности и стресс-тестирования
```bash
python3 audit_stress_test.py
```

---

## 🛡️ Безопасность и стресс-тестирование

Кодовая база микросервиса прошла глубокий ревизионный аудит и стресс-тестирование (`audit_stress_test.py`):
* 🛡️ **Контроль доступа REST API (CWE-306, CWE-862):** все управляющие эндпоинты (`/create`, `/delete`) и выгрузка реестра групп закрыты валидацией `SECRET_WEBHOOK_KEY` (через заголовок `X-Webhook-Secret` или `Authorization: Bearer <TOKEN>`).
* 🛡️ **Защита от DoS по памяти (CWE-770):** строгое ограничение размера входящего HTTP-тела до 1 МБ (`MAX_PAYLOAD_SIZE`) и отсечение некорректных значений `Content-Length`.
* 🛡️ **Защита от Formula Injection в CSV (CWE-1236):** функция `sanitize_csv_cell` экранирует инъекции формул (`=`, `+`, `-`, `@`, `\t`, `\r`) апострофом `'` с предварительной зачисткой управляющих символов перевода строк.
* 🛡️ **Исправление инвайт-ссылок Telegram:** устранён баг с `lstrip("-100")`, ссылки супергрупп генерируются строго по стандарту `https://t.me/c/<clean_id>/1`.
* 🛡️ **Отказоустойчивость МАКС (Fail-Closed):** устранена скрытая подмена на мок в боевом режиме, обеспечена прозрачная передача ошибок сетевого шлюза и проверка сертификатов Минцифры РФ (`russian_trusted_root_ca.pem`).
* 🛡️ **Высокая конкурентность SQLite (WAL-режим):** включен `PRAGMA journal_mode = WAL;`, `PRAGMA busy_timeout = 5000;`, многопоточный сервер `ThreadingHTTPServer`. Пропускная способность: **>1200 ops/sec** при нуле ошибок блокировки базы.
* 🛡️ **Маскирование персональных данных (PII, CWE-532):** скрытие номеров телефонов и идентификаторов подрядчиков в логах (`+7916***4567`).

*Результат стресс-теста: 0 Critical, 0 High, 0 Medium, 0 Low (12/12 проверок OK).*

---

## 🏗 Архитектура проекта

```text
CRM_Group_Manager/
├── server.py               # REST API сервер на ThreadingHTTPServer с авторизацией
├── storage.py              # SQLite3 движок, WAL-режим, дедупликация и экспорт в CSV
├── telegram_manager.py     # Оркестрация супергрупп Telegram (MTProto), права и бот-админ
├── max_manager.py          # Оркестрация групп Мессенджера МАКС (REST API), SSL Минцифры
├── models.py               # Валидация входных вебхуков и структуры сущностей
├── config.py               # Парсинг .env и настройки окружения
├── audit_stress_test.py    # Автономный аудит безопасности и стресс-тестирование
├── tests/
│   └── test_manager.py     # Модульные тесты (FSM, Telegram, МАКС, SQLite, CSV)
├── exports/                # Выгрузки реестра групп в CSV (UTF-8 BOM)
├── .env.example            # Шаблон конфигурации
├── .gitignore              # Исключение секретов, логов и баз данных
└── README.md               # Документация проекта
```

---

## ⚙️ Конфигурация (`.env`)

Скопируйте шаблон переменных окружения:
```bash
cp .env.example .env
```

| Переменная | Описание | По умолчанию |
| :--- | :--- | :--- |
| `SERVER_HOST` | Сетевой интерфейс для прослушивания | `0.0.0.0` |
| `SERVER_PORT` | Порт HTTP REST API сервиса | `8000` |
| `SECRET_WEBHOOK_KEY` | Секретный ключ авторизации вебхуков CRM | `""` |
| `TG_API_ID` | Telegram API ID приложения (my.telegram.org) | `0` |
| `TG_API_HASH` | Telegram API Hash приложения | `""` |
| `TG_CORPORATE_BOT_ID` | Идентификатор корпоративного бота | `@corp_bot` |
| `MAX_API_URL` | Базовый URL REST API Мессенджера МАКС | `https://platform-api2.max.ru` |
| `MAX_API_TOKEN` | Корпоративный токен авторизации Макс | `""` |
| `DEMO_MODE` | Режим работы (true / false) | `true` |

---

## 🖥️ Поддерживаемые операционные системы

* Linux (Ubuntu, Debian, RHEL)
* macOS
* Windows Server

---

## 📄 Лицензия и авторство

* **Автор разработки:** V1PER ([`viper86rus-arch`](https://github.com/viper86rus-arch))
* **Лицензия:** [MIT License](LICENSE) (2026) — открытый исходный код без ограничений на коммерческое и образовательное применение.

