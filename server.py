#!/usr/bin/env python3
"""
==============================================================================
Основной сервер сервиса: REST API Server (server.py)
==============================================================================
Автор: V1PER (viper86rus-arch)
GitHub: https://github.com/viper86rus-arch/CRM_Group_Manager
Лицензия: MIT License (2026)
Назначение: Приём команд от CRM, маршрутизация в Telegram и Макс,
            управление жизненным циклом групп заказов и дедупликация.
==============================================================================
"""

import argparse
import asyncio
import json
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse


import config
import storage
from max_manager import MaxManager
from models import CreateGroupRequest, DeleteGroupRequest, GroupRecord, ServiceResponse
from telegram_manager import TelegramManager

logger = config.logger

tg_mgr = TelegramManager()
max_mgr = MaxManager()


# ==============================================================================
# 1. СЕРВИСНЫЙ ДВИЖОК ОРКЕСТРАЦИИ ГРУПП
# ==============================================================================

async def process_create_group(data: Dict[str, Any]) -> ServiceResponse:
    """Оркестрация создания группы для нового заказа из CRM."""
    try:
        req = CreateGroupRequest.from_dict(data)
    except Exception as e:
        return ServiceResponse(
            success=False,
            order_id=str(data.get("order_id", "")),
            message=f"Ошибка валидации параметров заказа: {e}",
            error=str(e),
        )

    # Проверка: не создана ли уже группа для этого заказа
    existing = storage.get_group(req.order_id)
    if existing and existing.status == "active":
        logger.warning(f"Группа для заказа #{req.order_id} уже существует (ID: {existing.group_id})")
        return ServiceResponse(
            success=True,
            order_id=req.order_id,
            group_id=existing.group_id,
            invite_link=existing.invite_link,
            message="Группа для данного заказа уже была создана ранее",
        )

    # Выбор исполнительного модуля по мессенджеру
    try:
        if req.messenger in ("telegram", "tg"):
            res = await tg_mgr.handle_create_order_group(req)
        else:
            res = await max_mgr.handle_create_order_group(req)

        if res.get("error") or not res.get("group_id"):
            err_msg = res.get("error", "Не удалось создать группу")
            logger.error(f"Сбой при создании группы для заказа #{req.order_id}: {err_msg}")
            return ServiceResponse(
                success=False,
                order_id=req.order_id,
                message=f"Ошибка создания группы в {res.get('messenger', 'мессенджере')}: {err_msg}",
                error=err_msg,
            )

        # Фиксация в локальной базе данных

        record = GroupRecord(
            order_id=req.order_id,
            messenger=res["messenger"],
            group_id=res["group_id"],
            title=res["title"],
            contractor_id=req.contractor_id,
            invite_link=res["invite_link"],
            status="active",
        )
        storage.save_group(record)

        return ServiceResponse(
            success=True,
            order_id=req.order_id,
            group_id=res["group_id"],
            invite_link=res["invite_link"],
            message=f"Группа в {res['messenger'].capitalize()} успешно создана и сконфигурирована по ТЗ",
        )
    except Exception as e:
        logger.error(f"Сбой при создании группы для заказа #{req.order_id}: {e}")
        return ServiceResponse(
            success=False,
            order_id=req.order_id,
            message=f"Ошибка создания группы: {e}",
            error=str(e),
        )


async def process_delete_group(data: Dict[str, Any]) -> ServiceResponse:
    """Удаление группы при завершении заказа в CRM."""
    try:
        req = DeleteGroupRequest.from_dict(data)
    except Exception as e:
        return ServiceResponse(
            success=False,
            order_id=str(data.get("order_id", "")),
            message=f"Некорректный запрос на удаление: {e}",
            error=str(e),
        )

    record = storage.get_group(req.order_id)
    if not record or record.status != "active":
        return ServiceResponse(
            success=False,
            order_id=req.order_id,
            message=f"Активная группа для заказа #{req.order_id} не найдена в базе данных",
            error="Group not found or already deleted",
        )

    try:
        if record.messenger in ("telegram", "tg"):
            await tg_mgr.handle_delete_order_group(record.group_id)
        else:
            await max_mgr.handle_delete_order_group(record.group_id)

        storage.mark_deleted(req.order_id)
        return ServiceResponse(
            success=True,
            order_id=req.order_id,
            group_id=record.group_id,
            message=f"Группа {record.group_id} ({record.messenger}) успешно удалена по закрытию заказа",
        )
    except Exception as e:
        logger.error(f"Сбой при удалении группы #{record.group_id}: {e}")
        return ServiceResponse(
            success=False,
            order_id=req.order_id,
            group_id=record.group_id,
            message=f"Ошибка удаления группы: {e}",
            error=str(e),
        )


