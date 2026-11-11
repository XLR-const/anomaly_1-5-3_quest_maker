"""Безопасный ввод-вывод и экранирование для компилятора мода.

Модуль инкапсулирует две низкоуровневые операции, общие для всех генераторов
игровых файлов:

* запись текста в кодировке ``windows-1251`` без BOM с автоматическим
  созданием родительских каталогов;
* экранирование специальных символов XML, чтобы русский и английский текст
  реплик не нарушал структуру игровых ``*.xml``-файлов.

Все ошибки журналируются через общий логгер проекта и пробрасываются
вызывающему коду, чтобы сбой записи не оставался незамеченным.
"""

from __future__ import annotations

import codecs
from pathlib import Path

from src.logger import get_logger

logger = get_logger("compiler.encoding")


def write_file_cp1251(
    path: Path,
    content: str,
    *,
    bom: bool = False,
) -> None:
    """Записывает текст в файл в кодировке Windows-1251.

    Все сгенерированные файлы (``tm_<mod>.ltx``, ``dialogs_<mod>.xml``,
    ``st_<mod>.xml`` и ``<mod>_quests.script``) пишутся **без BOM**, как
    требует ``standart_of_auto.md`` (1.3 и 2.1). Патченные копии ванильных
    конфигов (``system.ltx`` и ``character_desc_<level>.xml``) наследуют
    исходный BOM, поэтому для них ``bom=True``: без этого движок X-Ray
    может прочитать первый ключ/тег как часть имени.

    Args:
        path (Path):
            Путь к создаваемому или перезаписываемому файлу. Родительские
            каталоги создаются автоматически.
        content (str):
            Текстовое содержимое файла. Кириллица передаётся обычными
            Unicode-символами; кодирование выполняется внутри функции.
        bom (bool):
            Если ``True``, перед байтами cp1251 записывается BOM
            ``EF BB BF``. Используется только для патченных ванильных
            файлов, где BOM уже был.

    Returns:
        None: Функция ничего не возвращает.

    Raises:
        OSError:
            Если не удалось создать родительские каталоги или открыть файл
            для записи.
        UnicodeEncodeError:
            Если в строке есть символы, которые невозможно представить в
            Windows-1251.
        TypeError:
            Если ``content`` не является строкой или ``bom`` не является
            ``bool``.
    """
    logger.debug(
        "Запись файла '%s' в cp1251 (символов: %d, BOM=%s).",
        path,
        len(content) if isinstance(content, str) else 0,
        bom,
    )

    if not isinstance(content, str):
        error = TypeError(
            f"Содержимое файла '{path}' должно быть строкой, "
            f"а получено {type(content).__name__}."
        )
        logger.error("Некорректный тип содержимого: %s", error)
        raise error
    if not isinstance(bom, bool):
        raise TypeError(
            "Аргумент bom должен быть bool, "
            f"а получен {type(bom).__name__}."
        )

    try:
        payload = content.encode("cp1251", errors="strict")
        if bom:
            payload = codecs.BOM_UTF8 + payload
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    except (OSError, UnicodeError) as exc:
        logger.exception(
            "Не удалось записать файл '%s' в кодировке cp1251: %s",
            path,
            exc,
        )
        raise

    logger.info(
        "Файл '%s' успешно сохранён в cp1251 (BOM=%s).", path, bom
    )


def read_file_cp1251(path: Path) -> tuple[str, bool]:
    """Читает ванильный конфиг cp1251, отделяя и сохраняя признак BOM.

    Патчер ``system.ltx`` и ``character_desc_<level>.xml`` обязан вернуть
    файл с тем же BOM, который был в исходнике (``standart_of_auto.md``,
    1.2 и 1.3). Декодирование выполняется по байтам, без ``utf-8-sig`` и
    без автоматического удаления BOM кодеком.

    Args:
        path (Path):
            Путь к ванильному файлу в ``_unpacked/configs``.

    Returns:
        tuple[str, bool]:
            Декодированный текст без BOM и флаг ``has_bom``.

    Raises:
        OSError: Если файл не удалось прочитать.
        UnicodeDecodeError: Если байты не являются корректным cp1251.
    """
    raw = Path(path).read_bytes()
    has_bom = raw.startswith(codecs.BOM_UTF8)
    if has_bom:
        raw = raw[len(codecs.BOM_UTF8) :]
    return raw.decode("cp1251"), has_bom


def escape_xml_text(text: str) -> str:
    """Экранирует специальные символы для безопасной вставки в XML.

    Заменяются пять символов, которые могут нарушить разметку XML или
    изменить смысл текстового узла:

    * ``&`` -> ``&amp;``;
    * ``<`` -> ``&lt;``;
    * ``>`` -> ``&gt;``;
    * ``"`` -> ``&quot;``;
    * ``'`` -> ``&apos;``.

    Амперсанд заменяется первым, поэтому уже вставленные сущности не
    экранируются повторно.

    Args:
        text (str):
            Исходный текст реплики или описания.

    Returns:
        str: Текст, пригодный для вставки в XML-документ.

    Raises:
        TypeError:
            Если ``text`` не является строкой.

    Examples:
        >>> escape_xml_text('Сталкер & "Проводник"')
        'Сталкер &amp; &quot;Проводник&quot;'
    """
    logger.debug(
        "Экранирование XML-текста длиной %d символов.",
        len(text) if isinstance(text, str) else 0,
    )

    try:
        if not isinstance(text, str):
            raise TypeError(
                "Аргумент text должен быть строкой, "
                f"а получен {type(text).__name__}."
            )

        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
    except Exception as exc:
        logger.exception("Не удалось экранировать XML-текст: %s", exc)
        raise

    logger.debug(
        "XML-текст экранирован: %d -> %d символов.",
        len(text),
        len(escaped),
    )
    return escaped


__all__ = ["escape_xml_text", "read_file_cp1251", "write_file_cp1251"]
