"""Runtime-проверки игровых ассетов, на которые ссылаются действия.

Pydantic-модели из :mod:`src.core.models` проверяют структуру действия, но не
могут определить, существует ли отряд или предмет в SQLite-базе конкретной
сборки Anomaly. Модуль содержит точку расширения для такой проверки и получает
клиент базы через dependency injection.

Сейчас функция является архитектурной заглушкой: она логирует вызов и
возвращает ``True``. Реальные запросы к базе и правила безопасности описаны в
TODO и будут добавлены на следующем этапе развития валидатора.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.models import BaseAction, GiveItem, SpawnSquad
from src.logger import get_logger

if TYPE_CHECKING:
    from src.db.repository import GameDatabase

logger = get_logger("core.actions")


def validate_action_assets(
    action: BaseAction,
    db_client: GameDatabase,
) -> bool:
    """Проверяет существование и безопасность ассетов, используемых действием.

    Функция вызывается оркестратором :class:`src.core.validator.ProjectValidator`
    для каждого действия квеста или реплики. В будущем она будет валидировать
    ссылки на отряды, смарты и предметы по SQLite-базе, а при обнаружении
    коллизии писать ``logger.error`` и возвращать ``False``.

    Args:
        action (BaseAction):
            Проверяемое действие — конкретный наследник ``BaseAction``
            (``SpawnSquad``, ``GiveItem``, ``SetTarget`` и т.д.).
        db_client (GameDatabase):
            Клиент игровой базы данных. Ожидаемый интерфейс включает методы
            ``find_squad_by_alias``, ``find_item_by_alias`` и
            ``find_smart_by_alias``; параметр позволяет подменять базу в
            тестах.

    Returns:
        bool:
            ``True``, если все ассеты действия найдены и проверка пройдена.
            В текущей заглушке всегда возвращается ``True``.

    TODO:
        Реализовать runtime-проверку ассетов действий. Для ``SpawnSquad``
        проверить через ``db_client.find_squad_by_alias``, что сквад
        существует и имеет флаг ``is_safe_field=1`` (подсвечивать ошибку,
        если пытаются заспавнить уникальный отряд с торговцем в поле).
        Для ``GiveItem`` — валидировать секцию предмета по базе.

    Notes:
        Проверка ``GiveMoney`` не требует обращения к таблице ассетов, так как
        сумма полностью задана в модели. Для ``SpawnSquad`` и ``SetTarget``
        в будущем также следует проверять ``smart_alias`` через
        ``find_smart_by_alias``.
    """
    logger.debug(
        "Runtime-проверка действия %s через %s пока не реализована.",
        type(action).__name__,
        type(db_client).__name__,
    )

    if isinstance(action, SpawnSquad):
        # TODO: squad = db_client.find_squad_by_alias(action.squad_alias)
        # TODO: if squad is None:
        # TODO:     logger.error(
        # TODO:         "Действие SpawnSquad ссылается на отсутствующий "
        # TODO:         "отряд '%s'.",
        # TODO:         action.squad_alias,
        # TODO:     )
        # TODO:     return False
        # TODO: if squad.get("is_safe_field") != 1:
        # TODO:     logger.error(
        # TODO:         "Небезопасный спавн отряда '%s': is_safe_field != 1. "
        # TODO:         "Уникальный отряд с торговцем нельзя спавнить в поле.",
        # TODO:         action.squad_alias,
        # TODO:     )
        # TODO:     return False
        pass
    elif isinstance(action, GiveItem):
        # TODO: item = db_client.find_item_by_alias(action.item_alias)
        # TODO: if item is None:
        # TODO:     logger.error(
        # TODO:         "Действие GiveItem ссылается на отсутствующий "
        # TODO:         "предмет '%s'.",
        # TODO:         action.item_alias,
        # TODO:     )
        # TODO:     return False
        pass
    else:
        # TODO: Для GiveInfo/RemoveInfo/GiveMoney внешние ассеты не нужны.
        #       Для SetTarget добавить проверку squad_alias и smart_alias.
        pass

    return True


__all__ = ["validate_action_assets"]
