from pathlib import Path
from datetime import datetime


def extract_pdf_text(path: Path) -> str:
    """Извлекает текстовый слой из PDF файла."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception as e:
        print(f"Ошибка чтения PDF {path.name}: {e}")
        return ""


def collect_documents(root: Path) -> list[dict]:
    """
    Агент сбора документов из локальной папки.
    Обрабатывает .txt и .pdf файлы.
    """
    docs = []

    # 1. Чтение .txt файлов
    for path in root.rglob("*.txt"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="latin-1")

        first_line = next(
            (line.strip() for line in text.splitlines() if line.strip()),
            path.stem
        )

        title = first_line[:100]
        mtime = datetime.fromtimestamp(path.stat().st_mtime)

        docs.append({
            "title": title,
            "text": text,
            "path": str(path.resolve()),
            "date": mtime.strftime("%Y-%m-%d"),
            "time": mtime.strftime("%H:%M:%S"),
        })

    # 2. Чтение .pdf файлов
    for path in root.rglob("*.pdf"):
        text = extract_pdf_text(path)
        
        # Пропускаем PDF, из которых не удалось достать текст (например, сканы-картинки)
        if not text.strip():
            continue

        first_line = next(
            (line.strip() for line in text.splitlines() if line.strip()),
            path.stem
        )

        title = first_line[:100]
        mtime = datetime.fromtimestamp(path.stat().st_mtime)

        docs.append({
            "title": title,
            "text": text,
            "path": str(path.resolve()),
            "date": mtime.strftime("%Y-%m-%d"),
            "time": mtime.strftime("%H:%M:%S"),
        })

    return docs