# ==============================================================================
# 2. ВСТРОЕННЫЙ АСИНХРОННЫЙ REST API СЕРВЕР (ZERO-PIP)
# ==============================================================================

class CRMRequestHandler(BaseHTTPRequestHandler):
    """Обработчик входящих HTTP-запросов от CRM с авторизацией и защитой от DoS."""

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        raw_body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw_body)))
        self.send_header("X-Powered-By", "CRM-Group-Manager/1.0.0 (V1PER)")
        self.end_headers()
        self.wfile.write(raw_body)

    def _is_authorized(self) -> bool:
        """Проверяет авторизацию запроса по SECRET_WEBHOOK_KEY (CWE-306, CWE-862)."""
        expected_secret = config.SECRET_WEBHOOK_KEY
        if not expected_secret:
            return True
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            if auth_header[7:].strip() == expected_secret:
                return True
        if self.headers.get("X-Webhook-Secret", "") == expected_secret:
            return True
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if qs.get("secret", [""])[0] == expected_secret:
            return True
        return False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # Health Check (публичный эндпоинт)
        if path == "/health" or path == "":
            self._send_json(200, {
                "status": "healthy",
                "service": "CRM Group Manager",
                "version": "1.0.0",
                "author": "V1PER (viper86rus-arch)",
                "active_messengers": ["telegram", "max"],
                "demo_mode": config.DEMO_MODE,
            })
            return

        # Проверка авторизации на доступ к данным (CWE-200)
        if not self._is_authorized():
            self._send_json(401, {
                "error": "Unauthorized",
                "message": "Требуется заголовок 'X-Webhook-Secret' или 'Authorization: Bearer <SECRET_WEBHOOK_KEY>'.",
            })
            return

        # Список активных групп (только для авторизованной CRM)
        if path == "/api/v1/groups":
            groups = [g.to_dict() for g in storage.list_active_groups()]
            self._send_json(200, {"count": len(groups), "groups": groups})
            return

        # Экспорт реестра в CSV
        if path == "/api/v1/groups/export":
            csv_path = storage.export_groups_to_csv()
            self._send_json(200, {"message": "Экспорт успешно сформирован", "file": str(csv_path)})
            return

        # Запрос статуса группы по order_id
        if path.startswith("/api/v1/groups/"):
            order_id = path.split("/")[-1]
            record = storage.get_group(order_id)
            if record:
                self._send_json(200, record.to_dict())
            else:
                self._send_json(404, {"error": f"Заказ #{order_id} не найден"})
            return

        self._send_json(404, {"error": "Not Found", "path": self.path})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # Проверка авторизации на управляющие действия (CWE-306, CWE-862)
        if not self._is_authorized():
            self._send_json(401, {
                "error": "Unauthorized",
                "message": "Требуется заголовок 'X-Webhook-Secret' или 'Authorization: Bearer <SECRET_WEBHOOK_KEY>'.",
            })
            return

        # Ограничение размера тела запроса для защиты от Memory DoS (CWE-770)
        MAX_PAYLOAD_SIZE = 1 * 1024 * 1024  # 1 MB
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            self._send_json(400, {"error": "Некорректный заголовок Content-Length"})
            return

        if content_length < 0 or content_length > MAX_PAYLOAD_SIZE:
            self._send_json(413, {"error": f"Превышен максимальный размер тела запроса (максимум {MAX_PAYLOAD_SIZE} байт)"})
            return

        if content_length == 0:
            self._send_json(400, {"error": "Отсутствует тело запроса JSON"})
            return

        try:
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
        except Exception as e:
            self._send_json(400, {"error": f"Невалидный JSON: {e}"})
            return

        # Эндпоинт 1: Создание группы для заказа
        if path == "/api/v1/groups/create":
            loop = asyncio.new_event_loop()
            try:
                resp = loop.run_until_complete(process_create_group(data))
                code = 200 if resp.success else 400
                self._send_json(code, resp.to_dict())
            finally:
                loop.close()
            return

        # Эндпоинт 2: Удаление группы при закрытии заказа
        if path == "/api/v1/groups/delete":
            loop = asyncio.new_event_loop()
            try:
                resp = loop.run_until_complete(process_delete_group(data))
                code = 200 if resp.success else 400
                self._send_json(code, resp.to_dict())
            finally:
                loop.close()
            return

        self._send_json(404, {"error": "Not Found", "path": self.path})


    def log_message(self, format: str, *args: Any) -> None:
        # Интеграция с нашим логером
        logger.debug(f"[HTTP] {self.address_string()} - {format % args}")


