import re
import html
from collections import defaultdict

import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer

_stemmer = PorterStemmer()
_stopwords = None


def ensure_nltk() -> None:
    # Для упрощения используем только stopwords.
    # Токенизация регулярным выражением, поэтому punkt не обязателен.
    nltk.download("stopwords", quiet=True)


def get_stopwords():
    global _stopwords
    if _stopwords is None:
        _stopwords = set(stopwords.words("english"))
    return _stopwords


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def process_text(text: str) -> list[tuple[str, str]]:
    """
    Возвращает список пар: (исходное слово, стемма).
    Стоп-слова удаляются.
    """
    tokens = tokenize(text)
    sw = get_stopwords()
    result = []

    for token in tokens:
        if token in sw:
            continue
        stem = _stemmer.stem(token)
        result.append((token, stem))

    return result


def parse_query(query: str):
    """
    Разбирает запрос.

    Возвращает:
        include: {stem: [original_words]}
        exclude: {stem: [original_words]}

    Исключение задаётся минусом перед словом: -network
    """
    exclude_tokens = []

    def _replace_minus(match):
        exclude_tokens.append(match.group(1))
        return " "

    cleaned = re.sub(r"-([a-zA-Z0-9]+)", _replace_minus, query)

    include_pairs = process_text(cleaned)
    exclude_pairs = process_text(" ".join(exclude_tokens))

    include = defaultdict(list)
    exclude = defaultdict(list)

    for original, stem in include_pairs:
        include[stem].append(original)

    for original, stem in exclude_pairs:
        exclude[stem].append(original)

    return include, exclude


def highlight_snippet(text: str, stems: set[str], max_length: int = 300) -> str:
    """
    Возвращает HTML-сниппет с подсветкой слов запроса.
    Сохраняет пробелы и пунктуацию.
    """
    if not text:
        return ""

    pattern = re.compile(r"[a-zA-Z0-9]+")
    pos = 0
    result = []
    visible_len = 0

    for match in pattern.finditer(text):
        start, end = match.span()

        between = text[pos:start]
        if between:
            result.append(html.escape(between))
            visible_len += len(between)

        token = match.group(0)
        token_lower = token.lower()
        token_html = html.escape(token)

        if token_lower in get_stopwords():
            result.append(token_html)
        else:
            stem = _stemmer.stem(token_lower)
            if stem in stems:
                result.append(f"<mark>{token_html}</mark>")
            else:
                result.append(token_html)

        visible_len += len(token)
        pos = end

        if visible_len >= max_length:
            break

    return "".join(result)