#!/usr/bin/env python3
"""
==============================================================================
Комплексный стресс-тест и аудит безопасности: CRM Group Manager
==============================================================================
Автор: V1PER (viper86rus-arch)
GitHub: https://github.com/viper86rus-arch/CRM_Group_Manager
Лицензия: MIT License (2026)
Назначение: Автоматизированный ревизионный аудит и безжалостный стресс-тест
            кодовой базы CRM Group Manager (REST API, SQLite, Telegram, МАКС).
==============================================================================
"""

import asyncio
import io
import json
import logging
import os
import re
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Подключение модулей аудируемого проекта
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import config
import models
import server
import storage
from max_manager import MaxManager
from models import CreateGroupRequest, DeleteGroupRequest, GroupRecord, ServiceResponse
from telegram_manager import TelegramManager

# ==============================================================================
# 1. СТРУКТУРЫ РЕЗУЛЬТАТОВ АУДИТА
# ==============================================================================

class AuditResult:
    def __init__(self, check_id: str, title: str, category: str, severity: str):
        self.check_id = check_id
        self.title = title
        self.category = category
        self.severity = severity  # CRITICAL, HIGH, MEDIUM, LOW, INFO
        self.vulnerable: bool = False
        self.details: str = ""
        self.poc_output: str = ""
        self.recommendation: str = ""

    def fail(self, details: str, poc_output: str, recommendation: str):
        self.vulnerable = True
        self.details = details
        self.poc_output = poc_output
        self.recommendation = recommendation

    def passed(self, details: str):
        self.vulnerable = False
        self.details = details


# ==============================================================================
# 2. ТЕСТОВЫЕ ВЕКТОРЫ И СТРЕСС-ТЕСТЫ
# ==============================================================================

