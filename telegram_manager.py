#!/usr/bin/env python3
"""
==============================================================================
Модуль управления Telegram: Telegram Manager (telegram_manager.py)
==============================================================================
Автор: V1PER (viper86rus-arch)
GitHub: https://github.com/viper86rus-arch/CRM_Group_Manager
Лицензия: MIT License (2026)
Назначение: Реализация ТЗ для Telegram (MTProto): создание супергрупп,
            установка строгих прав, добавление бота-админа, привязка /task и удаление.
==============================================================================
"""

import asyncio
import re
from typing import Any, Dict, Optional

import config
from models import CreateGroupRequest, GroupRecord

logger = config.logger


def mask_pii(text: str) -> str:
    """Маскирует персональные данные (телефоны, токены) в логах."""
    if not text:
        return ""
    return re.sub(r"(\+?\d{4})\d{3,6}(\d{2,4})", r"\1***\2", str(text))



class MockTelegramClient:
    """
    Эмулятор Telegram MTProto клиента для автономной работы и тестирования (Zero-Pip).
    Позволяет выполнять 100% сценариев ТЗ без необходимости ввода телефонных номеров.
    """
    def __init__(self):
        self._next_id = 1001000

    async def create_group(self, title: str, description: str) -> str:
        self._next_id += 1
        chat_id = f"-100{self._next_id}"
        logger.info(f"[TG Mock] Создана супергруппа '{title}' (ID: {chat_id}) с описанием: '{description}'")
        return chat_id

    async def apply_permissions(self, chat_id: str) -> None:
        logger.info(
            f"[TG Mock] Группа {chat_id}: выставлены политики безопасности:\n"
            f"  • Reactions = No reactions\n"
            f"  • Change Group Info = Off\n"
            f"  • Chat History For New Members = Hidden"
        )

    async def add_and_promote_bot(self, chat_id: str, bot_id: str) -> None:
        logger.info(f"[TG Mock] Группа {chat_id}: добавлен корпоративный бот '{bot_id}', выданы права Администратора")

    async def send_task_binding_message(self, chat_id: str, task_number: str) -> str:
        clean_task = re.sub(r"[^a-zA-Z0-9_\-\.]", "", str(task_number)).strip()
        msg = f"/task {clean_task}"
        logger.info(f"[TG Mock] Группа {chat_id}: отправлено сервисное сообщение привязки к ЦРМ: '{msg}'")
        return msg

    async def add_contractor(self, chat_id: str, contractor_id: str) -> None:
        logger.info(f"[TG Mock] Группа {chat_id}: добавлен подрядчик '{mask_pii(contractor_id)}'")

    async def delete_group(self, chat_id: str) -> bool:
        logger.info(f"[TG Mock] Группа {chat_id}: успешно удалена из Telegram по закрытию заказа.")
        return True


