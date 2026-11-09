"""Runtime-проверки игровых ассетов, на которые ссылаются условия.

Pydantic-модели из :mod:`src.core.models` гарантируют структурную корректность
условия, но не знают, существует ли предмет или смарт-террейн в конкретной
сборке S.T.A.L.K.E.R. Anomaly. Этот модуль отделяет такую проверку от слоя
моделей и получает клиент SQLite-базы через dependency injection.

Сейчас функции модуля являются архитектурным каркасом: они логируют вызов и
возвращают ``True``. Реализация запросов к базе намеренно оставлена в TODO,
чтобы слой моделей и слой валидации можно было развивать независимо.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.models import BaseCondition, HasItem, SmartOwner
from src.logger import get_logger

if TYPE_CHECKING:
    from src.db.repository import GameDatabase

logger = get_logger("core.conditions")


def validate_condition_assets(
    condition: BaseCondition,
    db_client: GameDatabase,
) -> bool:
    """Проверяет существование игровых ассетов, упомянутых в условии.

    Функция вызывается оркестратором :class:`src.core.validator.ProjectValidator`
    для каждого условия диалога или реплики. В будущем она будет обращаться к
    SQLite-базе через переданный ``db_client`` и сообщать о коллизиях через
    ``logger.error``.

    Args:
        condition (BaseCondition):
            Проверяемое условие — конкретный наследник ``BaseCondition``
            (``HasInfo``, ``HasItem``, ``SmartOwner`` и т.д.).
        db_client (GameDatabase):
            Клиент игровой базы данных. Ожидаемый интерфейс включает методы
            ``find_item_by_alias`` и ``find_smart_by_alias``; передача клиента
            параметром упрощает подмену в тестах.

    Returns:
        bool:
            ``True``, если все ассеты условия найдены и проверка пройдена.
            В текущей заглушке всегда возвращается ``True``.

    TODO:
        Здесь будет реализована runtime-проверка ассетов условий по
        SQLite-базе. Например, для ``HasItem`` проверить через
        ``db_client.find_item_by_alias(item_alias)``, что предмет существует
        в игре; для ``SmartOwner`` — проверить существование смарта. Если
        ассет не найден — писать ``logger.error`` с точным описанием
        коллизии и возвращать ``False``.

    Notes:
        Условия ``HasInfo`` и ``DontHasInfo`` ссылаются на инфопоршни, которые
        не хранятся в таблице ассетов. Их проверка относится к анализу графа
        выдачи информации на уровне проекта, а не к запросам к SQLite.
    """
    logger.debug(
        "Runtime-проверка условия %s через %s пока не реализована.",
        type(condition).__name__,
        type(db_client).__name__,
    )

    if isinstance(condition, HasItem):
        # TODO: item = db_client.find_item_by_alias(condition.item_alias)
        # TODO: if item is None:
        # TODO:     logger.error(
        # TODO:         "Условие HasItem ссылается на отсутствующий "
        # TODO:         "предмет '%s'.",
        # TODO:         condition.item_alias,
        # TODO:     )
        # TODO:     return False
        pass
    elif isinstance(condition, SmartOwner):
        # TODO: smart = db_client.find_smart_by_alias(condition.smart_alias)
        # TODO: if smart is None:
        # TODO:     logger.error(
        # TODO:         "Условие SmartOwner ссылается на отсутствующий "
        # TODO:         "смарт '%s' (фракция '%s').",
        # TODO:         condition.smart_alias,
        # TODO:         condition.faction,
        # TODO:     )
        # TODO:     return False
        pass
    else:
        # TODO: Для условий без внешних ассетов (HasInfo/DontHasInfo)
        #       достаточно вернуть True после проверки формата поршня.
        pass

    return True


__all__ = ["validate_condition_assets"]
