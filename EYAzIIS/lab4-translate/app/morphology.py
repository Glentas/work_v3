"""Морфологический синтез русских словоформ — этап синтеза системы с трансфером.

Реализованы продуктивные правила русского словоизменения и таблицы
исключений для частотной лексики:

* склонение существительных (6 падежей × 2 числа, три рода, одушевлённость);
* согласование прилагательных и притяжательных местоимений;
* спряжение глаголов (настоящее/простое будущее, прошедшее), модальные слова;
* краткие и полные страдательные причастия для пассива (был обследован);
* деепричастия несовершенного вида;
* числительные с падежным управлением (два пациента, пять пациентов).

Правила покрывают регулярные модели; нерегулярные формы берутся из таблиц
исключений модуля либо из поля ``forms`` грамматической информации словарной
записи — словарь всегда имеет приоритет над правилом.
"""

from __future__ import annotations

CASES = ("nom", "gen", "dat", "acc", "inst", "prep")

CASE_NAMES_RU = {
    "nom": "именительный",
    "gen": "родительный",
    "dat": "дательный",
    "acc": "винительный",
    "inst": "творительный",
    "prep": "предложный",
}

_SIBILANTS = "жчшщ"
_VELARS = "гкх"
_VOWELS = "аоуеиыяюёэ"


# ---------------------------------------------------------------------------
# Личные, указательные и притяжательные местоимения
# ---------------------------------------------------------------------------
PRONOUNS: dict[str, dict[str, object]] = {
    "я": {"nom": "я", "gen": "меня", "dat": "мне", "acc": "меня", "inst": "мной", "prep": "мне"},
    "ты": {"nom": "ты", "gen": "тебя", "dat": "тебе", "acc": "тебя", "inst": "тобой", "prep": "тебе"},
    "он": {
        "nom": "он", "gen": "его", "dat": "ему", "acc": "его", "inst": "им", "prep": "нём",
        "prep_form": {"gen": "него", "dat": "нему", "acc": "него", "inst": "ним", "prep": "нём"},
    },
    "она": {
        "nom": "она", "gen": "её", "dat": "ей", "acc": "её", "inst": "ею", "prep": "ней",
        "prep_form": {"gen": "неё", "dat": "ней", "acc": "неё", "inst": "нею", "prep": "ней"},
    },
    "оно": {
        "nom": "оно", "gen": "его", "dat": "ему", "acc": "его", "inst": "им", "prep": "нём",
        "prep_form": {"gen": "него", "dat": "нему", "acc": "него", "inst": "ним", "prep": "нём"},
    },
    "мы": {"nom": "мы", "gen": "нас", "dat": "нам", "acc": "нас", "inst": "нами", "prep": "нас"},
    "вы": {"nom": "вы", "gen": "вас", "dat": "вам", "acc": "вас", "inst": "вами", "prep": "вас"},
    "они": {
        "nom": "они", "gen": "их", "dat": "им", "acc": "их", "inst": "ими", "prep": "них",
        "prep_form": {"gen": "них", "dat": "ним", "acc": "них", "inst": "ними", "prep": "них"},
    },
    "кто": {"nom": "кто", "gen": "кого", "dat": "кому", "acc": "кого", "inst": "кем", "prep": "ком"},
    "что": {"nom": "что", "gen": "чего", "dat": "чему", "acc": "что", "inst": "чем", "prep": "чём"},
    "это": {"nom": "это", "gen": "этого", "dat": "этому", "acc": "это", "inst": "этим", "prep": "этом"},
    "себя": {"nom": "себя", "gen": "себя", "dat": "себе", "acc": "себя", "inst": "собой", "prep": "себе"},
}

#: Притяжательные местоимения склоняются как прилагательные — полные таблицы.
POSSESSIVES: dict[str, dict[str, dict[str, str]]] = {
    "мой": {
        "m": {"nom": "мой", "gen": "моего", "dat": "моему", "acc": "мой", "inst": "моим", "prep": "моём"},
        "f": {"nom": "моя", "gen": "моей", "dat": "моей", "acc": "мою", "inst": "моей", "prep": "моей"},
        "n": {"nom": "моё", "gen": "моего", "dat": "моему", "acc": "моё", "inst": "моим", "prep": "моём"},
        "pl": {"nom": "мои", "gen": "моих", "dat": "моим", "acc": "мои", "inst": "моими", "prep": "моих"},
    },
    "твой": {
        "m": {"nom": "твой", "gen": "твоего", "dat": "твоему", "acc": "твой", "inst": "твоим", "prep": "твоём"},
        "f": {"nom": "твоя", "gen": "твоей", "dat": "твоей", "acc": "твою", "inst": "твоей", "prep": "твоей"},
        "n": {"nom": "твоё", "gen": "твоего", "dat": "твоему", "acc": "твоё", "inst": "твоим", "prep": "твоём"},
        "pl": {"nom": "твои", "gen": "твоих", "dat": "твоим", "acc": "твои", "inst": "твоими", "prep": "твоих"},
    },
    "наш": {
        "m": {"nom": "наш", "gen": "нашего", "dat": "нашему", "acc": "наш", "inst": "нашим", "prep": "нашем"},
        "f": {"nom": "наша", "gen": "нашей", "dat": "нашей", "acc": "нашу", "inst": "нашей", "prep": "нашей"},
        "n": {"nom": "наше", "gen": "нашего", "dat": "нашему", "acc": "наше", "inst": "нашим", "prep": "нашем"},
        "pl": {"nom": "наши", "gen": "наших", "dat": "нашим", "acc": "наши", "inst": "нашими", "prep": "наших"},
    },
    "ваш": {
        "m": {"nom": "ваш", "gen": "вашего", "dat": "вашему", "acc": "ваш", "inst": "вашим", "prep": "вашем"},
        "f": {"nom": "ваша", "gen": "вашей", "dat": "вашей", "acc": "вашу", "inst": "вашей", "prep": "вашей"},
        "n": {"nom": "ваше", "gen": "вашего", "dat": "вашему", "acc": "ваше", "inst": "вашим", "prep": "вашем"},
        "pl": {"nom": "ваши", "gen": "ваших", "dat": "вашим", "acc": "ваши", "inst": "вашими", "prep": "ваших"},
    },
    "свой": {
        "m": {"nom": "свой", "gen": "своего", "dat": "своему", "acc": "свой", "inst": "своим", "prep": "своём"},
        "f": {"nom": "своя", "gen": "своей", "dat": "своей", "acc": "свою", "inst": "своей", "prep": "своей"},
        "n": {"nom": "своё", "gen": "своего", "dat": "своему", "acc": "своё", "inst": "своим", "prep": "своём"},
        "pl": {"nom": "свои", "gen": "своих", "dat": "своим", "acc": "свои", "inst": "своими", "prep": "своих"},
    },
}

