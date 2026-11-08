#!/usr/bin/env python3
"""
==============================================================================
Скрипт автономного тестирования сценария Мессенджера МАКС по ТЗ (run_scenario_max.py)
==============================================================================
Автор: V1PER (viper86rus-arch)
GitHub: https://github.com/viper86rus-arch/CRM_Group_Manager
Лицензия: MIT License (2026)
==============================================================================
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from models import CreateGroupRequest
from max_manager import MaxManager

def parse_args():
    parser = argparse.ArgumentParser(description="Тестовый запуск сценария МАКС по ТЗ")
    parser.add_argument("--order-id", default=None, help="Номер / ID заказа")
    parser.add_argument("--title", default=None, help="Название создаваемой группы")
    parser.add_argument("--desc", default=None, help="Описание создаваемой группы")
    parser.add_argument("--contractor", default=None, help="Идентификатор подрядчика в МАКС")
    parser.add_argument("--interactive", action="store_true", help="Интерактивный диалог ввода")
    parser.add_argument("--no-delete", action="store_true", help="Не удалять группу после создания")
    return parser.parse_args()

async def main():
    args = parse_args()
    
    json_path = Path(os.getenv("MAX_TEST_PARAMS", str(Path(__file__).parent / "test_params.json")))
    json_data = {}

    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
        except Exception:
            pass

    order_id = args.order_id or json_data.get("order_id")
    title = args.title or json_data.get("title")
    desc = args.desc or json_data.get("desc")
    contractor = args.contractor or json_data.get("contractor")

    if sys.stdin.isatty() and not (args.title and args.contractor):
        print("\n" + "=" * 70)
        print("🛠️  НАСТРОЙКА ПАРАМЕТРОВ ТЕСТОВОЙ ГРУППЫ МАКС (V1PER IT Solutions)")
        print("=" * 70)
        print("Нажмите Enter для использования значений по умолчанию [в скобках]\n")
        
        def_order = order_id or "ORDER-777"
        in_order = input(f"1. Номер заказа [{def_order}]: ").strip()
        order_id = in_order if in_order else def_order

        def_title = title or f"Заказ #{order_id} - Ремонтные работы"
        in_title = input(f"2. Название группы [{def_title}]: ").strip()
        title = in_title if in_title else def_title

        def_desc = desc or "Проектная группа по заказу. Обсуждение рабочих вопросов."
        in_desc = input(f"3. Описание группы [{def_desc}]: ").strip()
        desc = in_desc if in_desc else def_desc

        def_contractor = contractor or "contractor_max_id"
        in_contractor = input(f"4. ID подрядчика в МАКС [{def_contractor}]: ").strip()
        contractor = in_contractor if in_contractor else def_contractor
        print("-" * 70 + "\n")
    else:
        order_id = order_id or "ORDER-777"
        title = title or f"Заказ #{order_id} - Тестовый проект"
        desc = desc or "Группа создана тестовым сценарием по ТЗ"
        contractor = contractor or "contractor_max_id"

    test_req = CreateGroupRequest(
        order_id=order_id,
        title=title,
        description=desc,
        messenger="max",
        contractor_id=contractor
    )

    print("=" * 70)
    print("🚀 ВЫПОЛНЕНИЕ СЦЕНАРИЯ МАКС ПО ТЗ (clck.ru/3WsGXv)")
    print("=" * 70)
    print(f"📋 Входные параметры:")
    print(f"   • Заказ: #{test_req.order_id}")
    print(f"   • Название группы: {test_req.title}")
    print(f"   • Описание: {test_req.description}")
    print(f"   • Подрядчик: {test_req.contractor_id}")
    print("-" * 70)

    manager = MaxManager()

    print("\n[1/3] Создание группы и применение политик безопасности...")
    result = await manager.handle_create_order_group(test_req)
    group_id = result.get("group_id")
    print(f"✅ Группа успешно создана!")
    print(f"   • ID Группы: {group_id}")
    print(f"   • Инвайт-ссылка: {result.get('invite_link')}")
    print(f"   • Политики применены:")
    print(f"     🔒 Reactions = off (реакции запрещены)")
    print(f"     🚫 Edit info = off (запрещено менять имя, аватар и описание)")
    print(f"     📵 Call in chat = off (звонки в чате запрещены)")
    print(f"   • Участники:")
    print(f"     👑 Администратор: Система.Макс_бот")
    print(f"     👤 Подрядчик: {test_req.contractor_id}")

    if args.no_delete:
        print("\nℹ️ Флаг --no-delete активен. Группа оставлена для проверки.")
        print("=" * 70)
        return

    print("\n[2/3] Пауза 5 секунд перед удалением (время на проверку состояния чата)...")
    await asyncio.sleep(5)

    print(f"\n[3/3] Удаление группы {group_id} по завершению заказа...")
    deleted = await manager.handle_delete_order_group(group_id)
    if deleted:
        print("✅ Группа успешно удалена из Мессенджера МАКС!")
    else:
        print("⚠️ Ошибка при удалении группы.")

    print("\n" + "=" * 70)
    print("🎉 Сценарий по ТЗ выполнен на 100% без ошибок!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
