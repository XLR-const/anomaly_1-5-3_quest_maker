"""Генератор XML-диалогов и мультиязычных строковых таблиц мода.

Модуль формирует два вида игровых XML-документов S.T.A.L.K.E.R. Anomaly:

* строковые таблицы ``text/rus/st_mymod.xml`` и ``text/eng/st_mymod.xml``
  с текстами квестов, этапов и реплик;
* файл ``configs/gameplay/dialogs_mymod.xml`` с деревьями диалогов NPC.

Генератор не пишет файлы на диск: он возвращает готовые Unicode-строки,
а сохранение в Windows-1251 без BOM выполняет
:func:`src.compiler.encoding.write_file_cp1251`. Такое разделение позволяет
тестировать структуру XML без обращения к файловой системе.

Каждый квест, этап, диалог и реплика обрабатываются изолированно. Ошибка в
одном элементе журналируется и не прерывает генерацию остальных данных.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.compiler.encoding import escape_xml_text
from src.logger import get_logger

if TYPE_CHECKING:
    from src.core.models import Dialog, ModProject

logger = get_logger("compiler.xml_gen")

#: Обязательная XML-декларация игровых файлов Anomaly.
XML_DECLARATION = '<?xml version="1.0" encoding="windows-1251"?>'
#: Корневой тег мультиязычной строковой таблицы.
STRING_TABLE_TAG = "string_table"
#: Корневой тег файла диалогов.
GAME_DIALOGS_TAG = "game_dialogs"
#: Поддерживаемые языки строковых таблиц.
STRING_LANGUAGES = ("rus", "eng")

#: Запись строковой таблицы: ``(идентификатор, русский текст, английский)``.
StringEntry = tuple[str, str, str]


class XmlGenerator:
    """Собирает XML-файлы строк и диалогов из моделей проекта мода.

    Генератор рассчитан на модели :class:`~src.core.models.ModProject`,
    :class:`~src.core.models.Quest` и :class:`~src.core.models.Dialog`.
    Идентификаторы строк формируются по тем же правилам, что использует
    :class:`~src.compiler.ltx_gen.LtxGenerator`, поэтому LTX-секции и XML-тексты
    согласованы между собой.
    """

    def generate_string_tables(self, project: "ModProject") -> dict[str, str]:
        """Формирует русскую и английскую строковые таблицы проекта.

        Из проекта извлекаются все тексты квестов, их этапов и реплик
        диалогов. Для каждого элемента создаётся запись ``<string id="...">``
        с вложенным тегом ``<text>``. Русский документ содержит только
        ``*_ru``-поля, английский — только ``*_en``-поля.

        Args:
            project (ModProject):
                Корневая модель проекта с картами ``quests`` и ``dialogs``.

        Returns:
            dict[str, str]: Словарь из двух готовых XML-документов с ключами
            ``"rus"`` и ``"eng"``.

        Raises:
            TypeError:
                Если ``project`` не содержит словарных карт ``quests`` и
                ``dialogs``.
        """
        logger.debug("Начата генерация строковых таблиц проекта.")

        try:
            quests = getattr(project, "quests", None)
            dialogs = getattr(project, "dialogs", None)

            if not isinstance(quests, dict) or not isinstance(dialogs, dict):
                raise TypeError(
                    "Проект должен содержать словарные карты quests и dialogs, "
                    f"а получены {type(quests).__name__} и "
                    f"{type(dialogs).__name__}."
                )

            entries = self._collect_string_entries(project)
        except TypeError as exc:
            logger.error("Некорректный проект для генерации строк: %s", exc)
            raise
        except Exception as exc:
            logger.exception(
                "Не удалось извлечь строки проекта; будут созданы пустые "
                "таблицы: %s",
                exc,
            )
            entries = []

        result: dict[str, str] = {}

        for language in STRING_LANGUAGES:
            try:
                result[language] = self._build_string_table(entries, language)
            except Exception as exc:
                logger.exception(
                    "Не удалось сформировать строковую таблицу '%s': %s",
                    language,
                    exc,
                )
                result[language] = (
                    f"{XML_DECLARATION}\n<{STRING_TABLE_TAG}>\n"
                    f"</{STRING_TABLE_TAG}>"
                )

        logger.info(
            "Строковые таблицы сформированы: записей — %d, языков — %d.",
            len(entries),
            len(result),
        )
        return result

    def generate_dialogs_xml(self, dialogs: dict[str, "Dialog"]) -> str:
        """Формирует содержимое файла ``dialogs_mymod.xml``.

        Каждый диалог оборачивается в тег ``<dialog id="...">``, а его фразы —
        в ``<phrase id="...">``. Внутри фразы указываются ссылка на строку,
        переходы, предусловие и действие в пространстве ``mymod_quests``.

        Ошибка в отдельном диалоге журналируется через
        :meth:`logging.Logger.error`, после чего диалог пропускается, а
        остальные элементы продолжают собираться.

        Args:
            dialogs (dict[str, Dialog]):
                Карта диалогов проекта, индексированная по ``Dialog.id``.

        Returns:
            str: Полный XML-документ с корневым тегом ``<game_dialogs>``.

        Raises:
            TypeError:
                Если ``dialogs`` не является словарём.
        """
        logger.debug("Начата генерация dialogs_mymod.xml.")

        try:
            if not isinstance(dialogs, dict):
                raise TypeError(
                    "Аргумент dialogs должен быть словарём карты диалогов, "
                    f"а получен {type(dialogs).__name__}."
                )
        except TypeError as exc:
            logger.error("Некорректная карта диалогов: %s", exc)
            raise

        blocks: list[str] = []
        skipped = 0

        for dialog_id, dialog in dialogs.items():
            try:
                blocks.append(self._build_dialog(dialog_id, dialog))
            except Exception as exc:
                skipped += 1
                logger.error(
                    "Диалог '%s' пропущен из-за ошибки данных: %s",
                    dialog_id,
                    exc,
                    exc_info=True,
                )
                continue

            logger.debug("Диалог '%s' добавлен в XML.", dialog_id)

        lines = [XML_DECLARATION, f"<{GAME_DIALOGS_TAG}>"]
        lines.extend(blocks)
        lines.append(f"</{GAME_DIALOGS_TAG}>")
        content = "\n".join(lines)

        logger.info(
            "Сформирован dialogs_mymod.xml: диалогов — %d, пропущено — %d.",
            len(blocks),
            skipped,
        )
        return content

    def _collect_string_entries(self, project: "ModProject") -> list[StringEntry]:
        """Извлекает двуязычные строки из всех квестов и диалогов проекта.

        Ошибка в одном квесте, этапе, диалоге или реплике не прерывает обход:
        проблемный элемент пропускается и журналируется.

        Args:
            project (ModProject):
                Проверяемый проект мода.

        Returns:
            list[StringEntry]: Список троек ``(id, text_ru, text_en)`` в
            порядке квестов, этапов и диалогов проекта.

        Raises:
            TypeError:
                Если карты ``quests`` или ``dialogs`` не являются словарями.
        """
        logger.debug("Извлечение строк квестов и диалогов проекта.")

        try:
            quests = getattr(project, "quests", None)
            dialogs = getattr(project, "dialogs", None)

            if not isinstance(quests, dict) or not isinstance(dialogs, dict):
                raise TypeError(
                    "Карты quests и dialogs проекта должны быть словарями."
                )

            entries: list[StringEntry] = []

            for quest_id, quest in quests.items():
                try:
                    entries.extend(self._collect_quest_strings(quest_id, quest))
                except Exception as exc:
                    logger.error(
                        "Квест '%s' пропущен при сборе строк: %s",
                        quest_id,
                        exc,
                        exc_info=True,
                    )

            for dialog_id, dialog in dialogs.items():
                try:
                    entries.extend(self._collect_dialog_strings(dialog_id, dialog))
                except Exception as exc:
                    logger.error(
                        "Диалог '%s' пропущен при сборе строк: %s",
                        dialog_id,
                        exc,
                        exc_info=True,
                    )

            logger.debug("Извлечено строковых записей: %d.", len(entries))
            return entries
        except Exception as exc:
            logger.exception("Не удалось собрать строковые записи: %s", exc)
            raise

    def _collect_quest_strings(
        self,
        quest_id: Any,
        quest: Any,
    ) -> list[StringEntry]:
        """Собирает строки названия и описания квеста вместе с этапами.

        Args:
            quest_id (Any):
                Ключ карты квестов; должен совпадать с ``Quest.id``.
            quest (Any):
                Модель квеста или повреждённый объект с ожидаемыми полями.

        Returns:
            list[StringEntry]: Строки ``{quest_id}_title``, ``{quest_id}_descr``
            и строки всех корректных этапов.

        Raises:
            ValueError:
                Если идентификатор квеста некорректен или не совпадает с
                ``Quest.id``.
            TypeError:
                Если обязательные текстовые поля отсутствуют или имеют
                неверный тип.
        """
        try:
            self._validate_identifier(quest_id, "квеста")

            actual_id = getattr(quest, "id", None)
            if actual_id != quest_id:
                raise ValueError(
                    f"Ключ карты '{quest_id}' не совпадает с Quest.id="
                    f"'{actual_id}'."
                )

            title_ru = getattr(quest, "title_ru", None)
            title_en = getattr(quest, "title_en", None)
            descr_ru = getattr(quest, "descr_ru", None)
            descr_en = getattr(quest, "descr_en", None)

            if not all(
                isinstance(value, str)
                for value in (title_ru, title_en, descr_ru, descr_en)
            ):
                raise TypeError(
                    f"Квест '{quest_id}' содержит нестроковые title/descr."
                )

            entries: list[StringEntry] = [
                (f"{quest_id}_title", title_ru, title_en),
                (f"{quest_id}_descr", descr_ru, descr_en),
            ]

            stages = getattr(quest, "stages", None)
            if not isinstance(stages, dict):
                raise TypeError(
                    f"Квест '{quest_id}' содержит нестроковую карту stages."
                )

            try:
                ordered_stages = sorted(stages.items())
            except TypeError as exc:
                raise TypeError(
                    f"Ключи этапов квеста '{quest_id}' не поддаются сортировке."
                ) from exc

            for stage_id, stage in ordered_stages:
                try:
                    entries.extend(
                        self._collect_stage_strings(quest_id, stage_id, stage)
                    )
                except Exception as exc:
                    logger.error(
                        "Этап '%s' квеста '%s' пропущен при сборе строк: %s",
                        stage_id,
                        quest_id,
                        exc,
                        exc_info=True,
                    )

            logger.debug(
                "Квест '%s': собрано строк — %d.",
                quest_id,
                len(entries),
            )
            return entries
        except Exception as exc:
            logger.exception(
                "Не удалось собрать строки квеста '%s': %s",
                quest_id,
                exc,
            )
            raise

    def _collect_stage_strings(
        self,
        quest_id: str,
        stage_id: Any,
        stage: Any,
    ) -> list[StringEntry]:
        """Собирает строки названия и описания одного этапа квеста.

        Args:
            quest_id (str):
                Идентификатор родительского квеста.
            stage_id (Any):
                Ключ карты этапов; должен совпадать с ``Stage.id``.
            stage (Any):
                Модель этапа или повреждённый объект с ожидаемыми полями.

        Returns:
            list[StringEntry]: Две строки этапа — title и descr.

        Raises:
            ValueError:
                Если номер этапа некорректен или не совпадает с ``Stage.id``.
            TypeError:
                Если текстовые поля этапа отсутствуют или не являются
                строками.
        """
        try:
            if not isinstance(stage_id, int) or isinstance(stage_id, bool):
                raise ValueError(
                    f"Номер этапа квеста '{quest_id}' должен быть целым числом, "
                    f"а получен {type(stage_id).__name__}."
                )

            if stage_id < 0:
                raise ValueError(
                    f"Номер этапа квеста '{quest_id}' не может быть "
                    f"отрицательным: {stage_id}."
                )

            actual_id = getattr(stage, "id", None)
            if actual_id != stage_id:
                raise ValueError(
                    f"Ключ этапа {stage_id} квеста '{quest_id}' не совпадает "
                    f"с Stage.id='{actual_id}'."
                )

            title_ru = getattr(stage, "title_ru", None)
            title_en = getattr(stage, "title_en", None)
            descr_ru = getattr(stage, "descr_ru", None)
            descr_en = getattr(stage, "descr_en", None)

            if not all(
                isinstance(value, str)
                for value in (title_ru, title_en, descr_ru, descr_en)
            ):
                raise TypeError(
                    f"Этап '{stage_id}' квеста '{quest_id}' содержит "
                    "нестроковые title/descr."
                )

            prefix = f"{quest_id}_stage_{stage_id}"
            logger.debug(
                "Этап '%s' квеста '%s' подготовлен к экспорту.",
                stage_id,
                quest_id,
            )
            return [
                (f"{prefix}_title", title_ru, title_en),
                (f"{prefix}_descr", descr_ru, descr_en),
            ]
        except Exception as exc:
            logger.error(
                "Ошибка данных этапа '%s' квеста '%s': %s",
                stage_id,
                quest_id,
                exc,
            )
            raise

    def _collect_dialog_strings(
        self,
        dialog_id: Any,
        dialog: Any,
    ) -> list[StringEntry]:
        """Собирает строки всех реплик одного диалога.

        Args:
            dialog_id (Any):
                Ключ карты диалогов; должен совпадать с ``Dialog.id``.
            dialog (Any):
                Модель диалога или повреждённый объект с ожидаемыми полями.

        Returns:
            list[StringEntry]: Строки ``{dialog_id}_phrase_{id}_text`` для
            каждой корректной реплики.

        Raises:
            ValueError:
                Если идентификатор диалога некорректен или не совпадает с
                ``Dialog.id``.
            TypeError:
                Если карта фраз отсутствует или имеет неверный тип.
        """
        try:
            self._validate_identifier(dialog_id, "диалога")

            actual_id = getattr(dialog, "id", None)
            if actual_id != dialog_id:
                raise ValueError(
                    f"Ключ карты '{dialog_id}' не совпадает с Dialog.id="
                    f"'{actual_id}'."
                )

            phrases = getattr(dialog, "phrases", None)
            if not isinstance(phrases, dict):
                raise TypeError(
                    f"Диалог '{dialog_id}' содержит нестроковую карту phrases."
                )

            try:
                ordered_phrases = sorted(phrases.items())
            except TypeError as exc:
                raise TypeError(
                    f"Ключи фраз диалога '{dialog_id}' не поддаются "
                    "сортировке."
                ) from exc

            entries: list[StringEntry] = []

            for phrase_id, phrase in ordered_phrases:
                try:
                    text_ru = getattr(phrase, "text_ru", None)
                    text_en = getattr(phrase, "text_en", None)

                    if not isinstance(text_ru, str) or not isinstance(
                        text_en, str
                    ):
                        raise TypeError(
                            f"Фраза '{phrase_id}' диалога '{dialog_id}' "
                            "содержит нестроковый текст."
                        )

                    self._validate_phrase_identity(dialog_id, phrase_id, phrase)
                    entries.append(
                        (
                            f"{dialog_id}_phrase_{phrase_id}_text",
                            text_ru,
                            text_en,
                        )
                    )
                except Exception as exc:
                    logger.error(
                        "Фраза '%s' диалога '%s' пропущена при сборе строк: %s",
                        phrase_id,
                        dialog_id,
                        exc,
                        exc_info=True,
                    )

            logger.debug(
                "Диалог '%s': собрано строк — %d.",
                dialog_id,
                len(entries),
            )
            return entries
        except Exception as exc:
            logger.exception(
                "Не удалось собрать строки диалога '%s': %s",
                dialog_id,
                exc,
            )
            raise

    def _build_string_table(
        self,
        entries: list[StringEntry],
        language: str,
    ) -> str:
        """Формирует один XML-документ строковой таблицы для языка.

        Args:
            entries (list[StringEntry]):
                Двуязычные записи, подготовленные сборщиком строк.
            language (str):
                Язык документа: ``"rus"`` или ``"eng"``.

        Returns:
            str: XML-документ с декларацией Windows-1251 и корневым тегом
            ``<string_table>``.

        Raises:
            ValueError:
                Если язык не поддерживается или идентификатор записи
                некорректен.
            TypeError:
                Если запись имеет неверный формат или текст не является
                строкой.
        """
        logger.debug(
            "Формирование строковой таблицы '%s' (записей: %d).",
            language,
            len(entries),
        )

        try:
            if language not in STRING_LANGUAGES:
                raise ValueError(
                    f"Неподдерживаемый язык строковой таблицы: '{language}'."
                )

            lines = [XML_DECLARATION, f"<{STRING_TABLE_TAG}>"]

            for entry in entries:
                if not isinstance(entry, tuple) or len(entry) != 3:
                    raise TypeError(
                        "Запись строковой таблицы должна быть тройкой "
                        f"(id, text_ru, text_en), а получена {entry!r}."
                    )

                entry_id, text_ru, text_en = entry
                self._validate_identifier(entry_id, "строковой записи")

                text = text_ru if language == "rus" else text_en
                if not isinstance(text, str):
                    raise TypeError(
                        f"Текст записи '{entry_id}' должен быть строкой, "
                        f"а получен {type(text).__name__}."
                    )

                lines.append(f'<string id="{entry_id}">')
                lines.append(f"<text>{escape_xml_text(text)}</text>")
                lines.append("</string>")

            lines.append(f"</{STRING_TABLE_TAG}>")
            content = "\n".join(lines)

            logger.debug(
                "Строковая таблица '%s' сформирована: символов — %d.",
                language,
                len(content),
            )
            return content
        except Exception as exc:
            logger.exception(
                "Не удалось сформировать строковую таблицу '%s': %s",
                language,
                exc,
            )
            raise

    def _build_dialog(self, dialog_id: Any, dialog: Any) -> str:
        """Собирает XML-блок одного диалога.

        Args:
            dialog_id (Any):
                Ключ карты диалогов; должен совпадать с ``Dialog.id``.
            dialog (Any):
                Модель диалога или повреждённый объект с ожидаемыми полями.

        Returns:
            str: Блок ``<dialog>`` без XML-декларации и корневого тега.

        Raises:
            ValueError:
                Если идентификатор диалога некорректен или не совпадает с
                ``Dialog.id``.
            TypeError:
                Если карта фраз отсутствует, пуста или имеет неверный тип.
        """
        try:
            self._validate_identifier(dialog_id, "диалога")

            actual_id = getattr(dialog, "id", None)
            if actual_id != dialog_id:
                raise ValueError(
                    f"Ключ карты '{dialog_id}' не совпадает с Dialog.id="
                    f"'{actual_id}'."
                )

            phrases = getattr(dialog, "phrases", None)
            if not isinstance(phrases, dict) or not phrases:
                raise TypeError(
                    f"Диалог '{dialog_id}' должен содержать непустую карту "
                    "phrases."
                )

            try:
                ordered_phrases = sorted(phrases.items())
            except TypeError as exc:
                raise TypeError(
                    f"Ключи фраз диалога '{dialog_id}' не поддаются "
                    "сортировке."
                ) from exc

            lines = [f'<dialog id="{dialog_id}">']

            for phrase_id, phrase in ordered_phrases:
                lines.append(
                    self._build_phrase(dialog_id, phrase_id, phrase)
                )

            lines.append("</dialog>")
            block = "\n".join(lines)

            logger.debug(
                "Диалог '%s' собран: фраз — %d.",
                dialog_id,
                len(ordered_phrases),
            )
            return block
        except Exception as exc:
            logger.error(
                "Не удалось собрать диалог '%s': %s",
                dialog_id,
                exc,
                exc_info=True,
            )
            raise

    def _build_phrase(
        self,
        dialog_id: str,
        phrase_id: Any,
        phrase: Any,
    ) -> str:
        """Собирает XML-блок одной фразы диалога.

        Args:
            dialog_id (str):
                Идентификатор родительского диалога.
            phrase_id (Any):
                Ключ карты фраз; должен совпадать с ``Phrase.id``.
            phrase (Any):
                Модель реплики или повреждённый объект с ожидаемыми полями.

        Returns:
            str: Блок ``<phrase>`` со ссылкой на текст, переходами,
            предусловием и действием.

        Raises:
            ValueError:
                Если номер фразы или номер перехода некорректен.
            TypeError:
                Если ``next_phrases``, ``preconditions`` или ``actions``
                отсутствуют либо имеют неверный тип.
        """
        try:
            self._validate_phrase_identity(dialog_id, phrase_id, phrase)

            next_phrases = getattr(phrase, "next_phrases", None)
            preconditions = getattr(phrase, "preconditions", None)
            actions = getattr(phrase, "actions", None)

            if not isinstance(next_phrases, list):
                raise TypeError(
                    f"Фраза '{phrase_id}' диалога '{dialog_id}' содержит "
                    "нестроковый список next_phrases."
                )

            if not isinstance(preconditions, list):
                raise TypeError(
                    f"Фраза '{phrase_id}' диалога '{dialog_id}' содержит "
                    "нестроковый список preconditions."
                )

            if not isinstance(actions, list):
                raise TypeError(
                    f"Фраза '{phrase_id}' диалога '{dialog_id}' содержит "
                    "нестроковый список actions."
                )

            prefix = f"mymod_quests.{dialog_id}_phrase_{phrase_id}"
            lines = [
                f'<phrase id="{phrase_id}">',
                f"<text>{dialog_id}_phrase_{phrase_id}_text</text>",
            ]

            for next_id in next_phrases:
                if not isinstance(next_id, int) or isinstance(next_id, bool):
                    raise ValueError(
                        f"Переход фразы '{phrase_id}' диалога '{dialog_id}' "
                        f"должен быть целым числом, а получен "
                        f"{type(next_id).__name__}."
                    )

                if next_id < 0:
                    raise ValueError(
                        f"Переход фразы '{phrase_id}' диалога '{dialog_id}' "
                        f"не может быть отрицательным: {next_id}."
                    )

                lines.append(f'<next id="{next_id}"/>')

            if preconditions:
                lines.append(f"<precondition>{prefix}_precondition</precondition>")

            if actions:
                lines.append(f"<action>{prefix}_action</action>")

            lines.append("</phrase>")
            logger.debug(
                "Фраза '%s' диалога '%s' собрана: переходов — %d.",
                phrase_id,
                dialog_id,
                len(next_phrases),
            )
            return "\n".join(lines)
        except Exception as exc:
            logger.error(
                "Не удалось собрать фразу '%s' диалога '%s': %s",
                phrase_id,
                dialog_id,
                exc,
                exc_info=True,
            )
            raise

    def _validate_phrase_identity(
        self,
        dialog_id: str,
        phrase_id: Any,
        phrase: Any,
    ) -> None:
        """Проверяет корректность номера фразы и его совпадение с моделью.

        Args:
            dialog_id (str):
                Идентификатор родительского диалога для сообщений об ошибках.
            phrase_id (Any):
                Ключ карты фраз.
            phrase (Any):
                Модель реплики или повреждённый объект.

        Returns:
            None: Функция ничего не возвращает.

        Raises:
            ValueError:
                Если номер фразы не является неотрицательным целым или не
                совпадает с ``Phrase.id``.
        """
        try:
            if not isinstance(phrase_id, int) or isinstance(phrase_id, bool):
                raise ValueError(
                    f"Номер фразы диалога '{dialog_id}' должен быть целым "
                    f"числом, а получен {type(phrase_id).__name__}."
                )

            if phrase_id < 0:
                raise ValueError(
                    f"Номер фразы диалога '{dialog_id}' не может быть "
                    f"отрицательным: {phrase_id}."
                )

            actual_id = getattr(phrase, "id", None)
            if actual_id != phrase_id:
                raise ValueError(
                    f"Ключ фразы {phrase_id} диалога '{dialog_id}' не "
                    f"совпадает с Phrase.id='{actual_id}'."
                )

            logger.debug(
                "Фраза '%s' диалога '%s' прошла проверку идентификатора.",
                phrase_id,
                dialog_id,
            )
        except Exception as exc:
            logger.error(
                "Ошибка идентификатора фразы '%s' диалога '%s': %s",
                phrase_id,
                dialog_id,
                exc,
            )
            raise

    def _validate_identifier(self, value: Any, entity: str) -> str:
        """Проверяет пригодность идентификатора для XML-разметки.

        Идентификаторы попадают в атрибуты ``id`` и в имена строковых тегов,
        поэтому они не должны быть пустыми, содержать пробельные символы или
        символы, ломающие XML.

        Args:
            value (Any):
                Проверяемое значение идентификатора.
            entity (str):
                Человекочитаемое название сущности для сообщения об ошибке.

        Returns:
            str: Исходный идентификатор, если проверка прошла успешно.

        Raises:
            ValueError:
                Если значение пустое, не является строкой, содержит пробелы
                или запрещённые символы ``<>"'&``.
        """
        try:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Идентификатор {entity} должен быть непустой строкой, "
                    f"а получен {value!r}."
                )

            if any(character.isspace() for character in value):
                raise ValueError(
                    f"Идентификатор {entity} '{value}' не должен содержать "
                    "пробельных символов."
                )

            forbidden = set('<>"\'&')
            if any(character in forbidden for character in value):
                raise ValueError(
                    f"Идентификатор {entity} '{value}' содержит символы, "
                    "недопустимые в XML."
                )

            logger.debug("Идентификатор %s '%s' корректен.", entity, value)
            return value
        except Exception as exc:
            logger.error(
                "Некорректный идентификатор %s '%s': %s",
                entity,
                value,
                exc,
            )
            raise


__all__ = ["XmlGenerator"]
