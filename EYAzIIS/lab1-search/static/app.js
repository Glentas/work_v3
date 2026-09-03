document.addEventListener("DOMContentLoaded", function () {
    initSearchPage();
    initMetricsPage();
});

function initSearchPage() {
    const page = document.getElementById("search-page");
    if (!page) return;

    const params = {
        q: page.dataset.q || "",
        all_words: page.dataset.allWords === "true",
        date_start: page.dataset.dateStart || "",
        date_end: page.dataset.dateEnd || ""
    };

    let queryId = parseInt(page.dataset.queryId || "0", 10);

    const body = document.getElementById("results-body");
    const selectPage = document.getElementById("select-page");
    const selectAll = document.getElementById("select-all");
    const saveBtn = document.getElementById("save-metrics");
    const saveMessage = document.getElementById("save-message");

    function updateSelectPageState() {
        if (!selectPage) return;

        const boxes = Array.from(body.querySelectorAll(".result-checkbox"));
        if (!boxes.length) {
            selectPage.checked = false;
            return;
        }

        selectPage.checked = boxes.every(cb => cb.checked);
    }

    body.addEventListener("change", function (event) {
        const checkbox = event.target.closest(".result-checkbox");
        if (!checkbox) return;

        const docId = parseInt(checkbox.dataset.docId, 10);
        updateRelevance(docId, checkbox.checked);
        updateSelectPageState();
    });

    if (selectPage) {
        selectPage.addEventListener("change", function () {
            const boxes = Array.from(body.querySelectorAll(".result-checkbox"));
            const docIds = boxes.map(cb => parseInt(cb.dataset.docId, 10));

            boxes.forEach(cb => {
                cb.checked = selectPage.checked;
            });

            batchRelevance(docIds, selectPage.checked);
        });
    }

    if (selectAll) {
        selectAll.addEventListener("change", function () {
            const boxes = Array.from(body.querySelectorAll(".result-checkbox"));

            boxes.forEach(cb => {
                cb.checked = selectAll.checked;
            });

            updateSelectPageState();

            if (selectAll.checked) {
                fetch("/api/select-all", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(params)
                })
                    .then(response => response.json())
                    .then(data => {
                        queryId = data.query_id;
                        page.dataset.queryId = queryId;
                    })
                    .catch(error => {
                        console.error(error);
                        alert("Не удалось выбрать все результаты.");
                    });
            } else {
                fetch("/api/deselect-all", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(params)
                })
                    .then(response => response.json())
                    .then(data => {
                        queryId = data.query_id;
                        page.dataset.queryId = queryId;
                    })
                    .catch(error => {
                        console.error(error);
                        alert("Не удалось снять выбор со всех результатов.");
                    });
            }
        });
    }

    if (saveBtn) {
        saveBtn.addEventListener("click", function () {
            saveMessage.textContent = "Сохранение...";

            fetch("/api/save-metrics", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(params)
            })
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(data => {
                            throw new Error(data.error || "Ошибка сохранения оценки.");
                        });
                    }
                    return response.json();
                })
                .then(metrics => {
                    saveMessage.textContent =
                        "Оценка сохранена. Перейдите на страницу «Метрики», чтобы посмотреть результаты.";
                })
                .catch(error => {
                    saveMessage.textContent = error.message;
                });
        });
    }

    updateSelectPageState();

    function updateRelevance(docId, relevant) {
        const payload = {
            params: params,
            doc_id: docId,
            relevant: relevant
        };

        fetch("/api/relevance", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        })
            .then(response => response.json())
            .then(data => {
                queryId = data.query_id;
                page.dataset.queryId = queryId;
            })
            .catch(error => console.error(error));
    }

    function batchRelevance(docIds, relevant) {
        if (!docIds.length) return;

        const payload = {
            params: params,
            doc_ids: docIds,
            relevant: relevant
        };

        fetch("/api/relevance-batch", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        })
            .then(response => response.json())
            .then(data => {
                queryId = data.query_id;
                page.dataset.queryId = queryId;
            })
            .catch(error => console.error(error));
    }
}

function initMetricsPage() {
    const scroll = document.getElementById("metrics-scroll");
    if (!scroll) return;

    const tbody = document.getElementById("metrics-body");
    const limit = 100;

    let offset = 0;
    let loading = false;
    let done = false;

    function fmt(value) {
        if (value === null || value === undefined) return "-";
        return Number(value).toFixed(3);
    }

    function escapeHtml(value) {
        if (!value) return "";

        return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;");
    }

    function loadRows() {
        if (loading || done) return;

        loading = true;

        fetch(`/api/metrics?offset=${offset}&limit=${limit}`)
            .then(response => response.json())
            .then(data => {
                data.rows.forEach(row => {
                    const tr = document.createElement("tr");
                    tr.dataset.queryId = row.query_id;

                    tr.innerHTML = `
                        <td>${escapeHtml(row.query_text)}</td>
                        <td>${fmt(row.recall)}</td>
                        <td>${fmt(row.precision)}</td>
                        <td>${fmt(row.avg_prec)}</td>
                        <td>${fmt(row.p5)}</td>
                        <td>${fmt(row.p10)}</td>
                        <td>${fmt(row.r_prec)}</td>
                        <td>${escapeHtml(row.created_at)}</td>
                    `;

                    tr.addEventListener("click", function () {
                        selectMetricRow(tr);
                    });

                    tbody.appendChild(tr);
                });

                offset += data.rows.length;

                if (data.rows.length < limit) {
                    done = true;
                }

                loading = false;
            })
            .catch(error => {
                console.error(error);
                loading = false;
            });
    }

    scroll.addEventListener("scroll", function () {
        if (scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 50) {
            loadRows();
        }
    });

    loadRows();

    const avgChartBtn = document.getElementById("show-avg-chart");

    if (avgChartBtn) {
        avgChartBtn.addEventListener("click", function () {
            showAverageChart();
        });
    }

    if (window.hasMetrics) {
        showAverageChart();
    }
}

let prChart = null;

function selectMetricRow(tr) {
    document.querySelectorAll("#metrics-body tr.selected").forEach(el => {
        el.classList.remove("selected");
    });

    tr.classList.add("selected");

    const queryId = tr.dataset.queryId;

    fetch(`/api/pr-curve/${queryId}`)
        .then(response => response.json())
        .then(curve => {
            renderPrChart(curve, `Запрос: ${tr.cells[0].textContent}`);
        })
        .catch(error => console.error(error));
}

function showAverageChart() {
    renderPrChart(window.avgPrCurve, "Усреднённый график по всем запросам");
}

function renderPrChart(curve, label) {
    const ctx = document.getElementById("pr-chart");
    if (!ctx) return;

    const labels = Array.from({length: 11}, (_, index) => (index / 10).toFixed(1));

    if (prChart) {
        prChart.destroy();
    }

    prChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: label,
                    data: curve,
                    borderColor: "#2563eb",
                    backgroundColor: "rgba(37, 99, 235, 0.12)",
                    fill: true,
                    tension: 0.2
                }
            ]
        },
        options: {
            scales: {
                x: {
                    title: {
                        display: true,
                        text: "Полнота"
                    }
                },
                y: {
                    min: 0,
                    max: 1,
                    title: {
                        display: true,
                        text: "Точность"
                    }
                }
            },
            plugins: {
                legend: {
                    display: true
                }
            }
        }
    });
}