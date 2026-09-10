"""Проверка индексирования и логического поиска.

Ожидаемые значения весов вычислены вручную по формулам методички для
тестовой коллекции из conftest.py (N = 5 документов):

    B_cat  = log(5/3) ≈ 0.5108      B_dog  = log(5/2) ≈ 0.9163
    B_bird = log(5/2) ≈ 0.9163      B_zebra = log(5)  ≈ 1.6094
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from app.db import connect
from app.domain import SearchParams
from app.search import ranked_doc_ids, retrieve, search, _rank

IDF_CAT = math.log(5 / 3)
IDF_DOG = math.log(5 / 2)


@pytest.fixture
def ids(doc_id_by_name):
    return doc_id_by_name


def ranked(params: SearchParams) -> list[int]:
    return list(ranked_doc_ids(params))


class TestIndexWeights:
    def test_inverse_frequency_follows_formula_1_5(self, sample_index):
        """B_i = log(N / P_i)."""
        with connect() as conn:
            rows = {r["term"]: r for r in conn.execute("SELECT term, df, idf FROM terms")}

        assert rows["cat"]["df"] == 3
        assert rows["cat"]["idf"] == pytest.approx(math.log(5 / 3))
        assert rows["dog"]["df"] == 2
        assert rows["dog"]["idf"] == pytest.approx(math.log(5 / 2))
        assert rows["zebra"]["df"] == 1
        assert rows["zebra"]["idf"] == pytest.approx(math.log(5))

    def test_term_weight_follows_formula_1_6(self, sample_index, ids):
        """A_i^j = Q_i^j * B_i."""
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT t.term AS term, d.path AS path, p.tf AS tf, p.weight AS weight
                FROM postings p
                JOIN terms t ON t.id = p.term_id
                JOIN documents d ON d.id = p.doc_id
                """
            ).fetchall()

        weights = {(r["term"], Path(r["path"]).name): r for r in rows}

        cat_01 = weights[("cat", "doc_01.txt")]
        assert cat_01["tf"] == 3
        assert cat_01["weight"] == pytest.approx(3 * IDF_CAT)

        dog_02 = weights[("dog", "doc_02.txt")]
        assert dog_02["tf"] == 3
        assert dog_02["weight"] == pytest.approx(3 * IDF_DOG)

    def test_document_ids_are_deterministic(self, sample_index):
        """Идентификаторы назначаются по имени файла — индекс воспроизводим."""
        with connect() as conn:
            paths = [r["path"] for r in conn.execute("SELECT path FROM documents ORDER BY id")]

        names = [Path(path).name for path in paths]
        assert names == sorted(names)
        assert names[0] == "doc_01.txt"

    def test_keywords_are_top_weighted_terms(self, sample_index, ids):
        with connect() as conn:
            keywords = conn.execute(
                "SELECT keywords FROM documents WHERE id = ?", (ids["doc_01.txt"],)
            ).fetchone()["keywords"]

        assert keywords == "cat, dog"       # cat весит больше: 3 * B_cat > 1 * B_dog


