"""Генератор конфигов кастомных NPC и резолвер ванильных шаблонов.

Модуль изолирован от ``builder.py`` и ``lua_gen.py``: он только формирует
тексты/байты артефактов и идемпотентные патчи. Интеграция в сборочный
конвейер выполняется в следующей итерации.

Артефакты (``docs/CUSTOM_ENTITIES_SPEC.md``, §4):

* ``creatures/spawn_sections_<slug>.ltx`` — spawn-секции и, при
  необходимости, секция иммунитетов;
* ``gameplay/npc_profile_<slug>.xml`` — реестр ``<character>`` (UTF-8);
* ``gameplay/character_desc_<slug>.xml`` — ``<specific_character>``
  (windows-1251).

Резолвер ``template_npc_id`` открывает **ровно один** файл
``<vanilla_root>/configs/gameplay/<source_file>``; ``source_file`` берётся
только из колонки ``npcs.source_file`` базы ``anomaly_db.sqlite``.
Сканирование ``_unpacked/`` запрещено спецификацией (§3.2, CAT-CUSTOM-011).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree

from src.compiler.encoding import escape_xml_text
from src.core.models import CustomNpc, ModProject

if TYPE_CHECKING:
    from src.db.repository import GameDatabase

#: XML-декларация ``character_desc_<slug>.xml`` (windows-1251).
CHARACTER_DESC_DECLARATION = (
    '<?xml version="1.0" encoding="windows-1251"?>'
)
#: XML-декларация ``npc_profile_<slug>.xml`` (UTF-8).
NPC_PROFILE_DECLARATION = '<?xml version="1.0" encoding="utf-8"?>'
#: Корневой тег обоих XML-файлов Anomaly.
XML_ROOT_TAG = "xml"

#: Полный набор полей секции иммунитетов (9 + ``wound_2_immunity``).
IMMUNITY_FIELDS = (
    "burn_immunity",
    "strike_immunity",
    "shock_immunity",
    "wound_immunity",
    "radiation_immunity",
    "telepatic_immunity",
    "chemical_burn_immunity",
    "explosion_immunity",
    "fire_wound_immunity",
    "wound_2_immunity",
)

#: Ширина выравнивания ключей LTX.
_LTX_KEY_WIDTH = 26
#: Теги, которые разрешено копировать из ванильного шаблона (§3.2).
_TEMPLATE_TAGS = (
    "visual",
    "icon",
    "bio",
    "rank",
    "reputation",
    "money",
    "supplies",
)
_XML_DECLARATION_RE = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _mod_slug(project: ModProject) -> str:
    """Возвращает slug мода для имён артефактов.

    Args:
        project (ModProject): Проект мода.

    Returns:
        str: ``mod_slug`` из extra-полей либо slug, построенный из ``name``.
    """
    slug = getattr(project, "mod_slug", None)
    cleaned = str(slug).strip() if slug else ""
    if cleaned:
        return cleaned
    name = str(getattr(project, "name", "") or "mod").lower()
    generated = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return generated or "mod"


def _character_profile(npc: CustomNpc) -> str:
    """Возвращает ``character_profile`` NPC (по умолчанию ``id``).

    Args:
        npc (CustomNpc): Модель NPC.

    Returns:
        str: Непустой профиль для spawn-секции и XML.
    """
    return npc.character_profile or npc.id


def _template_for(
    npc: CustomNpc, resolved_templates: dict[str, Any] | None
) -> dict[str, Any]:
    """Находит разобранный шаблон NPC по id профиля или template id.

    Args:
        npc (CustomNpc): Модель NPC.
        resolved_templates (dict[str, Any] | None): Результат
            :func:`resolve_npc_template` по нескольким NPC либо один словарь
            тегов.

    Returns:
        dict[str, Any]: Теги шаблона; пустой словарь, если шаблона нет.
    """
    if not resolved_templates:
        return {}
    if all(
        key not in _TEMPLATE_TAGS and key != "supplies_text"
        for key in resolved_templates
    ):
        candidate_keys = (
            npc.id,
            _character_profile(npc),
            npc.template_npc_id or "",
        )
        for key in candidate_keys:
            value = resolved_templates.get(key)
            if isinstance(value, dict):
                return value
        return {}
    return resolved_templates


def _as_int(value: Any, default: int = 0) -> int:
    """Приводит значение XML-тега к ``int`` без исключений.

    Args:
        value (Any): Сырое значение.
        default (int): Значение при ошибке разбора.

    Returns:
        int: Разобранное число или ``default``.
    """
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _xml_text(value: Any) -> str:
    """Экранирует текст для игрового XML.

    Args:
        value (Any): Сырое значение.

    Returns:
        str: Экранированная строка (``&``, ``<``, ``>``).
    """
    return escape_xml_text("" if value is None else str(value))


def _xml_attribute(value: Any) -> str:
    """Экранирует значение XML-атрибута.

    Args:
        value (Any): Сырое значение.

    Returns:
        str: Экранированная строка, пригодная для двойных кавычек.
    """
    return escape_xml_text("" if value is None else str(value)).replace(
        '"', "&quot;"
    )


# ---------------------------------------------------------------------------
# Резолвер ванильного шаблона
# ---------------------------------------------------------------------------


def _query_source_file(
    db: "GameDatabase", table: str, entity_id: str
) -> str | None:
    """Возвращает ``source_file`` строки БД точечным запросом.

    Args:
        db (GameDatabase): Открытая база ассетов.
        table (str): ``npcs`` или ``squads`` (только доверенные литералы).
        entity_id (str): Значение колонки ``id``.

    Returns:
        str | None: Имя XML/LTX-файла без пути или ``None``.

    Raises:
        ValueError: Если таблица не поддерживается.
    """
    if table not in ("npcs", "squads"):
        raise ValueError(f"Неподдерживаемая таблица БД: {table!r}.")
    sql = f"SELECT source_file FROM {table} WHERE id = ? LIMIT 1"

    query = getattr(db, "_query", None)
    if callable(query):
        rows = query(sql, (entity_id,))
    else:
        cursor = db.conn.cursor()
        try:
            cursor.execute(sql, (entity_id,))
            rows = cursor.fetchall()
        finally:
            cursor.close()

    if not rows:
        return None
    row = rows[0]
    try:
        value = row["source_file"]
    except (KeyError, IndexError, TypeError):
        value = dict(row).get("source_file") if row else None
    cleaned = str(value).strip() if value else ""
    return cleaned or None


def resolve_npc_template(
    npc: CustomNpc,
    db: "GameDatabase | None",
    vanilla_root: Path | None,
) -> dict[str, Any]:
    """Извлекает разрешённые теги ванильного ``<specific_character>``.

    Выполняется **один** запрос ``SELECT source_file FROM npcs WHERE id=?``,
    затем читается **ровно один** файл
    ``<vanilla_root>/configs/gameplay/<source_file>`` в windows-1251.

    Копируются только теги §3.2: ``visual``, ``icon``, ``bio``, ``rank``,
    ``reputation``, ``money``, ``supplies``.

    Args:
        npc (CustomNpc): Кастомный NPC с заполненным ``template_npc_id``.
        db (GameDatabase | None): База ассетов Anomaly.
        vanilla_root (Path | None): Корень распакованной ванильной игры.

    Returns:
        dict[str, Any]: Теги шаблона. ``money`` — словарь ``min/max/
        infinitive``, ``supplies`` — список непустых строк,
        ``supplies_text`` — исходный текст тега.

    Raises:
        ValueError: Если шаблон не задан/не найден в БД, нет
            ``vanilla_root``/файла или в файле отсутствует
            ``<specific_character id="...">`` (CAT-CUSTOM-011).
    """
    template_id = (npc.template_npc_id or "").strip()
    if not template_id:
        raise ValueError(
            f"NPC '{npc.id}': template_npc_id не задан — резолвер вызван "
            "для NPC без шаблона."
        )
    if db is None:
        raise ValueError(
            f"NPC '{npc.id}': для template_npc_id '{template_id}' требуется "
            "база anomaly_db.sqlite."
        )
    if vanilla_root is None:
        raise ValueError(
            f"NPC '{npc.id}': для чтения шаблона '{template_id}' требуется "
            "vanilla_root."
        )

    source_file = _query_source_file(db, "npcs", template_id)
    if not source_file:
        raise ValueError(
            f"NPC '{npc.id}': template_npc_id '{template_id}' не найден в "
            "таблице npcs БД (CAT-CUSTOM-011)."
        )

    template_path = Path(vanilla_root) / "configs" / "gameplay" / source_file
    if not template_path.is_file():
        # В anomaly_db.sqlite source_file иногда хранится как
        # ``gameplay\character_desc_escape.xml``. Такой путь уже содержит
        # каталог относительно configs.
        relative = Path(str(source_file).replace("\\", "/"))
        if len(relative.parts) > 1:
            candidate = Path(vanilla_root) / "configs" / relative
            if candidate.is_file():
                template_path = candidate
    if not template_path.is_file():
        raise ValueError(
            f"NPC '{npc.id}': файл шаблона не найден: {template_path} "
            "(CAT-CUSTOM-011)."
        )

    raw_bytes = template_path.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raw_bytes = raw_bytes[3:]
    raw_text = raw_bytes.decode(
        "windows-1251", errors="replace"
    )
    xml_text = _XML_DECLARATION_RE.sub("", raw_text, count=1).lstrip()
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise ValueError(
            f"NPC '{npc.id}': не удалось разобрать шаблон "
            f"'{template_path}': {exc}."
        ) from exc

    specific: ElementTree.Element | None = None
    for candidate in root.iter("specific_character"):
        if (candidate.get("id") or "").strip() == template_id:
            specific = candidate
            break
    if specific is None:
        raise ValueError(
            f"NPC '{npc.id}': в '{template_path}' отсутствует "
            f"<specific_character id=\"{template_id}\"> (CAT-CUSTOM-011)."
        )

    def child_text(tag: str) -> str | None:
        """Возвращает текст первого дочернего тега ``tag``.

        Args:
            tag (str): Имя тега.

        Returns:
            str | None: Очищенный текст или ``None``.
        """
        child = specific.find(tag)
        if child is None:
            return None
        text = "".join(child.itertext()).strip()
        return text or None

    money_element = specific.find("money")
    money: dict[str, Any] | None = None
    if money_element is not None:
        money = {
            "min": _as_int(money_element.get("min"), 0),
            "max": _as_int(money_element.get("max"), 0),
            "infinitive": str(money_element.get("infinitive", "")).strip()
            in ("1", "true", "True"),
        }

    supplies_text = child_text("supplies")
    supplies = (
        [
            line.strip()
            for line in supplies_text.splitlines()
            if line.strip()
        ]
        if supplies_text
        else []
    )

    common_actor_dialogs: list[str] = []
    for element in specific.findall("actor_dialog"):
        dialog_id = "".join(element.itertext()).strip()
        if dialog_id.startswith("dm_ordered_task_"):
            continue
        if dialog_id and re.match(
            r"^(?:actor_break_dialog|dm_.+|hello_dialog|meet_.+)$",
            dialog_id,
            re.IGNORECASE,
        ):
            if dialog_id not in common_actor_dialogs:
                common_actor_dialogs.append(dialog_id)

    resolved: dict[str, Any] = {
        "source_file": source_file,
        "template_npc_id": template_id,
        "visual": child_text("visual"),
        "icon": child_text("icon"),
        "bio": child_text("bio"),
        "common_actor_dialogs": common_actor_dialogs,
        "rank": _as_int(child_text("rank"), 0)
        if child_text("rank") is not None
        else None,
        "reputation": _as_int(child_text("reputation"), 0)
        if child_text("reputation") is not None
        else None,
        "money": money,
        "supplies": supplies,
        "supplies_text": supplies_text,
    }
    return resolved


# ---------------------------------------------------------------------------
# spawn_sections_<slug>.ltx
# ---------------------------------------------------------------------------


def _immunities_section_name(mod_slug: str) -> str:
    """Возвращает имя сгенерированной секции полного бессмертия.

    Args:
        mod_slug (str): Slug мода.

    Returns:
        str: ``<slug>_immunities_immortal``.
    """
    return f"{mod_slug}_immunities_immortal"


def _ltx_line(key: str, value: str) -> str:
    """Форматирует одну строку LTX с выравниванием ключа.

    Args:
        key (str): Имя ключа.
        value (str): Значение без кавычек.

    Returns:
        str: Строка ``key<пробелы>= value``.
    """
    return f"{key:<{_LTX_KEY_WIDTH}} = {value}"


def _needs_generated_immunities(npcs: list[CustomNpc]) -> bool:
    """Проверяет, нужна ли сгенерированная секция иммунитетов.

    Args:
        npcs (list[CustomNpc]): NPC проекта.

    Returns:
        bool: ``True``, если есть ``immortal=True`` без явной секции.
    """
    return any(npc.immortal and not npc.immunities_sect for npc in npcs)


def build_spawn_sections_ltx(project: ModProject) -> str:
    """Формирует ``spawn_sections_<slug>.ltx``.

    Если хотя бы один NPC бессмертен и не имеет явной ``immunities_sect``,
    файл начинается с секции ``[<slug>_immunities_immortal]`` со всеми
    10 полями ``0.0``. Секция объявляется **до** spawn-секций, потому что
    X-Ray разбирает LTX текстуально (§1.5).

    Args:
        project (ModProject): Проект мода.

    Returns:
        str: Полный текст LTX.
    """
    slug = _mod_slug(project)
    npcs = list(project.npcs.values())
    lines: list[str] = []

    if _needs_generated_immunities(npcs):
        lines.append(f"[{_immunities_section_name(slug)}]")
        for field in IMMUNITY_FIELDS:
            lines.append(_ltx_line(field, "0.0"))
        lines.append("")

    for npc in npcs:
        profile = _character_profile(npc)
        lines.append(f"[{npc.id}]:{npc.parent_section}")
        lines.append(_ltx_line("$spawn", f'"respawn\\{npc.id}"'))
        lines.append(_ltx_line("character_profile", profile))
        lines.append(_ltx_line("spec_rank", npc.spec_rank))
        lines.append(_ltx_line("community", npc.faction))
        lines.append(
            _ltx_line(
                "trade_config",
                r"misc\trade\trade_generic.ltx",
            )
        )
        if npc.story_id:
            lines.append(_ltx_line("story_id", npc.story_id))
        immunities_sect = npc.immunities_sect
        if npc.immortal and not immunities_sect:
            immunities_sect = _immunities_section_name(slug)
        if immunities_sect:
            lines.append(_ltx_line("immunities_sect", immunities_sect))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n" if lines else ""


# ---------------------------------------------------------------------------
# npc_profile_<slug>.xml
# ---------------------------------------------------------------------------


def build_npc_profile_xml(project: ModProject) -> bytes:
    """Формирует ``npc_profile_<slug>.xml`` в кодировке UTF-8.

    Args:
        project (ModProject): Проект мода.

    Returns:
        bytes: UTF-8 XML с ``<character>`` на каждого NPC.
    """
    lines = [NPC_PROFILE_DECLARATION, f"<{XML_ROOT_TAG}>", ""]
    for npc in project.npcs.values():
        profile = _xml_attribute(_character_profile(npc))
        npc_class = _xml_text(npc.npc_class or npc.id)
        lines.append(f'\t<character id="{profile}">')
        lines.append(f"\t\t<class>{npc_class}</class>")
        lines.append(
            f"\t\t<specific_character>{_xml_text(_character_profile(npc))}"
            "</specific_character>"
        )
        lines.append("\t</character>")
        lines.append("")
    lines.append(f"</{XML_ROOT_TAG}>")
    return "\n".join(lines).encode("utf-8")


# ---------------------------------------------------------------------------
# character_desc_<slug>.xml
# ---------------------------------------------------------------------------


def _collect_actor_dialogs(
    project: ModProject,
    npc: CustomNpc,
    template_dialogs: Any = (),
    leading: Any = (),
) -> list[str]:
    """Объединяет системные, шаблонные и кастомные ``actor_dialog``.

    Диалог считается привязанным к NPC, если его ``npc_id`` совпадает с
    ``CustomNpc.id`` или ``character_profile``.

    Args:
        project (ModProject): Проект мода.
        npc (CustomNpc): Модель NPC.
        template_dialogs (Any): Общие диалоги из шаблона (``dm_*`` и т. п.).
        leading (Any): Обязательные системные диалоги в начале списка.

    Returns:
        list[str]: Уникальные id диалогов в порядке объявления.
    """
    result: list[str] = []
    seen: set[str] = set()

    def add(dialog_id: Any) -> None:
        """Добавляет непустой id диалога без дубликатов.

        Args:
            dialog_id (Any): Кандидат в ``<actor_dialog>``.
        """
        cleaned = str(dialog_id).strip() if dialog_id else ""
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)

    for dialog_id in leading or ():
        add(dialog_id)
    for dialog_id in template_dialogs or ():
        add(dialog_id)
    for dialog_id in npc.actor_dialogs:
        add(dialog_id)

    profiles = {npc.id, _character_profile(npc)}
    for key, dialog in project.dialogs.items():
        npc_id = getattr(dialog, "npc_id", None)
        if npc_id and str(npc_id) in profiles:
            add(
                getattr(dialog, "dialog_id", None)
                or getattr(dialog, "id", None)
                or key
            )
    return result


def _money_values(
    npc: CustomNpc, template: dict[str, Any]
) -> tuple[int, int, bool]:
    """Выбирает значения ``<money>`` с учётом шаблона.

    Явно заданные непустые поля NPC имеют приоритет; иначе используются
    значения шаблона.

    Args:
        npc (CustomNpc): Модель NPC.
        template (dict[str, Any]): Разрешённые теги шаблона.

    Returns:
        tuple[int, int, bool]: ``(min, max, infinitive)``.
    """
    if npc.money_min or npc.money_max or npc.money_infinitive:
        return npc.money_min, npc.money_max, npc.money_infinitive
    money = template.get("money") or {}
    return (
        _as_int(money.get("min"), 0),
        _as_int(money.get("max"), 0),
        bool(money.get("infinitive")),
    )


def _supplies_text(npc: CustomNpc, template: dict[str, Any]) -> str:
    """Возвращает содержимое ``<supplies>``.

    Args:
        npc (CustomNpc): Модель NPC.
        template (dict[str, Any]): Разрешённые теги шаблона.

    Returns:
        str: Текст тега без внешних пробелов.
    """
    if npc.supplies:
        sections = ["[spawn]", *[str(item).strip() for item in npc.supplies]]
        return "\n".join(item for item in sections if item)
    raw = template.get("supplies_text")
    if raw:
        return str(raw).strip()
    supplies = template.get("supplies") or []
    if supplies:
        return "\n".join(str(item) for item in supplies)
    return "[spawn]"


def build_character_desc_xml(
    project: ModProject,
    resolved_templates: dict[str, Any] | None = None,
) -> bytes:
    """Формирует ``character_desc_<slug>.xml`` в кодировке windows-1251.

    Для NPC с ``template_npc_id`` теги ``visual/icon/bio/rank/reputation/
    money/supplies`` берутся из ``resolved_templates`` (§3.2), если не
    переопределены явно. ``<name>`` всегда указывает на строку
    ``<id>_name`` из :func:`build_npc_text_entries`.

    Args:
        project (ModProject): Проект мода.
        resolved_templates (dict[str, Any] | None): Результаты
            :func:`resolve_npc_template`, ключ — ``CustomNpc.id`` /
            ``character_profile`` / ``template_npc_id``.

    Returns:
        bytes: XML в windows-1251.

    Raises:
        ValueError: Если у NPC нет ``visual`` ни в модели, ни в шаблоне.
    """
    lines = [CHARACTER_DESC_DECLARATION, f"<{XML_ROOT_TAG}>", ""]

    for npc in project.npcs.values():
        template = _template_for(npc, resolved_templates)
        profile = _character_profile(npc)

        visual = npc.visual or template.get("visual")
        if not visual:
            raise ValueError(
                f"NPC '{npc.id}': не удалось получить visual ни из модели, "
                "ни из шаблона (CAT-CUSTOM-009/011)."
            )

        icon = npc.icon or template.get("icon")
        rank = npc.rank if npc.rank else _as_int(template.get("rank"), 0)
        reputation = (
            npc.reputation
            if npc.reputation
            else _as_int(template.get("reputation"), 0)
        )
        money_min, money_max, money_infinitive = _money_values(npc, template)

        lines.append(
            f'\t<specific_character id="{_xml_attribute(profile)}" '
            'no_random="1">'
        )
        lines.append(f"\t\t<name>{_xml_text(npc.id)}_name</name>")
        if icon:
            lines.append(f"\t\t<icon>{_xml_text(icon)}</icon>")
        if npc.bio:
            lines.append(f"\t\t<bio>{_xml_text(npc.id)}_bio</bio>")
        elif template.get("bio"):
            lines.append(f"\t\t<bio>{_xml_text(template['bio'])}</bio>")
        lines.append(
            f"\t\t<class>{_xml_text(npc.npc_class or npc.id)}</class>"
        )
        lines.append(f"\t\t<community>{_xml_text(npc.faction)}</community>")
        lines.append('\t\t<map_icon x="1" y="0"/>')
        lines.append(
            f"\t\t<terrain_sect>{_xml_text(npc.terrain_sect)}</terrain_sect>"
        )
        lines.append(f"\t\t<visual>{_xml_text(visual)}</visual>")
        lines.append(f"\t\t<rank>{rank}</rank>")
        lines.append(f"\t\t<reputation>{reputation}</reputation>")
        money_attrs = f'min="{money_min}" max="{money_max}"'
        if money_infinitive:
            money_attrs += ' infinitive="1"'
        lines.append(f"\t\t<money {money_attrs}/>")
        supplies = _supplies_text(npc, template)
        lines.append("\t\t<supplies>")
        for supply_line in supplies.splitlines():
            lines.append(f"\t\t\t{supply_line}")
        lines.append("\t\t</supplies>")
        if npc.snd_config:
            lines.append(
                f"\t\t<snd_config>{_xml_text(npc.snd_config)}</snd_config>"
            )
        if npc.crouch_type is not None:
            lines.append(
                f"\t\t<crouch_type>{npc.crouch_type}</crouch_type>"
            )
        start_dialog = npc.start_dialog or "hello_dialog"
        lines.append(
            f"\t\t<start_dialog>{_xml_text(start_dialog)}</start_dialog>"
        )
        for dialog_id in _collect_actor_dialogs(
            project,
            npc,
            template.get("common_actor_dialogs"),
            (
                "dm_init_stalker_trade",
                "dm_universal_dialog",
                "actor_break_dialog",
            ),
        ):
            lines.append(
                f"\t\t<actor_dialog>{_xml_text(dialog_id)}</actor_dialog>"
            )
        lines.append("\t</specific_character>")
        lines.append("")

    lines.append(f"</{XML_ROOT_TAG}>")
    return "\n".join(lines).encode("windows-1251")


# ---------------------------------------------------------------------------
# Строки локализации
# ---------------------------------------------------------------------------


def build_npc_text_entries(
    project: ModProject,
) -> tuple[dict[str, str], dict[str, str]]:
    """Формирует строки ``<name>`` и ``<bio>`` для ``st_<slug>.xml``.

    Args:
        project (ModProject): Проект мода.

    Returns:
        tuple[dict[str, str], dict[str, str]]: ``(rus, eng)`` — словари
        ``id -> текст`` для вливания в таблицы строк в Итерации 2.
    """
    rus: dict[str, str] = {}
    eng: dict[str, str] = {}
    for npc in project.npcs.values():
        rus[f"{npc.id}_name"] = npc.name_ru or npc.id
        eng[f"{npc.id}_name"] = npc.name_en or npc.name_ru or npc.id
        if npc.bio:
            rus[f"{npc.id}_bio"] = npc.bio
            eng[f"{npc.id}_bio"] = npc.bio
    return rus, eng


# ---------------------------------------------------------------------------
# Идемпотентные патчи
# ---------------------------------------------------------------------------


def patch_spawn_sections_index(content: str, mod_slug: str) -> str:
    """Добавляет ``#include "spawn_sections_<slug>.ltx"`` один раз.

    Args:
        content (str): Исходный ``spawn_sections.ltx``.
        mod_slug (str): Slug мода.

    Returns:
        str: Текст с инклюдом; при повторном вызове не меняется.
    """
    include_line = f'#include "spawn_sections_{mod_slug}.ltx"'
    for line in content.splitlines():
        if line.strip() == include_line:
            return content
    updated = content
    if updated and not updated.endswith(("\n", "\r")):
        updated += "\n"
    return f"{updated}{include_line}\n"


def _find_profiles_section(lines: list[str]) -> int | None:
    """Находит индекс строки ``[profiles]``.

    Args:
        lines (list[str]): Строки файла с сохранением переводов.

    Returns:
        int | None: Индекс секции или ``None``.
    """
    for index, line in enumerate(lines):
        if line.strip() == "[profiles]":
            return index
    return None


def _append_profile_entry(lines: list[str], key: str, name: str) -> None:
    """Идемпотентно дописывает ``name`` в строку ``key`` секции ``[profiles]``.

    Args:
        lines (list[str]): Изменяемый список строк с переводами строк.
        key (str): ``files`` или ``specific_characters_files``.
        name (str): Имя файла без ``.xml``.
    """
    section_index = _find_profiles_section(lines)
    if section_index is None:
        raise ValueError("В system.ltx не найдена секция [profiles].")

    end_index = len(lines)
    for index in range(section_index + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end_index = index
            break

    for index in range(section_index + 1, end_index):
        raw = lines[index]
        if "=" not in raw:
            continue
        raw_key, raw_value = raw.split("=", 1)
        if raw_key.strip() != key:
            continue

        newline = ""
        value = raw_value
        if value.endswith("\r\n"):
            value = value[:-2]
            newline = "\r\n"
        elif value.endswith("\n") or value.endswith("\r"):
            value = value[:-1]
            newline = raw_value[-1]

        tokens = [token.strip() for token in value.split(",")]
        if name in tokens:
            return
        cleaned = value.rstrip()
        if not cleaned.strip():
            new_value = f" {name}"
        elif cleaned.rstrip().endswith(","):
            new_value = f"{cleaned} {name}"
        else:
            new_value = f"{cleaned}, {name}"
        lines[index] = f"{raw_key}={new_value}{newline}"
        return

    newline = "\r\n" if any("\r\n" in line for line in lines) else "\n"
    lines.insert(
        section_index + 1,
        f"{key:<{_LTX_KEY_WIDTH}} = {name}{newline}",
    )


def patch_system_ltx_profiles(
    content: str,
    mod_slug: str,
    include_npc_profile: bool = True,
    include_character_desc: bool = True,
) -> str:
    """Идемпотентно регистрирует XML мода в ``[profiles]`` файла system.ltx.

    Args:
        content (str): Исходный ``system.ltx``.
        mod_slug (str): Slug мода.
        include_npc_profile (bool): Добавить ``npc_profile_<slug>`` в
            ``files``.
        include_character_desc (bool): Добавить ``character_desc_<slug>`` в
            ``specific_characters_files``.

    Returns:
        str: Обновлённый текст; повторный вызов не создаёт дубликатов.

    Raises:
        ValueError: Если в тексте нет секции ``[profiles]``.
    """
    lines = content.splitlines(keepends=True)
    if _find_profiles_section(lines) is None:
        raise ValueError("В system.ltx не найдена секция [profiles].")

    if include_npc_profile:
        _append_profile_entry(lines, "files", f"npc_profile_{mod_slug}")
    if include_character_desc:
        _append_profile_entry(
            lines,
            "specific_characters_files",
            f"character_desc_{mod_slug}",
        )
    return "".join(lines)


__all__ = [
    "CHARACTER_DESC_DECLARATION",
    "IMMUNITY_FIELDS",
    "NPC_PROFILE_DECLARATION",
    "build_character_desc_xml",
    "build_npc_profile_xml",
    "build_npc_text_entries",
    "build_spawn_sections_ltx",
    "patch_spawn_sections_index",
    "patch_system_ltx_profiles",
    "resolve_npc_template",
]
