# build_deadcity_test.py
"""Сценарий автоматической сборки тестового квеста наемников в Мёртвом городе.

Скрипт формирует Pydantic-модель ModProject, передает расширенные метаданные
локации и профилей Душмана и запускает ModBuilder для компиляции оверлея gamedata
строго по стандартам `standart_of_auto.md` и лекалам эталона «M».
"""

from __future__ import annotations

import sys
from pathlib import Path

# Гарантируем, что корень проекта находится в sys.path для импорта модулей src
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.builder import ModBuilder
from src.core.models import Dialog, ModProject, Phrase, Quest, Stage

# Константы идентификаторов для Мёртвого города по базе игры
PROJECT_NAME = "Dead City Merc Test"
# Было: DUSHMAN_CHARACTER_ID = "cit_killers_merc_trader"
# Меняем на ОФИЦИАЛЬНЫЙ XML ID Душмана:
DUSHMAN_CHARACTER_ID = "cit_killers_merc_trader_stalker"

DIALOG_ID = "mymod_dushman_test_dialog"
QUEST_ID = "mymod_dushman_test_quest"


def _build_test_quest() -> Quest:
    """Формирует модель тестового квеста Синдиката в Мёртвом городе."""
    return Quest(
        id=QUEST_ID,
        title_ru="Тестовый контракт Душмана",
        title_en="Test Dushman Contract",
        descr_ru="Проверка стабильности No-Code конвейера автоматизации в Мёртвом городе.",
        descr_en="Testing No-Code automation pipeline stability in Dead City.",
        is_storyline=False,
        stages={
            0: Stage(
                id=0,
                title_ru="Поговорить с Душманом",
                title_en="Talk to Dushman",
                descr_ru="Убедитесь, что диалоговое No-Code дерево и скрипты слинковались без вылетов.",
                descr_en="Make sure the dialogue No-Code tree and scripts linked without crashes.",
                target_alias=DUSHMAN_CHARACTER_ID,
            ),
        },
        # Передача метаданных в extra-поля для компилятора и патчера character_desc
        npc_id=DUSHMAN_CHARACTER_ID,
        npc_location="deadcity",
        dialog_id=DIALOG_ID,
    )


def _build_dushman_dialog() -> Dialog:
    """Строит полный граф диалога Душмана с соблюдением phrase_list и парных next."""
    return Dialog(
        id=DIALOG_ID,
        npc_alias=DUSHMAN_CHARACTER_ID,
        npc_location="deadcity",  # Локация для нормализации в character_desc_deadcity.xml
        phrases={
            0: Phrase(
                id=0,
                text_ru="Душман, Синдикат готов запустить тестовый конвейер квестов?",
                text_en="Dushman, is the Syndicate ready to launch the test quest pipeline?",
                next_phrases=[1],
                preconditions=[],
                actions=[],
            ),
            1: Phrase(
                id=1,
                text_ru="Да, наёмник. Раз ты видишь этот текст, значит XML-граф, string-таблицы и Lua слинковались идеально.",
                text_en="Yes, mercenary. If you see this text, the XML graph, string tables, and Lua linked perfectly.",
                next_phrases=[2],
                preconditions=[],
                actions=[],
            ),
            2: Phrase(
                id=2,
                text_ru="Отлично. Конвейер запущен, переходим к графическому интерфейсу!",
                text_en="Excellent. The pipeline is live, moving on to the graphical interface!",
                next_phrases=[],
                preconditions=[],
                actions=[],
            ),
        },
    )


def main() -> int:
    """Запускает процесс компиляции проекта оверлея gamedata."""
    print("[Компиляция] Сборка проекта: " + PROJECT_NAME)
    
    project = ModProject(
        name=PROJECT_NAME,
        quests={QUEST_ID: _build_test_quest()},
        dialogs={DIALOG_ID: _build_dushman_dialog()},
    )
    
    # Инициализируем МодБилдер, передавая выходную директорию
    builder = ModBuilder(output_dir=Path("output"))
    
    # Запускаем компиляцию. Возвращаем 0 при успехе, 1 при ошибке.
    success = builder.build_project(project)
    return 0 if success else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[Критическая ошибка]: {e}", file=sys.stderr)
        sys.exit(1)