#: Неизменяемые притяжательные формы 3-го лица.
INVARIANT_POSSESSIVES = {"его", "её", "их"}


def pronoun_form(key: str, case: str, after_prep: bool = False) -> str:
    """Падежная форма личного местоимения; после предлогов — него/ним и т. п."""
    paradigm = PRONOUNS.get(key)
    if paradigm is None:
        return key
    if after_prep and case != "nom":
        prep_forms = paradigm.get("prep_form")
        if isinstance(prep_forms, dict):
            form = prep_forms.get(case)
            if form:
                return form
    value = paradigm.get(case, key)
    return value if isinstance(value, str) else key


def possessive_form(word: str, gender: str, number: str, case: str, anim: bool = False) -> str:
    """Форма притяжательного местоимения, согласованная с существительным."""
    if word in INVARIANT_POSSESSIVES:
        return word
    paradigm = POSSESSIVES.get(word)
    if paradigm is None:
        return word
    key = "pl" if number == "plur" else gender
    if case == "acc" and anim:
        case = "gen"
    return paradigm.get(key, {}).get(case, word)


# ---------------------------------------------------------------------------
# Прилагательные
# ---------------------------------------------------------------------------
def _adj_kind(adj_m: str) -> tuple[str, str]:
    """Основа и тип склонения прилагательного по форме м. р. ед. ч."""
    if adj_m.endswith("ой"):
        return adj_m[:-2], "hard"
    if adj_m.endswith("ый"):
        return adj_m[:-2], "hard"
    if adj_m.endswith("ий"):
        # русский, широкий — твёрдое (после г/к/х); синий, висящий — мягкое
        if len(adj_m) >= 3 and adj_m[-3] in _VELARS:
            return adj_m[:-2], "hard"
        return adj_m[:-2], "soft"
    return adj_m, "hard"


def _adj_to_masc(form: str) -> str:
    """Приводит женскую/среднюю/множественную форму прилагательного к мужской."""
    if form.endswith("ая"):
        return form[:-2] + "ый"
    if form.endswith("яя"):
        return form[:-2] + "ий"
    if form.endswith("ое"):
        return form[:-2] + "ый"
    if form.endswith("ее"):
        return form[:-2] + "ий"
    if form.endswith("ые"):
        return form[:-2] + "ый"
    if form.endswith("ие"):
        return form[:-2] + "ий"
    return form


# Окончания прилагательных в словарных формах (м./ж./ср. р. ед. ч.).
# «-ие» и «-ые» намеренно исключены: производство/произведение (сущ. на -ие)
# и существительные мн. ч. не должны приниматься за прилагательные.
_ADJ_ENDING_RE = ("ый", "ий", "ой", "ая", "яя", "ое", "ее")


_ADJ_ENDINGS = {
    "hard": {
        "m": {"nom": "ый", "gen": "ого", "dat": "ому", "acc": "ый", "inst": "ым", "prep": "ом"},
        "f": {"nom": "ая", "gen": "ой", "dat": "ой", "acc": "ую", "inst": "ой", "prep": "ой"},
        "n": {"nom": "ое", "gen": "ого", "dat": "ому", "acc": "ое", "inst": "ым", "prep": "ом"},
        "pl": {"nom": "ые", "gen": "ых", "dat": "ым", "acc": "ые", "inst": "ыми", "prep": "ых"},
    },
    "soft": {
        "m": {"nom": "ий", "gen": "его", "dat": "ему", "acc": "ий", "inst": "им", "prep": "ем"},
        "f": {"nom": "яя", "gen": "ей", "dat": "ей", "acc": "юю", "inst": "ей", "prep": "ей"},
        "n": {"nom": "ее", "gen": "его", "dat": "ему", "acc": "ее", "inst": "им", "prep": "ем"},
        "pl": {"nom": "ие", "gen": "их", "dat": "им", "acc": "ие", "inst": "ими", "prep": "их"},
    },
}


