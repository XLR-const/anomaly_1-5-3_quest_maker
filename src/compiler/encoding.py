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


def write_file_cp1251(path: Path, content: str) -> None:
    """Записывает текст в файл в кодировке Windows-1251 без BOM.

    Перед записью автоматически создаются все отсутствующие родительские
    каталоги. Кодек ``cp1251`` не добавляет BOM, поэтому итоговый файл
    начинается непосредственно с содержимого, как того требуют игровые
    конфиги, Lua-скрипты и XML-таблицы S.T.A.L.K.E.R. Anomaly.

    Args:
        path (Path):
            Путь к создаваемому или перезаписываемому файлу.
        content (str):
            Текстовое содержимое файла. Кириллица должна быть представлена
            обычными Unicode-символами; кодирование выполняется внутри
            функции.

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
            Если ``content`` не является строкой.
    """
    logger.debug(
        "Запись файла '%s' в cp1251 (символов: %d).",
        path,
        len(content) if isinstance(content, str) else 0,
    )

    if not isinstance(content, str):
        error = TypeError(
            f"Содержимое файла '{path}' должно быть строкой, "
            f"а получено {type(content).__name__}."
        )
        logger.error("Некорректный тип содержимого: %s", error)
        raise error

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with codecs.open(
            path,
            mode="w",
            encoding="cp1251",
            errors="strict",
        ) as stream:
            stream.write(content)
    except (OSError, UnicodeError) as exc:
        logger.exception(
            "Не удалось записать файл '%s' в кодировке cp1251: %s",
            path,
            exc,
        )
        raise

    logger.info("Файл '%s' успешно сохранён в cp1251 без BOM.", path)


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


__all__ = ["escape_xml_text", "write_file_cp1251"]
