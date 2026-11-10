import os
from pathlib import Path

def find_vector_squad():
    print("=" * 60)
    print(" 🔍 ПОИСК СКРИПТОВОГО ID СКВАДА ДЛЯ ВЕКТОРА")
    print("=" * 60)
    
    # Путь к распакованным конфигам твоей сборки
    unpacked_configs = Path("_unpacked/configs")
    if not unpacked_configs.exists():
        # Если папки _unpacked нет в корне, попробуем поискать в родительской директории
        unpacked_configs = Path("../_unpacked/configs")
        
    if not unpacked_configs.exists():
        print("[Ошибка] Не найдена папка с распакованными конфигами '_unpacked/configs'.")
        print("Пожалуйста, убедись, что папка ассетов сборки доступна в проекте.")
        return

    target_id = "zat_stancia_trader_merc"
    print(f"[Запуск] Сканирование сквадов на локации Затон по ID: {target_id}...")

    # Ищем файлы конфигурации сквадов Затона
    squad_files = list(unpacked_configs.glob("**/squad_descr*.ltx"))
    
    found_squads = []
    for file_path in squad_files:
        try:
            content = file_path.read_text(encoding="cp1251", errors="ignore")
            # Ищем секции сквадов, где прописан наш торговец
            sections = content.split("[")
            for section in sections:
                if target_id in section and "npc" in section:
                    squad_name = section.split("]")[0].strip()
                    found_squads.append((squad_name, file_path.name))
        except Exception as e:
            continue

    if found_squads:
        print("\n🎯 НАЙДЕНЫ СЛЕДУЮЩИЕ СКВАДЫ В КОНФИГАХ ИГРЫ:")
        for name, file in found_squads:
            print(f" -> Сквад ID для константы (ASLAN_NPC): '{name}' (найден в {file})")
        print("\nСкопируй этот ID отряда и пропиши его в tools/build_merc_story.py!")
    else:
        print(f"\n[Внимание] Прямое упоминание {target_id} в сквадах не найдено.")
        print("В ванильной Anomaly сквад Вектора называется: 'zat_killers_merc_trader_squad'")
        print("Мы принудительно зашьем комбинированную инжекцию в компилятор!")

if __name__ == "__main__":
    find_vector_squad()