def agree_adj(adj_m: str, gender: str = "m", number: str = "sing", case: str = "nom",
              anim: bool = False) -> str:
    """Согласует прилагательное (словарная форма — м. р. им. п.) с существительным."""
    stem, kind = _adj_kind(adj_m)
    table = _ADJ_ENDINGS[kind]
    key = "pl" if number == "plur" else gender
    if case == "acc" and anim and key in ("m", "pl"):
        case = "gen"
    ending = table[key][case]
    # Орфография: после г, к, х не пишется «ы» — клинических, русских, широкие.
    if kind == "hard" and stem and stem[-1] in _VELARS and ending.startswith("ы"):
        ending = "и" + ending[1:]
    # После г, к, х и шипящих творительный твёрдого склонения — «-им/-ими»:
    # большим, русским, широкими (женский род всегда «-ой»: широкой).
    if kind == "hard" and case == "inst" and stem and stem[-1] in _VELARS + _SIBILANTS:
        if key == "pl":
            ending = "ими"
        elif key in ("m", "n"):
            ending = "им"
    # После шипящих мягкое склонение ж. р.: висящая/висящую (не висящяя/висящюю).
    if kind == "soft" and key == "f" and stem and stem[-1] in _SIBILANTS:
        if case == "nom":
            ending = "ая"
        elif case == "acc":
            ending = "ую"
    return stem + ending


# ---------------------------------------------------------------------------
# Существительные
# ---------------------------------------------------------------------------
def _m_stem_fleeting(word: str) -> str:
    """Основа косвенных падежей с беглой гласной: кусок -> куск, порошок -> порошк.

    Применяется только к -ок после согласной; слова вроде «человек» (человека)
    и «ребёнок» (ребёнка) беглой гласной не имеют — для них формы задаются
    в словаре.
    """
    if len(word) > 3 and word.endswith("ок") and word[-3] not in _VOWELS + "й":
        return word[:-2] + "к"
    return word


def _noun_singular(word: str, gender: str, case: str, anim: bool,
                   gram: dict | None = None) -> str:
    gram = gram or {}
    if gender == "f":
        if word.endswith("ия"):
            stem = word[:-2]
            return {"nom": word, "gen": stem + "ии", "dat": stem + "ии",
                    "acc": stem + "ию", "inst": stem + "ией", "prep": stem + "ии"}[case]
        if word.endswith("ь"):
            stem = word[:-1]
            return {"nom": word, "gen": stem + "и", "dat": stem + "и", "acc": word,
                    "inst": stem + "ью", "prep": stem + "и"}[case]
        if word.endswith("я"):
            stem = word[:-1]
            return {"nom": word, "gen": stem + "и", "dat": stem + "е", "acc": stem + "ю",
                    "inst": stem + "ей", "prep": stem + "е"}[case]
        if word.endswith("а"):
            stem = word[:-1]
            gen = stem + ("и" if stem[-1] in _VELARS + _SIBILANTS else "ы")
            inst = stem + ("ей" if stem[-1] == "ц" else "ой")
            return {"nom": word, "gen": gen, "dat": stem + "е", "acc": stem + "у",
                    "inst": inst, "prep": stem + "е"}[case]
        return word  # несклоняемые (леди, мисс)

    if gender == "n":
        if word.endswith("ие"):
            stem = word[:-2]
            return {"nom": word, "gen": stem + "ия", "dat": stem + "ию", "acc": word,
                    "inst": stem + "ием", "prep": stem + "ии"}[case]
        if word.endswith(("ое", "ее")):
            # Субстантивированные прилагательные: лёгкое -> в лёгком, лёгкого.
            stem = word[:-2]
            hard = word.endswith("ое")
            inst = "ым" if (hard and stem[-1] not in _VELARS + _SIBILANTS) else "им"
            return {"nom": word, "gen": stem + ("ого" if hard else "его"),
                    "dat": stem + ("ому" if hard else "ему"), "acc": word,
                    "inst": stem + inst,
                    "prep": stem + ("ом" if hard else "ем")}[case]
        if word.endswith("е"):
            stem = word[:-1]
            return {"nom": word, "gen": stem + "я", "dat": stem + "ю", "acc": word,
                    "inst": stem + "ем", "prep": stem + "е"}[case]
        if word.endswith("о"):
            stem = word[:-1]
            return {"nom": word, "gen": stem + "а", "dat": stem + "у", "acc": word,
                    "inst": stem + "ом", "prep": stem + "е"}[case]
        return word  # несклоняемые (кино, метро)

    # Мужской род
    if word.endswith(("ый", "ой")) and gram.get("adjdecl"):
        # Субстантивированные прилагательные: учёный -> учёного, об учёном.
        # Обычные существительные на -ой (герой, злодей) склоняются по правилу -й.
        stem = word[:-2]
        acc = stem + "ого" if anim else word
        return {"nom": word, "gen": stem + "ого", "dat": stem + "ому", "acc": acc,
                "inst": stem + "ым", "prep": stem + "ом"}[case]
    if word.endswith("ий"):
        stem = word[:-2]
        acc = stem + "ия" if anim else word
        return {"nom": word, "gen": stem + "ия", "dat": stem + "ию", "acc": acc,
                "inst": stem + "ием", "prep": stem + "ии"}[case]
    # Примечание: ветка -ие ниже обрабатывает средний род (здание -> здания).
    if word.endswith("ь"):
        stem = word[:-1]
        acc = stem + "я" if anim else word
        return {"nom": word, "gen": stem + "я", "dat": stem + "ю", "acc": acc,
                "inst": stem + "ем", "prep": stem + "е"}[case]
    if word.endswith("й"):
        stem = word[:-1]
        acc = stem + "я" if anim else word
        return {"nom": word, "gen": stem + "я", "dat": stem + "ю", "acc": acc,
                "inst": stem + "ем", "prep": stem + "е"}[case]
    if word.endswith("я"):  # юноша, дядя
        stem = word[:-1]
        return {"nom": word, "gen": stem + "и", "dat": stem + "е", "acc": stem + "ю",
                "inst": stem + "ей", "prep": stem + "е"}[case]
    if word.endswith("а"):  # папа, мужчина
        stem = word[:-1]
        gen = stem + ("и" if stem[-1] in _VELARS + _SIBILANTS else "ы")
        return {"nom": word, "gen": gen, "dat": stem + "е", "acc": stem + "у",
                "inst": stem + "ой", "prep": stem + "е"}[case]
    if word.endswith(("о", "е", "у", "ю", "и")):
        return word  # несклоняемые м. р. (кино, жюри)

    # Согласная основа
    stem = _m_stem_fleeting(word)
    inst = stem + ("ем" if stem[-1] in _SIBILANTS + "ц" else "ом")
    acc = stem + "а" if anim else word
    return {"nom": word, "gen": stem + "а", "dat": stem + "у", "acc": acc,
            "inst": inst, "prep": stem + "е"}[case]


