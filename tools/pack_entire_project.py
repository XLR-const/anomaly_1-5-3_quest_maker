import os
from pathlib import Path

def pack_entire_project(project_root: Path, output_file: Path):
    """Собирает все текстовые исходники проекта в один структурированный файл."""
    # Папки и файлы, которые нужно строго ИГНОРИРОВАТЬ (чтобы не раздувать контекст)
    ignore_dirs = {
        "venv", ".git", "__pycache__", ".pytest_cache", 
        "output", "_unpacked", "manual_mod", "data"
    }
    ignore_files = {
        "anomaly_db.sqlite"
    }
    # Разрешенные расширения для текстового анализа
    allowed_extensions = {".py", ".md", ".json", ".ltx", ".xml", ".script"}

    print("=" * 60)
    print(" 📦 ЗАПУСК ПОЛНОЙ СБОРКИ КОНТЕКСТА ПРОЕКТА ДЛЯ DEEPSEEK")
    print("=" * 60)

    count = 0
    with open(output_file, "w", encoding="utf-8") as out:
        out.write("=== ПОЛНЫЙ СЛЕПОК ИСХОДНОГО КОДА И СТРУКТУРЫ ПРОЕКТА ===\n")
        out.write("Используй этот файл как единственный источник правды о фреймворке.\n\n")

        # Пробегаемся по всему дереву проекта
        for root, dirs, files in os.walk(project_root):
            # Фильтруем запрещенные папки на лету
            dirs[:] = [d for dirs_list in [dirs] for d in dirs_list if d not in ignore_dirs]

            for file in files:
                if file in ignore_files:
                    continue

                file_path = Path(root) / file
                if file_path.suffix in allowed_extensions:
                    rel_path = file_path.relative_to(project_root)
                    
                    out.write(f"=========================================\n")
                    out.write(f"ФАЙЛ: {rel_path.as_posix()}\n")
                    out.write(f"=========================================\n")
                    
                    try:
                        content = file_path.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        try:
                            content = file_path.read_text(encoding="cp1251", errors="ignore")
                        except Exception:
                            content = "-- [Ошибка чтения файла: нетекстовый формат]"

                    out.write(content)
                    out.write("\n\n")
                    count += 1
                    print(f"[Упакован]: {rel_path.as_posix()}")

    print("=" * 60)
    print(f"[УСПЕХ] Сборка завершена. Всего упаковано файлов: {count}")
    print(f"[ИТОГОВЫЙ СЛЕПОК]: {output_file.resolve()}")
    print("=" * 60)

if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parents[1]
    OUTPUT = ROOT / "tools" / "entire_project_snapshot.txt"
    pack_entire_project(ROOT, OUTPUT)
