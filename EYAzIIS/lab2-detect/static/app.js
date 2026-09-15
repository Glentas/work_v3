/* Клиентская логика страницы результатов: два столбчатых графика.
   Данные передаёт шаблон через window.CHART_DATA. Библиотека Chart.js
   подключается локально из static/vendor/, без CDN. */

(function () {
    "use strict";

    var data = window.CHART_DATA;
    if (!data || typeof Chart === "undefined") {
        return;
    }

    function bar(canvasId, title, values, suffix) {
        var canvas = document.getElementById(canvasId);
        if (!canvas) {
            return;
        }
        new Chart(canvas, {
            type: "bar",
            data: {
                labels: data.labels,
                datasets: [{
                    label: title,
                    data: values,
                    backgroundColor: ["#2563eb", "#15803d", "#b45309"],
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: { display: true, text: title },
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                return ctx.parsed.y + suffix;
                            }
                        }
                    }
                },
                scales: { y: { beginAtZero: true } }
            }
        });
    }

    bar("chart-accuracy", "Точность методов, %", data.accuracy, "%");
    bar("chart-time", "Медиана времени на документ, мс", data.time, " мс");
})();