def plural_nom(word: str, gender: str) -> str:
    """Именительный множественного числа (регулярные модели)."""
    if word.endswith(("ы", "и")):
        return word  # форма уже во множественном числе
    if word.endswith("я"):
        return word[:-1] + "и"
    if word.endswith("а"):
        stem = word[:-1]
        return stem + ("и" if stem[-1] in _VELARS + _SIBILANTS else "ы")
    if word.endswith("о"):
        return word[:-1] + "а"
    if word.endswith("е"):
        return word[:-1] + "я"
    if word.endswith(("ь", "й")):
        return word[:-1] + "и"
    stem = _m_stem_fleeting(word)  # рисунок -> рисунки
    if stem[-1] in _VELARS + _SIBILANTS:
        return stem + "и"
    return stem + "ы"


def plural_soft(word: str) -> bool:
    """Мягкая основа множественного числа (для окончаний -ям/-ями/-ях).

    Мягкие: поле -> полям, море -> морям, музей -> музеям, неделя -> неделям,
    болезнь -> болезням; твёрдые: стол -> столам, книга -> книгам.
    """
    return word.endswith(("я", "ь", "е", "й"))


def _plural_gen_guess(word: str, gender: str, nompl: str) -> str:
    """Эвристика родительного множественного; в словаре обычно задан явно (gpl)."""
    if word.endswith("я"):
        stem = word[:-1]
        if stem.endswith("ь"):
            return stem[:-1] + "ей"   # статья -> статей, семья -> семей
        if stem[-1] in _VOWELS:
            return stem + "й"         # армия -> армий
        return stem + "ь"             # неделя -> недель
    if word.endswith("а"):
        return word[:-1]  # книга -> книг
    if word.endswith("о"):
        return word[:-1]  # лекарство -> лекарств (окно -> окон задаётся в словаре)
    if word.endswith(("ое", "ее")):
        # Субстантивированные прилагательные: данное -> данных.
        return word[:-2] + ("ых" if word.endswith("ое") else "их")
    if word.endswith("ие"):
        return word[:-1] + "й"  # испытание -> испытаний, здание -> зданий
    if word.endswith("е"):
        return word[:-1] + "ей"  # море -> морей, поле -> полей
    if word.endswith("ь"):
        return word[:-1] + "ей"  # болезней, посетителей, словарей
    if word.endswith("й"):
        return word + "ев"
    if word.endswith("ин"):  # солдат -> солдат
        return word[:-1]
    stem = _m_stem_fleeting(word)   # рисунок -> рисунков
    if stem[-1] in _SIBILANTS:
        return stem + "ей"  # врач -> врачей, нож -> ножей
    return stem + "ов"


def _decline_multiword(target: str, gender: str, case: str, number: str,
                       anim: bool) -> str:
    """Склонение многословного эквивалента («головная боль», «анализ крови»).

    * первое слово — прилагательное: все прилагательные согласуются,
      последнее слово склоняется как существительное («головную боль»);
    * иначе склоняется первое (главное) слово, зависимые остаются в
      родительном («анализа крови», «болезни сердца»).
    """
    words = target.split()
    if len(words) < 2:
        return target
    if words[0].endswith(_ADJ_ENDING_RE):
        out = []
        for w in words[:-1]:
            if w.endswith(_ADJ_ENDING_RE):
                out.append(agree_adj(_adj_to_masc(w), gender, number, case, anim))
            else:
                out.append(w)
        out.append(decline_noun(words[-1], gender, case, number, anim))
        return " ".join(out)
    head = decline_noun(words[0], gender, case, number, anim)
    return " ".join([head] + words[1:])


