import os
from pathlib import Path

def merge_compiler_to_text(compiler_dir: Path, output_file: Path):
    """Сканирует папку src/compiler/ и собирает исходный код в единый файл."""
    if not compiler_dir.exists():
        print(f"[Ошибка] Папка не найдена: {compiler_dir}")
        return
        
    with open(output_file, "w", encoding="utf-8") as out:
        out.write("=== ИСХОДНЫЙ КОД АВТОМАТИЧЕСКОГО КОМПИЛЯТОРА PYTHON ===\n\n")
        
        for root, _, files in os.walk(compiler_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(compiler_dir.parent.parent)
                    
                    out.write(f"=========================================\n")
                    out.write(f"ФАЙЛ: {rel_path.as_posix()}\n")
                    out.write(f"=========================================\n")
                    out.write(full_path.read_text(encoding="utf-8", errors="ignore"))
                    out.write("\n\n")
                    
    print(f"[УСПЕХ] Слепок компилятора собран в файл: {output_file.resolve()}")

if __name__ == "__main__":
    TARGET_DIR = Path("src/compiler")
    OUTPUT_TEXT = Path("tools/compiler_snapshot.txt")
    merge_compiler_to_text(TARGET_DIR, OUTPUT_TEXT)
