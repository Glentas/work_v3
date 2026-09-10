"""Сквозные проверки веб-интерфейса и JSON API."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client(sample_index):
    with TestClient(app) as test_client:
        yield test_client


class TestPages:
    @pytest.mark.parametrize(
        "url",
        ["/", "/help", "/metrics", "/search?q=cat&all_words=false",
         "/search?q=cat&all_words=false&page=2", "/api/status"],
    )
    def test_pages_render(self, client, url):
        response = client.get(url)
        assert response.status_code == 200

    def test_search_page_lists_results(self, client):
        html = client.get("/search?q=cat&all_words=false").text

        assert 'id="results-body"' in html
        assert 'class="result-checkbox"' in html
        assert "/documents/" in html
        assert "<mark>" in html

    def test_chart_library_is_local(self, client):
        """Графики не должны зависеть от CDN — система работает в локальной сети."""
        html = client.get("/metrics").text

        assert "/static/vendor/chart.umd.min.js" in html
        assert "cdn." not in html
        assert client.get("/static/vendor/chart.umd.min.js").status_code == 200

    def test_document_page(self, client, doc_id_by_name):
        response = client.get(f"/documents/{doc_id_by_name['doc_01.txt']}")

        assert response.status_code == 200
        assert "cat cat cat dog" in response.text

    def test_missing_document_returns_404(self, client):
        assert client.get("/documents/999999").status_code == 404

    def test_fallback_is_reported_to_user(self, client):
        """При пустой конъюнкции пользователь видит объяснение, а не пустоту."""
        html = client.get("/search?q=cat+xylophone&all_words=true").text

        # в шаблоне часть слов обёрнута в <strong>, поэтому проверяем непрерывный фрагмент
        assert "словами запроса не найдено" in html
        assert "показаны документы с частью слов" in html
        assert "xylophone" in html


class TestLogicalModeSwitch:
    """Регрессия: режим OR был недостижим из интерфейса.

    Чекбокс «Все слова вместе» в снятом состоянии вообще не отправляет
    параметр, сервер подставлял значение по умолчанию (True), а затем
    возвращал страницу с тем же отмеченным чекбоксом — снятие не работало.
    Переключатель заменён на радиокнопки, которые всегда отправляют
    ровно одно значение.
    """

    QUERY = "cat+dog"          # AND -> 2 документа, OR -> 3

    @staticmethod
    def badge(html: str) -> str | None:
        match = re.search(r'<span class="badge">(AND|OR)</span>', html)
        return match.group(1) if match else None

    def test_form_uses_radio_buttons(self, client):
        html = client.get(f"/search?q={self.QUERY}").text
        values = re.findall(
            r'<input type="radio"[^>]*name="all_words"[^>]*value="(true|false)"', html
        )

        assert sorted(values) == ["false", "true"]

    def test_default_mode_is_or(self, client):
        """Без явно заданного параметра поиск идёт по любому из слов.

        Регрессия: значение по умолчанию True делало выдачу уже, чем была
        до переделки интерфейса, — пользователь терял часть документов.
        """
        html = client.get(f"/search?q={self.QUERY}").text

        assert self.badge(html) == "OR"
        assert re.search(r'id="mode-or"[^>]*checked', html)
        assert re.search(r"Найдено: <strong>3</strong>", html)

    def test_explicit_or_is_applied(self, client):
        html = client.get(f"/search?q={self.QUERY}&all_words=false").text

        assert self.badge(html) == "or".upper()
        assert re.search(r'id="mode-or"[^>]*checked', html)

    def test_explicit_and_is_applied(self, client):
        html = client.get(f"/search?q={self.QUERY}&all_words=true").text

        assert self.badge(html) == "AND"
        assert re.search(r'id="mode-and"[^>]*checked', html)
        assert not re.search(r'id="mode-or"[^>]*checked', html)

    def test_modes_return_different_result_sets(self, client):
        and_total = re.search(
            r"Найдено: <strong>(\d+)</strong>",
            client.get(f"/search?q={self.QUERY}&all_words=true").text,
        ).group(1)
        or_total = re.search(
            r"Найдено: <strong>(\d+)</strong>",
            client.get(f"/search?q={self.QUERY}&all_words=false").text,
        ).group(1)

        assert and_total == "2"
        assert or_total == "3"

    def test_pagination_preserves_mode(self, client, monkeypatch):
        """Ссылки на другие страницы не должны терять выбранный режим.

        Размер страницы уменьшен, иначе на тестовой коллекции из пяти
        документов пагинация не появляется вовсе.
        """
        from app import config

        monkeypatch.setattr(config, "PER_PAGE", 2)

        html = client.get("/search?q=cat&all_words=false").text
        links = re.findall(r'href="(/search\?[^"]+page=\d+)"', html)

        assert links, "при PER_PAGE=2 и трёх результатах должна появиться пагинация"
        assert "all_words=false" in links[0]
        assert "q=cat" in links[0]


class TestJsonApi:
    def test_search_endpoint(self, client, doc_id_by_name):
        data = client.get("/api/search?q=cat+dog&all_words=false&limit=2").json()

        assert data["mode"] == "or"
        assert data["total"] == 3
        assert len(data["results"]) == 2
        first = data["results"][0]
        assert first["doc_id"] == doc_id_by_name["doc_02.txt"]
        assert first["position"] == 1
        assert set(first["matched_words"]) == {"cat", "dog"}
        assert first["url"] == f"/documents/{first['doc_id']}"

    def test_pr_curve_returns_cuts_and_interpolation(self, client, doc_id_by_name):
        """График отдаёт и интерполяцию, и фактические срезы выдачи."""
        params = {"q": "cat dog", "all_words": False, "date_start": "", "date_end": ""}
        client.post("/api/deselect-all", json=params)

        ranked = [r["doc_id"] for r in client.get(
            "/api/search?q=cat+dog&all_words=false").json()["results"]]
        # Отмечаем 1-й и 3-й документы: кривая должна иметь ступень.
        for doc_id in (ranked[0], ranked[2]):
            client.post(
                "/api/relevance",
                json={"params": params, "doc_id": doc_id, "relevant": True},
            )
        query_id = client.post("/api/save-metrics", json=params).json()["query_id"]

        data = client.get(f"/api/pr-curve/{query_id}").json()

        assert len(data["interpolated"]) == 11
        assert data["relevant_positions"] == [1, 3]
        assert data["cuts"] == [[0.5, 1.0], [1.0, 2 / 3]]
        assert data["interpolated"][:6] == [1.0] * 6
        assert all(abs(v - 2 / 3) < 1e-9 for v in data["interpolated"][6:])

        client.post("/api/deselect-all", json=params)

    def test_pr_curve_for_unknown_query(self, client):
        assert client.get("/api/pr-curve/999999").status_code == 404

    def test_status_reports_index(self, client):
        data = client.get("/api/status").json()

        assert data["index"]["documents"] == 5
        assert data["index"]["terms"] > 0
        assert data["fallback_enabled"] is True


class TestEvaluationFlow:
    """Полный цикл: разметка релевантности -> сохранение оценки -> графики."""

    PARAMS = {"q": "cat dog", "all_words": False, "date_start": "", "date_end": ""}

    @pytest.fixture(autouse=True)
    def _clean(self, clean_evaluations):
        """Каждая проверка потока оценки начинается с чистой базы отметок."""

    def test_metrics_require_relevant_documents(self, client):
        client.post("/api/deselect-all", json=self.PARAMS)

        response = client.post("/api/save-metrics", json=self.PARAMS)

        assert response.status_code == 400
        assert "релевантн" in response.json()["detail"].lower()

    def test_marking_and_saving(self, client, doc_id_by_name):
        client.post("/api/deselect-all", json=self.PARAMS)

        ranked = [r["doc_id"] for r in client.get(
            "/api/search?q=cat+dog&all_words=false").json()["results"]
        ]
        assert ranked == [
            doc_id_by_name["doc_02.txt"],
            doc_id_by_name["doc_01.txt"],
            doc_id_by_name["doc_05.txt"],
        ]

        # Отмечаем 1-й и 3-й документы выдачи.
        for doc_id in (ranked[0], ranked[2]):
            response = client.post(
                "/api/relevance",
                json={"params": self.PARAMS, "doc_id": doc_id, "relevant": True},
            )
            assert response.status_code == 200
            query_id = response.json()["query_id"]

        metrics = client.post("/api/save-metrics", json=self.PARAMS).json()

        assert metrics["total_found"] == 3
        assert metrics["total_relevant"] == 2
        assert metrics["found_relevant"] == 2
        # Позиции отсчитываются от 1: отмечены первый и третий документы.
        assert metrics["recall"] == pytest.approx(1.0)
        assert metrics["precision"] == pytest.approx(2 / 3)
        assert metrics["avg_prec"] == pytest.approx((1 / 1 + 2 / 3) / 2)
        assert metrics["p5"] == pytest.approx(2 / 5)
        assert metrics["r_prec"] == pytest.approx(1 / 2)
        assert metrics["f_measure"] == pytest.approx(
            2 * (2 / 3) * 1.0 / (2 / 3 + 1.0)
        )

        curve = client.get(f"/api/pr-curve/{query_id}").json()["interpolated"]
        assert len(curve) == 11

        summary = client.get("/api/metrics/summary").json()
        assert summary["total_queries"] >= 1
        assert summary["micro"]["precision"] == pytest.approx(2 / 3)
        assert len(summary["avg_pr_curve"]) == 11

        rows = client.get("/api/metrics").json()["rows"]
        assert any(row["query_text"] == "cat dog" for row in rows)

        client.post("/api/deselect-all", json=self.PARAMS)

    def test_unmark_removes_document(self, client, doc_id_by_name):
        params = {"q": "zebra", "all_words": False, "date_start": "", "date_end": ""}
        doc_id = doc_id_by_name["doc_04.txt"]

        client.post("/api/relevance", json={"params": params, "doc_id": doc_id, "relevant": True})
        client.post("/api/relevance", json={"params": params, "doc_id": doc_id, "relevant": False})

        assert client.post("/api/save-metrics", json=params).status_code == 400

    def test_select_all_marks_whole_result_set(self, client):
        params = {"q": "bird", "all_words": False, "date_start": "", "date_end": ""}

        data = client.post("/api/select-all", json=params).json()
        assert data["count"] == 2

        metrics = client.post("/api/save-metrics", json=params).json()
        # Вся выдача отмечена релевантной -> метрики вырождаются в единицу.
        assert metrics["recall"] == pytest.approx(1.0)
        assert metrics["precision"] == pytest.approx(1.0)

        client.post("/api/deselect-all", json=params)
        assert client.post("/api/save-metrics", json=params).status_code == 400

    def test_batch_marking(self, client, doc_id_by_name):
        params = {"q": "cat", "all_words": False, "date_start": "", "date_end": ""}
        doc_ids = [doc_id_by_name["doc_01.txt"], doc_id_by_name["doc_05.txt"]]

        client.post("/api/deselect-all", json=params)
        response = client.post(
            "/api/relevance-batch",
            json={"params": params, "doc_ids": doc_ids, "relevant": True},
        )
        assert response.status_code == 200

        metrics = client.post("/api/save-metrics", json=params).json()
        assert metrics["total_relevant"] == 2

        client.post(
            "/api/relevance-batch",
            json={"params": params, "doc_ids": doc_ids, "relevant": False},
        )
        assert client.post("/api/save-metrics", json=params).status_code == 400
