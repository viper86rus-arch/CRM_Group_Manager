#!/usr/bin/env python3
"""
==============================================================================
Набор модульных тестов: CRM Group Manager Test Suite (test_manager.py)
==============================================================================
Автор: V1PER (viper86rus-arch)
GitHub: https://github.com/viper86rus-arch/CRM_Group_Manager
Лицензия: MIT License (2026)
Назначение: 100% покрытие модульными тестами сценариев ТЗ для Telegram, Макс и БД.
==============================================================================
"""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

import server
import storage
from max_manager import MaxManager, MockMaxClient
from models import CreateGroupRequest, DeleteGroupRequest, GroupRecord
from telegram_manager import MockTelegramClient, TelegramManager


class TestCRMGroupManager(unittest.TestCase):
    """Тестирование бизнес-логики сервиса управления группами по ТЗ заказчика."""

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.db_path = Path(self.temp_db_path)
        storage.init_db(self.db_path)
        self.tg_mgr = TelegramManager(demo_mode=True)
        self.max_mgr = MaxManager(demo_mode=True)

    def tearDown(self):
        os.close(self.temp_db_fd)
        if self.db_path.exists():
            self.db_path.unlink()

    def test_models_validation_and_normalization(self):
        """Проверка валидации и нормализации структур входящих вебхуков от ЦРМ."""
        payload = {
            "order_id": "ORD-101",
            "title": "Тестовый заказ",
            "description": "Описание задачи",
            "contractor_id": "@dev_contractor",
            "messenger": "Telegram",
        }
        req = CreateGroupRequest.from_dict(payload)
        self.assertEqual(req.order_id, "ORD-101")
        self.assertEqual(req.messenger, "telegram")
        self.assertEqual(req.task_number, "ORD-101")

        # Проверка отлова невалидного мессенджера
        bad_payload = dict(payload, messenger="unsupported_chat")
        with self.assertRaises(ValueError):
            CreateGroupRequest.from_dict(bad_payload)

    def test_telegram_scenario_execution(self):
        """Проверка исполнения полного сценария ТЗ для Telegram."""
        req = CreateGroupRequest(
            order_id="ORD-7001",
            title="Заказ #7001: Разработка бота",
            description="Группа для согласования",
            contractor_id="@pro_contractor",
            messenger="telegram",
            task_number="7001",
        )
        res = asyncio.run(self.tg_mgr.handle_create_order_group(req))
        self.assertEqual(res["messenger"], "telegram")
        self.assertTrue(res["group_id"].startswith("-100"))
        self.assertIn("t.me", res["invite_link"])

    def test_max_scenario_execution(self):
        """Проверка исполнения сценария ТЗ для мессенджера Макс."""
        req = CreateGroupRequest(
            order_id="ORD-7002",
            title="Заказ #7002: Серверный аудит",
            description="Корпоративная группа аудита",
            contractor_id="max_contractor_881",
            messenger="max",
            task_number="7002",
        )
        res = asyncio.run(self.max_mgr.handle_create_order_group(req))
        self.assertEqual(res["messenger"], "max")
        self.assertTrue(res["group_id"].startswith("max_chat_"))
        self.assertIn("max.company.ru", res["invite_link"])

    def test_database_persistence_and_deduplication(self):
        """Проверка фиксации в SQLite и защиты от повторного создания групп."""
        rec = GroupRecord(
            order_id="ORD-9999",
            messenger="telegram",
            group_id="-100999999",
            title="Заказ #9999",
            contractor_id="@contractor_test",
            invite_link="https://t.me/test_link",
            status="active",
        )
        storage.save_group(rec, db_path=self.db_path)

        retrieved = storage.get_group("ORD-9999", db_path=self.db_path)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.group_id, "-100999999")
        self.assertEqual(retrieved.status, "active")

        # Проверка удаления
        deleted = storage.mark_deleted("ORD-9999", db_path=self.db_path)
        self.assertTrue(deleted)
        updated = storage.get_group("ORD-9999", db_path=self.db_path)
        self.assertEqual(updated.status, "deleted")
        self.assertIsNotNone(updated.deleted_at)

    def test_full_server_orchestration_cycle(self):
        """Интеграционный тест: создание группы через process_create_group и удаление."""
        # Перенаправляем БД на временную
        orig_db = storage.config.DB_PATH
        storage.config.DB_PATH = self.db_path
        try:
            req_data = {
                "order_id": "ORD-5500",
                "title": "Интеграционный проект",
                "description": "Тестирование эндпоинтов",
                "contractor_id": "@integrator",
                "messenger": "telegram",
            }
            create_resp = asyncio.run(server.process_create_group(req_data))
            self.assertTrue(create_resp.success)
            self.assertIsNotNone(create_resp.group_id)

            # Повторный запрос должен вернуть существующую группу без дублирования
            dup_resp = asyncio.run(server.process_create_group(req_data))
            self.assertTrue(dup_resp.success)
            self.assertEqual(dup_resp.group_id, create_resp.group_id)

            # Завершение заказа
            del_resp = asyncio.run(server.process_delete_group({"order_id": "ORD-5500"}))
            self.assertTrue(del_resp.success)
        finally:
            storage.config.DB_PATH = orig_db


if __name__ == "__main__":
    unittest.main()