def decline_noun(word: str, gender: str = "m", case: str = "nom", number: str = "sing",
                 anim: bool = False, gram: dict | None = None) -> str:
    """Склоняет существительное; явные формы из словаря (gram['forms']) важнее правил."""
    gram = gram or {}
    forms: dict[str, str] = gram.get("forms", {})
    if number == "sing":
        if case in forms:
            return forms[case]
        if gram.get("inv"):
            return word
        if " " in word:
            return _decline_multiword(word, gender, case, number, anim)
        return _noun_singular(word, gender, case, anim, gram)

    key = {"nom": "nompl", "gen": "genpl", "dat": "datpl",
           "acc": "accpl", "inst": "instpl", "prep": "preppl"}[case]
    if key in forms:
        return forms[key]
    if " " in word:
        return _decline_multiword(word, gender, case, number, anim)
    nompl = gram.get("pl") or plural_nom(word, gender)
    if case == "nom":
        return nompl
    genpl = gram.get("gpl") or _plural_gen_guess(word, gender, nompl)
    if case == "gen":
        return genpl
    if case == "acc":
        return genpl if anim else nompl
    stem = nompl[:-1] if nompl.endswith(("ы", "и", "а", "я")) else nompl
    soft = plural_soft(word) or nompl.endswith("ья")
    ending = {"dat": ("ям" if soft else "ам"),
              "inst": ("ями" if soft else "ами"),
              "prep": ("ях" if soft else "ах")}[case]
    return stem + ending