class TestLogicalSearch:
    def test_conjunction(self, ids):
        """AND: остаются только документы, содержащие все термины."""
        result = search(SearchParams(q="cat dog", all_words=True))

        assert result.mode == "and"
        assert not result.fallback
        assert [hit.doc_id for hit in result.hits] == [ids["doc_02.txt"], ids["doc_01.txt"]]

    def test_disjunction_ranks_by_matched_term_count_first(self, ids):
        """OR: сначала число совпавших слов, затем сумма весов TF-IDF.

        doc_05 («cat» пять раз) имеет больший вес TF-IDF, чем doc_01,
        но содержит только одно из двух слов запроса и поэтому ниже.
        """
        result = search(SearchParams(q="cat dog", all_words=False))

        assert result.mode == "or"
        order = [hit.doc_id for hit in result.hits]
        assert order == [ids["doc_02.txt"], ids["doc_01.txt"], ids["doc_05.txt"]]

        by_id = {hit.doc_id: hit for hit in result.hits}
        assert by_id[ids["doc_05.txt"]].matched_count == 1
        assert by_id[ids["doc_01.txt"]].matched_count == 2
        # Вес doc_05 больше веса doc_01, но приоритет у числа совпавших терминов.
        assert by_id[ids["doc_05.txt"]].rank > by_id[ids["doc_01.txt"]].rank

    def test_negation(self, ids):
        """NOT: документы с запрещённым термином исключаются."""
        result = search(SearchParams(q="cat -dog", all_words=False))

        assert [hit.doc_id for hit in result.hits] == [ids["doc_05.txt"]]

    def test_negation_applies_to_conjunction_too(self, ids):
        result = search(SearchParams(q="cat bird -dog", all_words=True))

        assert result.total == 0            # cat AND bird даёт doc_02, но он содержит dog

    def test_stemming_matches_word_forms(self, ids):
        """Запрос в другой словоформе находит те же документы."""
        assert ranked(SearchParams(q="cats", all_words=False)) == ranked(
            SearchParams(q="cat", all_words=False)
        )

    def test_stopwords_are_ignored(self, ids):
        assert ranked(SearchParams(q="the cat of", all_words=False)) == ranked(
            SearchParams(q="cat", all_words=False)
        )

    def test_empty_query(self):
        result = search(SearchParams(q="", all_words=True))

        assert result.total == 0
        assert result.hits == []
        assert result.doc_ids == ()

    def test_unknown_term_only(self):
        result = search(SearchParams(q="xylophone", all_words=True))

        assert result.total == 0
        assert result.unknown_terms == ("xylophone",)


class TestDefaultMode:
    """Режим по умолчанию — дизъюнкция (OR).

    Выбор обоснован свойством ранжирования: выдача строгой конъюнкции всегда
    оказывается началом выдачи дизъюнкции, поэтому OR по умолчанию показывает
    все те же документы на тех же позициях и дополнительно — документы
    с частичным совпадением. Ничего не теряется, а результатов больше.
    """

    def test_model_default_is_disjunction(self):
        assert SearchParams(q="cat").all_words is False
        assert SearchParams().all_words is False

    @pytest.mark.parametrize("query", ["cat", "cat dog", "cat bird", "dog bird", "cat dog bird"])
    def test_conjunction_is_a_prefix_of_disjunction(self, ids, query):
        """Документы со всеми словами запроса всегда стоят первыми."""
        conjunction = ranked(SearchParams(q=query, all_words=True))
        disjunction = ranked(SearchParams(q=query, all_words=False))

        assert disjunction[: len(conjunction)] == conjunction
        assert len(disjunction) >= len(conjunction)

    def test_disjunction_is_not_narrower(self, ids):
        assert len(ranked(SearchParams(q="cat dog", all_words=False))) > len(
            ranked(SearchParams(q="cat dog", all_words=True))
        )


class TestFallbackStrategy:
    """Стратегия с отказами (методичка: сведение ЕЯ-запроса к логическому)."""

    def test_unknown_term_relaxes_conjunction(self, ids):
        result = search(SearchParams(q="cat xylophone", all_words=True))

        assert result.fallback is True
        assert result.mode == "or"
        assert result.unknown_terms == ("xylophone",)
        assert result.known_terms == ("cat",)
        assert [hit.doc_id for hit in result.hits] == [
            ids["doc_05.txt"], ids["doc_01.txt"], ids["doc_02.txt"]
        ]

    def test_empty_conjunction_relaxes_to_disjunction(self, ids):
        """Все слова известны, но вместе не встречаются ни в одном документе."""
        assert search(SearchParams(q="cat zebra", all_words=True)).fallback is True

        result = search(SearchParams(q="cat zebra", all_words=True))

        assert result.mode == "or"
        assert result.unknown_terms == ()
        assert {hit.doc_id for hit in result.hits} == {
            ids["doc_01.txt"], ids["doc_02.txt"], ids["doc_04.txt"], ids["doc_05.txt"]
        }

    def test_no_fallback_when_conjunction_succeeds(self, ids):
        result = search(SearchParams(q="cat dog", all_words=True))

        assert result.fallback is False

    def test_fallback_can_be_disabled(self, monkeypatch, ids):
        from app import config

        monkeypatch.setattr(config, "ENABLE_FALLBACK", False)

        result = search(SearchParams(q="cat xylophone", all_words=True))

        assert result.total == 0
        assert result.fallback is False


