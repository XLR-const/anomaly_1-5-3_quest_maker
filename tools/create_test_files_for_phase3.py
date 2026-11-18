from pathlib import Path

def create_empty_quest_files(base_dir: str = "examples/phase3") -> None:
    """
    Создаёт 12 пустых .py-файлов для промптов phase3:
    story_01.py ... story_08.py и warfare_01.py ... warfare_04.py.
    Если файл уже существует — не перезаписывает его.
    """
    out_dir = Path(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    filenames = (
        [f"story_{i:02d}.py" for i in range(1, 9)]
        + [f"warfare_{i:02d}.py" for i in range(1, 5)]
    )

    created, skipped = [], []
    for name in filenames:
        path = out_dir / name
        if path.exists():
            skipped.append(name)
            continue
        path.touch()  # создаёт пустой файл, если его нет
        created.append(name)

    print(f"Папка: {out_dir.resolve()}")
    print(f"Создано ({len(created)}): {', '.join(created) if created else '—'}")
    print(f"Пропущено, уже существует ({len(skipped)}): {', '.join(skipped) if skipped else '—'}")


if __name__ == "__main__":
    create_empty_quest_files()