# ---------------------------------------------------------------------------
# Глаголы
# ---------------------------------------------------------------------------
#: Настоящее время (1л.ед., 2л.ед., 3л.ед., 1л.мн., 2л.мн., 3л.мн.).
#: Для глаголов совершенного вида эти же формы — простое будущее.
IRREGULAR_PRESENT: dict[str, list[str]] = {
    "быть": ["есть", "есть", "есть", "есть", "есть", "есть"],
    "дать": ["дам", "дашь", "даст", "дадим", "дадите", "дадут"],
    "создать": ["создам", "создашь", "создаст", "создадим", "создадите", "создадут"],
    "есть": ["ем", "ешь", "ест", "едим", "едите", "едят"],
    "хотеть": ["хочу", "хочешь", "хочет", "хотим", "хотите", "хотят"],
    "мочь": ["могу", "можешь", "может", "можем", "можете", "могут"],
    "бежать": ["бегу", "бежишь", "бежит", "бежим", "бежите", "бегут"],
    "жить": ["живу", "живёшь", "живёт", "живём", "живёте", "живут"],
    "пить": ["пью", "пьёшь", "пьёт", "пьём", "пьёте", "пьют"],
    "спать": ["сплю", "спишь", "спит", "спим", "спите", "спят"],
    "стоять": ["стою", "стоишь", "стоит", "стоим", "стоите", "стоят"],
    "бояться": ["боюсь", "боишься", "боится", "боимся", "боитесь", "боятся"],
    "держать": ["держу", "держишь", "держит", "держим", "держите", "держат"],
    "видеть": ["вижу", "видишь", "видит", "видим", "видите", "видят"],
    "смотреть": ["смотрю", "смотришь", "смотрит", "смотрим", "смотрите", "смотрят"],
    "слышать": ["слышу", "слышишь", "слышит", "слышим", "слышите", "слышат"],
    "сидеть": ["сижу", "сидишь", "сидит", "сидим", "сидите", "сидят"],
    "висеть": ["вишу", "висишь", "висит", "висим", "висите", "висят"],
    "лететь": ["лечу", "летишь", "летит", "летим", "летите", "летят"],
    "гореть": ["горю", "горишь", "горит", "горим", "горите", "горят"],
    "терпеть": ["терплю", "терпишь", "терпит", "терпим", "терпите", "терпят"],
    "зависеть": ["завишу", "зависишь", "зависит", "зависим", "зависите", "зависят"],
    "идти": ["иду", "идёшь", "идёт", "идём", "идёте", "идут"],
    "ехать": ["еду", "едешь", "едет", "едем", "едете", "едут"],
    "нести": ["несу", "несёшь", "несёт", "несём", "несёте", "несут"],
    "везти": ["везу", "везёшь", "везёт", "везём", "везёте", "везут"],
    "вести": ["веду", "ведёшь", "ведёт", "ведём", "ведёте", "ведут"],
    "расти": ["расту", "растёшь", "растёт", "растём", "растёте", "растут"],
    "цвести": ["цвету", "цветёшь", "цветёт", "цветём", "цветёте", "цветут"],
    "спасти": ["спасу", "спасёшь", "спасёт", "спасём", "спасёте", "спасут"],
    "найти": ["найду", "найдёшь", "найдёт", "найдём", "найдёте", "найдут"],
    "пойти": ["пойду", "пойдёшь", "пойдёт", "пойдём", "пойдёте", "пойдут"],
    "прийти": ["приду", "придёшь", "придёт", "придём", "придёте", "придут"],
    "помочь": ["помогу", "поможешь", "поможет", "поможем", "поможете", "помогут"],
    "беречь": ["берегу", "бережёшь", "бережёт", "бережём", "бережёте", "берегут"],
    "жечь": ["жгу", "жжёшь", "жжёт", "жжём", "жжёте", "жгут"],
    "стричь": ["стригу", "стрижёшь", "стрижёт", "стрижём", "стрижёте", "стригут"],
    "привлечь": ["привлеку", "привлечёшь", "привлечёт", "привлечём", "привлечёте", "привлекут"],
    "достичь": ["достигну", "достигнешь", "достигнет", "достигнем", "достигнете", "достигнут"],
    "сказать": ["скажу", "скажешь", "скажет", "скажем", "скажете", "скажут"],
    "рассказать": ["расскажу", "расскажешь", "расскажет", "расскажем", "расскажете", "расскажут"],
    "показать": ["покажу", "покажешь", "покажет", "покажем", "покажете", "покажут"],
    "указать": ["укажу", "укажешь", "укажет", "укажем", "укажете", "укажут"],
    "доказать": ["докажу", "докажешь", "докажет", "докажем", "докажете", "докажут"],
    "заметить": ["замечу", "заметишь", "заметит", "заметим", "заметите", "заметят"],
    "отметить": ["отмечу", "отметишь", "отметит", "отметим", "отметите", "отметят"],
    "ответить": ["отвечу", "ответишь", "ответит", "ответим", "ответите", "ответят"],
    "встретить": ["встречу", "встретишь", "встретит", "встретим", "встретите", "встретят"],
    "учить": ["учу", "учишь", "учит", "учим", "учите", "учат"],
    "платить": ["плачу", "платишь", "платит", "платим", "платите", "платят"],
    "ходить": ["хожу", "ходишь", "ходит", "ходим", "ходите", "ходят"],
    "любить": ["люблю", "любишь", "любит", "любим", "любите", "любят"],
    "ловить": ["ловлю", "ловишь", "ловит", "ловим", "ловите", "ловят"],
    "готовить": ["готовлю", "готовишь", "готовит", "готовим", "готовите", "готовят"],
    "поставить": ["поставлю", "поставишь", "поставит", "поставим", "поставите", "поставят"],
    "просить": ["прошу", "просишь", "просит", "просим", "просите", "просят"],
    "носить": ["ношу", "носишь", "носит", "носим", "носите", "носят"],
    "бросить": ["брошу", "бросишь", "бросит", "бросим", "бросите", "бросят"],
    "звать": ["зову", "зовёшь", "зовёт", "зовём", "зовёте", "зовут"],
    "принять": ["приму", "примешь", "примет", "примем", "примете", "примут"],
    "начать": ["начну", "начнёшь", "начнёт", "начнём", "начнёте", "начнут"],
    "понять": ["пойму", "поймёшь", "поймёт", "поймём", "поймёте", "поймут"],
    "взять": ["возьму", "возьмёшь", "возьмёт", "возьмём", "возьмёте", "возьмут"],
    "писать": ["пишу", "пишешь", "пишет", "пишем", "пишете", "пишут"],
    "написать": ["напишу", "напишешь", "напишет", "напишем", "напишете", "напишут"],
    "описать": ["опишу", "опишешь", "опишет", "опишем", "опишете", "опишут"],
    "стать": ["стану", "станешь", "станет", "станем", "станете", "станут"],
    "произойти": ["произойду", "произойдёшь", "произойдёт", "произойдём", "произойдёте", "произойдут"],
    "войти": ["войду", "войдёшь", "войдёт", "войдём", "войдёте", "войдут"],
    "выйти": ["выйду", "выйдешь", "выйдет", "выйдем", "выйдете", "выйдут"],
    "пройти": ["пройду", "пройдёшь", "пройдёт", "пройдём", "пройдёте", "пройдут"],
    "изобрести": ["изобрету", "изобретёшь", "изобретёт", "изобретём", "изобретёте", "изобретут"],
    "осмотреть": ["осмотрю", "осмотришь", "осмотрит", "осмотрим", "осмотрите", "осмотрят"],
    "изучить": ["изучу", "изучишь", "изучит", "изучим", "изучите", "изучат"],
    "вылечить": ["вылечу", "вылечишь", "вылечит", "вылечим", "вылечите", "вылечат"],
    "завершить": ["завершу", "завершишь", "завершит", "завершим", "завершите", "завершат"],
    "улучшить": ["улучшу", "улучшишь", "улучшит", "улучшим", "улучшите", "улучшат"],
    "уменьшить": ["уменьшу", "уменьшишь", "уменьшит", "уменьшим", "уменьшите", "уменьшат"],
    "увеличить": ["увеличу", "увеличишь", "увеличит", "увеличим", "увеличите", "увеличат"],
    "изменить": ["изменю", "изменишь", "изменит", "изменим", "измените", "изменят"],
    "сохранить": ["сохраню", "сохранишь", "сохранит", "сохраним", "сохраните", "сохранят"],
    "объединить": ["объединю", "объединишь", "объединит", "объединим", "объедините", "объединят"],
    "подтвердить": ["подтвержу", "подтвердишь", "подтвердит", "подтвердим", "подтвердите", "подтвердят"],
    "возвратить": ["возвращу", "возвратишь", "возвратит", "возвратим", "возвратите", "возвратят"],
    "произвести": ["произведу", "произведёшь", "произведёт", "произведём", "произведёте", "произведут"],
    "провести": ["проведу", "проведёшь", "проведёт", "проведём", "проведёте", "проведут"],
}

#: Прошедшее время: строка — основа м. р. (далее +а/+о/+и), список — полный набор.
IRREGULAR_PAST: dict[str, str | list[str]] = {
    "идти": ["шёл", "шла", "шло", "шли"],
    "быть": ["был", "была", "было", "были"],
    "есть": ["ел", "ела", "ело", "ели"],
    "дать": ["дал", "дала", "дало", "дали"],
    "создать": ["создал", "создала", "создало", "создали"],
    "мочь": "мог",
    "помочь": "помог",
    "беречь": "берёг",
    "нести": "нёс",
    "везти": "вёз",
    "вести": ["вёл", "вела", "вело", "вели"],
    "расти": "рос",
    "спасти": "спас",
    "найти": ["нашёл", "нашла", "нашло", "нашли"],
    "пойти": ["пошёл", "пошла", "пошло", "пошли"],
    "прийти": ["пришёл", "пришла", "пришло", "пришли"],
    "стать": "стал",
    "произойти": ["произошёл", "произошла", "произошло", "произошли"],
    "войти": ["вошёл", "вошла", "вошло", "вошли"],
    "выйти": ["вышел", "вышла", "вышло", "вышли"],
    "пройти": ["прошёл", "прошла", "прошло", "прошли"],
    "снять": "снял",
    "понять": "понял",
    "принять": "принял",
    "взять": "взял",
    "начать": "начал",
    "звать": "звал",
    "достичь": "достиг",
    "жить": "жил",
    "пить": "пил",
    "шить": "шил",
    "бить": "бил",
    "вить": "вил",
    "гнать": "гнал",
    "ждать": "ждал",
    "держать": "держал",
}


