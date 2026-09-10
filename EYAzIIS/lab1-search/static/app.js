/* Клиентская логика интерфейса информационно-поисковой системы.
 *
 * Два независимых модуля: страница поиска (разметка релевантности)
 * и страница метрик (таблицы и графики). Внешних ресурсов нет —
 * библиотека Chart.js подключается из static/vendor/.
 */
(() => {
    "use strict";

    // ------------------------------------------------------------------
    // Утилиты
    // ------------------------------------------------------------------
    const $ = (selector, root = document) => root.querySelector(selector);

    const number = (value, digits = 3) =>
        value === null || value === undefined ? "—" : Number(value).toFixed(digits);

    async function send(url, body) {
        const response = await fetch(url, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            let detail = `Ошибка сервера (${response.status})`;
            try {
                detail = (await response.json()).detail || detail;
            } catch { /* тело ответа не JSON — оставляем статус */ }
            throw new Error(detail);
        }

        return response.json();
    }

    async function load(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`Ошибка сервера (${response.status})`);
        return response.json();
    }

    // ------------------------------------------------------------------
    // Страница поиска: разметка релевантности
    // ------------------------------------------------------------------
    function initSearchPage() {
        const root = $("#search-page");
        if (!root) return;

        const params = JSON.parse(root.dataset.params);
        const total = Number(root.dataset.total || 0);
        const body = $("#results-body");
        const message = $("#save-message");
        const judged = $("#judged-count");
        const selectPage = $("#select-page");
        const selectPageLabel = $("#select-page-label");
        const selectAll = $("#select-all");
        const saveButton = $("#save-metrics");

        const boxes = () => Array.from(body.querySelectorAll(".result-checkbox"));

        function notify(text, kind = "info") {
            if (!text) {
                message.innerHTML = "";
                return;
            }
            const icon = kind === "danger" ? "✕" : kind === "ok" ? "✓" : kind === "warn" ? "!" : "i";
            message.innerHTML =
                `<div class="banner banner-${kind}">` +
                `<span class="banner-icon">${icon}</span><span>${text}</span></div>`;
        }

        // Счётчик размеченных документов всей выдачи (не только текущей страницы).
        let judgedCount = Number(judged.textContent) || 0;

        function setJudged(value) {
            judgedCount = Math.max(0, Math.min(total, value));
            judged.textContent = judgedCount;
        }

        /**
         * Групповой чекбокс страницы имеет три состояния:
         * галочка — отмечены все, черта (indeterminate) — отмечена часть,
         * пусто — ни одного. Черта — стандартное обозначение частичного
         * выбора, но она непонятна без пояснения, поэтому подпись рядом
         * показывает конкретное число отмеченных документов.
         */
        function syncSelectPage() {
            if (!selectPage) return;

            const list = boxes();
            const marked = list.filter(cb => cb.checked).length;
            const all = list.length > 0 && marked === list.length;

            selectPage.checked = all;
            selectPage.indeterminate = !all && marked > 0;

            if (selectPageLabel) {
                selectPageLabel.textContent = marked > 0 && !all
                    ? `Отмечено ${marked} из ${list.length} на странице`
                    : "Все на странице";
            }
        }

        async function mark(docIds, relevant) {
            const url = docIds.length === 1 ? "/api/relevance" : "/api/relevance-batch";
            const payload = docIds.length === 1
                ? {params, doc_id: docIds[0], relevant}
                : {params, doc_ids: docIds, relevant};

            const data = await send(url, payload);
            root.dataset.queryId = data.query_id;
            return data;
        }

        body.addEventListener("change", async (event) => {
            const checkbox = event.target.closest(".result-checkbox");
            if (!checkbox) return;

            try {
                await mark([Number(checkbox.dataset.docId)], checkbox.checked);
                setJudged(judgedCount + (checkbox.checked ? 1 : -1));
                notify("");
            } catch (error) {
                checkbox.checked = !checkbox.checked;   // откатываем состояние
                notify(error.message, "danger");
            }
            syncSelectPage();
        });

        if (selectPage) {
            selectPage.addEventListener("change", async () => {
                const list = boxes();
                const before = list.filter(cb => cb.checked).length;
                list.forEach(cb => { cb.checked = selectPage.checked; });
                const delta = (selectPage.checked ? list.length : 0) - before;

                try {
                    await mark(list.map(cb => Number(cb.dataset.docId)), selectPage.checked);
                    setJudged(judgedCount + delta);
                    notify("");
                } catch (error) {
                    list.forEach(cb => { cb.checked = !selectPage.checked; });
                    notify(error.message, "danger");
                }
            });
        }

        if (selectAll) {
            selectAll.addEventListener("change", async () => {
                if (selectAll.checked) {
                    const confirmed = confirm(
                        `Отметить все ${total} найденных документов как релевантные?\n\n` +
                        "Внимание: при такой разметке полнота и точность становятся равными 1,\n" +
                        "и оценка теряет смысл. Режим предназначен для проверки расчёта метрик."
                    );
                    if (!confirmed) {
                        selectAll.checked = false;
                        return;
                    }
                }

                try {
                    const data = await send(
                        selectAll.checked ? "/api/select-all" : "/api/deselect-all",
                        params
                    );
                    root.dataset.queryId = data.query_id;
                    boxes().forEach(cb => { cb.checked = selectAll.checked; });
                    setJudged(selectAll.checked ? data.count ?? total : 0);

                    if (selectAll.checked) {
                        notify(
                            `Отмечены все найденные документы (${data.count}). ` +
                            "Метрики для такой разметки будут равны 1.000 — " +
                            "это проверка механизма расчёта, а не результат оценки.",
                            "warn"
                        );
                    } else {
                        notify("Все отметки сняты.", "ok");
                    }
                } catch (error) {
                    selectAll.checked = !selectAll.checked;
                    notify(error.message, "danger");
                }
                syncSelectPage();
            });
        }

        if (saveButton) {
            saveButton.addEventListener("click", async () => {
                saveButton.disabled = true;
                notify("Вычисление оценок…", "info");

                try {
                    const m = await send("/api/save-metrics", params);
                    notify(
                        "Оценка сохранена. " +
                        `Найдено ${m.total_found}, отмечено релевантными ${m.total_relevant}, ` +
                        `из них в выдаче ${m.found_relevant}. ` +
                        `Precision ${number(m.precision)} · F-мера ${number(m.f_measure)} · ` +
                        `AvgPrec ${number(m.avg_prec)} · P@10 ${number(m.p10)} · ` +
                        `R-Prec ${number(m.r_prec)}. ` +
                        `<a href="/metrics">Открыть страницу метрик →</a>`,
                        "ok"
                    );
                } catch (error) {
                    notify(error.message, "danger");
                } finally {
                    saveButton.disabled = false;
                }
            });
        }

        syncSelectPage();
    }

    // ------------------------------------------------------------------
    // Страница метрик: таблицы и графики
    // ------------------------------------------------------------------
    const chartTheme = {
        accent: "rgba(37, 99, 235, 1)",
        accentSoft: "rgba(37, 99, 235, 0.14)",
        cuts: "#22c55e",          // яркие зелёные маркеры фактических срезов
        grid: "rgba(15, 23, 42, 0.07)",
        text: "#475569"
    };

    function barGradient(context) {
        const {ctx, chartArea} = context.chart;
        if (!chartArea) return chartTheme.accent;

        const gradient = ctx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
        gradient.addColorStop(0, "rgba(37, 99, 235, 0.70)");
        gradient.addColorStop(1, "rgba(124, 58, 237, 0.95)");
        return gradient;
    }

    function lineGradient(context) {
        const {ctx, chartArea} = context.chart;
        if (!chartArea) return chartTheme.accentSoft;

        const gradient = ctx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
        gradient.addColorStop(0, "rgba(37, 99, 235, 0.02)");
        gradient.addColorStop(1, "rgba(37, 99, 235, 0.28)");
        return gradient;
    }

    function renderBarChart(data) {
        const canvas = $("#metrics-bar-chart");
        if (!canvas || typeof Chart === "undefined") return;

        const values = data.fields.map(field => data.macro[field]);

        new Chart(canvas, {
            type: "bar",
            data: {
                labels: data.labels,
                datasets: [{
                    label: "Среднее значение",
                    data: values,
                    backgroundColor: barGradient,
                    borderRadius: 7,
                    borderSkipped: false,
                    maxBarThickness: 58
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {display: true},
                    // точные значения уже показаны плитками над диаграммой
                    tooltip: {enabled: true}
                },
                scales: {
                    y: {
                        min: 0,
                        max: 1,
                        ticks: {stepSize: 0.2, color: chartTheme.text},
                        grid: {color: chartTheme.grid}
                    },
                    x: {
                        ticks: {color: chartTheme.text, font: {size: 11.5}},
                        grid: {display: false}
                    }
                }
            }
        });
    }

    let prChart = null;

    /**
     * График полнота/точность.
     *
     * Повторяет рис. 2 методички РОМИП: маркерами показаны фактические срезы
     * выдачи, пунктирной линией — интерполированные значения точности.
     * Ось X линейная, потому что полнота на срезах принимает дробные значения
     * (1/3, 2/3), не совпадающие с сеткой из 11 уровней.
     *
     * Сглаживание (tension) отключено намеренно: интерполированная точность —
     * ступенчатая функция, и кривая Безье искажала бы её, превращая ступень
     * в наклонную прямую.
     */
    function renderPrChart(data, label) {
        const canvas = $("#pr-chart");
        if (!canvas || typeof Chart === "undefined") return;

        const curve = data.interpolated || [];
        const cuts = data.cuts || [];

        if (prChart) prChart.destroy();

        prChart = new Chart(canvas, {
            type: "line",
            data: {
                datasets: [
                    {
                        label: label,
                        data: curve.map((y, index) => ({x: index / 10, y})),
                        borderColor: chartTheme.accent,
                        backgroundColor: lineGradient,
                        borderWidth: 2.2,
                        borderDash: [7, 4],
                        fill: true,
                        tension: 0,
                        pointRadius: 2.5,
                        pointHoverRadius: 4,
                        pointBackgroundColor: "#ffffff",
                        pointBorderColor: chartTheme.accent,
                        pointBorderWidth: 2
                    },
                    {
                        label: "Фактические срезы выдачи",
                        data: cuts.map(cut => ({x: cut[0], y: cut[1]})),
                        showLine: false,
                        borderColor: chartTheme.cuts,
                        backgroundColor: chartTheme.cuts,
                        pointRadius: 3,
                        pointHoverRadius: 4,
                        pointStyle: "rectRot"
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {color: chartTheme.text, usePointStyle: true, boxWidth: 8}
                    },
                    tooltip: {enabled: true}
                },
                scales: {
                    x: {
                        type: "linear",
                        min: 0,
                        max: 1,
                        title: {display: true, text: "Полнота (recall)", color: chartTheme.text},
                        ticks: {
                            stepSize: 0.1,
                            color: chartTheme.text,
                            callback: value => Number(value).toFixed(1)
                        },
                        grid: {color: chartTheme.grid}
                    },
                    y: {
                        min: 0,
                        max: 1,
                        title: {display: true, text: "Точность (precision)", color: chartTheme.text},
                        ticks: {stepSize: 0.2, color: chartTheme.text},
                        grid: {color: chartTheme.grid}
                    }
                }
            }
        });
    }

    function initMetricsPage() {
        const data = window.metricsData;
        if (!data) return;

        if (data.hasMetrics) {
            renderBarChart(data);
            renderPrChart(data.avgPrCurve, "Усреднённый график по всем запросам");
        }

        const showAverage = $("#show-avg-chart");
        if (showAverage) {
            showAverage.addEventListener("click", () =>
                renderPrChart(
                    {interpolated: data.avgPrCurve, cuts: []},
                    "Усреднённая интерполированная точность"
                ));
        }

        initMetricsTable();
    }

    function initMetricsTable() {
        const scroll = $("#metrics-scroll");
        const body = $("#metrics-body");
        if (!scroll || !body) return;

        const pageSize = 100;
        let offset = 0;
        let loading = false;
        let finished = false;

        function cell(value) {
            const td = document.createElement("td");
            td.className = "num";
            td.textContent = number(value);
            return td;
        }

        function textCell(value) {
            const td = document.createElement("td");
            td.textContent = value ?? "";
            return td;
        }

        function addRow(row) {
            const tr = document.createElement("tr");
            tr.className = "clickable";
            tr.dataset.queryId = row.query_id;

            tr.append(
                textCell(row.query_text),
                textCell(row.total_found),
                textCell(row.total_relevant),
                cell(row.recall),
                cell(row.precision),
                cell(row.f_measure),
                cell(row.avg_prec),
                cell(row.p5),
                cell(row.p10),
                cell(row.r_prec),
                textCell(row.created_at)
            );

            tr.addEventListener("click", () => selectRow(tr, row.query_text));
            body.appendChild(tr);
        }

        async function loadRows() {
            if (loading || finished) return;
            loading = true;

            try {
                const data = await load(`/api/metrics?offset=${offset}&limit=${pageSize}`);
                data.rows.forEach(addRow);
                offset += data.rows.length;
                finished = offset >= data.total || data.rows.length === 0;
            } catch (error) {
                console.error(error);
                finished = true;
            } finally {
                loading = false;
            }
        }

        scroll.addEventListener("scroll", () => {
            if (scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 60) {
                loadRows();
            }
        });

        loadRows();
    }

    async function selectRow(row, queryText) {
        document.querySelectorAll("#metrics-body tr.selected")
            .forEach(el => el.classList.remove("selected"));
        row.classList.add("selected");

        try {
            const data = await load(`/api/pr-curve/${row.dataset.queryId}`);
            renderPrChart(data, `Интерполированная точность — «${queryText}»`);
        } catch (error) {
            console.error(error);
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        initSearchPage();
        initMetricsPage();
    });
})();