class TestRanking:
    def test_tie_break_is_deterministic(self):
        """При равных весах порядок задаёт идентификатор документа."""
        candidates = {7, 3, 5}
        score = {3: 1.0, 5: 1.0, 7: 1.0}
        matched = {3: ["a"], 5: ["a"], 7: ["a"]}

        assert _rank(candidates, score, matched) == [3, 5, 7]

    def test_matched_count_outranks_weight(self):
        candidates = {1, 2}
        score = {1: 100.0, 2: 1.0}
        matched = {1: ["a"], 2: ["a", "b"]}

        assert _rank(candidates, score, matched) == [2, 1]

    def test_repeated_search_is_stable(self):
        params = SearchParams(q="cat dog", all_words=False)

        assert [ranked(params) for _ in range(5)] == [ranked(params)] * 5

    def test_positions_are_one_based_and_continuous(self, ids):
        result = search(SearchParams(q="cat", all_words=False), offset=1, limit=2)

        assert [hit.position for hit in result.hits] == [2, 3]


class TestPagination:
    def test_pages_partition_the_result(self, ids):
        params = SearchParams(q="cat", all_words=False)
        total = search(params).total

        first = search(params, offset=0, limit=2)
        second = search(params, offset=2, limit=2)

        assert first.total == total == second.total
        assert [h.doc_id for h in first.hits] + [h.doc_id for h in second.hits] == ranked(params)

    def test_offset_beyond_results(self):
        result = search(SearchParams(q="cat", all_words=False), offset=100, limit=10)

        assert result.hits == []
        assert result.total == 3            # общее число результатов сохраняется


class TestDateFilter:
    def test_range_restricts_results(self, ids):
        """Фильтр по дате сравнивает ISO-строки лексикографически."""
        dates = {
            ids["doc_01.txt"]: "2020-01-01",
            ids["doc_02.txt"]: "2024-06-01",
            ids["doc_05.txt"]: "2025-01-01",
        }
        with connect() as conn:
            original = {
                r["id"]: r["date"] for r in conn.execute("SELECT id, date FROM documents")
            }
            for doc_id, date in dates.items():
                conn.execute("UPDATE documents SET date = ? WHERE id = ?", (date, doc_id))

            try:
                result = search(
                    SearchParams(q="cat", all_words=False, date_start="2024-01-01")
                )
                assert {hit.doc_id for hit in result.hits} == {
                    ids["doc_02.txt"], ids["doc_05.txt"]
                }

                result = search(
                    SearchParams(
                        q="cat", all_words=False,
                        date_start="2024-01-01", date_end="2024-12-31",
                    )
                )
                assert {hit.doc_id for hit in result.hits} == {ids["doc_02.txt"]}
            finally:
                for doc_id, date in original.items():
                    conn.execute(
                        "UPDATE documents SET date = ? WHERE id = ?", (date, doc_id)
                    )


class TestRetrievalInternals:
    def test_retrieve_reports_known_and_unknown_terms(self):
        params = SearchParams(q="cat xylophone -dog", all_words=False)

        with connect() as conn:
            retrieval = retrieve(conn, params)

        assert retrieval.known == ["cat"]
        assert retrieval.unknown == ["xylophone"]
        assert "dog" in retrieval.query.exclude

    def test_hits_contain_required_fields(self, ids):
        """Требование методички: ссылка на документ и список слов запроса в нём."""
        result = search(SearchParams(q="cat dog", all_words=False), limit=1)
        hit = result.hits[0]

        assert hit.title
        assert "<mark>" in hit.snippet_html
        assert set(hit.matched_words) == {"cat", "dog"}
        assert hit.rank > 0
        assert hit.position == 1
        assert hit.keywords
