#!/usr/bin/env python3
"""
==============================================================================
Модуль структур данных: Data Models (models.py)
==============================================================================
Автор: V1PER (viper86rus-arch)
GitHub: https://github.com/viper86rus-arch/CRM_Group_Manager
Лицензия: MIT License (2026)
Назначение: Типизированные структуры данных для входящих вебхуков CRM и ответов.
==============================================================================
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class CreateGroupRequest:
    """Входящий вебхук от CRM на создание группы под новый заказ."""
    order_id: str
    title: str
    description: str
    contractor_id: str
    messenger: str = "telegram"
    avatar_url: Optional[str] = None
    task_number: Optional[str] = None

    def __post_init__(self):
        self.messenger = self.messenger.lower().strip()
        if self.messenger not in ("telegram", "tg", "max", "макс"):
            raise ValueError(f"Неподдерживаемый мессенджер: {self.messenger}. Доступны: telegram, max")
        if not self.task_number:
            self.task_number = self.order_id

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CreateGroupRequest":
        return cls(
            order_id=str(data.get("order_id", "")).strip(),
            title=str(data.get("title", "")).strip(),
            description=str(data.get("description", "")).strip(),
            contractor_id=str(data.get("contractor_id", "")).strip(),
            messenger=str(data.get("messenger", "telegram")).strip(),
            avatar_url=data.get("avatar_url"),
            task_number=str(data.get("task_number")) if data.get("task_number") else None,
        )


@dataclass
class DeleteGroupRequest:
    """Входящий вебхук от CRM на завершение заказа и удаление группы."""
    order_id: str
    reason: Optional[str] = "Order completed"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeleteGroupRequest":
        return cls(
            order_id=str(data.get("order_id", "")).strip(),
            reason=data.get("reason", "Order completed"),
        )


@dataclass
class GroupRecord:
    """Запись о созданной группе в локальной базе данных."""
    order_id: str
    messenger: str
    group_id: str
    title: str
    contractor_id: str
    invite_link: Optional[str] = None
    status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    deleted_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ServiceResponse:
    """Стандартизированный ответ сервиса для CRM."""
    success: bool
    order_id: str
    message: str
    group_id: Optional[str] = None
    invite_link: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