def _verb_base(inf: str) -> tuple[str, bool]:
    """Инфинитив без возвратной частицы -ся; флаг возвратности."""
    reflexive = inf.endswith("ся") or inf.endswith("сь")
    return (inf[:-2] if reflexive else inf), reflexive


def _add_reflexive(word: str, reflexive: bool, past: bool = False) -> str:
    """Добавляет -ся/-сь к готовой словоформе: после гласной -сь, иначе -ся."""
    if not reflexive or word.endswith(("ся", "сь")):
        return word
    return word + ("сь" if word[-1] in _VOWELS else "ся")


#: Чередования согласных основы в 1-м лице ед. ч. глаголов на -ить:
#: находить -> нахожу, платить -> плачу, купить -> куплю, пустить -> пущу.
_STEM_MUTATIONS: tuple[tuple[str, str], ...] = (
    ("ст", "щ"), ("ск", "щ"),
    ("д", "ж"), ("т", "ч"), ("з", "ж"), ("с", "ш"),
    ("б", "бл"), ("в", "вл"), ("п", "пл"), ("м", "мл"),
)


def _mutate_stem(stem: str) -> str:
    """Основа 1-го лица ед. ч. с чередованием конечного согласного."""
    for src, dst in _STEM_MUTATIONS:
        if stem.endswith(src):
            return stem[: -len(src)] + dst
    return stem


def _present_regular(inf: str) -> list[str]:
    """Регулярное настоящее время по продуктивным моделям спряжения."""
    if inf.endswith("овать"):
        root = inf[:-5]
        return [root + "ую", root + "уешь", root + "ует", root + "уем", root + "уете", root + "уют"]
    if inf.endswith("евать"):
        root = inf[:-5]
        return [root + "еваю", root + "еваешь", root + "евает",
                root + "еваем", root + "еваете", root + "евают"]
    if inf.endswith("ить"):
        stem = inf[:-3]
        first = _mutate_stem(stem)
        # После ж, ч, ш, щ, ц пишется «у», а не «ю»: нахожу, пущу, плачу.
        first_ending = "у" if first[-1] in _SIBILANTS + "ц" else "ю"
        return [first + first_ending, stem + "ишь", stem + "ит",
                stem + "им", stem + "ите", stem + "ят"]
    if inf.endswith(("ать", "ять", "еть", "уть", "оть", "ыть", "ти")):
        stem = inf[:-2]
        return [stem + "ю", stem + "ешь", stem + "ет", stem + "ем", stem + "ете", stem + "ют"]
    if inf.endswith(("сти", "зти")):
        stem = inf[:-3]
        return [stem + "у", stem + "ёшь", stem + "ёт", stem + "ём", stem + "ёте", stem + "ут"]
    if inf.endswith("чь"):
        stem = inf[:-2] + "г"
        return [stem + "у", stem[:-1] + "жёшь", stem[:-1] + "жёт", stem[:-1] + "жём",
                stem[:-1] + "жёте", stem + "ут"]
    stem = inf[:-1]
    return [stem + "ю", stem + "ешь", stem + "ет", stem + "ем", stem + "ете", stem + "ют"]


def conjugate(inf: str, person: int = 3, number: str = "sing", gram: dict | None = None) -> str:
    """Настоящее (для сов. вида — простое будущее) время: лицо 1..3, число sing/plur."""
    gram = gram or {}
    base, reflexive = _verb_base(inf)
    forms: dict[str, str] = gram.get("forms", {})
    idx = (3 if number == "plur" else 0) + max(1, min(3, person)) - 1
    key = f"pres{idx + 1}"
    if key in forms:
        return forms[key]
    if base in IRREGULAR_PRESENT:
        word = IRREGULAR_PRESENT[base][idx]
    else:
        word = _present_regular(base)[idx]
    return _add_reflexive(word, reflexive)


