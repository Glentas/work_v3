"""Проверка лингвистической обработки: разбор запроса и построение сниппета."""

from __future__ import annotations

from app.text import analyze, make_snippet, parse_query, stem, stopwords, tokenize


class TestTokenizeAndAnalyze:
    def test_tokenize_lowercases_and_splits(self):
        assert tokenize("Hello, World! 42") == ["hello", "world", "42"]

    def test_stopwords_are_loaded_offline(self):
        words = stopwords()
        assert len(words) > 100
        assert "the" in words and "and" in words

    def test_analyze_removes_stopwords_and_stems(self):
        assert analyze("The cats are running") == [("cats", "cat"), ("running", "run")]

    def test_stem_is_consistent(self):
        assert stem("running") == stem("runs") == "run"
        assert stem("foxes") == "fox"


class TestParseQuery:
    def test_plain_query(self):
        query = parse_query("Cat Running")

        assert set(query.include) == {"cat", "run"}
        assert query.include["cat"] == ["cat"]         # токены приводятся к нижнему регистру
        assert query.exclude == {}
        assert not query.is_empty

    def test_word_forms_collapse_to_one_term(self):
        query = parse_query("run runs running")

        assert list(query.include) == ["run"]
        assert query.include["run"] == ["run", "runs", "running"]

    def test_minus_excludes_term(self):
        query = parse_query("holmes -watson")

        assert list(query.include) == ["holm"]
        assert list(query.exclude) == ["watson"]

    def test_minus_at_start(self):
        query = parse_query("-watson holmes")

        assert list(query.include) == ["holm"]
        assert list(query.exclude) == ["watson"]

    def test_hyphen_inside_word_is_not_exclusion(self):
        """Дефис в well-known не должен запрещать слово known."""
        query = parse_query("well-known fact")

        assert query.exclude == {}
        assert set(query.include) == {"well", "known", "fact"}

    def test_only_stopwords_gives_empty_query(self):
        assert parse_query("the and of").is_empty

    def test_only_exclusions_gives_empty_query(self):
        assert parse_query("-cat -dog").is_empty

    def test_empty_string(self):
        assert parse_query("").is_empty


class TestMakeSnippet:
    def test_highlights_matching_words(self):
        snippet = make_snippet("The cat sat on the mat", {"cat"}, max_length=100)

        assert "<mark>cat</mark>" in snippet
        assert "<mark>The</mark>" not in snippet      # стоп-слова не подсвечиваются

    def test_selects_window_around_match(self):
        """Сниппет строится вокруг совпадения, а не по началу документа."""
        text = (
            "STARTMARKER " + "lorem ipsum dolor sit amet. " * 80
            + "Here appears the unicorn word. "
            + "trailing filler text. " * 80
        )

        snippet = make_snippet(text, {"unicorn"}, max_length=200)

        assert "<mark>unicorn</mark>" in snippet
        assert "STARTMARKER" not in snippet      # начало документа не попало во фрагмент
        assert snippet.startswith("…")           # фрагмент вырезан из середины
        assert len(snippet) < 320                # ограничение длины соблюдено

    def test_picks_densest_window(self):
        text = "cat one two three four five six seven eight nine ten cat cat cat"
        snippet = make_snippet(text, {"cat"}, max_length=40)

        assert snippet.count("<mark>") == 3

    def test_ellipsis_marks_truncation(self):
        text = "alpha beta gamma delta epsilon zeta"
        snippet = make_snippet(text, {"gamma"}, max_length=14)

        assert snippet.startswith("…")
        assert snippet.endswith("…")

    def test_no_ellipsis_when_nothing_dropped(self):
        """Многоточие не показывается, если отброшены только пробелы."""
        snippet = make_snippet("   alpha beta gamma   ", {"beta"}, max_length=100)

        assert snippet == "alpha <mark>beta</mark> gamma"

    def test_escapes_html(self):
        snippet = make_snippet("<script>alert('x')</script> cat", {"cat"}, 200)

        assert "<script>" not in snippet          # тег не должен остаться сырым
        assert "&lt;" in snippet and "&gt;" in snippet
        assert "<mark>cat</mark>" in snippet

    def test_without_matches_returns_document_start(self):
        snippet = make_snippet("alpha beta gamma", {"absent"}, max_length=20)

        assert "<mark>" not in snippet
        assert snippet.startswith("alpha")

    def test_empty_text(self):
        assert make_snippet("", {"cat"}) == ""
        assert make_snippet("!!! ???", {"cat"}) == ""