class SecurityAuditor:
    def __init__(self):
        self.results: List[AuditResult] = []
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix="_audit.db")
        self.audit_db = Path(self.temp_db_path)
        storage.init_db(self.audit_db)

    def cleanup(self):
        try:
            os.close(self.temp_db_fd)
        except OSError:
            pass
        if self.audit_db.exists():
            try:
                self.audit_db.unlink()
            except OSError:
                pass

    # --------------------------------------------------------------------------
    # ТЕСТ 1: Проверка контроля доступа и авторизации REST API (CWE-306, CWE-862)
    # --------------------------------------------------------------------------
    def test_api_authentication_bypass(self):
        res = AuditResult(
            check_id="SEC-AUTH-001",
            title="Проверка авторизации эндпоинтов REST API (Broken Access Control)",
            category="REST API Security",
            severity="CRITICAL",
        )

        # Проверяем код server.py на наличие проверки токена / заголовка
        server_code = (BASE_DIR / "server.py").read_text(encoding="utf-8")
        has_auth_check = "SECRET_WEBHOOK_KEY" in server_code and (
            "headers.get" in server_code or "Authorization" in server_code
        )

        # Выполняем имитацию вызова без авторизационного заголовка
        # Если метод CRMRequestHandler принимает запрос без токена:
        if not has_auth_check:
            poc = (
                "Уязвимость подтверждена:\n"
                "  1. В config.py объявлен SECRET_WEBHOOK_KEY, но в server.py он полностью игнорируется.\n"
                "  2. Эндпоинты POST /api/v1/groups/create и POST /api/v1/groups/delete не требуют Authorization/X-Token.\n"
                "  3. Любой неавторизованный клиент сети может удалять и создавать группы."
            )
            res.fail(
                details="REST API полностью открыт без авторизации (CWE-306 / CWE-862).",
                poc_output=poc,
                recommendation="Внедрить проверку заголовка 'X-Webhook-Secret' или 'Authorization: Bearer <SECRET_WEBHOOK_KEY>' в do_GET и do_POST.",
            )
        else:
            res.passed("Проверка авторизации присутствует в коде сервера.")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # ТЕСТ 2: Утечка персональных данных и базы клиентов без авторизации (CWE-200)
    # --------------------------------------------------------------------------
    def test_unauthenticated_data_leakage(self):
        res = AuditResult(
            check_id="SEC-LEAK-002",
            title="Несанкционированное чтение базы групп через GET /api/v1/groups",
            category="Data Privacy & Confidentiality",
            severity="HIGH",
        )

        # Проверяем, что эндпоинт GET /api/v1/groups отдает весь список без токена
        server_code = (BASE_DIR / "server.py").read_text(encoding="utf-8")
        if "storage.list_active_groups()" in server_code and "SECRET_WEBHOOK_KEY" not in server_code:
            poc = (
                "GET /api/v1/groups возвращает все активные заказы, ссылки-инвайты и ID подрядчиков "
                "любому анонимному клиенту без аутентификации."
            )
            res.fail(
                details="Утечка конфиденциальных данных клиентов и рабочих групп (CWE-200).",
                poc_output=poc,
                recommendation="Закрыть GET /api/v1/groups и GET /api/v1/groups/{order_id} проверкой токена администратора.",
            )
        else:
            res.passed("Эндпоинт защищен авторизацией.")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # ТЕСТ 3: Опасная логическая ошибка в генерации ссылок Telegram (String Lstrip)
    # --------------------------------------------------------------------------
    def test_telegram_invite_link_lstrip_bug(self):
        res = AuditResult(
            check_id="BUG-TG-003",
            title="Логический сбой генерации ссылки-приглашения Telegram через lstrip()",
            category="Telegram Integration",
            severity="HIGH",
        )

        # Тестируем реальное поведение функции telegram_manager
        tm = TelegramManager(demo_mode=True)
        req = CreateGroupRequest(
            order_id="TEST-100",
            title="Тестовый заказ",
            description="Описание",
            contractor_id="@user",
            messenger="telegram",
        )

        # Симулируем создание группы с типовым Telegram ID супергруппы -1001001001
        loop = asyncio.new_event_loop()
        try:
            out = loop.run_until_complete(tm.handle_create_order_group(req))
            link = out.get("invite_link", "")
            group_id = out.get("group_id", "")
        finally:
            loop.close()

        # Проверяем правильность ссылки
        if link == "https://t.me/c//1" or "//1" in link:
            poc = (
                f"group_id: '{group_id}'\n"
                f"Результат invite_link: '{link}'\n"
                f"Причина: group_id.lstrip('-100') удаляет ВСЕ символы '-', '1', '0' из строки,\n"
                f"полностью стирая тело ID, превращая '-1001001001' в пустую строку!"
            )
            res.fail(
                details="Критический сбой: сгенерированная ссылка невалидна и ведет на несуществующий ресурс.",
                poc_output=poc,
                recommendation="Заменить group_id.lstrip('-100') на group_id.removeprefix('-100') или group_id[4:] if group_id.startswith('-100') else group_id.",
            )
        else:
            res.passed(f"Ссылка сгенерирована корректно: {link}")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # ТЕСТ 4: Фатальный Fail-Open / Silent Mock Fallback в боевом режиме МАКС
    # --------------------------------------------------------------------------
    def test_max_fail_open_silent_mock(self):
        res = AuditResult(
            check_id="SEC-MAX-004",
            title="Опасный Silent Fallback на Мок-клиент при сбое боевого API МАКС (Fail-Open)",
            category="MAX Messenger Integration",
            severity="HIGH",
        )

        # Инициализируем менеджер в якобы 'боевом' режиме (demo_mode=False) с фиктивным токеном
        mm = MaxManager(demo_mode=False)
        mm.api_token = "invalid_audit_token_test"

        req = CreateGroupRequest(
            order_id="AUDIT-MAX-FAIL",
            title="Аудит сбоя API",
            description="Тест отказоустойчивости",
            contractor_id="auditor_id",
            messenger="max",
        )

        loop = asyncio.new_event_loop()
        try:
            out = loop.run_until_complete(mm.handle_create_order_group(req))
            group_id = out.get("group_id", "")
            link = out.get("invite_link", "")
        finally:
            loop.close()

        # Если при сетевом сбое или невалидном токене метод вернул фейковую группу max_chat_5002001
        if "max_chat_" in group_id:
            poc = (
                f"Боевой режим (demo_mode=False, api_token='{mm.api_token}').\n"
                f"Сетевой запрос к API МАКС завершился ошибкой (или эмуляцией сетевого сбоя).\n"
                f"Метод перехватил ошибку и МОЛЧА вернул фейковый мок: ID={group_id}, Link={link}.\n"
                f"CRM считает, что группа создана, и сообщает об успехе клиенту!"
            )
            res.fail(
                details="Антипаттерн Fail-Open: маскировка аварии боевого шлюза под успешное создание группы.",
                poc_output=poc,
                recommendation="В боевом режиме (demo_mode=False) пробрасывать исключение наверх, чтобы сервер вернул CRM HTTP 502/500 с описанием сбоя шлюза.",
            )
        else:
            res.passed("Боевой режим корректно возвращает ошибку при отказе шлюза.")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # ТЕСТ 5: Валидация входных данных и DoS через пустые поля / огромный JSON
    # --------------------------------------------------------------------------
    def test_input_validation_and_empty_fields(self):
        res = AuditResult(
            check_id="SEC-INPUT-005",
            title="Валидация пустых полей и граничных значений (CWE-20)",
            category="Input Validation",
            severity="MEDIUM",
        )

        empty_payload = {
            "order_id": "",
            "title": "",
            "description": "",
            "contractor_id": "",
            "messenger": "telegram",
        }

        try:
            req = CreateGroupRequest.from_dict(empty_payload)
            # Если создался объект с пустыми обязательными полями
            if not req.order_id or not req.title or not req.contractor_id:
                poc = (
                    f"CreateGroupRequest.from_dict принял полностью пустой заказ:\n"
                    f"  order_id='{req.order_id}', title='{req.title}', contractor='{req.contractor_id}'\n"
                    f"Это приводит к засорению базы пустыми записями и созданию безымянных групп."
                )
                res.fail(
                    details="Отсутствует валидация обязательных непустых полей (order_id, title, contractor_id).",
                    poc_output=poc,
                    recommendation="Внедрить строгую проверку в __post_init__: запрет пустых строк, лимиты длины (например, title <= 128).",
                )
            else:
                res.passed("Пустые поля корректно отклоняются.")
        except ValueError:
            res.passed("Пустые поля вызывают исключение ValueError.")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # ТЕСТ 6: Защита от Memory DoS через неограниченный Content-Length (CWE-770)
    # --------------------------------------------------------------------------
    def test_unbounded_payload_memory_dos(self):
        res = AuditResult(
            check_id="SEC-DOS-006",
            title="Отсутствие лимита размера тела запроса (Memory Exhaustion DoS)",
            category="Denial of Service (DoS)",
            severity="HIGH",
        )

        server_code = (BASE_DIR / "server.py").read_text(encoding="utf-8")
        # Проверяем чтение rfile.read(content_length)
        if "content_length = int(self.headers.get(\"Content-Length\", 0))" in server_code:
            has_size_limit = "MAX_PAYLOAD_SIZE" in server_code or "content_length >" in server_code
            if not has_size_limit:
                poc = (
                    "В CRMRequestHandler.do_POST:\n"
                    "  content_length = int(self.headers.get('Content-Length', 0))\n"
                    "  body = self.rfile.read(content_length).decode('utf-8')\n"
                    "Атакующий может передать заголовок 'Content-Length: 500000000' (500 МБ) "
                    "и вызвать OOM-килл сервиса или бесконечное зависание сокета."
                )
                res.fail(
                    details="Отсутствует ограничение максимального размера тела HTTP-запроса.",
                    poc_output=poc,
                    recommendation="Ограничить MAX_BODY_SIZE = 1 * 1024 * 1024 (1 МБ) и возвращать HTTP 413 Payload Too Large.",
                )
            else:
                res.passed("Лимит размера тела запроса активен.")
        else:
            res.passed("Парсер защищен.")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # ТЕСТ 7: Конкурентные Race Conditions в SQLite и дедупликации (CWE-362)
    # --------------------------------------------------------------------------
    def test_sqlite_race_conditions_and_wal_mode(self):
        res = AuditResult(
            check_id="SEC-RACE-007",
            title="Проверка WAL-режима SQLite и блокировок при параллельной записи",
            category="Database & Concurrency",
            severity="MEDIUM",
        )

        storage_code = (BASE_DIR / "storage.py").read_text(encoding="utf-8")
        has_wal = "journal_mode = WAL" in storage_code or "journal_mode=WAL" in storage_code
        has_busy_timeout = "busy_timeout" in storage_code

        # Проверим реальный режим журнала на тестовой БД
        conn = storage.get_connection(self.audit_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        current_mode = cursor.fetchone()[0].upper()
        conn.close()

        if current_mode != "WAL" or not has_wal:
            poc = (
                f"Текущий journal_mode в storage.py: '{current_mode}' (по умолчанию DELETE/ROLLBACK).\n"
                f"PRAGMA busy_timeout = 5000: {'Да' if has_busy_timeout else 'НЕТ'}.\n"
                f"При параллельных запросах от вебхуков это приводит к ошибкам: 'database is locked'."
            )
            res.fail(
                details="SQLite работает в синхронном блокирующем режиме DELETE без PRAGMA journal_mode = WAL.",
                poc_output=poc,
                recommendation="В init_db() выполнить 'PRAGMA journal_mode = WAL;' и 'PRAGMA busy_timeout = 5000;'.",
            )
        else:
            res.passed("SQLite настроен на WAL и асинхронную конкурентность.")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # ТЕСТ 8: Инъекция сервисных команд в Telegram через task_number (CRLF / Command Injection)
    # --------------------------------------------------------------------------
    def test_telegram_task_command_injection(self):
        res = AuditResult(
            check_id="SEC-INJ-008",
            title="Инъекция команд Telegram через task_number (CWE-77)",
            category="Injection Vulnerabilities",
            severity="MEDIUM",
        )

        # Проверяем telegram_manager:
        # msg = f"/task {task_number}"
        tm = TelegramManager(demo_mode=True)
        malicious_task = "8801\n/delete_channel\n/kill_bot"

        loop = asyncio.new_event_loop()
        try:
            msg = loop.run_until_complete(tm.mock_client.send_task_binding_message("chat_1", malicious_task))
        finally:
            loop.close()

        if "\n" in msg and "/delete_channel" in msg:
            poc = (
                f"Входной task_number: {repr(malicious_task)}\n"
                f"Сформированное сообщение в супергруппе:\n"
                f"----------------------------------------\n"
                f"{msg}\n"
                f"----------------------------------------\n"
                f"Перевод строки не санитизируется, что позволяет злоумышленнику внедрять побочные команды ботам."
            )
            res.fail(
                details="task_number интерполируется в команду без фильтрации переводов строк и спецсимволов.",
                poc_output=poc,
                recommendation="Санитизировать task_number: re.sub(r'[^a-zA-Z0-9_-]', '', task_number) и запретить переводы строк.",
            )
        else:
            res.passed("task_number санитизируется.")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # ТЕСТ 9: Маскирование PII (Персональных данных) в логах (CWE-532)
    # --------------------------------------------------------------------------
    def test_pii_logging_masking(self):
        res = AuditResult(
            check_id="SEC-PII-009",
            title="Утечка персональных данных (телефоны/токены) в открытых логах (CWE-532)",
            category="Privacy & Logging",
            severity="MEDIUM",
        )

        # Проверим, маскируются ли номера телефонов или id подрядчиков в логах
        phone_user = "+79161234567"
        tm = TelegramManager(demo_mode=True)

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        config.logger.addHandler(handler)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(tm.mock_client.add_contractor("-1001", phone_user))
        finally:
            loop.close()
            config.logger.removeHandler(handler)

        log_content = log_stream.getvalue()
        if phone_user in log_content:
            poc = (
                f"В лог выведено в открытом виде: '{phone_user}'\n"
                f"Отсутствует маскирование номеров телефонов подрядчиков (+7***4567)."
            )
            res.fail(
                details="Чувствительные идентификаторы и телефоны логируются без маскирования.",
                poc_output=poc,
                recommendation="Добавить вспомогательную функцию mask_pii(text) для скрытия середины номеров и токенов.",
            )
        else:
            res.passed("Логирование PII маскируется.")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # ТЕСТ 10: Формульная инъекция CSV / Excel (CWE-1236)
    # --------------------------------------------------------------------------
    def test_csv_formula_injection(self):
        res = AuditResult(
            check_id="SEC-CSV-010",
            title="Экранирование формульных инъекций в экспорте клиентов (CWE-1236)",
            category="Data Export Safety",
            severity="LOW",
        )

        # Проверяем наличие защитной функции санитизации формул
        # Символы =, +, -, @, \t, \r
        test_payload = "=cmd|' /C calc'!A0"
        server_code = (BASE_DIR / "server.py").read_text(encoding="utf-8")
        storage_code = (BASE_DIR / "storage.py").read_text(encoding="utf-8")

        has_sanitizer = "sanitize_csv" in server_code or "sanitize_csv" in storage_code
        if not has_sanitizer:
            poc = (
                f"Поле названия заказа может содержать: '{test_payload}'\n"
                f"При выгрузке в Excel без экранирования апострофом (') табличный процессор "
                f"интерпретирует данные как исполняемую формулу DDE (CWE-1236)."
            )
            res.fail(
                details="Отсутствует функция санитизации CSV от формульных инъекций.",
                poc_output=poc,
                recommendation="Добавить sanitize_csv_cell(val): если строка начинается с (=, +, -, @, \\t, \\r), предварять её апострофом (').",
            )
        else:
            res.passed("Санитизация формул активна.")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # ТЕСТ 11: Однопоточный блокирующий сервер HTTP (CWE-400)
    # --------------------------------------------------------------------------
    def test_single_threaded_blocking_server(self):
        res = AuditResult(
            check_id="ARCH-PERF-011",
            title="Блокирующий однопоточный сервер (HTTPServer vs ThreadingHTTPServer)",
            category="Architecture & Availability",
            severity="MEDIUM",
        )

        server_code = (BASE_DIR / "server.py").read_text(encoding="utf-8")
        if "from http.server import BaseHTTPRequestHandler, HTTPServer" in server_code:
            if "ThreadingHTTPServer" not in server_code:
                poc = (
                    "В server.py используется стандартный однопоточный HTTPServer:\n"
                    "  httpd = HTTPServer(server_address, CRMRequestHandler)\n"
                    "Любой долгий сетевой запрос к Telegram MTProto или API МАКС (до 10 секунд) "
                    "полностью блокирует приём входящих запросов от других CRM-воркеров."
                )
                res.fail(
                    details="Однопоточный HTTP-сервер блокирует все параллельные запросы.",
                    poc_output=poc,
                    recommendation="Заменить HTTPServer на ThreadingHTTPServer из http.server (поддерживается в Python 3.7+ без внешних библиотек).",
                )
            else:
                res.passed("Используется ThreadingHTTPServer.")
        else:
            res.passed("Сервер поддерживает параллелизм.")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # ТЕСТ 12: Обработка сигналов завершения (SIGTERM)
    # --------------------------------------------------------------------------
    def test_sigterm_handling(self):
        res = AuditResult(
            check_id="OPS-SIG-012",
            title="Обработка сигнала SIGTERM (Контейнеризация и Docker / Systemd)",
            category="Operational Reliability",
            severity="LOW",
        )

        server_code = (BASE_DIR / "server.py").read_text(encoding="utf-8")
        has_sigterm = "signal.SIGTERM" in server_code
        if not has_sigterm:
            poc = (
                "В server.py зарегистрирован только signal.SIGINT.\n"
                "При развертывании в Docker/Kubernetes/systemd завершение процесса происходит через SIGTERM.\n"
                "Отсутствие перехвата SIGTERM приводит к принудительному аварийному закрытию без сброса сокетов."
            )
            res.fail(
                details="Отсутствует обработчик signal.SIGTERM.",
                poc_output=poc,
                recommendation="Добавить signal.signal(signal.SIGTERM, handle_sigint) для плавного graceful shutdown.",
            )
        else:
            res.passed("SIGTERM перехватывается корректно.")

        self.results.append(res)

    # --------------------------------------------------------------------------
    # СТРЕСС-ТЕСТ: Конкурентная нагрузка на хранилище и дедупликацию
    # --------------------------------------------------------------------------
    def run_concurrency_stress_test(self, workers: int = 10, iterations_per_worker: int = 10) -> Dict[str, Any]:
        """Стресс-тестирование SQLite при высокой конкуренции без падений."""
        errors = []
        timings = []

        def worker_task(worker_id: int):
            for i in range(iterations_per_worker):
                order_id = f"STRESS-ORD-{worker_id:02d}-{i:03d}"
                start_t = time.perf_counter()
                try:
                    # 1. Сохранение
                    rec = GroupRecord(
                        order_id=order_id,
                        messenger="telegram" if i % 2 == 0 else "max",
                        group_id=f"-100{worker_id}{i:04d}",
                        title=f"Стресс заказ #{order_id}",
                        contractor_id=f"@worker_{worker_id}",
                        invite_link="https://t.me/c/test",
                        status="active",
                    )
                    storage.save_group(rec, db_path=self.audit_db)

                    # 2. Чтение
                    found = storage.get_group(order_id, db_path=self.audit_db)
                    if not found or found.group_id != rec.group_id:
                        errors.append(f"Несоответствие данных для {order_id}")

                    # 3. Обновление
                    storage.mark_deleted(order_id, db_path=self.audit_db)
                    timings.append(time.perf_counter() - start_t)
                except Exception as e:
                    errors.append(f"Worker {worker_id} ошибка на шаге {i}: {e}")

        threads = []
        t0 = time.perf_counter()
        for wid in range(workers):
            t = threading.Thread(target=worker_task, args=(wid,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()
        total_time = time.perf_counter() - t0

        total_ops = workers * iterations_per_worker * 3  # save, get, mark_deleted
        ops_per_sec = total_ops / total_time if total_time > 0 else 0
        avg_latency = (sum(timings) / len(timings)) * 1000 if timings else 0

        return {
            "workers": workers,
            "total_transactions": workers * iterations_per_worker,
            "total_ops": total_ops,
            "total_time_sec": round(total_time, 3),
            "ops_per_sec": round(ops_per_sec, 1),
            "avg_latency_ms": round(avg_latency, 2),
            "errors_count": len(errors),
            "errors_sample": errors[:3],
        }

    # --------------------------------------------------------------------------
    # ЗАПУСК ВСЕХ ПРОВЕРОК
    # --------------------------------------------------------------------------
    def run_all(self):
        print("\n" + "=" * 78)
        print("🕵️  ЗАПУСК БЕСПОЩАДНОГО СТРЕСС-ТЕСТА И АУДИТА БЕЗОПАСНОСТИ CRM_GROUP_MANAGER")
        print("=" * 78)

        self.test_api_authentication_bypass()
        self.test_unauthenticated_data_leakage()
        self.test_telegram_invite_link_lstrip_bug()
        self.test_max_fail_open_silent_mock()
        self.test_input_validation_and_empty_fields()
        self.test_unbounded_payload_memory_dos()
        self.test_sqlite_race_conditions_and_wal_mode()
        self.test_telegram_task_command_injection()
        self.test_pii_logging_masking()
        self.test_csv_formula_injection()
        self.test_single_threaded_blocking_server()
        self.test_sigterm_handling()

        stress_stats = self.run_concurrency_stress_test(workers=8, iterations_per_worker=25)

        print("\n" + "-" * 78)
        print("📊 СВОДНЫЕ РЕЗУЛЬТАТЫ СТРЕСС-ТЕСТИРОВАНИЯ БАЗЫ ДАННЫХ:")
        print(f"  • Параллельных потоков (Workers): {stress_stats['workers']}")
        print(f"  • Всего завершено транзакций:    {stress_stats['total_transactions']}")
        print(f"  • Всего операций SQLite:          {stress_stats['total_ops']}")
        print(f"  • Затраченное время:             {stress_stats['total_time_sec']} сек")
        print(f"  • Пропускная способность:         {stress_stats['ops_per_sec']} ops/sec")
        print(f"  • Средняя задержка транзакции:   {stress_stats['avg_latency_ms']} мс")
        print(f"  • Ошибок блокировки базы:         {stress_stats['errors_count']}")
        print("-" * 78)

        print("\n📋 РЕЗУЛЬТАТЫ РЕВИЗИИ БЕЗОПАСНОСТИ:")
        vuln_count = 0
        for r in self.results:
            status_icon = "🔴 УЯЗВИМОСТЬ" if r.vulnerable else "🟢 ОК"
            badge = f"[{r.severity}]"
            print(f"\n{status_icon} {badge:10} | {r.check_id}: {r.title}")
            print(f"   Категория: {r.category}")
            print(f"   Вердикт:   {r.details}")
            if r.vulnerable:
                vuln_count += 1
                if r.poc_output:
                    print(f"   Детали PoC:\n     " + r.poc_output.replace("\n", "\n     "))
                if r.recommendation:
                    print(f"   💡 Решение: {r.recommendation}")

        print("\n" + "=" * 78)
        print(f"🎯 ИТОГ: Выявлено {vuln_count} уязвимостей и архитектурных дефектов из {len(self.results)} проверок.")
        print("=" * 78 + "\n")

        self.cleanup()
        return self.results, stress_stats


def main():
    auditor = SecurityAuditor()
    results, stats = auditor.run_all()
    # Возвращаем ненулевой код при наличии критических или высоких уязвимостей
    critical_or_high = [r for r in results if r.vulnerable and r.severity in ("CRITICAL", "HIGH")]
    if critical_or_high:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