def verb_past(inf: str, gender: str = "m", number: str = "sing", gram: dict | None = None) -> str:
    """Прошедшее время: согласуется с подлежащим в роде и числе."""
    gram = gram or {}
    base, reflexive = _verb_base(inf)
    forms: dict[str, str] = gram.get("forms", {})
    key = "pastpl" if number == "plur" else {"m": "pastm", "f": "pastf", "n": "pastn"}.get(gender, "pastm")
    if key in forms:
        return forms[key]

    irr = IRREGULAR_PAST.get(base)
    if isinstance(irr, list):
        word = irr[3] if number == "plur" else irr[{"m": 0, "f": 1, "n": 2}.get(gender, 0)]
        return _add_reflexive(word, reflexive, past=True)

    if isinstance(irr, str):
        # Основа м. р.: мог -> могла, но жил -> жила (после «л» только -а/-о/-и).
        stem = irr.replace("ё", "е")
        if number == "plur":
            word = stem + ("и" if stem.endswith("л") else "ли")
        elif stem.endswith("л"):
            word = stem + {"m": "", "f": "а", "n": "о"}.get(gender, "")
        else:
            word = stem + {"m": "", "f": "ла", "n": "ло"}.get(gender, "")
        return _add_reflexive(word, reflexive, past=True)

    # Регулярно: основа = инфинитив без «ть» (сесть/украсть — без «сть»)
    if base.endswith("сть"):
        stem = base[:-3] + "л"
    else:
        stem = base[:-2] + "л"
    word = stem + {("m", "sing"): "", ("f", "sing"): "а", ("n", "sing"): "о"}.get((gender, number), "")
    if number == "plur":
        word = stem + "и"
    return _add_reflexive(word, reflexive, past=True)


#: Краткие страдательные причастия — исключения (форма м. р. ед. ч.).
IRREGULAR_PP: dict[str, str] = {
    "найти": "найден",
    "взять": "взят",
    "снять": "снят",
    "принять": "принят",
    "понять": "понят",
    "дать": "дан",
    "создать": "создан",
    "начать": "начат",
    "изобрести": "изобретён",
    "произвести": "произведён",
    "провести": "проведён",
    "привести": "приведён",
    "привлечь": "привлечён",
    "достичь": "достигнут",
    "выбрать": "выбран",
    "признать": "признан",
    "принять": "принят",
}


def short_participle(pf_inf: str, gender: str = "m", number: str = "sing",
                     gram: dict | None = None) -> str:
    """Краткое страдательное причастие для пассива: был обследован/обследована."""
    gram = gram or {}
    base, reflexive = _verb_base(pf_inf)
    if gram.get("pp"):
        masc = gram["pp"]
    elif base in IRREGULAR_PP:
        masc = IRREGULAR_PP[base]
    elif base.endswith("овать"):
        masc = base[:-5] + "ован"   # обследовать -> обследован
    elif base.endswith("ять"):
        masc = base[:-2] + "т"      # снять -> снят
    elif base.endswith("ать"):
        masc = base[:-2] + "н"      # написать -> написан
    elif base.endswith("ить"):
        stem = base[:-3]
        # решить -> решен, но выставить -> выставлен, купить -> куплен
        masc = stem + ("лен" if stem.endswith(("в", "п")) else "ен")
    elif base.endswith(("сти", "зти")):
        masc = base[:-2] + "ён"     # принести -> принесён
    elif base.endswith("чь"):
        masc = base[:-2] + "чён"
    elif base.endswith("ть"):
        masc = base[:-2] + "т"      # открыть -> открыт, помыть -> помыт
    else:
        masc = base + "т"
    if reflexive and not masc.endswith("ся"):
        masc += "ся"
    if number == "plur":
        return masc.replace("ён", "ен") + "ы"
    if gender == "m":
        return masc                       # принесён, решён — «ё» сохраняется
    return masc.replace("ён", "ен") + {"f": "а", "n": "о"}.get(gender, "")


def full_participle(pf_inf: str, gram: dict | None = None) -> str:
    """Полное страдательное причастие (м. р.): «обследованный пациент»."""
    masc = short_participle(pf_inf, "m", "sing", gram)
    if masc.endswith("т"):
        return masc + "ый"          # открыт -> открытый, взят -> взятый
    return masc + "ный"             # сделан -> сделанный, найден -> найденный


def gerund(inf: str) -> str:
    """Деепричастие несовершенного вида: читать -> читая, говорить -> говоря."""
    base, reflexive = _verb_base(inf)
    if base.endswith("овать"):
        word = base[:-5] + "уя"
    elif base.endswith(("ать", "ять", "еть")):
        word = base[:-2] + "я"
    elif base.endswith("ить"):
        word = base[:-3] + "я"
    else:
        word = base + "я"
    return word + ("сь" if reflexive else "")


# ---------------------------------------------------------------------------
# Числительные и счёт
# ---------------------------------------------------------------------------
NUMBER_WORDS = {
    "one": "один", "two": "два", "three": "три", "four": "четыре", "five": "пять",
    "six": "шесть", "seven": "семь", "eight": "восемь", "nine": "девять", "ten": "десять",
    "eleven": "одиннадцать", "twelve": "двенадцать", "twenty": "двадцать",
    "thirty": "тридцать", "forty": "сорок", "fifty": "пятьдесят", "sixty": "шестьдесят",
    "seventy": "семьдесят", "eighty": "восемьдесят", "ninety": "девяносто",
    "hundred": "сто", "thousand": "тысяча", "million": "миллион", "billion": "миллиард",
    "first": "первый", "second": "второй", "third": "третий", "fourth": "четвёртый",
    "fifth": "пятый", "sixth": "шестой", "seventh": "седьмой", "eighth": "восьмой",
    "ninth": "девятый", "tenth": "десятый",
}


def numeral_noun_case(value: int) -> str:
    """Падеж и число существительного после количественного числительного.

    1 -> именительный ед. ч.; 2..4 -> родительный ед. ч.; 5+ -> родительный мн. ч.
    """
    last100 = value % 100
    last = value % 10
    if last == 1 and last100 != 11:
        return "nom_sing"
    if 2 <= last <= 4 and not 12 <= last100 <= 14:
        return "gen_sing"
    return "gen_plur"
