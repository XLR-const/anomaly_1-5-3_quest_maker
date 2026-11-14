"""Генератор XML-графа диалогов и таблиц локализации мода.

Модуль реализует шаги ``[4] RENDER`` для двух видов файлов
(``standart_of_auto.md``, 1.1 и 2.1):

* ``gamedata/configs/gameplay/dialogs_<mod>.xml`` — весь граф диалогов;
* ``gamedata/configs/text/rus|eng/st_<mod>.xml`` — строки реплик и квестов.

Генератор намеренно не создаёт ``character_desc_*.xml``: привязка диалогов к
NPC выполняется текстовым патчером :class:`src.compiler.builder.ModBuilder`,
который копирует ванильный файл локации и вставляет ``<actor_dialog>``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.compiler.encoding import escape_xml_text
from src.core.models import (
    DontHasInfo,
    GiveInfo,
    HasInfo,
    phrase_action_mode,
)
from src.logger import get_logger

if TYPE_CHECKING:
    from src.core.models import Dialog, ModProject, Phrase

logger = get_logger("compiler.xml_gen")

#: XML-декларация, обязательная для всех игровых XML Anomaly (cp1251, без BOM).
XML_DECLARATION = '<?xml version="1.0" encoding="windows-1251"?>'
#: Корневой тег таблицы строк ``st_<mod>.xml``.
STRING_TABLE_TAG = "string_table"
#: Корневой тег файла диалогов ``dialogs_<mod>.xml``.
GAME_DIALOGS_TAG = "game_dialogs"
#: Поддерживаемые языковые каталоги ``configs/text/<lang>``.
STRING_LANGUAGES = ("rus", "eng")

#: Одна запись таблицы строк: ``(id, русский текст, английский текст)``.
StringEntry = tuple[str, str, str]


class XmlGenerator:
    """Собирает ``dialogs_<mod>.xml`` и ``st_<mod>.xml`` из моделей проекта.

    Класс не знает имени мода: имена файлов подставляет
    :class:`src.compiler.builder.ModBuilder`. Все идентификаторы диалогов
    берутся из модели (``Dialog.dialog_id`` или ``Dialog.id``), а не из ключа
    словаря, чтобы XML и ``<actor_dialog>`` всегда совпадали.
    """

    # ------------------------------------------------------------------
    # Таблицы строк
    # ------------------------------------------------------------------

    def generate_string_tables(self, project: "ModProject") -> dict[str, str]:
        """Генерирует русскую и английскую таблицы строк.

        Результат записывается генератором в
        ``gamedata/configs/text/rus/st_<mod>.xml`` и
        ``gamedata/configs/text/eng/st_<mod>.xml``.

        Args:
            project (ModProject):
                Проект с квестами и диалогами.

        Returns:
            dict[str, str]:
                Словарь ``{"rus": xml, "eng": xml}`` с готовыми XML-строками.
        """
        entries = self._collect_string_entries(project)
        return {
            lang: self._build_string_table(entries, lang)
            for lang in STRING_LANGUAGES
        }

    def _collect_string_entries(
        self, project: "ModProject"
    ) -> list[StringEntry]:
        """Собирает все строковые записи проекта в порядке генерации.

        Args:
            project (ModProject):
                Проект мода.

        Returns:
            list[StringEntry]:
                Список ``(id, текст_ru, текст_en)`` без дубликатов id.
        """
        entries: list[StringEntry] = []
        seen: set[str] = set()

        def add(entry_id: str, ru: str, en: str) -> None:
            """Добавляет запись, если такого id ещё нет.

            Args:
                entry_id (str): Идентификатор строки.
                ru (str): Русский текст.
                en (str): Английский текст.
            """
            if entry_id in seen:
                logger.warning("Дублирующийся id строки пропущен: '%s'.", entry_id)
                return
            seen.add(entry_id)
            entries.append((entry_id, ru or "", en or ""))

        for quest_id, quest in (project.quests or {}).items():
            add(f"{quest_id}_title", quest.title_ru, quest.title_en)
            add(f"{quest_id}_descr", quest.descr_ru, quest.descr_en)
            add(
                f"{quest_id}_msg_reward",
                self._quest_message(
                    quest.msg_reward_ru,
                    quest.title_ru,
                    "Задание выполнено: {title}.",
                    "Задание выполнено.",
                ),
                self._quest_message(
                    quest.msg_reward_en,
                    quest.title_en,
                    "Task completed: {title}.",
                    "Task completed.",
                ),
            )
            add(
                f"{quest_id}_msg_fail",
                self._quest_message(
                    quest.msg_fail_ru,
                    quest.title_ru,
                    "Задание провалено: {title}.",
                    "Задание провалено.",
                ),
                self._quest_message(
                    quest.msg_fail_en,
                    quest.title_en,
                    "Task failed: {title}.",
                    "Task failed.",
                ),
            )
            for stage_id, stage in sorted(quest.stages.items()):
                prefix = f"{quest_id}_stage_{stage_id}"
                add(f"{prefix}_title", stage.title_ru, stage.title_en)
                add(f"{prefix}_descr", stage.descr_ru, stage.descr_en)
                add(f"{prefix}_msg", stage.title_ru, stage.title_en)

        for dialog in (project.dialogs or {}).values():
            dialog_id = self._dialog_output_id(dialog)
            for phrase_id, phrase in sorted(dialog.phrases.items()):
                add(
                    f"{dialog_id}_phrase_{phrase_id}_text",
                    phrase.text_ru,
                    phrase.text_en,
                )
        return entries

    @staticmethod
    def _quest_message(
        custom: str | None,
        title: str,
        template: str,
        fallback: str,
    ) -> str:
        """Возвращает кастомный или сгенерированный текст PDA-подсказки.

        Args:
            custom (str | None): Значение поля ``Quest.msg_*``.
            title (str): Заголовок квеста для подстановки.
            template (str): Шаблон с ``{title}``.
            fallback (str): Текст, если заголовок пуст.

        Returns:
            str: Готовая строка ``st_<mod>.xml``.
        """
        if custom:
            return custom
        cleaned = (title or "").strip()
        return template.format(title=cleaned) if cleaned else fallback

    def _build_string_table(
        self, entries: list[StringEntry], language: str
    ) -> str:
        """Формирует один XML-документ ``st_<mod>.xml``.

        Args:
            entries (list[StringEntry]):
                Записи ``(id, ru, en)``.
            language (str):
                ``"rus"`` или ``"eng"``.

        Returns:
            str: XML-документ таблицы строк.

        Raises:
            ValueError: Если язык не входит в :data:`STRING_LANGUAGES`.
        """
        if language not in STRING_LANGUAGES:
            raise ValueError(f"Неподдерживаемый язык: {language}")
        lines = [XML_DECLARATION, f"<{STRING_TABLE_TAG}>", ""]
        for entry_id, ru, en in entries:
            text = ru if language == "rus" else en
            lines.append(f'\t<string id="{entry_id}">')
            lines.append(f"\t\t<text>{escape_xml_text(text)}</text>")
            lines.append("\t</string>")
        lines.append("")
        lines.append(f"</{STRING_TABLE_TAG}>")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # dialogs_<mod>.xml
    # ------------------------------------------------------------------

    def generate_dialogs_xml(self, dialogs: dict[str, "Dialog"]) -> str:
        """Формирует файл ``gamedata/configs/gameplay/dialogs_<mod>.xml``.

        Каждый диалог оборачивается в ``<dialog id="...">`` с обязательным
        ``<phrase_list>``; повреждённый диалог логируется и пропускается, не
        ломая остальные (стандарт, 2.1 и 4.VERIFY).

        Args:
            dialogs (dict[str, Dialog]):
                Карта диалогов проекта.

        Returns:
            str: Полный XML-документ ``<game_dialogs>``.

        Raises:
            TypeError: Если ``dialogs`` не является словарём.
        """
        if not isinstance(dialogs, dict):
            raise TypeError(
                "dialogs должен быть dict, а получен "
                f"{type(dialogs).__name__}."
            )

        blocks: list[str] = []
        for key, dialog in dialogs.items():
            try:
                blocks.append(self._build_dialog(str(key), dialog))
            except Exception as exc:  # noqa: BLE001 - изоляция одного диалога
                logger.error(
                    "Диалог '%s' пропущен: %s", key, exc, exc_info=True
                )

        lines = [XML_DECLARATION, f"<{GAME_DIALOGS_TAG}>", ""]
        for block in blocks:
            lines.append(block)
            lines.append("")
        lines.append(f"</{GAME_DIALOGS_TAG}>")
        return "\n".join(lines)

    @staticmethod
    def _dialog_output_id(dialog: "Dialog") -> str:
        """Возвращает канонический id диалога для XML и ``<actor_dialog>``.

        Args:
            dialog (Dialog): Модель диалога.

        Returns:
            str: ``dialog.dialog_id``, если он задан, иначе ``dialog.id``.

        Raises:
            ValueError: Если у диалога нет ни того, ни другого идентификатора.
        """
        dialog_id = getattr(dialog, "dialog_id", None) or getattr(
            dialog, "id", None
        )
        if not isinstance(dialog_id, str) or not dialog_id.strip():
            raise ValueError(f"Некорректный ID диалога: {dialog_id!r}")
        return dialog_id.strip()

    def _build_dialog(self, dialog_key: str, dialog: "Dialog") -> str:
        """Собирает один блок ``<dialog>``.

        Args:
            dialog_key (str): Ключ карты диалогов (для сообщений об ошибках).
            dialog (Dialog): Модель диалога.

        Returns:
            str: XML-блок диалога.

        Raises:
            TypeError: Если у диалога нет непустой карты фраз.
            ValueError: Если ключ фразы не совпадает с ``Phrase.id``.
        """
        dialog_id = self._dialog_output_id(dialog)

        phrases = getattr(dialog, "phrases", None)
        if not isinstance(phrases, dict) or not phrases:
            raise TypeError(f"Диалог '{dialog_id}' без phrases.")

        lines = [f'\t<dialog id="{dialog_id}">']

        # Уровень диалога: инфопоршни и одно Lua-условие на все прочие типы.
        # Для стартовых диалогов role="take*" Lua-условие обязательно: именно
        # _can_take блокирует повторное взятие завершённого квеста.
        info_tags, needs_condition = self._split_dialog_conditions(dialog)
        role = str(getattr(dialog, "role", "") or "").strip().lower()
        if role.startswith("take"):
            needs_condition = True

        # Диалог сдачи закрывается проверкой стадии задачи, а не поршнем из
        # on_start_actions: _can_turn_in читает tsk.stage и работает после
        # save/load даже без тика _status. Ручные не-info условия имеют
        # приоритет: тогда используется общий _can_take.
        precondition: str | None = None
        if needs_condition:
            precondition = "can_take"
        elif role in ("turnin", "turn_in") and getattr(dialog, "task_id", None):
            precondition = "can_turn_in"
        if precondition:
            lines.append(
                f"\t\t<precondition>dialogs.{dialog_id}_{precondition}"
                "</precondition>"
            )
        for tag, value in info_tags:
            lines.append(f"\t\t<{tag}>{escape_xml_text(value)}</{tag}>")

        lines.append("\t\t<phrase_list>")
        for phrase_id in sorted(phrases):
            phrase = phrases[phrase_id]
            lines.append(
                self._build_phrase(dialog_id, phrase_id, phrase)
            )
        lines.append("\t\t</phrase_list>")
        lines.append("\t</dialog>")
        return "\n".join(lines)

    @staticmethod
    def _split_dialog_conditions(
        dialog: "Dialog",
    ) -> tuple[list[tuple[str, str]], bool]:
        """Делит условия диалога на прямые info-теги и Lua-условие.

        ``HasInfo``/``DontHasInfo`` имеют штатные XML-теги (стандарт, 2.1,
        п. 5). Остальные типы условий не представимы тегами и выносятся в
        функцию ``dialogs.<dialog_id>_can_take``.

        Дополнительно для диалогов ``role="take"``/``take_*`` Lua-условие
        требуется всегда, даже если все условия заданы info-тегами: в
        ``_can_take`` генератор добавляет проверку ``complete_info``/``done_info``
        связанного квеста, чтобы закрытый квест нельзя было взять повторно.

        Args:
            dialog (Dialog): Модель диалога.

        Returns:
            tuple[list[tuple[str, str]], bool]:
                Список ``(tag, value)`` и признак необходимости Lua-условия.
        """
        tags: list[tuple[str, str]] = []
        needs_condition = False
        for condition in getattr(dialog, "preconditions", []) or []:
            if isinstance(condition, HasInfo):
                tags.append(("has_info", condition.info))
            elif isinstance(condition, DontHasInfo):
                tags.append(("dont_has_info", condition.info))
            else:
                needs_condition = True
        return tags, needs_condition

    def _build_phrase(
        self, dialog_id: str, phrase_id: Any, phrase: "Phrase"
    ) -> str:
        """Собирает один блок ``<phrase>``.

        Порядок тегов соответствует ``standart_of_auto.md`` (2.1, п. 6):
        ``<text>`` → ``<next>`` → ``<precondition>`` → info-теги →
        ``<give_info>`` → ``<action>``.

        В реплике генерируется **не более одного** ``<action>``: движок
        X-Ray/OpenXRay хранит одно действие на реплику и отбрасывает все
        последующие теги. Комбинация действий сводится к единой функции
        ``dialogs.<dialog_id>_phrase_<n>_action``.

        Args:
            dialog_id (str): Канонический id диалога.
            phrase_id (Any): Ключ фразы в карте диалога.
            phrase (Phrase): Модель реплики.

        Returns:
            str: XML-блок реплики.

        Raises:
            ValueError: Если id реплики не целый или не совпадает с ключом.
        """
        if not isinstance(phrase_id, int) or isinstance(phrase_id, bool):
            raise ValueError(
                f"Фраза диалога '{dialog_id}' имеет не-int id."
            )
        if getattr(phrase, "id", None) != phrase_id:
            raise ValueError(
                f"Ключ фразы {phrase_id} != Phrase.id="
                f"{getattr(phrase, 'id', None)}."
            )

        prefix = f"{dialog_id}_phrase_{phrase_id}"
        next_phrases = list(getattr(phrase, "next_phrases", []))
        preconditions = list(getattr(phrase, "preconditions", []))
        actions = list(getattr(phrase, "actions", []))

        lines = [f'\t\t\t<phrase id="{phrase_id}">']
        lines.append(f"\t\t\t\t<text>{prefix}_text</text>")

        for next_id in next_phrases:
            if not isinstance(next_id, int) or isinstance(next_id, bool):
                raise ValueError(
                    f"<next> фразы {phrase_id} должен быть int."
                )
            lines.append(f"\t\t\t\t<next>{next_id}</next>")

        info_tags: list[tuple[str, str]] = []
        needs_condition = False
        for condition in preconditions:
            if isinstance(condition, HasInfo):
                info_tags.append(("has_info", condition.info))
            elif isinstance(condition, DontHasInfo):
                info_tags.append(("dont_has_info", condition.info))
            else:
                needs_condition = True
        if needs_condition:
            lines.append(
                f"\t\t\t\t<precondition>dialogs.{prefix}_precondition"
                "</precondition>"
            )
        for tag, value in info_tags:
            lines.append(
                f"\t\t\t\t<{tag}>{escape_xml_text(value)}</{tag}>"
            )

        give_info = [
            action.info for action in actions if isinstance(action, GiveInfo)
        ]

        for info_id in give_info:
            lines.append(
                f"\t\t\t\t<give_info>{escape_xml_text(info_id)}</give_info>"
            )

        # Движок исполняет только первый <action>; генератор обязан
        # сгенерировать ровно один тег на реплику (см. phrase_action_mode).
        action_mode = phrase_action_mode(actions)
        if action_mode == "accept":
            lines.append(
                f"\t\t\t\t<action>dialogs.{dialog_id}_accept</action>"
            )
        elif action_mode == "turn_in":
            lines.append(
                f"\t\t\t\t<action>dialogs.{dialog_id}_turn_in</action>"
            )
        elif action_mode == "combined":
            lines.append(
                f"\t\t\t\t<action>dialogs.{prefix}_action</action>"
            )

        lines.append("\t\t\t</phrase>")
        return "\n".join(lines)


__all__ = ["XmlGenerator"]
