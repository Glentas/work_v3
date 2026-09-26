/* Клиентская логика системы перевода: небольшие улучшения интерфейса.
   Основные действия (вкладки, выбор предложения) выполняются ссылками и
   формами на сервере — скрипт не обязателен для работы системы. */

(function () {
    "use strict";

    // Автоподстройка высоты основного текстового поля.
    document.querySelectorAll("textarea").forEach(function (area) {
        function resize() {
            area.style.height = "auto";
            area.style.height = Math.max(90, area.scrollHeight) + "px";
        }
        area.addEventListener("input", resize);
        resize();
    });

    // Подстановка демо-текста: клик по «Подставить» уже обрабатывается
    // сервером; здесь лишь фокус на поле после загрузки.
    var text = document.getElementById("text");
    if (text && text.value.trim()) {
        text.focus();
    }

    // Фильтры словаря: отправка по Enter выполняется формой;
    // добавляем сброс поля поиска по Escape.
    var search = document.querySelector(".filters input[name='q']");
    if (search) {
        search.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                search.value = "";
                search.form.submit();
            }
        });
    }
})();
