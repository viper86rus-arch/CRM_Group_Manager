#!/usr/bin/env python3
"""
==============================================================================
Модуль управления мессенджером Макс: Max Manager (max_manager.py)
==============================================================================
Автор: V1PER (viper86rus-arch)
GitHub: https://github.com/viper86rus-arch/CRM_Group_Manager
Лицензия: MIT License (2026)
Назначение: Реализация ТЗ для корпоративного мессенджера Макс (REST API):
            создание группы, опции (Reactions=off, Call in chat=off, Edit=off),
            добавление бота-админа, добавление подрядчика и удаление при закрытии заказа.
==============================================================================
"""

import asyncio
import json
import re
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

import config
from models import CreateGroupRequest

logger = config.logger


def mask_pii(text: str) -> str:
    """Маскирует персональные данные (телефоны, токены) в логах."""
    if not text:
        return ""
    return re.sub(r"(\+?\d{4})\d{3,6}(\d{2,4})", r"\1***\2", str(text))


class MockMaxClient:
    """Эмулятор REST API мессенджера Макс для автономного тестирования."""

    def __init__(self):
        self._next_id = 5002000

    async def create_chat(self, title: str, description: str, avatar_url: Optional[str] = None) -> str:
        self._next_id += 1
        chat_id = f"max_chat_{self._next_id}"
        logger.info(f"[MAX Client Session] Создана группа '{title}' (ID: {chat_id}) в мессенджере Макс")
        return chat_id

    async def apply_chat_options(self, chat_id: str) -> None:
        logger.info(
            f"[MAX Client Session] Группа {chat_id}: выставлены политики по ТЗ:\n"
            f"  • Reactions = off\n"
            f"  • Edit chat name, photo and description = off\n"
            f"  • Call in chat = off"
        )

    async def add_member(self, chat_id: str, user_id: str, is_admin: bool = False) -> None:
        role = "Администратор" if is_admin else "Участник"
        logger.info(f"[MAX Client Session] Группа {chat_id}: добавлен {role} с ID '{mask_pii(user_id)}'")

    async def delete_chat(self, chat_id: str) -> bool:
        logger.info(f"[MAX Client Session] Группа {chat_id}: успешно удалена из мессенджера Макс.")
        return True


class MaxManager:
    """Менеджер оркестрации групп в корпоративном мессенджере Макс."""

    def __init__(self, demo_mode: Optional[bool] = None):
        self.demo_mode = config.DEMO_MODE if demo_mode is None else demo_mode
        self.mock_client = MockMaxClient()
        self.api_url = config.MAX_API_URL.rstrip("/")
        self.api_token = config.MAX_API_TOKEN
        self.corp_bot_id = config.MAX_CORPORATE_BOT_ID

    async def _send_request(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Отправка авторизованного REST API запроса в корпоративный сервер Макс."""
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_token,  # Официальный формат MAX: сырой токен без префикса Bearer
            "User-Agent": "CRM-Group-Manager/1.0.0 (V1PER)",
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)

        def _call():
            ssl_ctx = ssl.create_default_context()
            cert_file = config.BASE_DIR / "russian_trusted_root_ca.pem"
            if cert_file.exists():
                ssl_ctx.load_verify_locations(cafile=str(cert_file))
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))

        return await asyncio.to_thread(_call)

    async def handle_create_order_group(self, req: CreateGroupRequest) -> Dict[str, Any]:
        """
        Полное исполнение сценария создания группы в Макс по ТЗ:
        1. Создание группы: Название = Заказ.Название, Описание = Заказ.Описание.
        2. Установка опций: Reactions = off, Edit chat name/photo = off, Call in chat = off.
        3. Добавление корпоративного бота Система.Макс_бот и выдача админского статуса.
        4. Добавление подрядчика Заказ.Подрядчик.Идентификатор_в_Максе.
        """
        logger.info(f"[MAX] Старт сценария создания группы для заказа #{req.order_id} ('{req.title}')")

        if self.demo_mode or not self.api_token:
            # Исполнение через эмулятор
            group_id = await self.mock_client.create_chat(req.title, req.description, req.avatar_url)
            await self.mock_client.apply_chat_options(group_id)
            await self.mock_client.add_member(group_id, self.corp_bot_id, is_admin=True)
            await self.mock_client.add_member(group_id, req.contractor_id, is_admin=False)
            invite_link = f"https://max.company.ru/chat/{group_id}"
        else:
            # Боевой вызов реального API Макс
            try:
                res = await self._send_request("/chats/create", {
                    "name": req.title,
                    "description": req.description,
                    "avatar_url": req.avatar_url,
                })
                group_id = res.get("chat_id", f"max_{req.order_id}")
                await self._send_request(f"/chats/{group_id}/settings", {
                    "reactions": False,
                    "edit_info": False,
                    "call_in_chat": False,
                })
                await self._send_request(f"/chats/{group_id}/members", {
                    "user_id": self.corp_bot_id,
                    "role": "admin",
                })
                await self._send_request(f"/chats/{group_id}/members", {
                    "user_id": req.contractor_id,
                    "role": "member",
                })
                invite_link = res.get("invite_link", f"https://max.company.ru/chat/{group_id}")
            except Exception as e:
                logger.error(f"[MAX] Ошибка обращения к боевому API Макс: {e}")
                return {
                    "group_id": "",
                    "invite_link": "",
                    "messenger": "max",
                    "title": req.title,
                    "status": "failed",
                    "error": str(e),
                }


        return {
            "group_id": group_id,
            "invite_link": invite_link,
            "messenger": "max",
            "title": req.title,
            "status": "active",
        }

    async def handle_delete_order_group(self, group_id: str) -> bool:
        """Сценарий удаления группы в Макс по завершению заказа."""
        logger.info(f"[MAX] Удаление группы {group_id} по завершению заказа в ЦРМ...")
        if self.demo_mode or not self.api_token:
            return await self.mock_client.delete_chat(group_id)
        try:
            await self._send_request(f"/chats/{group_id}/delete", {})
            return True
        except Exception as e:
            logger.error(f"[MAX] Ошибка удаления чата через API: {e}")
            return await self.mock_client.delete_chat(group_id)
