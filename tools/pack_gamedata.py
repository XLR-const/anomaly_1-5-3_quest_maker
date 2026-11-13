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


def list_output_subfolders(output_dir: Path) -> list[Path]:
    """Возвращает отсортированный список подпапок внутри output-каталога."""
    if not output_dir.exists() or not output_dir.is_dir():
        return []
    return sorted(
        (p for p in output_dir.iterdir() if p.is_dir()),
        key=lambda p: p.name.lower(),
    )


def pick_folder_from_output(output_dir: Path) -> Path | None:
    """
    Показывает пронумерованный список папок внутри output и ждёт номер.
    Возвращает выбранный путь или None, если пользователь ушёл в ручной ввод.
    """
    folders = list_output_subfolders(output_dir)

    if not folders:
        print(f"[Инфо] В каталоге '{output_dir}' не найдено папок. Переход в ручной ввод пути.")
        return None

    while True:
        print()
        print("=" * 60)
        print(f"  ДОСТУПНЫЕ ПАПКИ В: {output_dir}")
        print("=" * 60)
        for idx, folder in enumerate(folders, start=1):
            print(f"  [{idx}] {folder.name}")
        print(f"  [0] Ввести полный путь вручную")
        print("=" * 60)

        raw = input("Введите номер папки: ").strip()
        if not raw:
            print("[Ошибка] Пустой ввод. Попробуйте снова.")
            continue
        if not raw.isdigit():
            print("[Ошибка] Нужно ввести число.")
            continue

        choice = int(raw)
        if choice == 0:
            return None
        if 1 <= choice <= len(folders):
            return folders[choice - 1]
        print(f"[Ошибка] Номера {choice} нет в списке. Диапазон: 0..{len(folders)}.")


def ask_manual_path() -> Path | None:
    """Ручной ввод полного пути. Возвращает валидный Path или None при отказе."""
    user_input = input(
        "\nВведите или вставьте ПОЛНЫЙ абсолютный путь к папке мода\n"
        "(например, C:/Users/Name/Desktop/MyManualMod): "
    ).strip()

    user_input = user_input.strip('"').strip("'")

    if not user_input:
        print("[Ошибка] Путь не может быть пустым.")
        return None

    target_path = Path(user_input)

    if not target_path.is_absolute():
        print("[Ошибка] Вы ввели относительный путь. Введите полный путь, начиная с буквы диска (например, C:/...)")
        return None

    if not target_path.exists():
        print(f"[Ошибка] Указанный путь физически не существует на диске: {target_path}")
        return None

    return target_path


def resolve_gamedata(target_path: Path) -> Path | None:
    """Определяет, где именно лежит gamedata внутри выбранной папки мода."""
    if target_path.name == "gamedata":
        return target_path

    potential_gamedata = target_path / "gamedata"
    if potential_gamedata.exists() and potential_gamedata.is_dir():
        return potential_gamedata

    print(f"[Предупреждение] В указанной папке '{target_path.name}' не найдена подпапка 'gamedata'.")
    confirm = input("Сканировать корень указанной папки напрямую? (y/n): ").strip().lower()
    if confirm == "y":
        return target_path
    return None


def sanitize_filename(name: str) -> str:
    """Убирает из имени папки символы, недопустимые в имени файла."""
    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in invalid else ch for ch in name).strip()
    return cleaned or "mod"


def main():
    print("=" * 60)
    print("  УПАКОВЩИК МОДА ДЛЯ КОНТЕКСТА В .txt")
    print("=" * 60)

    # Скрипт лежит в tools/, output — на уровень выше, рядом с tools
    script_dir = Path(__file__).resolve().parent
    tools_dir = script_dir
    output_dir = script_dir.parent / "output"

    mod_name_for_filename = None

    while True:
        selected = pick_folder_from_output(output_dir)

        if selected is None:
            target_path = ask_manual_path()
            if target_path is None:
                continue
        else:
            target_path = selected
            print(f"[Выбрано] {target_path}")

        gamedata_path = resolve_gamedata(target_path)
        if gamedata_path is None:
            continue

        # Имя мода для файла-слепка:
        # - если выбрали из output — берём имя выбранной папки;
        # - если вручную — берём имя папки-родителя gamedata (или её самой).
        if selected is not None:
            mod_name_for_filename = target_path.name
        else:
            mod_name_for_filename = gamedata_path.parent.name if gamedata_path.name == "gamedata" else gamedata_path.name
        break

    safe_name = sanitize_filename(mod_name_for_filename)
    output_file = tools_dir / f"manual_mod_snapshot_{safe_name}.txt"

    print(f"\n[Запуск] Сканирование структуры сталкерских файлов в: {gamedata_path}")
    merge_gamedata_to_text(gamedata_path, output_file)


if __name__ == "__main__":
    main()