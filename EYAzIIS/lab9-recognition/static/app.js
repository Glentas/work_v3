/* Лабораторная работа 9. Система распознавания речи (вариант 7 — немецкий).
 *
 * Браузер записывает речь с микрофона, кодирует WAV (16 кГц, моно, 16 бит) и
 * отправляет на сервер (Vosk). Сервер возвращает распознанный текст и
 * сопоставленную операцию; клиент автоматически исполняет её и уведомляет
 * пользователя (всплывающее сообщение + журнал).
 *
 * Дополнительно: выбор языка (ЕЯ), список операций, симуляция команды без
 * микрофона, просмотр сочинений предметной области, уровень микрофона, тема.
 */
(function () {
    "use strict";

    const el = {};
    const IDS = [
        "rec", "status", "langSelect", "meterBar", "simText", "simBtn",
        "commands", "essayTitle", "essayText", "essayPos", "prevBtn", "nextBtn",
        "log", "clearLog", "toast", "theme", "commandsCard", "ttsAudio",
    ];

    let essays = [];
    let essayIndex = 0;
    let lang = "de";

    // запись
    let audioCtx = null, mediaStream = null, processor = null, sourceNode = null, workletNode = null;
    let recording = false, chunks = [], recordedRate = 48000, captureMode = "";

    // озвучивание (браузерный синтез — бонус для команды «read»)
    const synth = window.speechSynthesis;
    let speaking = false;

    const LS = "lab9.";
    const store = {
        get: (k, d) => (localStorage.getItem(LS + k) ?? d),
        set: (k, v) => localStorage.setItem(LS + k, v),
    };
    const $ = (id) => document.getElementById(id);

    /* --- Уведомления и журнал ------------------------------------------- */
    let toastTimer = null;
    function toast(msg, type = "") {
        el.toast.textContent = msg;
        el.toast.className = "toast show " + type;
        el.toast.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { el.toast.className = "toast"; }, 2600);
    }
    function setStatus(msg, cls = "") { el.status.textContent = msg; el.status.className = "status " + cls; }
    function log(said, action, type = "") {
        const li = document.createElement("li");
        const t = new Date().toLocaleTimeString();
        li.innerHTML = `<span class="t">${t}</span><span class="said"></span><span class="act ${type}"></span>`;
        li.querySelector(".said").textContent = said ? `«${said}»` : "—";
        li.querySelector(".act").textContent = action;
        el.log.prepend(li);
    }

    /* --- Конфигурация / языки ------------------------------------------- */
    async function loadConfig() {
        let cfg;
        try { cfg = await (await fetch("/api/config")).json(); }
        catch { setStatus("Не удалось получить конфигурацию сервера.", "err"); return; }

        el.langSelect.innerHTML = "";
        cfg.languages.forEach((l) => {
            const o = document.createElement("option");
            o.value = l.code;
            o.textContent = l.available ? l.name : `${l.name} — нет модели`;
            o.disabled = !l.available;
            el.langSelect.appendChild(o);
        });

        const saved = store.get("lang", "");
        lang = (saved && cfg.languages.some((l) => l.code === saved && l.available))
            ? saved : (cfg.default_lang || "de");
        el.langSelect.value = lang;

        const anyAvailable = cfg.languages.some((l) => l.available);
        if (!anyAvailable) {
            setStatus("Модели не установлены. Запустите: uv run python scripts/download_model.py de", "err");
            toast("Скачайте модель Vosk (scripts/download_model.py de)", "err");
        }
        loadCommands(lang);
    }

    async function loadCommands(l) {
        try {
            const d = await (await fetch("/api/commands?lang=" + encodeURIComponent(l))).json();
            el.commands.innerHTML = "";
            d.commands.forEach((c) => {
                const li = document.createElement("li");
                const kw = (c.keywords || []).slice(0, 4).join(", ");
                li.innerHTML = `<b>${c.action}</b> — ${escapeHtml(c.title)}<span class="kw">${escapeHtml(kw)}</span>`;
                el.commands.appendChild(li);
            });
            // операция открытия сочинений
            const li = document.createElement("li");
            li.innerHTML = `<b>open</b> — открыть сочинение по имени<span class="kw">Faust, Kafka, Buddenbrooks, Romantik…</span>`;
            el.commands.appendChild(li);
        } catch { /* игнорируем */ }
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) =>
            ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }

    /* --- Сочинения ------------------------------------------------------- */
    async function loadEssays() {
        try {
            const d = await (await fetch("/api/essays")).json();
            essays = d.essays || [];
            renderEssay(0);
        } catch { setStatus("Не удалось загрузить сочинения.", "err"); }
    }
    function renderEssay(i) {
        if (!essays.length) return;
        essayIndex = (i + essays.length) % essays.length;
        const e = essays[essayIndex];
        el.essayTitle.textContent = e.title;
        el.essayText.textContent = e.text;
        el.essayPos.textContent = `${essayIndex + 1} / ${essays.length}`;
    }
    function openEssayById(id) {
        const i = essays.findIndex((e) => e.id === id);
        if (i >= 0) { renderEssay(i); toast(`Открыто: ${essays[i].title}`, "ok"); log("", "open → " + essays[i].title, "ok"); }
    }
    const navigate = (d) => { renderEssay(essayIndex + d); toast(essays[essayIndex].title, "ok"); };
    const gotoFirst = () => { renderEssay(0); toast(essays[essayIndex].title, "ok"); };

    /* --- Озвучивание (команда read): серверный espeak-ng, фолбэк браузер -- */
    function readEssay() {
        if (!essays.length) return;
        const e = essays[essayIndex];
        readAloud(e.text, e.title);
    }

    async function readAloud(text, title) {
        stopReading(true); // прервать текущее воспроизведение
        // 1) серверный синтез (espeak-ng) — работает в любом браузере, вкл. LibreWolf
        try {
            setStatus("Синтез на сервере…", "busy");
            const res = await fetch("/api/tts", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text }),
            });
            if (res.ok) {
                const blob = await res.blob();
                el.ttsAudio.src = URL.createObjectURL(blob);
                el.ttsAudio.onended = () => { speaking = false; setStatus("Чтение завершено.", "ok"); };
                el.ttsAudio.onerror = () => { speaking = false; setStatus("Ошибка воспроизведения аудио.", "err"); };
                await el.ttsAudio.play();
                speaking = true;
                toast("Читаю вслух: " + title, "ok");
                log("", "read → " + title, "ok");
                setStatus("Чтение вслух…", "ok");
                return;
            }
        } catch { /* переходим к браузерному синтезу */ }
        // 2) браузерный синтез (Web Speech API) — если серверный недоступен
        if (synth) {
            synth.cancel();
            const u = new SpeechSynthesisUtterance(text);
            u.lang = "de-DE";
            const v = synth.getVoices().find((vv) => (vv.lang || "").toLowerCase().startsWith("de"));
            if (v) u.voice = v;
            u.onstart = () => { speaking = true; };
            u.onend = () => { speaking = false; };
            synth.speak(u);
            toast("Читаю вслух (браузер): " + title, "ok");
            log("", "read → " + title, "ok");
            return;
        }
        toast("Синтез недоступен: установите espeak-ng на сервере", "err");
        log("", "read → синтез недоступен", "err");
        setStatus("Синтез недоступен.", "err");
    }

    function stopReading(silent) {
        try { el.ttsAudio.pause(); el.ttsAudio.currentTime = 0; } catch {}
        if (synth) synth.cancel();
        speaking = false;
        if (!silent) { toast("Остановлено", "ok"); log("", "stop", "ok"); setStatus("Остановлено.", ""); }
    }

    /* --- Исполнение операции --------------------------------------------- */
    function executeCommand(c) {
        if (!c) return;
        switch (c.action) {
            case "help":
                el.commandsCard.scrollIntoView({ behavior: "smooth", block: "center" });
                toast("Список операций показан", "ok"); log("", "help", "ok"); break;
            case "list":
                toast("Сочинения: " + essays.map((e) => e.title).join("; "), "ok");
                log("", "list", "ok"); break;
            case "read": readEssay(); break;
            case "stop": stopReading(); break;
            case "next": navigate(1); log("", "next", "ok"); break;
            case "prev": navigate(-1); log("", "prev", "ok"); break;
            case "first": gotoFirst(); log("", "first", "ok"); break;
            case "open": openEssayById(c.essay_id); break;
            default: toast("Неизвестная операция: " + c.action, "none");
        }
    }

    function handleResult(res) {
        const text = (res.text || "").trim();
        if (res.command) {
            log(text, res.command.action, "ok");
            executeCommand(res.command);
        } else {
            log(text, text ? "не распознано" : "пусто", "none");
            toast(text ? `Команда не распознана: «${text}»` : "Речь не распознана", "none");
            setStatus(text ? "Команда не распознана." : "Речь не распознана. Попробуйте ещё раз.", "");
        }
    }

    /* --- Запись микрофона (AudioWorklet, фолбэк ScriptProcessor) --------- */
    async function startRecording() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            setStatus("Микрофон недоступен. Откройте страницу через http://127.0.0.1:5000 (защищённый контекст).", "err");
            toast("Нужен http://127.0.0.1 или https", "err");
            return;
        }
        try {
            mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
            });
        } catch (e) {
            setStatus("Нет доступа к микрофону: " + (e.name || e.message), "err");
            toast("Разрешите микрофон (проверьте также настройки LibreWolf)", "err");
            return;
        }

        const AC = window.AudioContext || window.webkitAudioContext;
        audioCtx = new AC();
        recordedRate = audioCtx.sampleRate;
        chunks = []; recording = true;

        // В Firefox/LibreWolf контекст может стартовать приостановленным — возобновляем.
        try { if (audioCtx.state !== "running") await audioCtx.resume(); } catch {}

        sourceNode = audioCtx.createMediaStreamSource(mediaStream);

        // Предпочтительно AudioWorklet (надёжно в Firefox); иначе ScriptProcessor.
        captureMode = "scriptprocessor";
        if (audioCtx.audioWorklet && audioCtx.audioWorklet.addModule) {
            try {
                await audioCtx.audioWorklet.addModule("/static/recorder-worklet.js");
                workletNode = new AudioWorkletNode(audioCtx, "recorder-processor");
                workletNode.port.onmessage = (ev) => onAudioChunk(ev.data);
                sourceNode.connect(workletNode);
                workletNode.connect(audioCtx.destination); // гарантируем обработку графом (выход тихий)
                captureMode = "audioworklet";
            } catch (e) {
                workletNode = null; // упадём на ScriptProcessor ниже
            }
        }
        if (captureMode !== "audioworklet") {
            processor = audioCtx.createScriptProcessor(4096, 1, 1);
            processor.onaudioprocess = (e) => { if (recording) onAudioChunk(e.inputBuffer.getChannelData(0)); };
            sourceNode.connect(processor);
            processor.connect(audioCtx.destination);
        }

        el.rec.textContent = "⏹ Остановить и распознать";
        el.rec.classList.add("recording");
        setStatus(`Запись… (${captureMode}) произнесите команду.`, "busy");
    }

    function onAudioChunk(data) {
        if (!recording || !data || !data.length) return;
        chunks.push(new Float32Array(data));
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
        const rms = Math.sqrt(sum / data.length);
        el.meterBar.style.width = Math.min(100, rms * 300) + "%";
    }

    async function stopRecording() {
        if (!recording) return;
        recording = false;
        el.meterBar.style.width = "0%";
        try { if (workletNode) { workletNode.port.close(); workletNode.disconnect(); } } catch {}
        try { if (processor) processor.disconnect(); } catch {}
        try { if (sourceNode) sourceNode.disconnect(); } catch {}
        if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop());
        try { if (audioCtx) await audioCtx.close(); } catch {}
        workletNode = null; processor = null; audioCtx = null;

        el.rec.textContent = "🎙 Начать запись";
        el.rec.classList.remove("recording");

        const total = chunks.reduce((n, c) => n + c.length, 0);
        if (total < 1600) {
            setStatus("Звук не захвачен (пустая запись). Проверьте микрофон и разрешение.", "err");
            toast("Микрофон не захватил звук", "err");
            log("", "пустая запись", "err");
            return;
        }
        const merged = new Float32Array(total);
        let off = 0; chunks.forEach((c) => { merged.set(c, off); off += c.length; });

        const secs = (total / recordedRate).toFixed(1);
        setStatus(`Распознавание… (записано ${secs} с)`, "busy");
        const wav = encodeWAV(downsample(merged, recordedRate, 16000), 16000);
        try {
            const res = await fetch("/api/recognize?lang=" + encodeURIComponent(lang), {
                method: "POST", headers: { "Content-Type": "audio/wav" }, body: wav,
            });
            const data = await res.json();
            if (!res.ok) { setStatus(data.error || "Ошибка распознавания", "err"); toast(data.hint || data.error || "Ошибка", "err"); log("", "ошибка", "err"); return; }
            setStatus(data.text ? `Распознано: «${data.text}»` : "Речь не распознана.", data.text ? "ok" : "");
            handleResult(data);
        } catch (e) {
            setStatus("Не удалось отправить аудио на сервер.", "err");
        }
    }

    /* --- Кодирование WAV ------------------------------------------------- */
    function downsample(buffer, inRate, outRate) {
        if (outRate >= inRate) return buffer;
        const ratio = inRate / outRate;
        const newLen = Math.round(buffer.length / ratio);
        const result = new Float32Array(newLen);
        let oR = 0, oB = 0;
        while (oR < newLen) {
            const next = Math.round((oR + 1) * ratio);
            let acc = 0, cnt = 0;
            for (let i = oB; i < next && i < buffer.length; i++) { acc += buffer[i]; cnt++; }
            result[oR] = cnt ? acc / cnt : 0;
            oR++; oB = next;
        }
        return result;
    }
    function encodeWAV(samples, sampleRate) {
        const buf = new ArrayBuffer(44 + samples.length * 2);
        const v = new DataView(buf);
        const wstr = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
        wstr(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); wstr(8, "WAVE");
        wstr(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
        v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true);
        v.setUint16(32, 2, true); v.setUint16(34, 16, true);
        wstr(36, "data"); v.setUint32(40, samples.length * 2, true);
        let o = 44;
        for (let i = 0; i < samples.length; i++, o += 2) {
            const s = Math.max(-1, Math.min(1, samples[i]));
            v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        }
        return new Blob([v], { type: "audio/wav" });
    }

    /* --- Симуляция (без микрофона) --------------------------------------- */
    async function simulate() {
        const text = el.simText.value.trim();
        if (!text) return;
        try {
            const res = await fetch("/api/match?lang=" + encodeURIComponent(lang), {
                method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
            });
            const data = await res.json();
            setStatus(data.text ? `Распознано: «${data.text}»` : "", "ok");
            handleResult(data);
            el.simText.value = "";
        } catch { setStatus("Ошибка симуляции.", "err"); }
    }

    /* --- Тема ------------------------------------------------------------ */
    function applyTheme(t) { document.documentElement.setAttribute("data-theme", t); store.set("theme", t); }

    /* --- События --------------------------------------------------------- */
    function bind() {
        el.rec.addEventListener("click", () => (recording ? stopRecording() : startRecording()));
        el.simBtn.addEventListener("click", simulate);
        el.simText.addEventListener("keydown", (e) => { if (e.key === "Enter") simulate(); });
        el.prevBtn.addEventListener("click", () => navigate(-1));
        el.nextBtn.addEventListener("click", () => navigate(1));
        el.clearLog.addEventListener("click", () => { el.log.innerHTML = ""; });
        el.langSelect.addEventListener("change", () => { lang = el.langSelect.value; store.set("lang", lang); loadCommands(lang); toast("Язык: " + el.langSelect.selectedOptions[0].textContent, "ok"); });
        el.theme.addEventListener("click", () => applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark"));
    }

    function init() {
        IDS.forEach((id) => (el[id] = $(id)));
        applyTheme(store.get("theme", "dark"));
        bind();
        loadConfig();
        loadEssays();
    }

    document.addEventListener("DOMContentLoaded", init);
})();