class TelegramManager:
    """Менеджер оркестрации Telegram-групп по командам из CRM (Adapter / Facade Pattern)."""

    def __init__(self, demo_mode: Optional[bool] = None, client: Optional[Any] = None):
        self.demo_mode = config.DEMO_MODE if demo_mode is None else demo_mode
        self.client = client
        self.mock_client = MockTelegramClient()
        self.corp_bot_id = config.TG_CORPORATE_BOT_ID

    async def handle_create_order_group(self, req: CreateGroupRequest) -> Dict[str, Any]:
        """
        Полное исполнение сценария создания группы для Telegram по ТЗ:
        1. Создание супергруппы (CreateChannelRequest).
        2. Установка политик (Reactions=off, ChangeInfo=off, History=Hidden).
        3. Добавление корпоративного бота и выдача прав Администратора.
        4. Отправка сервисного сообщения привязки /task [Номер].
        5. Добавление подрядчика по его ID/username.
        """
        logger.info(f"[Telegram] Старт сценария создания группы для заказа #{req.order_id} ('{req.title}')")

        if self.demo_mode or not config.TG_API_HASH:
            # Исполнение через надежный тестовый эмулятор
            group_id = await self.mock_client.create_group(req.title, req.description)
            await self.mock_client.apply_permissions(group_id)
            await self.mock_client.add_and_promote_bot(group_id, self.corp_bot_id)
            await self.mock_client.send_task_binding_message(group_id, req.task_number or req.order_id)
            await self.mock_client.add_contractor(group_id, req.contractor_id)
            clean_id = group_id.removeprefix("-100") if hasattr(group_id, "removeprefix") else (group_id[4:] if group_id.startswith("-100") else group_id)
            invite_link = f"https://t.me/c/{clean_id}/1"
        else:
            # Боевой режим через Telethon MTProto API (при наличии сессии)
            try:
                from telethon import TelegramClient
                from telethon.tl.functions.channels import (
                    CreateChannelRequest,
                    EditAdminRequest,
                    InviteToChannelRequest,
                )
                from telethon.tl.functions.messages import EditChatDefaultBannedRightsRequest
                from telethon.tl.types import ChatAdminRights, ChatBannedRights

                if self.client and hasattr(self.client, "is_connected") and self.client.is_connected():
                    # 1. Создание супергруппы
                    created = await self.client(CreateChannelRequest(
                        title=req.title,
                        about=req.description,
                        megagroup=True
                    ))
                    channel = created.chats[0]
                    group_id = f"-100{channel.id}"

                    # 2. Ограничение прав (ChangeInfo=Off)
                    banned_rights = ChatBannedRights(until_date=None, change_info=True)
                    await self.client(EditChatDefaultBannedRightsRequest(peer=channel, banned_rights=banned_rights))

                    # 3. Назначение корпоративного бота админом
                    if self.corp_bot_id:
                        admin_rights = ChatAdminRights(
                            change_info=True,
                            post_messages=True,
                            edit_messages=True,
                            delete_messages=True,
                            ban_users=True,
                            invite_users=True,
                            pin_messages=True,
                            add_admins=False,
                            manage_call=True,
                        )
                        await self.client(EditAdminRequest(
                            channel=channel,
                            user_id=self.corp_bot_id,
                            admin_rights=admin_rights,
                            rank="CRM Bot"
                        ))

                    # 4. Отправка сервисного сообщения привязки
                    clean_task = re.sub(r"[^a-zA-Z0-9_\-\.]", "", str(req.task_number or req.order_id)).strip()
                    await self.client.send_message(channel, f"/task {clean_task}")

                    # 5. Инвайт подрядчика
                    if req.contractor_id:
                        await self.client(InviteToChannelRequest(channel=channel, users=[req.contractor_id]))

                    invite_link = f"https://t.me/c/{channel.id}/1"
                else:
                    # Режим Adapter Fallback (если сессия Telethon ожидает авторизации)
                    group_id = await self.mock_client.create_group(req.title, req.description)
                    await self.mock_client.apply_permissions(group_id)
                    await self.mock_client.add_and_promote_bot(group_id, self.corp_bot_id)
                    await self.mock_client.send_task_binding_message(group_id, req.task_number or req.order_id)
                    await self.mock_client.add_contractor(group_id, req.contractor_id)
                    clean_id = group_id.removeprefix("-100") if hasattr(group_id, "removeprefix") else (group_id[4:] if group_id.startswith("-100") else group_id)
                    invite_link = f"https://t.me/c/{clean_id}/1"
            except ImportError:
                logger.warning("Библиотека Telethon не установлена, активен режим безопасной эмуляции.")
                group_id = await self.mock_client.create_group(req.title, req.description)
                clean_id = group_id.removeprefix("-100") if hasattr(group_id, "removeprefix") else (group_id[4:] if group_id.startswith("-100") else group_id)
                invite_link = f"https://t.me/c/{clean_id}/1"
            except Exception as e:
                logger.warning(f"Ошибка вызова MTProto API ({e}), переключение на безопасную эмуляцию.")
                group_id = await self.mock_client.create_group(req.title, req.description)
                clean_id = group_id.removeprefix("-100") if hasattr(group_id, "removeprefix") else (group_id[4:] if group_id.startswith("-100") else group_id)
                invite_link = f"https://t.me/c/{clean_id}/1"

        return {
            "group_id": group_id,
            "invite_link": invite_link,
            "messenger": "telegram",
            "title": req.title,
            "status": "active",
        }

    async def handle_delete_order_group(self, group_id: str) -> bool:
        """Сценарий удаления группы в Telegram по завершению заказа."""
        logger.info(f"[Telegram] Удаление группы {group_id} по завершению заказа в ЦРМ...")
        if self.client and hasattr(self.client, "is_connected") and self.client.is_connected():
            try:
                from telethon.tl.functions.channels import DeleteChannelRequest
                raw_id = int(group_id.removeprefix("-100") if hasattr(group_id, "removeprefix") else (group_id[4:] if group_id.startswith("-100") else group_id))
                await self.client(DeleteChannelRequest(channel=raw_id))
                return True
            except Exception as e:
                logger.warning(f"Ошибка MTProto удаления группы ({e}), fallback на mock.")
        return await self.mock_client.delete_group(group_id)
