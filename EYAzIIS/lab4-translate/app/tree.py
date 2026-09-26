"""Дерево синтаксического разбора предложения (вкладка 2).

Строится по синтаксическим ролям зависимостей spaCy (функциональность
лр. №3 весеннего семестра: у каждого токена известен родитель head_id,
корень помечен ROOT_IDX = -1). Представления:

* ``tree_svg``  — графическое дерево (SVG без внешних библиотек);
* ``tree_text`` — текстовое дерево с отступами (для экспорта в TXT);
* ``token_rows`` — таблица токенов под деревом.
"""

from __future__ import annotations

import html

from .domain import TokenData

NODE_HEIGHT = 54
LEVEL_HEIGHT = 88
NODE_GAP = 16
CHAR_WIDTH = 7.6
MIN_NODE_WIDTH = 64
PAD_X = 24
PAD_Y = 30


# ---------------------------------------------------------------------------
# Структура дерева
# ---------------------------------------------------------------------------
def word_tokens(tokens: list[TokenData]) -> list[TokenData]:
    """Токены-слова (пунктуация в дерево разбора не включается)."""
    return [t for t in tokens if t.kind != "punct"]


def children_map(tokens: list[TokenData]) -> dict[int, list[TokenData]]:
    ids = {t.id for t in tokens}
    kids: dict[int, list[TokenData]] = {}
    for t in tokens:
        if t.head_id in ids and t.head_id != t.id:
            kids.setdefault(t.head_id, []).append(t)
    for group in kids.values():
        group.sort(key=lambda t: t.id)
    return kids


def roots(tokens: list[TokenData]) -> list[TokenData]:
    ids = {t.id for t in tokens}
    found = [t for t in tokens if t.head_id not in ids or t.head_id == t.id]
    return found or (tokens[:1] if tokens else [])


# ---------------------------------------------------------------------------
# Текстовое представление (для экспорта и вкладки)
# ---------------------------------------------------------------------------
def tree_text(tokens: list[TokenData]) -> str:
    """Текстовое дерево: слово — тег (расшифровка) — роль (расшифровка)."""
    words = word_tokens(tokens)
    if not words:
        return ""
    kids = children_map(words)
    lines: list[str] = []

    def label(t: TokenData) -> str:
        return f"{t.word} — {t.tag} ({t.tag_ru}) — {t.dep} ({t.dep_ru})"

    def walk(tok: TokenData, prefix: str, is_last: bool, is_root: bool) -> None:
        connector = "" if is_root else ("└─ " if is_last else "├─ ")
        marker = "ROOT: " if is_root else ""
        lines.append(f"{prefix}{connector}{marker}{label(tok)}")
        children = kids.get(tok.id, [])
        child_prefix = prefix + ("" if is_root else ("   " if is_last else "│  "))
        for i, child in enumerate(children):
            walk(child, child_prefix, i == len(children) - 1, False)

    found_roots = roots(words)
    for r_i, root in enumerate(found_roots):
        walk(root, "" if r_i == 0 else "\n", True, True)
    return "\n".join(lines)


def token_rows(tokens: list[TokenData]) -> list[dict]:
    """Таблица токенов: № , слово, лемма, часть речи, тег, роль, родитель."""
    by_id = {t.id: t for t in tokens}
    rows = []
    for t in word_tokens(tokens):
        parent = by_id.get(t.head_id)
        rows.append(
            {
                "id": t.id,
                "word": t.word,
                "lemma": t.lemma,
                "pos": t.pos,
                "pos_ru": t.pos_ru,
                "tag": t.tag,
                "tag_ru": t.tag_ru,
                "dep": t.dep,
                "dep_ru": t.dep_ru,
                "parent": parent.word if parent else "—",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Графическое представление (SVG)
# ---------------------------------------------------------------------------
def tree_svg(tokens: list[TokenData]) -> str:
    """Дерево зависимостей в SVG: узлы «слово / тег / роль», дуги к родителю."""
    words = word_tokens(tokens)
    if not words:
        return "<svg></svg>"
    kids = children_map(words)
    found_roots = roots(words)

    # Ширина узла по самой длинной подписи.
    widths: dict[int, float] = {}
    for t in words:
        text_width = max(len(t.word), len(t.tag), len(t.dep) + 2) * CHAR_WIDTH + 18
        widths[t.id] = max(MIN_NODE_WIDTH, text_width)

    # Раскладка: листья идут по порядку токенов, узел — над центром детей.
    positions: dict[int, tuple[float, float]] = {}
    cursor = 0.0
    depth_of: dict[int, int] = {}

    def layout(tok: TokenData, depth: int) -> float:
        nonlocal cursor
        depth_of[tok.id] = depth
        children = kids.get(tok.id, [])
        if not children:
            x = cursor + widths[tok.id] / 2
            cursor += widths[tok.id] + NODE_GAP
            positions[tok.id] = (x, depth * LEVEL_HEIGHT)
            return x
        child_xs = [layout(c, depth + 1) for c in children]
        x = (min(child_xs) + max(child_xs)) / 2
        positions[tok.id] = (x, depth * LEVEL_HEIGHT)
        return x

    for root in found_roots:
        layout(root, 0)
        cursor += NODE_GAP * 2

    max_depth = max(depth_of.values()) if depth_of else 0
    width = max(cursor + PAD_X * 2, 320)
    height = (max_depth + 1) * LEVEL_HEIGHT + PAD_Y * 2

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="Segoe UI, system-ui, sans-serif">'
    ]
    # Дуги родитель -> потомок
    for t in words:
        for child in kids.get(t.id, []):
            px, py = positions[t.id]
            cx, cy = positions[child.id]
            x1, y1 = px + PAD_X, py + PAD_Y + NODE_HEIGHT
            x2, y2 = cx + PAD_X, cy + PAD_Y
            mid = (y1 + y2) / 2
            parts.append(
                f'<path d="M {x1:.1f} {y1:.1f} C {x1:.1f} {mid:.1f}, {x2:.1f} {mid:.1f}, '
                f'{x2:.1f} {y2:.1f}" fill="none" stroke="#9aa7c4" stroke-width="1.6"/>'
            )
    # Узлы
    for t in words:
        x, y = positions[t.id]
        w = widths[t.id]
        left = x - w / 2 + PAD_X
        top = y + PAD_Y
        is_root = t in found_roots
        stroke = "#2563eb" if is_root else "#dfe4ef"
        fill = "#eef4ff" if is_root else "#ffffff"
        parts.append(
            f'<g><rect x="{left:.1f}" y="{top:.1f}" width="{w:.1f}" height="{NODE_HEIGHT}" '
            f'rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
        )
        parts.append(
            f'<text x="{left + w / 2:.1f}" y="{top + 19:.1f}" text-anchor="middle" '
            f'font-size="14" font-weight="600" fill="#16213a">{html.escape(t.word)}</text>'
        )
        parts.append(
            f'<text x="{left + w / 2:.1f}" y="{top + 35:.1f}" text-anchor="middle" '
            f'font-size="11" fill="#64708a">{html.escape(t.tag)}</text>'
        )
        parts.append(
            f'<text x="{left + w / 2:.1f}" y="{top + 48:.1f}" text-anchor="middle" '
            f'font-size="10" fill="#2563eb">{html.escape(t.dep)}</text></g>'
        )
    parts.append("</svg>")
    return "".join(parts)
