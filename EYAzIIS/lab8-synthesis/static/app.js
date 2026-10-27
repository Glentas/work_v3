/* Лабораторная работа 8. Система синтеза речи (вариант 7 — немецкий язык).
 *
 * Два движка синтеза:
 *   • browser — Web Speech API (speechSynthesis): голоса ОС, подсветка предложений;
 *   • server  — espeak-ng на сервере (Flask /api/tts -> WAV -> <audio>):
 *               надёжно в Firefox/LibreWolf, где Web Speech API не настроен.
 *
 * Доп. возможности: озвучивание выделенного мышью фрагмента, подсветка текущего
 * предложения, загрузка/сохранение .txt + drag-and-drop, сохранение настроек в
 * localStorage, статистика текста, пресеты темпа, горячие клавиши, темы.
 */
(function () {
    "use strict";

    const synth = window.speechSynthesis;
    const LS = "lab8.";
    const WPM = 150; // средняя скорость чтения вслух (слов/мин) при темпе 1.0

    const el = {};
    const IDS = [
        "text", "chars", "words", "time", "voice", "rate", "pitch", "volume",
        "rateVal", "pitchVal", "volumeVal", "speak", "pause", "stop", "paste",
        "open", "save", "clear", "file", "samples", "status", "reader",
        "speakSel", "theme", "resetSettings", "audio", "engineNote",
    ];

    let engine = "browser";        // активный движок
    let voices = [];               // голоса браузера (все)
    let deVoices = [];             // голоса браузера (немецкие)
    let serverVoices = [];         // голоса серверного движка
    let serverAvailable = false;   // найден ли espeak-ng на сервере
    let sentences = [];            // [{start,end,node}] для подсветки
    let selText = "";              // выделенный мышью фрагмент

    /* --- Утилиты -------------------------------------------------------- */
    const $ = (id) => document.getElementById(id);
    const setStatus = (m) => { el.status.textContent = m; };
    const store = {
        get: (k, d) => (localStorage.getItem(LS + k) ?? d),
        set: (k, v) => localStorage.setItem(LS + k, v),
    };
    const engineRadios = () => document.querySelectorAll('input[name="engine"]');

    function fmtTime(sec) {
        sec = Math.max(0, Math.round(sec));
        return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
    }

    /* --- Голоса (зависят от движка) -------------------------------------- */
    function readBrowserVoices() {
        voices = synth ? synth.getVoices() : [];
        deVoices = voices.filter((v) => (v.lang || "").toLowerCase().startsWith("de"));
    }

    function populateVoiceSelect() {
        el.voice.innerHTML = "";
        if (engine === "server") {
            if (!serverAvailable) {
                const o = document.createElement("option");
                o.textContent = "espeak-ng не найден на сервере";
                o.disabled = true;
                el.voice.appendChild(o);
                return;
            }
            serverVoices.forEach((v) => addOption(v.id, `${v.label}  [${v.id}]`));
        } else {
            const list = deVoices.length ? deVoices : voices;
            list.forEach((v) => addOption(v.name, `${v.name} (${v.lang})${v.default ? " — по умолчанию" : ""}`));
        }
        // восстановить сохранённый для этого движка голос
        const saved = store.get("voice." + engine, "");
        if (saved && [...el.voice.options].some((o) => o.value === saved && !o.disabled)) {
            el.voice.value = saved;
        }
    }

    function addOption(value, label) {
        const o = document.createElement("option");
        o.value = value; o.textContent = label;
        el.voice.appendChild(o);
    }

    function selectedBrowserVoice() {
        return voices.find((v) => v.name === el.voice.value) || null;
    }

    function updateEngineNote() {
        if (engine === "server") {
            el.engineNote.textContent = serverAvailable
                ? "Серверный движок: espeak-ng синтезирует WAV на сервере. Подсветка предложений недоступна."
                : "espeak-ng не найден на сервере. Установите (Arch): sudo pacman -S espeak-ng — и перезапустите приложение.";
        } else {
            el.engineNote.textContent = deVoices.length
                ? `Браузерный движок: немецких голосов найдено ${deVoices.length}.`
                : "Браузерный движок: немецкие голоса не найдены. Переключитесь на серверный движок (espeak-ng) — он работает в Firefox/LibreWolf.";
        }
    }

    function setEngine(next, { save = true } = {}) {
        engine = next;
        engineRadios().forEach((r) => (r.checked = r.value === engine));
        if (save) store.set("engine", engine);
        stopAll();
        populateVoiceSelect();
        updateEngineNote();
    }

    /* --- Читалка и подсветка (только браузерный движок) ------------------ */
    function splitSentences(text) {
        const out = [];
        const term = new Set([".", "!", "?", "…"]);
        const closers = new Set(["”", "’", "\"", "»", "‹", ")", "]"]);
        let start = 0, i = 0;
        while (i < text.length) {
            if (term.has(text[i])) {
                let j = i + 1;
                while (j < text.length && closers.has(text[j])) j++;
                while (j < text.length && /\s/.test(text[j])) j++;
                out.push({ start, end: j }); start = j; i = j;
            } else i++;
        }
        if (start < text.length) out.push({ start, end: text.length });
        return out;
    }

    function buildReader(text) {
        el.reader.innerHTML = ""; sentences = [];
        if (!text.trim()) {
            const p = document.createElement("span");
            p.className = "placeholder";
            p.textContent = "Загрузите пример или введите текст — он появится здесь. " +
                "В браузерном режиме текущее предложение подсвечивается.";
            el.reader.appendChild(p); return;
        }
        splitSentences(text).forEach((s) => {
            const node = document.createElement("span");
            node.className = "sent";
            node.textContent = text.slice(s.start, s.end);
            el.reader.appendChild(node);
            sentences.push({ start: s.start, end: s.end, node });
        });
    }

    function highlightAt(charIndex) {
        const cur = sentences.find((s) => charIndex >= s.start && charIndex < s.end);
        if (!cur) return;
        sentences.forEach((s) => s.node.classList.toggle("active", s === cur));
        cur.node.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    const clearHighlight = () => sentences.forEach((s) => s.node.classList.remove("active"));

    /* --- Статистика ------------------------------------------------------ */
    function updateStats() {
        const text = el.text.value;
        const words = (text.trim().match(/\S+/g) || []).length;
        const rate = parseFloat(el.rate.value) || 1;
        el.chars.textContent = text.length;
        el.words.textContent = words;
        el.time.textContent = words ? fmtTime((words / (WPM * rate)) * 60) : "0:00";
    }

    /* --- Кнопки воспроизведения ------------------------------------------ */
    function setPlaying(playing) {
        el.speak.disabled = playing;
        el.pause.disabled = !playing;
        el.stop.disabled = !playing;
    }
    function resetButtons(msg) {
        setPlaying(false);
        el.pause.textContent = "⏸ Пауза";
        if (msg) setStatus(msg);
    }

    /* --- Синтез: общий вход ---------------------------------------------- */
    function speak(text, highlight = true) {
        text = (text ?? el.text.value).trim();
        if (!text) { setStatus("Введите текст для озвучивания."); return; }
        stopAll();
        if (highlight) buildReader(text); // читалка синхронна с озвучиваемым текстом
        if (engine === "server") speakServer(text);
        else speakBrowser(text, highlight);
    }

    /* --- Браузерный движок ----------------------------------------------- */
    function speakBrowser(text, highlight) {
        if (!("speechSynthesis" in window)) { setStatus("Web Speech API не поддерживается браузером."); return; }
        const u = new SpeechSynthesisUtterance(text);
        const v = selectedBrowserVoice();
        if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = "de-DE"; }
        u.rate = parseFloat(el.rate.value);
        u.pitch = parseFloat(el.pitch.value);
        u.volume = parseFloat(el.volume.value);

        u.onstart = () => { setStatus("Воспроизведение…"); setPlaying(true); };
        u.onend = () => { clearHighlight(); resetButtons("Завершено."); };
        u.onerror = (e) => { clearHighlight(); resetButtons("Ошибка синтеза: " + (e.error || "неизвестно")); };
        u.onpause = () => setStatus("Пауза.");
        u.onresume = () => setStatus("Воспроизведение…");
        if (highlight) u.onboundary = (e) => { if (typeof e.charIndex === "number") highlightAt(e.charIndex); };
        setPlaying(true);
        synth.speak(u);
    }

    /* --- Серверный движок (espeak-ng) ------------------------------------ */
    async function speakServer(text) {
        if (!serverAvailable) {
            setStatus("Серверный движок недоступен: установите espeak-ng на сервере (sudo pacman -S espeak-ng).");
            return;
        }
        setStatus("Синтез на сервере…"); setPlaying(true);
        try {
            const res = await fetch("/api/tts", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    text, voice: el.voice.value,
                    rate: parseFloat(el.rate.value), pitch: parseFloat(el.pitch.value),
                }),
            });
            if (!res.ok) {
                const e = await res.json().catch(() => ({}));
                resetButtons("Ошибка серверного синтеза: " + (e.error || res.status));
                return;
            }
            const blob = await res.blob();
            el.audio.src = URL.createObjectURL(blob);
            el.audio.volume = parseFloat(el.volume.value);
            el.audio.onplay = () => { setStatus("Воспроизведение…"); setPlaying(true); };
            el.audio.onpause = () => { if (!el.audio.ended) setStatus("Пауза."); };
            el.audio.onended = () => resetButtons("Завершено.");
            el.audio.onerror = () => resetButtons("Ошибка воспроизведения аудио.");
            await el.audio.play();
        } catch (err) {
            resetButtons("Не удалось получить аудио с сервера.");
        }
    }

    /* --- Пауза / стоп ---------------------------------------------------- */
    function togglePause() {
        if (engine === "server") {
            if (!el.audio.src) return;
            if (el.audio.paused) { el.audio.play(); el.pause.textContent = "⏸ Пауза"; }
            else { el.audio.pause(); el.pause.textContent = "⏵ Продолжить"; }
        } else if (synth && synth.speaking) {
            if (synth.paused) { synth.resume(); el.pause.textContent = "⏸ Пауза"; }
            else { synth.pause(); el.pause.textContent = "⏵ Продолжить"; }
        }
    }

    function stopAll() {
        if (synth) synth.cancel();
        try { el.audio.pause(); } catch {}
        clearHighlight();
    }
    function stop() { stopAll(); resetButtons("Остановлено."); }

    /* --- Буфер, файлы ---------------------------------------------------- */
    async function pasteFromClipboard() {
        try {
            const t = await navigator.clipboard.readText();
            if (t) { setText(t); setStatus("Текст вставлен из буфера обмена."); }
            else setStatus("Буфер обмена пуст.");
        } catch {
            setStatus("Нет доступа к буферу. Разрешите доступ или вставьте вручную (Ctrl+V).");
        }
    }

    function setText(t) { el.text.value = t; updateStats(); buildReader(t); }

    function readFile(file) {
        if (!file) return;
        const r = new FileReader();
        r.onload = () => { setText(String(r.result)); setStatus(`Загружен файл: ${file.name}`); };
        r.onerror = () => setStatus("Не удалось прочитать файл.");
        r.readAsText(file, "utf-8");
    }

    function saveFile() {
        const blob = new Blob([el.text.value], { type: "text/plain;charset=utf-8" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob); a.download = "text.txt"; a.click();
        URL.revokeObjectURL(a.href); setStatus("Файл сохранён.");
    }

    /* --- Выделение мышью → озвучить -------------------------------------- */
    function onReaderMouseUp() {
        setTimeout(() => {
            const s = window.getSelection();
            if (!s || s.isCollapsed || !s.rangeCount) { el.speakSel.hidden = true; return; }
            const range = s.getRangeAt(0);
            if (!el.reader.contains(range.commonAncestorContainer)) { el.speakSel.hidden = true; return; }
            selText = s.toString().trim();
            if (!selText) { el.speakSel.hidden = true; return; }
            const rect = range.getBoundingClientRect();
            el.speakSel.hidden = false;
            let top = rect.top - 44; if (top < 8) top = rect.bottom + 8;
            el.speakSel.style.top = top + "px";
            el.speakSel.style.left = Math.max(8, rect.left) + "px";
        }, 0);
    }
    function speakSelection() {
        if (!selText) return;
        el.speakSel.hidden = true;
        speak(selText, false);
    }

    /* --- Примеры --------------------------------------------------------- */
    async function loadSamples() {
        try {
            const data = await (await fetch("/api/samples")).json();
            (data.samples || []).forEach((s) => {
                const b = document.createElement("button");
                b.type = "button"; b.textContent = s.title;
                b.title = "Подставить текст в поле ввода";
                b.addEventListener("click", () => { setText(s.text); setStatus(`Загружен пример: ${s.title}`); });
                el.samples.appendChild(b);
            });
        } catch { setStatus("Не удалось загрузить примеры."); }
    }

    /* --- Тема и настройки ------------------------------------------------ */
    function applyTheme(t) { document.documentElement.setAttribute("data-theme", t); store.set("theme", t); }

    function syncLabels() {
        el.rateVal.textContent = parseFloat(el.rate.value).toFixed(1);
        el.pitchVal.textContent = parseFloat(el.pitch.value).toFixed(1);
        el.volumeVal.textContent = Math.round(el.volume.value * 100);
    }
    function persist() {
        store.set("rate", el.rate.value); store.set("pitch", el.pitch.value);
        store.set("volume", el.volume.value); store.set("voice." + engine, el.voice.value);
    }
    function loadSettings() {
        el.rate.value = store.get("rate", "1");
        el.pitch.value = store.get("pitch", "1");
        el.volume.value = store.get("volume", "1");
        syncLabels();
    }
    function resetSettings() {
        el.rate.value = 1; el.pitch.value = 1; el.volume.value = 1;
        el.voice.selectedIndex = 0;
        syncLabels(); persist();
        setStatus("Настройки сброшены к значениям по умолчанию.");
    }

    /* --- Авто-выбор движка ----------------------------------------------- */
    function maybeAutoChooseEngine() {
        // Если пользователь ещё не выбирал движок, а немецких голосов в браузере
        // нет и серверный доступен — переключаемся на серверный.
        if (store.get("engine", "") !== "") return;
        readBrowserVoices();
        if (!deVoices.length && serverAvailable && engine !== "server") {
            setEngine("server", { save: false });
            setStatus("Немецкие голоса в браузере не найдены — включён серверный движок (espeak-ng).");
        }
    }

    /* --- Привязка событий ------------------------------------------------ */
    function bind() {
        ["rate", "pitch", "volume"].forEach((k) =>
            el[k].addEventListener("input", () => {
                syncLabels(); updateStats(); persist();
                if (engine === "server" && k === "volume") el.audio.volume = parseFloat(el.volume.value);
            }));

        el.voice.addEventListener("change", persist);
        el.text.addEventListener("input", () => { updateStats(); buildReader(el.text.value); });

        el.speak.addEventListener("click", () => speak());
        el.pause.addEventListener("click", togglePause);
        el.stop.addEventListener("click", stop);
        el.paste.addEventListener("click", pasteFromClipboard);
        el.clear.addEventListener("click", () => { setText(""); setStatus("Поле очищено."); });
        el.open.addEventListener("click", () => el.file.click());
        el.file.addEventListener("change", (e) => readFile(e.target.files[0]));
        el.save.addEventListener("click", saveFile);
        el.resetSettings.addEventListener("click", resetSettings);
        el.theme.addEventListener("click", () =>
            applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark"));

        engineRadios().forEach((r) => r.addEventListener("change", () => setEngine(r.value)));

        document.querySelectorAll(".presets button").forEach((b) =>
            b.addEventListener("click", () => { el.rate.value = b.dataset.rate; syncLabels(); updateStats(); persist(); }));

        ["dragenter", "dragover"].forEach((ev) =>
            el.text.addEventListener(ev, (e) => { e.preventDefault(); el.text.classList.add("dragover"); }));
        ["dragleave", "drop"].forEach((ev) =>
            el.text.addEventListener(ev, (e) => { e.preventDefault(); el.text.classList.remove("dragover"); }));
        el.text.addEventListener("drop", (e) => readFile(e.dataTransfer.files[0]));

        el.reader.addEventListener("mouseup", onReaderMouseUp);
        el.speakSel.addEventListener("click", speakSelection);
        document.addEventListener("mousedown", (e) => { if (e.target !== el.speakSel) el.speakSel.hidden = true; });

        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") stop();
            else if (e.ctrlKey && e.key === "Enter") { e.preventDefault(); speak(); }
        });
    }

    /* --- Инициализация --------------------------------------------------- */
    async function init() {
        IDS.forEach((id) => (el[id] = $(id)));
        applyTheme(store.get("theme", "dark"));
        bind();
        loadSettings();

        // серверные голоса + доступность espeak-ng
        try {
            const sv = await (await fetch("/api/server-voices")).json();
            serverAvailable = !!sv.available; serverVoices = sv.voices || [];
        } catch { serverAvailable = false; serverVoices = []; }

        // стартовый движок: сохранённый, иначе browser (потом возможен авто-переход)
        readBrowserVoices();
        const savedEngine = store.get("engine", "");
        setEngine(savedEngine === "server" || savedEngine === "browser" ? savedEngine : "browser", { save: false });

        if ("speechSynthesis" in window && typeof speechSynthesis.onvoiceschanged !== "undefined") {
            speechSynthesis.onvoiceschanged = () => { readBrowserVoices(); if (engine === "browser") { populateVoiceSelect(); updateEngineNote(); } maybeAutoChooseEngine(); };
        }
        // голоса могут подгрузиться позже — перепроверим и решим, нужен ли серверный движок
        setTimeout(() => { readBrowserVoices(); if (engine === "browser") { populateVoiceSelect(); updateEngineNote(); } maybeAutoChooseEngine(); }, 1000);

        loadSamples();
        buildReader("");
        updateStats();

        if (!("speechSynthesis" in window) && !serverAvailable) {
            setStatus("Ни Web Speech API, ни espeak-ng недоступны. Установите espeak-ng на сервере.");
        }
    }

    document.addEventListener("DOMContentLoaded", init);
})();
