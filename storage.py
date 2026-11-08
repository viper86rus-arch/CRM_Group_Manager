#!/usr/bin/env python3
"""
==============================================================================
Модуль постоянного хранения: Storage Engine (storage.py)
==============================================================================
Автор: V1PER (viper86rus-arch)
GitHub: https://github.com/viper86rus-arch/CRM_Group_Manager
Лицензия: MIT License (2026)
Назначение: Управление локальной базой данных SQLite для сопоставления Заказ <-> Группа.
==============================================================================
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import csv

from typing import Any, List, Optional

import config
from models import GroupRecord



def sanitize_csv_cell(value: Any) -> str:
    """Нейтрализует CSV/Excel Formula Injection (CWE-1236)."""
    if value is None:
        return ""
    s = str(value).replace("\r", " ").replace("\n", " ").strip()
    if s and s[0] in ("=", "+", "-", "@", "\t"):
        return f"'{s}"
    return s


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Получение потокобезопасного соединения с базой данных SQLite."""
    path = db_path or config.DB_PATH
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Инициализация схемы таблиц базы данных."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS order_groups (
                    order_id TEXT PRIMARY KEY,
                    messenger TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    contractor_id TEXT NOT NULL,
                    invite_link TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TIMESTAMP NOT NULL,
                    deleted_at TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_group_id ON order_groups(group_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON order_groups(status)")
    finally:
        conn.close()



def save_group(record: GroupRecord, db_path: Optional[Path] = None) -> None:
    """Сохранение или обновление записи о группе заказа."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO order_groups (
                    order_id, messenger, group_id, title, contractor_id,
                    invite_link, status, created_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.order_id,
                record.messenger,
                record.group_id,
                record.title,
                record.contractor_id,
                record.invite_link,
                record.status,
                record.created_at,
                record.deleted_at,
            ))
    finally:
        conn.close()


def get_group(order_id: str, db_path: Optional[Path] = None) -> Optional[GroupRecord]:
    """Поиск активной записи группы по номеру заказа."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM order_groups WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return GroupRecord(
            order_id=row["order_id"],
            messenger=row["messenger"],
            group_id=row["group_id"],
            title=row["title"],
            contractor_id=row["contractor_id"],
            invite_link=row["invite_link"],
            status=row["status"],
            created_at=row["created_at"],
            deleted_at=row["deleted_at"],
        )
    finally:
        conn.close()


def mark_deleted(order_id: str, db_path: Optional[Path] = None) -> bool:
    """Фиксация удаления группы и завершения заказа в базе данных."""
    conn = get_connection(db_path)
    try:
        with conn:
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute("""
                UPDATE order_groups
                SET status = 'deleted', deleted_at = ?
                WHERE order_id = ? AND status = 'active'
            """, (now_iso, order_id))
            return cursor.rowcount > 0
    finally:
        conn.close()


def list_active_groups(db_path: Optional[Path] = None) -> List[GroupRecord]:
    """Получение списка всех находящихся в работе групп."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM order_groups WHERE status = 'active' ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [
            GroupRecord(
                order_id=r["order_id"],
                messenger=r["messenger"],
                group_id=r["group_id"],
                title=r["title"],
                contractor_id=r["contractor_id"],
                invite_link=r["invite_link"],
                status=r["status"],
                created_at=r["created_at"],
                deleted_at=r["deleted_at"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def export_groups_to_csv(filepath: Optional[Path] = None, db_path: Optional[Path] = None) -> Path:
    """Безопасный экспорт реестра групп в CSV с защитой от Formula Injection (CWE-1236)."""
    out_path = filepath or (config.BASE_DIR / "exports" / f"groups_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    if out_path.parent:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    groups = list_active_groups(db_path=db_path)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Номер заказа", "Мессенджер", "ID группы", "Название", "Подрядчик", "Инвайт-ссылка", "Статус", "Дата создания"])
        for g in groups:
            writer.writerow([
                sanitize_csv_cell(g.order_id),
                sanitize_csv_cell(g.messenger),
                sanitize_csv_cell(g.group_id),
                sanitize_csv_cell(g.title),
                sanitize_csv_cell(g.contractor_id),
                sanitize_csv_cell(g.invite_link),
                sanitize_csv_cell(g.status),
                sanitize_csv_cell(g.created_at),
            ])
    return out_path