# ==============================================================================
# 3. ДЕМОНСТРАЦИОННЫЙ СКРИПТ ПО СЦЕНАРИЮ ТЗ (--demo)
# ==============================================================================

async def run_demo_lifecycle():
    """Демонстрация полного жизненного цикла заказов в Telegram и Макс по ТЗ."""
    print("\n" + "=" * 70)
    print("🚀 ДЕМОНСТРАЦИЯ ЖИЗНЕННОГО ЦИКЛА СЕРВИСА УПРАВЛЕНИЯ ГРУППАМИ (V1PER)")
    print("=" * 70)

    storage.init_db()

    # Сценарий 1: Заказ в Telegram
    print("\n[1/4] Поступление Заказа #ORD-8801 из ЦРМ (Мессенджер: Telegram)...")
    req_tg = {
        "order_id": "ORD-8801",
        "title": "Заказ #8801: Монтаж серверной стойки",
        "description": "Рабочая группа проекта по монтажу оборудования в ЦОД. Заказчик: ООО Вектор",
        "contractor_id": "@network_engineer_pro",
        "messenger": "telegram",
        "avatar_url": "https://company.ru/avatars/order_8801.png",
        "task_number": "8801",
    }
    res_tg = await process_create_group(req_tg)
    print(f"Результат: {json.dumps(res_tg.to_dict(), ensure_ascii=False, indent=2)}")

    # Сценарий 2: Заказ в мессенджере Макс
    print("\n[2/4] Поступление Заказа #ORD-8802 из ЦРМ (Мессенджер: Макс)...")
    req_max = {
        "order_id": "ORD-8802",
        "title": "Заказ #8802: Аудит информационной безопасности",
        "description": "Закрытая группа аудита инфраструктуры. Корпоративный контур.",
        "contractor_id": "max_user_44912",
        "messenger": "max",
        "avatar_url": "https://company.ru/avatars/order_8802.png",
        "task_number": "8802",
    }
    res_max = await process_create_group(req_max)
    print(f"Результат: {json.dumps(res_max.to_dict(), ensure_ascii=False, indent=2)}")

    # Проверка активных групп в базе
    print("\n[3/4] Проверка активных групп в локальной БД...")
    active = storage.list_active_groups()
    print(f"Активных групп в работе: {len(active)}")
    for g in active:
        print(f"  • Заказ {g.order_id} [{g.messenger.upper()}]: '{g.title}' (ID: {g.group_id})")

    # Сценарий 3: Завершение Заказа #ORD-8801 в ЦРМ и удаление группы
    print("\n[4/4] Завершение Заказа #ORD-8801 в ЦРМ -> Автоудаление группы...")
    del_res = await process_delete_group({"order_id": "ORD-8801", "reason": "Работы приняты"})
    print(f"Результат удаления: {json.dumps(del_res.to_dict(), ensure_ascii=False, indent=2)}")

    print("\n" + "=" * 70)
    print("✅ ВСЕ СЦЕНАРИИ ТЗ (TELEGRAM + МАКС + ЦРМ) УСПЕШНО ВЫПОЛНЕНЫ!")
    print("=" * 70 + "\n")


# ==============================================================================
# 4. ТОЧКА ВХОДА (MAIN)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="CRM Group Manager Service")
    parser.add_argument("--demo", action="store_true", help="Запустить демонстрационный прогон сценариев ТЗ")
    parser.add_argument("--port", type=int, default=config.SERVER_PORT, help="Порт HTTP сервера")
    parser.add_argument("--host", type=str, default=config.SERVER_HOST, help="Хост HTTP сервера")
    args = parser.parse_args()

    storage.init_db()

    if args.demo:
        asyncio.run(run_demo_lifecycle())
        return

    server_address = (args.host, args.port)
    httpd = ThreadingHTTPServer(server_address, CRMRequestHandler)

    def handle_sigint(sig, frame):
        logger.info("\nОстановка сервера по сигналу завершения...")
        httpd.server_close()
        sys.exit(130)

    signal.signal(signal.SIGINT, handle_sigint)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_sigint)


    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК СЕРВИСА CRM GROUP MANAGER (V1PER)")
    logger.info(f"Слушаю адрес: http://{args.host}:{args.port}")
    logger.info("Эндпоинты:")
    logger.info("  • GET  /health")
    logger.info("  • GET  /api/v1/groups")
    logger.info("  • POST /api/v1/groups/create")
    logger.info("  • POST /api/v1/groups/delete")
    logger.info("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
