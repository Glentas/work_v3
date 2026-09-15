"""Метод N-грамм: построение профиля и мера out-of-place."""

from __future__ import annotations

from app import config, distances, text
from app.profiles import NgramProfile, build_ngram_profile


def test_char_ngrams_padding_and_lengths():
    # Слово chat, N=1..2: токен дополнен пробелами '_' с обеих сторон.
    assert text.char_ngrams("chat", n_max=2) == [
        *"_chat_",                              # униграммы с паддингом
        "_c", "ch", "ha", "at", "t_",           # биграммы с паддингом
    ]


def test_char_ngrams_use_letters_and_apostrophes_only():
    # Цифры и пунктуация отбрасываются (Cavnar–Trenkle, §3.1).
    assert text.char_ngrams("chat, 42! dog", n_max=1) == list("_chat_") + list("_dog_")


def test_char_ngrams_case_insensitive():
    assert text.char_ngrams("Chat") == text.char_ngrams("chat")


def test_profile_sorted_by_frequency_with_deterministic_tiebreak():
    profile = build_ngram_profile("aa bb cc", size=10, n_max=1)
    # Все униграммы встречаются по одному разу -> порядок лексикографический.
    assert profile.ngrams == tuple(sorted(profile.ngrams))


def test_profile_size_limited():
    # 400 различных псевдослов (тройки букв в 26-ричной системе):
    # различных N-грамм заведомо больше 300.
    words = [
        "".join(chr(ord("a") + (i // 26 ** k) % 26) for k in (2, 1, 0))
        for i in range(400)
    ]
    profile = build_ngram_profile(" ".join(words), size=300)
    assert len(profile) == 300
    assert profile.ranks[profile.ngrams[0]] == 0


def test_out_of_place_figure_1_of_the_methodical_guide():
    """Эталонный пример рисунка 1 методички (= рис. 3 Cavnar–Trenkle).

    Категория: TH ER ON LE ING AND; документ: TH ING ON ER AND ED.
    Разности позиций: 0 + 3 + 0 + 2 + 1 = 6; ED отсутствует -> штраф,
    равный длине профиля категории (6). Итого 12.
    """
    category = NgramProfile(
        ngrams=("TH", "ER", "ON", "LE", "ING", "AND"),
        ranks={g: i for i, g in enumerate(("TH", "ER", "ON", "LE", "ING", "AND"))},
    )
    document = NgramProfile(
        ngrams=("TH", "ING", "ON", "ER", "AND", "ED"),
        ranks={g: i for i, g in enumerate(("TH", "ING", "ON", "ER", "AND", "ED"))},
    )
    assert distances.out_of_place(document, category) == 6 + len(category)


def test_out_of_place_penalty_equals_category_profile_length():
    lang = NgramProfile(ngrams=("a", "b"), ranks={"a": 0, "b": 1})
    doc = NgramProfile(ngrams=("z",), ranks={"z": 0})
    assert distances.out_of_place(doc, lang) == len(lang)  # 2 = максимальная величина


def test_out_of_place_zero_for_identical_profiles():
    profile = build_ngram_profile("la mer et le bateau", size=50)
    assert distances.out_of_place(profile, profile) == 0


def test_profile_size_from_config():
    assert config.NGRAM_PROFILE_SIZE == 300
    assert config.NGRAM_MAX_N == 5
