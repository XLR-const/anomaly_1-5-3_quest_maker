import os
import sys
from pathlib import Path

def merge_gamedata_to_text(gamedata_dir: Path, output_file: Path):
    """Сканирует указанный каталог, читает файлы Сталкера и собирает в единый текстовый срез."""
    with open(output_file, "w", encoding="utf-8") as out:
        out.write("=== ЭТАЛОННЫЙ РУЧНОЙ МОД СЮЖЕТА (СЛЕПОК СТРУКТУРЫ) ===\n\n")
        
        count = 0
        for root, _, files in os.walk(gamedata_dir):
            for file in files:
                if file.endswith((".script", ".xml", ".ltx")):
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(gamedata_dir)
                    
                    out.write(f"=========================================\n")
                    out.write(f"ФАЙЛ: gamedata/{rel_path.as_posix()}\n")
                    out.write(f"=========================================\n")
                    
                    try:
                        content = full_path.read_text(encoding="cp1251")
                    except UnicodeDecodeError:
                        content = full_path.read_text(encoding="utf-8", errors="ignore")
                        
                    out.write(content)
                    out.write("\n\n")
                    count += 1
                    
    print(f"\n[УСПЕХ] Успешно упаковано файлов: {count}")
    print(f"[ФАЙЛ СЛЕПКА]: {output_file.resolve()}")

def main():
    print("=" * 60)
    print("  УПАКОВЩИК МОДА ДЛЯ КОНТЕКСТА В .txt")
    print("=" * 60)
    
    while True:
        # Прямой опрос полного пути у пользователя
        user_input = input("\nВведите или вставьте ПОЛНЫЙ абсолютный путь к папке мода\n(например, C:/Users/Name/Desktop/MyManualMod): ").strip()
        
        # Автоматически очищаем кавычки (бывает, если путь перетащили мышкой в терминал)
        user_input = user_input.strip('"').strip("'")
        
        if not user_input:
            print("[Ошибка] Путь не может быть пустым. Попробуйте снова.")
            continue
            
        target_path = Path(user_input)
        
        # Проверяем, что введен действительно абсолютный путь
        if not target_path.is_absolute():
            print("[Ошибка] Вы ввели относительный путь. Введите полный путь, начиная с буквы диска (например, C:/...)")
            continue
            
        # Проверяем физическое существование каталога
        if not target_path.exists():
            print(f"[Ошибка] Указанный путь физически не существует на диске: {target_path}")
            continue
            
        # Умный поиск: если внутри указанного пути есть подпапка gamedata, переключаемся на неё.
        # Если пользователь сразу указал саму папку gamedata — работаем с ней напрямую.
        if target_path.name == "gamedata":
            gamedata_path = target_path
        else:
            potential_gamedata = target_path / "gamedata"
            if potential_gamedata.exists() and potential_gamedata.is_dir():
                gamedata_path = potential_gamedata
            else:
                print(f"[Предупреждение] В указанной папке '{target_path.name}' не найдена подпапка 'gamedata'.")
                confirm = input("Сканировать корень указанной папки напрямую? (y/n): ").strip().lower()
                if confirm == 'y':
                    gamedata_path = target_path
                else:
                    continue
                    
        break

    # Сборка файла-слепка в папку tools
    output_file = Path(__file__).resolve().parent / "manual_mod_snapshot.txt"
    print(f"\n[Запуск] Сканирование структуры сталкерских файлов в: {gamedata_path}")
    merge_gamedata_to_text(gamedata_path, output_file)

if __name__ == "__main__":
    main()
