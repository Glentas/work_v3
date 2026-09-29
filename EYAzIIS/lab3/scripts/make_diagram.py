# -*- coding: utf-8 -*-
"""Диаграммы для отчёта: структура системы и схема алгоритма (matplotlib)."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrow

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "report")
os.makedirs(OUT, exist_ok=True)

BOX = dict(boxstyle="round,pad=0.45", fc="#e8f0fe", ec="#2563eb", lw=1.4)
BOX2 = dict(boxstyle="round,pad=0.45", fc="#e9f9ef", ec="#0f9d58", lw=1.4)
BOX3 = dict(boxstyle="round,pad=0.45", fc="#fdf1e3", ec="#d97706", lw=1.4)
DATA = dict(boxstyle="round,pad=0.45", fc="#f3f4f6", ec="#6b7280", lw=1.2,
            ls="--")


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(FancyArrow(x1, y1, x2 - x1, y2 - y1, width=0.012,
                            head_width=0.05, head_length=0.06,
                            length_includes_head=True, color="#374151"))


def box(ax, x, y, text, style=BOX, fs=10):
    ax.text(x, y, text, ha="center", va="center", fontsize=fs,
            bbox=style, wrap=True)


def diagram_algorithm():
    fig, ax = plt.subplots(figsize=(10.5, 13.5))
    ax.set_xlim(0, 10); ax.set_ylim(0, 16); ax.axis("off")
    steps = [
        (5, 15.2, "ВХОД: текстовый документ D\n(français / english, ~10 стр. А4)", BOX3),
        (5, 13.9, "1. Предобработка: разбиение на абзацы P и предложения Sᵢ;\n"
                  "офильтровка стоп-слов, чисел, слов чужой письменности;\n"
                  "вычисление |D|, BD(Sᵢ), |P|, BP(Sᵢ)", BOX),
        (5, 12.5, "2. Индекс коллекции: df(t), |DB|;\n"
                  "tf(t,Sᵢ), tf(t,D), tf_max(D)", BOX),
        (5, 11.1, "3. Базовый вес слова (TF·IDF):\nw(t) = tf(t,D)·log(|DB|/df(t))", BOX),
        (5, 9.6, "4. Модифицированный TF-IDF:\nw(t,D) = 0.5·(1 + tf(t,D)/tf_max(D))·log(|DB|/df(t))", BOX),
        (5, 8.1, "5. Позиционные функции:\nPosd(Sᵢ) = 1 − BD(Sᵢ)/|D|;   Posp(Sᵢ) = 1 − BP(Sᵢ)/|P|", BOX),
        (5, 6.6, "6. Вес предложения:\nW(Sᵢ) = Posd(Sᵢ)·Posp(Sᵢ)·Σ tf(t,Sᵢ)·w(t,D)", BOX),
        (5, 5.1, "7. НЕЙРОСЕТЕВОЙ МЕТОД (замена OSTIS):\nэмбеддинги предложений (трансформер / skip-gram);\n"
                 "MMR-отбор: λ·W(Sᵢ) − (1−λ)·max cos(Sᵢ,Sⱼ) — защита от повторов", BOX2),
        (5, 3.6, "8. Генерация: N=10 предложений с наибольшим W\nв порядке следования в тексте", BOX),
        (5, 2.2, "9. Реферат в виде списка ключевых слов:\nTF-IDF-вершины + словосочетания + нейросетевая группировка", BOX2),
        (5, 0.8, "ВЫХОД: ссылка на источник + классический реферат\n+ список ключевых слов; сохранение в файл, печать", BOX3),
    ]
    for x, y, t, st in steps:
        box(ax, x, y, t, st, fs=9.5)
    for i in range(len(steps) - 1):
        arrow(ax, 5, steps[i][1] - 0.55, 5, steps[i + 1][1] + 0.62)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "algorithm.png"), dpi=150)
    plt.close(fig)
    print("algorithm.png ok")


def diagram_structure():
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.set_xlim(0, 12); ax.set_ylim(0, 9); ax.axis("off")
    box(ax, 6, 8.2, "ВЕБ-ИНТЕРФЕЙС (Jinja2 + HTML/CSS/JS):\nвыбор документа · загрузка · параметры · справка (help)", BOX3, 9.5)
    box(ax, 6, 6.8, "FastAPI: маршруты /, /summarize, /result, /document, /help,\n/api/*, экспорт .txt/.html", BOX, 9.5)
    box(ax, 2.6, 5.0, "Токенизатор:\nабзацы, предложения,\nсмещения BD/BP", BOX, 9)
    box(ax, 6.0, 5.0, "Модуль sentence extraction:\nTF-IDF, модиф. TF-IDF,\nPosd/Posp, веса W(Sᵢ)", BOX, 9)
    box(ax, 9.4, 5.0, "Нейросетевой модуль:\nONNX-трансформер (multilingual),\nskip-gram (numpy); MMR", BOX2, 9)
    box(ax, 2.6, 3.2, "Генератор реферата:\nтоп-N по порядку текста", BOX, 9)
    box(ax, 6.0, 3.2, "Генератор ключевых слов:\nдерево терминов", BOX, 9)
    box(ax, 9.4, 3.2, "Оценка качества:\nROUGE, покрытие,\nадекватность, время", BOX, 9)
    box(ax, 6, 1.6, "ДАННЫЕ: тестовая коллекция (8 док., meta.json, эталоны),\nиндекс df/|DB|, загруженные документы, результаты", DATA, 9.5)
    box(ax, 6, 0.4, "ВЫХОД: страница результата, файлы .txt/.html, печать", BOX3, 9.5)
    arrow(ax, 6, 7.75, 6, 7.35)
    for x in (2.6, 6.0, 9.4):
        arrow(ax, 6, 6.25, x, 5.62)
        arrow(ax, x, 4.45, x if x != 9.4 else 7.6, 3.75 if x != 9.4 else 3.7)
    arrow(ax, 2.6, 2.65, 5.2, 2.0)
    arrow(ax, 6.0, 2.65, 6.0, 2.0)
    arrow(ax, 9.4, 2.65, 6.8, 2.0)
    arrow(ax, 6, 1.15, 6, 0.75)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "structure.png"), dpi=150)
    plt.close(fig)
    print("structure.png ok")


if __name__ == "__main__":
    diagram_algorithm()
    diagram_structure()
