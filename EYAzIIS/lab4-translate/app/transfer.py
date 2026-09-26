"""Межъязыковые операции (трансфер) и синтез русского предложения.

Архитектура соответствует системам непрямого перевода из ТЗ:

1. **анализ** — выполнен в ``analysis.py`` (spaCy: леммы, теги, роли, признаки);
2. **трансфер** — лексическая замена по двуязычному словарю с выбором
   эквивалента по части речи и предметной области, грамматические
   преобразования (артикль, пассив, перфект, модальность, вопрос,
   отрицание, посессив, of-конструкция, составные существительные);
3. **синтез** — порождение русских словоформ средствами ``morphology.py``
   (падежи, согласование, спряжение, причастия).

Режим ``literal`` (система прямого перевода) выполняет только лексическую
замену найденных в словаре элементов и оборотов без морфологического
синтеза и перестановок — результат близок к пословному.

Осознанные упрощения учебной системы перечислены в справке и README.
"""

from __future__ import annotations

import logging
import re

from . import morphology
from .dictionary import lookup, lookup_phrase
from .domain import SentenceData, TokenData

log = logging.getLogger(__name__)

# --- Служебная лексика -------------------------------------------------------
ARTICLES = {"the", "a", "an"}

#: Глаголы движения: предлоги in/on/to при них получают винительный падеж
#: («в больницу» — направление) вместо предложного («в больнице» — место).
MOTION_VERBS = frozenset(
    """go come arrive enter return travel move send put place bring walk run
    fly drive transfer admit refer take carry deliver rush transport""".split()
)

#: Глаголы с дательным беспредложным: give smth to smb -> «дать кому».
DATIVE_VERBS = frozenset(
    """give send tell show offer bring lend pay teach explain recommend
    prescribe present deliver pass hand write read report return according""".split()
)

#: Квантификаторы: требуют родительного падежа множественного числа.
QUANTIFIERS = {
    "many": "много", "much": "много", "few": "мало", "fewer": "меньше",
    "several": "несколько", "numerous": "множество", "multiple": "несколько",
    "more": "больше", "less": "меньше", "most": "большинство",
}

#: Синтаксические роли определителей, которые синтезирует именная группа.
MODIFIER_DEPS = ("det", "predet", "poss", "amod", "compound", "nummod", "quantmod")

#: Предлог -> (русский предлог, управляемый падеж). Пустая строка вместо
#: предлога означает беспредложное управление (of -> родительный, by -> творительный).
PREP_MAP: dict[str, tuple[str, str]] = {
    "in": ("в", "prep"), "on": ("на", "prep"), "at": ("в", "prep"),
    "into": ("в", "acc"), "onto": ("на", "acc"), "to": ("к", "dat"),
    "for": ("для", "gen"), "of": ("", "gen"), "from": ("из", "gen"),
    "with": ("с", "inst"), "without": ("без", "gen"), "about": ("о", "prep"),
    "after": ("после", "gen"), "before": ("до", "gen"), "between": ("между", "inst"),
    "among": ("среди", "gen"), "during": ("в течение", "gen"), "until": ("до", "gen"),
    "till": ("до", "gen"), "since": ("с", "gen"), "through": ("через", "acc"),
    "over": ("над", "inst"), "under": ("под", "inst"), "above": ("над", "inst"),
    "below": ("под", "inst"), "near": ("около", "gen"), "behind": ("за", "inst"),
    "beside": ("рядом с", "inst"), "along": ("вдоль", "gen"), "across": ("через", "acc"),
    "against": ("против", "gen"), "upon": ("на", "prep"), "within": ("в", "prep"),
    "toward": ("к", "dat"), "towards": ("к", "dat"), "by": ("у", "gen"),
    "per": ("в", "acc"), "via": ("через", "acc"), "versus": ("против", "gen"),
    "despite": ("несмотря на", "acc"), "except": ("кроме", "gen"),
    "like": ("как", "nom"), "as": ("как", "nom"), "than": ("чем", "nom"),
    "out": ("из", "gen"), "off": ("с", "gen"), "plus": ("плюс", "nom"),
    "minus": ("минус", "nom"),
}

#: Модальные глаголы.
MODALS = {"can", "could", "will", "would", "shall", "should", "must", "may", "might"}

#: Будущее время глагола «быть» (описательное будущее несовершенного вида).
BE_FUTURE = ["буду", "будешь", "будет", "будем", "будете", "будут"]

#: Личные местоимения -> (лицо, число, род) для согласования сказуемого.
PRON_AGREEMENT = {
    "я": (1, "sing", "m"), "ты": (2, "sing", "m"), "он": (3, "sing", "m"),
    "она": (3, "sing", "f"), "оно": (3, "sing", "n"), "мы": (1, "plur", "m"),
    "вы": (2, "plur", "m"), "они": (3, "plur", "m"),
}

#: Wh-слова вопроса (порядок слов сохраняется, частица «ли» не добавляется).
WH_LEMMAS = {"who", "what", "which", "where", "when", "why", "how", "whose", "whom"}

#: Существительные времени: for + время -> творительный падеж («веками»).
TIME_NOUNS = frozenset(
    "century decade year month week day hour minute second summer winter "
    "spring autumn season morning evening night".split()
)

#: Глаголы, после которых именная часть сказуемого стоит в творительном падеже:
#: remains effective -> «остаётся эффективной» (но: is effective -> «эффективная»).
COPULAR_INST_VERBS = {"remain", "become", "stay", "seem", "feel", "look", "appear"}

#: Переопределение предлога по глаголу: depend on -> «зависеть от».
PREP_HEAD_OVERRIDES: dict[tuple[str, str], tuple[str, str]] = {
    ("depend", "on"): ("от", "gen"),
    ("result", "in"): ("в", "prep"),
    ("participate", "in"): ("в", "prep"),
    ("specialize", "in"): ("в", "prep"),
    ("protect", "from"): ("от", "gen"),
    ("suffer", "from"): ("от", "gen"),
    ("die", "from"): ("от", "gen"),
    ("die", "of"): ("от", "gen"),
    ("differ", "from"): ("от", "gen"),
}

#: Склеивает пунктуацию с предшествующим словом: «словом .» -> «словом.»
_PUNCT_CLEANUP = re.compile(r"\s+([,.!?;:])")

#: Особые местоименные прилагательные (нерегулярное согласование).
SPECIAL_AGREEMENT: dict[str, dict[str, dict[str, str]]] = {
    "этот": {
        "m": {"nom": "этот", "gen": "этого", "dat": "этому", "acc": "этот", "inst": "этим", "prep": "этом"},
        "f": {"nom": "эта", "gen": "этой", "dat": "этой", "acc": "эту", "inst": "этой", "prep": "этой"},
        "n": {"nom": "это", "gen": "этого", "dat": "этому", "acc": "это", "inst": "этим", "prep": "этом"},
        "pl": {"nom": "эти", "gen": "этих", "dat": "этим", "acc": "эти", "inst": "этими", "prep": "этих"},
    },
    "тот": {
        "m": {"nom": "тот", "gen": "того", "dat": "тому", "acc": "тот", "inst": "тем", "prep": "том"},
        "f": {"nom": "та", "gen": "той", "dat": "той", "acc": "ту", "inst": "той", "prep": "той"},
        "n": {"nom": "то", "gen": "того", "dat": "тому", "acc": "то", "inst": "тем", "prep": "том"},
        "pl": {"nom": "те", "gen": "тех", "dat": "тем", "acc": "те", "inst": "теми", "prep": "тех"},
    },
    "чей": {
        "m": {"nom": "чей", "gen": "чьего", "dat": "чьему", "acc": "чей", "inst": "чьим", "prep": "чьём"},
        "f": {"nom": "чья", "gen": "чьей", "dat": "чьей", "acc": "чью", "inst": "чьей", "prep": "чьей"},
        "n": {"nom": "чьё", "gen": "чьего", "dat": "чьему", "acc": "чьё", "inst": "чьим", "prep": "чьём"},
        "pl": {"nom": "чьи", "gen": "чьих", "dat": "чьим", "acc": "чьи", "inst": "чьими", "prep": "чьих"},
    },
    "весь": {
        "m": {"nom": "весь", "gen": "всего", "dat": "всему", "acc": "весь", "inst": "всем", "prep": "всем"},
        "f": {"nom": "вся", "gen": "всей", "dat": "всей", "acc": "всю", "inst": "всей", "prep": "всей"},
        "n": {"nom": "всё", "gen": "всего", "dat": "всему", "acc": "всё", "inst": "всем", "prep": "всем"},
        "pl": {"nom": "все", "gen": "всех", "dat": "всем", "acc": "все", "inst": "всеми", "prep": "всех"},
    },
}

#: Числительные 1 и 2 согласуются с существительным в роде.
ONE_FORMS = {"m": "один", "f": "одна", "n": "одно", "pl": "одни"}
TWO_FORMS = {"m": "два", "f": "две", "n": "два", "pl": "две"}


def _agree_special(word: str, gender: str, number: str, case: str) -> str:
    """Согласование особых определителей (этот, тот, чей, весь)."""
    table = SPECIAL_AGREEMENT.get(word)
    if table is None:
        return morphology.agree_adj(word, gender, number, case)
    key = "pl" if number == "plur" else gender
    return table[key][case]


def _is_aux(tok: TokenData) -> bool:
    """Вспомогательный глагол, свёртываемый в форму знаменательного глагола."""
    return tok.pos == "AUX" and tok.dep in ("aux", "auxpass") and tok.lemma in (
        "be", "have", "do", "will", "would", "shall", "should",
        "can", "could", "may", "might", "must",
    )


class SentenceTranslator:
    """Перевод одного предложения: слоты русских словоформ по индексам токенов."""

    def __init__(self, sent: SentenceData, domain: str) -> None:
        self.sent = sent
        self.tokens = sent.tokens
        self.by_id = {t.id: t for t in sent.tokens}
        self.domain = domain
        self.children: dict[int, list[TokenData]] = {}
        for t in self.tokens:
            if t.head_id >= 0 and t.head_id in self.by_id:
                self.children.setdefault(t.head_id, []).append(t)
        for kids in self.children.values():
            kids.sort(key=lambda t: t.id)

        self.slots: dict[int, str] = {}
        self.consumed: set[int] = set()
        self.deferred: set[int] = set()   # определители, отложенные до именной группы
        self.translated: set[int] = set()
        self.unknown: list[str] = []
        self.articles_skipped = 0
        self.li_slot: int | None = None   # сказуемое с частицей «ли» (выносится в начало)
        self.phrase_owner: dict[int, int] = {}  # токен -> владелец слота оборота
        self.adj_feats: dict[int, tuple[str, str, str]] = {}  # id -> (род, число, падеж)
        self.phrase_base: dict[int, str] = {}   # владелец -> базовая форма оборота
        self.orphan_forms: dict[int, list[str]] = {}  # владелец -> пристроенные определения
        first_words = [t.id for t in sent.tokens if t.kind == "word"]
        self.first_word_id = first_words[0] if first_words else -1
        self.question = sent.text.strip().endswith("?")
        self.has_wh = any(
            t.kind == "word" and (t.lemma in WH_LEMMAS or t.tag in ("WP", "WRB", "WP$", "WDT"))
            for t in self.tokens
        )

    # --- утилиты ----------------------------------------------------------------
    def kids(self, tid: int, deps: tuple[str, ...] | None = None) -> list[TokenData]:
        result = self.children.get(tid, [])
        if deps:
            result = [t for t in result if t.dep in deps]
        return result

    def head(self, tok: TokenData) -> TokenData | None:
        return self.by_id.get(tok.head_id) if tok.head_id >= 0 else None

    def lookup_token(self, tok: TokenData, count_stats: bool = True):
        """Словарный эквивалент токена: сначала лемма, затем словоформа."""
        entry = lookup(tok.lemma, tok.pos, self.domain)
        if entry is None or not entry.target:
            entry = lookup(tok.word.lower(), tok.pos, self.domain)
        if (entry is None or not entry.target) and tok.lemma.endswith("s") \
                and tok.pos in ("NOUN", "PROPN"):
            entry = lookup(tok.lemma[:-1], tok.pos, self.domain)
        if entry is not None and entry.target:
            if count_stats and tok.kind == "word":
                self.translated.add(tok.id)
            return entry
        if count_stats and tok.kind == "word" and tok.id not in self.translated:
            self.unknown.append(tok.lemma)
        return None

    def _gender_of(self, entry, tok: TokenData | None) -> str:
        gram = entry.gram if entry else {}
        gender = (gram or {}).get("gender")
        if gender in ("m", "f", "n"):
            return gender
        target = entry.target if entry and entry.target else (tok.word if tok else "")
        if target.endswith(("а", "я")):
            return "f"
        return "m"

    def _number_of(self, tok: TokenData) -> str:
        return "plur" if tok.feats.get("Number") == "Plur" else "sing"

    # --- трансфер: свёртывание оборотов и служебных элементов ---------------------
    def match_phrases(self) -> None:
        """Замена оборотов словаря как единого целого (пословно-оборотный перевод).

        Сопоставляются леммы подряд идущих слов: и знаменательные обороты
        (clinical trial -> «клиническое исследование»), и служебные
        (in order to -> «чтобы»). Оборот переводится словарной формой целиком;
        падежное склонение внутри оборота не выполняется (упрощение учебной
        системы, см. справку).
        """
        word_tokens = [t for t in self.tokens if t.kind == "word"]
        lemmas = [t.lemma for t in word_tokens]
        i = 0
        while i < len(word_tokens):
            found = lookup_phrase(lemmas, i, self.domain)
            if found is not None:
                entry, size = found
                phrase_tokens = word_tokens[i:i + size]
                gender = (entry.gram or {}).get("gender")
                if gender in ("m", "f", "n"):
                    # Знаменательный оборот склоняется по падежу/числу своего
                    # корня — токена, чей родитель лежит вне оборота:
                    # after the clinical trial -> «после клинического
                    # исследования»; quality of life (dobj) -> «качество жизни».
                    phrase_ids = {t.id for t in phrase_tokens}
                    root = next((t for t in phrase_tokens if t.head_id not in phrase_ids),
                                phrase_tokens[0])
                    case, _after = self.case_for(root)
                    number = "plur" if root.feats.get("Number") == "Plur" else "sing"
                    target = morphology.decline_noun(
                        entry.target, gender, case, number,
                        bool(entry.gram.get("anim")), entry.gram)
                else:
                    # Служебный оборот переводится как есть («чтобы», «например»).
                    target = _phrase_target(entry, phrase_tokens)
                self.slots[word_tokens[i].id] = target
                self.phrase_base[word_tokens[i].id] = target
                for tok in phrase_tokens:
                    self.consumed.add(tok.id)
                    self.translated.add(tok.id)
                    self.phrase_owner[tok.id] = word_tokens[i].id
                i += size
                continue
            i += 1

    def prepass(self) -> None:
        self.match_phrases()
        for tok in self.tokens:
            if tok.kind != "word" or tok.id in self.consumed:
                continue
            # Артикли: в русском нет категории определённости — опускаются.
            if tok.lemma in ARTICLES and tok.pos == "DET":
                self.consumed.add(tok.id)
                self.articles_skipped += 1
                continue
            # Притяжательный аффикс 's обрабатывается внутри именной группы.
            if tok.tag == "POS":
                self.consumed.add(tok.id)
                self.translated.add(tok.id)
                continue
            # Эксплетив there (there is/are) — передаётся через сказуемое.
            if tok.dep == "expl" and tok.lemma == "there":
                self.consumed.add(tok.id)
                self.translated.add(tok.id)
                continue
            # Вспомогательные глаголы свёртываются в форму основного.
            if _is_aux(tok):
                self.consumed.add(tok.id)
                self.translated.add(tok.id)
                continue
            # Отрицание при сказуемом: «не» выдаётся вместе с глагольной формой.
            if tok.dep == "neg" or tok.lemma in ("not", "n't"):
                head_tok = self.head(tok)
                if head_tok is not None and (head_tok.pos in ("VERB", "AUX")
                                             or head_tok.tag.startswith("VB")):
                    self.consumed.add(tok.id)
                    self.translated.add(tok.id)
                    continue
            # Инфинитивная частица to перед глаголом (нет дополнения pobj).
            if tok.lemma == "to" and tok.pos in ("PART", "ADP", "SCONJ", "AUX") \
                    and not self.kids(tok.id, ("pobj", "pcomp")):
                self.consumed.add(tok.id)
                self.translated.add(tok.id)
                continue
            # Связка be (dep=cop): настоящее время опускается, прошедшее -> был/была/…
            if tok.dep == "cop" and tok.lemma == "be":
                self.consumed.add(tok.id)
                self.translated.add(tok.id)
                if tok.feats.get("Tense") == "Past":
                    owner = self.head(tok)
                    gender, number = "m", "sing"
                    if owner is not None:
                        subj = self.kids(owner.id, ("nsubj",))
                        if subj:
                            gender, number, _ = self._subject_agreement(subj[0])
                    self.slots[tok.id] = morphology.verb_past("быть", gender, number)
                continue

    # --- согласование сказуемого ---------------------------------------------------
    def _subject_agreement(self, subj: TokenData | None, verb: TokenData | None = None):
        """(род, число, лицо) для согласования русского сказуемого."""
        person = 3
        if verb is not None and verb.feats.get("Person"):
            try:
                person = int(verb.feats["Person"])
            except ValueError:
                person = 3
        if subj is None:
            number = "plur" if verb is not None and verb.feats.get("Number") == "Plur" else "sing"
            return "m", number, person
        if self.kids(subj.id, ("cc", "conj")):  # союзное подлежащее -> мн. ч.
            number = "plur"
        elif any(self.kids(ap.id, ("cc", "conj")) for ap in self.kids(subj.id, ("appos",))):
            number = "plur"  # перечисление через аппозицию: «A, B, and C play»
        else:
            number = self._number_of(subj)
        gender = self._gender_of(self.lookup_token(subj, count_stats=False), subj)
        if subj.pos == "PRON":
            entry = lookup(subj.lemma, "PRON", self.domain)
            key = entry.target if entry else None
            if key in PRON_AGREEMENT:
                person, number, gender = PRON_AGREEMENT[key]
            elif key == "это":
                gender = "n"
        if number == "plur":
            person = 1 if (subj is not None and subj.lemma == "i") else (3 if person == 3 else person)
        return gender, number, person

    # --- именная группа --------------------------------------------------------------
    def prep_info(self, prep: TokenData) -> tuple[str, str]:
        """Русский предлог и падеж дополнения с учётом локального контекста."""
        ru_prep, case = PREP_MAP.get(prep.lemma, ("", "nom"))
        head = self.head(prep)
        head_lemma = head.lemma if head else ""
        override = PREP_HEAD_OVERRIDES.get((head_lemma, prep.lemma))
        if override:
            return override
        if prep.lemma == "by":
            if prep.dep == "agent" or (head is not None and any(
                    k.dep == "auxpass" for k in self.kids(head.id))):
                return "", "inst"  # examined by doctors -> «(обследован) врачами»
            pobj = next(iter(self.kids(prep.id, ("pobj",))), None)
            # Степень изменения: reduce the risk by 30 percent -> «на 30 процентов».
            if pobj is not None and (pobj.pos == "NUM" or pobj.kind == "digit"
                                     or pobj.lemma == "percent"):
                return "на", "acc"
            # Авторство при существительном: a painting by Monet -> «картина Моне».
            if head is not None and head.pos in ("NOUN", "PROPN"):
                if pobj is not None and (pobj.pos == "PROPN" or self._is_anim(pobj)):
                    return "", "gen"
            return ru_prep, case
        if prep.lemma == "for":
            # for centuries -> «веками»: длительность — творительный без предлога.
            pobj = next(iter(self.kids(prep.id, ("pobj",))), None)
            if pobj is not None and pobj.lemma in TIME_NOUNS:
                return "", "inst"
            return ru_prep, case
        if prep.lemma == "to":
            if head_lemma in DATIVE_VERBS:
                return "", "dat"
            if head_lemma in MOTION_VERBS:
                return "в", "acc"
            return ru_prep, case
        if prep.lemma in ("in", "on", "at") and head_lemma in MOTION_VERBS:
            return ru_prep or "в", "acc"  # put in the box -> «в коробку»
        if prep.lemma == "at":
            # Устойчивое управление: at an early stage -> «на ранней стадии».
            pobj = next(iter(self.kids(prep.id, ("pobj",))), None)
            if pobj is not None and pobj.lemma in ("stage", "level", "end", "beginning"):
                return "на", "prep"
        return ru_prep, case

    def _attach_orphan(self, mod: TokenData, head: TokenData) -> bool:
        """Определение при главном слове, поглощённом оборотом словаря.

        Согласует определение с родом/числом/падежом оборота и дописывает его
        перед слотом главного слова. Возвращает True, если токен пристроен.
        """
        owner_id = self.phrase_owner.get(head.id, head.id)
        if head.id not in self.consumed or owner_id not in self.slots or not self.slots[owner_id]:
            return False
        head_entry = self.lookup_token(head, count_stats=False)
        if head_entry is None:
            return False
        gender = self._gender_of(head_entry, head)
        number = "plur" if head.feats.get("Number") == "Plur" else "sing"
        case, _after = self.case_for(head)
        anim = bool(head_entry.gram.get("anim"))
        if mod.pos == "ADJ":
            form = self._modifier_form(mod, gender, number, case, anim)
        else:
            det_entry = self.lookup_token(mod)
            if det_entry is None:
                return False
            base = det_entry.target
            form = (_agree_special(base, gender, number, case)
                    if base in SPECIAL_AGREEMENT
                    else morphology.agree_adj(base, gender, number, case, anim))
        forms = self.orphan_forms.setdefault(owner_id, [])
        forms.append(form)
        base = self.phrase_base.get(owner_id, self.slots[owner_id])
        self.slots[owner_id] = " ".join(forms + [base])
        self.consumed.add(mod.id)
        return True

    def _modifier_noun_head(self, tok: TokenData) -> TokenData | None:
        """Существительное-хозяин для определения через цепочку причастий.

        «A large randomized controlled trial»: randomized (npadvmod) ->
        controlled (amod) -> trial (NOUN).
        """
        head = self.head(tok)
        seen = 0
        while head is not None and seen < 6:
            if head.pos in ("NOUN", "PROPN", "PRON"):
                return head
            chained = (head.tag in ("VBN", "VBG") and head.dep in ("amod", "npadvmod", "acl")) \
                or (head.pos == "ADJ" and head.dep in ("amod", "npadvmod"))
            if chained:
                head = self.head(head)
                seen += 1
                continue
            break
        return None

    def _is_anim(self, tok: TokenData) -> bool:
        entry = lookup(tok.lemma, tok.pos, self.domain)
        return bool(entry and entry.gram.get("anim"))

    def case_for(self, tok: TokenData, depth: int = 0) -> tuple[str, bool]:
        """Падеж токена по синтаксической роли; флаг «после предлога» (него/ним)."""
        dep = tok.dep
        head = self.head(tok)
        if dep in ("conj", "appos") and head is not None and depth < 5:
            return self.case_for(head, depth + 1)
        if dep == "pobj" and head is not None:
            _, case = self.prep_info(head)
            return case, True
        if dep in ("dobj", "obj"):
            # Глагольное управление из словаря: help smb -> «помогать кому».
            if head is not None and head.pos in ("VERB", "AUX"):
                head_entry = lookup(head.lemma, "VERB", self.domain)
                gov = (head_entry.gram or {}).get("gov") if head_entry else None
                if gov in morphology.CASES:
                    return gov, False
            return "acc", False
        if dep == "dative":
            return "dat", False
        if dep in ("poss", "compound"):
            return "gen", False
        if dep == "npadvmod":
            return "acc", False
        if dep == "attr":
            # remains the main strategy -> «остаётся главной стратегией»
            if head is not None and head.pos == "VERB" and head.lemma in COPULAR_INST_VERBS:
                return "inst", False
            # Именная часть сказуемого: после прошедшей связки — творительный.
            if head is not None and head.lemma == "be":
                past = head.feats.get("Tense") == "Past" or any(
                    k.feats.get("Tense") == "Past" for k in self.kids(head.id, ("aux", "cop")))
                if past:
                    return "inst", False
            if head is not None:
                cop = self.kids(head.id, ("cop",))
                if cop and cop[0].feats.get("Tense") == "Past":
                    return "inst", False
            return "nom", False
        return "nom", False

    def nominal_form(self, tok: TokenData, case: str, number: str, after_prep: bool) -> str:
        """Русская словоформа имени/местоимения в заданном падеже."""
        entry = self.lookup_token(tok)
        if entry is None:
            return f"[{tok.word}]"
        target = entry.target
        if target in morphology.PRONOUNS:
            return morphology.pronoun_form(target, case, after_prep)
        if target in morphology.POSSESSIVES or target in morphology.INVARIANT_POSSESSIVES:
            return morphology.possessive_form(target, "m", number, case)
        if target in SPECIAL_AGREEMENT:
            gender = "pl" if number == "plur" else self._gender_of(entry, tok)
            return _agree_special(target, gender, number, case)
        if tok.pos in ("NOUN", "PROPN"):
            gender = self._gender_of(entry, tok)
            anim = bool(entry.gram.get("anim"))
            form = morphology.decline_noun(target, gender, case, number, anim, entry.gram)
            return form.capitalize() if tok.pos == "PROPN" else form
        if tok.pos == "ADJ":
            return morphology.agree_adj(target, self._gender_of(entry, tok), number, case)
        return target

    def _modifier_form(self, mod: TokenData, gender: str, number: str, case: str,
                       anim: bool = False) -> str:
        """Форма определения: прилагательное, причастие или степень сравнения."""
        entry = self.lookup_token(mod)
        if entry is None:
            return f"[{mod.word}]"
        degree = mod.feats.get("Degree", "")
        if degree == "Cmp" and entry.gram.get("compattr"):
            return morphology.agree_adj(entry.gram["compattr"], gender, number, case, anim)
        if degree == "Cmp" and entry.gram.get("comp"):
            return entry.gram["comp"]
        if degree == "Sup" and entry.gram.get("sup"):
            return entry.gram["sup"]
        base = entry.target
        if base in SPECIAL_AGREEMENT:
            return _agree_special(base, gender, number, case)
        is_infinitive = base.endswith(("ть", "сь", "чь"))
        if mod.tag == "VBN" and is_infinitive:
            base = morphology.full_participle(entry.gram.get("pair") or base, entry.gram)
        elif mod.tag == "VBG" and is_infinitive:
            base = self.active_participle(base)
        elif degree == "Cmp":
            return "более " + morphology.agree_adj(base, gender, number, case, anim)
        elif degree == "Sup":
            return "наиболее " + morphology.agree_adj(base, gender, number, case, anim)
        return morphology.agree_adj(base, gender, number, case, anim)

    @staticmethod
    def active_participle(inf: str) -> str:
        """Действительное причастие настоящего времени: висеть -> висящий."""
        form3pl = morphology.conjugate(inf, 3, "plur")
        for ending, suffix in (("ют", "ющ"), ("ут", "ущ"), ("ят", "ящ"), ("ат", "ащ")):
            if form3pl.endswith(ending):
                return form3pl[: -len(ending)] + suffix + "ий"
        return form3pl + "ий"

    def np(self, tid: int, case: str = "nom", after_prep: bool = False) -> str:
        """Синтез именной группы: определения до главного слова, посессивы,
        составные и предложные группы — после него."""
        tok = self.by_id[tid]
        self.consumed.add(tid)
        number = self._number_of(tok)
        kids = self.kids(tid)

        entry = self.lookup_token(tok)
        gender = self._gender_of(entry, tok)
        anim = bool(entry.gram.get("anim")) if entry else False

        # Квантификаторы: many symptoms -> «много симптомов» (род. п. мн. ч.).
        quant_word = ""
        for kid in kids:
            if kid.dep in ("amod", "quantmod", "det") and kid.lemma in QUANTIFIERS:
                quant_word = QUANTIFIERS[kid.lemma]
                case, number = "gen", "plur"
                self.consumed.add(kid.id)
                self.deferred.discard(kid.id)
                self.translated.add(kid.id)
                break

        # Числительные: two weeks -> «две недели» (род. п. ед. ч.).
        numeral_word = ""
        for kid in kids:
            if (kid.id in self.consumed and kid.id not in self.deferred) \
                    or kid.dep not in ("nummod", "det"):
                continue
            if kid.kind != "digit" and kid.lemma not in morphology.NUMBER_WORDS:
                continue
            if kid.kind == "digit":
                numeral_word = kid.word
                digits = re.sub(r"\D", "", kid.word)
                value = int(digits) if digits else 5
            else:
                numeral_word = morphology.NUMBER_WORDS[kid.lemma]
                value = {"один": 1, "два": 2, "три": 3, "четыре": 4}.get(numeral_word, 5)
                self.translated.add(kid.id)
            gov = morphology.numeral_noun_case(value)
            case, number = gov.split("_")[0], gov.split("_")[1]
            self.consumed.add(kid.id)
            if value == 1 and numeral_word == "один":
                numeral_word = ONE_FORMS["pl" if number == "plur" else gender]
            elif value == 2 and numeral_word == "два":
                numeral_word = TWO_FORMS["pl" if number == "plur" else gender]
            break

        pre: list[str] = []
        post: list[str] = []
        for kid in kids:
            if kid.id in self.consumed and kid.id not in self.deferred:
                continue
            if kid.dep in ("det", "predet") and kid.pos in ("DET", "PRON"):
                self.consumed.add(kid.id)
                self.deferred.discard(kid.id)
                if kid.lemma in ARTICLES:
                    continue
                det_entry = self.lookup_token(kid)
                if det_entry is None:
                    pre.append(f"[{kid.word}]")
                    continue
                base = det_entry.target
                if base in SPECIAL_AGREEMENT:
                    pre.append(_agree_special(base, gender, number, case))
                else:
                    pre.append(morphology.agree_adj(base, gender, number, case, anim))
                continue
            if kid.dep == "poss":
                # my book -> «моя книга»; the doctor's decision -> «решение врача».
                self.consumed.add(kid.id)
                self.deferred.discard(kid.id)
                if kid.pos == "PRON" or kid.tag == "PRP$":
                    poss_entry = self.lookup_token(kid)
                    if poss_entry is not None:
                        pre.append(morphology.possessive_form(
                            poss_entry.target, gender, number, case, anim))
                    else:
                        pre.append(f"[{kid.word}]")
                else:
                    for mark in self.kids(kid.id, ("case",)):
                        self.consumed.add(mark.id)
                    post.append(self.np(kid.id, "gen"))
                continue
            if kid.dep == "amod":
                self.consumed.add(kid.id)
                self.deferred.discard(kid.id)
                pre.append(self._modifier_form(kid, gender, number, case, anim))
                continue
            if kid.dep == "compound" and kid.pos in ("NOUN", "PROPN", "NUM"):
                # blood test -> «анализ крови»: зависимый компонент после главного.
                self.consumed.add(kid.id)
                self.deferred.discard(kid.id)
                kentry = self.lookup_token(kid, count_stats=False)
                if kentry is not None and kentry.pos == "ADJ":
                    # spaCy пометил прилагательное существительным (timeless value):
                    # согласуем его как определение — «вневременную ценность».
                    pre.append(self._modifier_form(kid, gender, number, case, anim))
                else:
                    post.append(self.np(kid.id, "gen"))
                continue
            if kid.dep == "compound" and kid.pos in ("ADJ",):
                self.consumed.add(kid.id)
                self.deferred.discard(kid.id)
                pre.append(self._modifier_form(kid, gender, number, case, anim))
                continue
            if kid.dep == "prep" and kid.pos in ("ADP", "SCONJ"):
                # of the painting -> «картины»; on the wall -> «на стене».
                self.consumed.add(kid.id)
                ru_prep, prep_case = self.prep_info(kid)
                fragments = [self.np(p.id, prep_case, after_prep=True)
                             for p in self.kids(kid.id, ("pobj", "pcomp"))
                             if p.id not in self.consumed]
                joined = " и ".join(f for f in fragments if f)
                post.append((ru_prep + " " + joined).strip() if joined else ru_prep)
                continue
            if kid.dep == "appos":
                self.consumed.add(kid.id)
                self.deferred.discard(kid.id)
                # Приложение выделяется запятой: «диета, упражнение и диагноз».
                post.append(", " + self.np(kid.id, case, after_prep))
                continue
            if kid.dep == "cc":
                # Союз: если однородный член жив — обработается списком ниже;
                # если поглощён оборотом словаря — выдаём союз здесь.
                has_conj = any(k.dep == "conj" and (k.id not in self.consumed
                                                    or k.id in self.deferred)
                               for k in kids)
                self.consumed.add(kid.id)
                self.deferred.discard(kid.id)
                if not has_conj:
                    cc_entry = self.lookup_token(kid)
                    post.append(cc_entry.target if cc_entry and cc_entry.target else "и")
                continue
            if kid.dep == "conj":
                # Однородные члены собираются по цепочке: A, B, C and D
                # (spaCy может выстраивать их и плоско, и цепочкой).
                chain = [kid]
                cur = kid
                while True:
                    nxt = next((k for k in self.kids(cur.id, ("conj",))
                                if k.id not in self.consumed or k.id in self.deferred), None)
                    if nxt is None:
                        break
                    chain.append(nxt)
                    cur = nxt
                cc_word = "и"
                for node in [tok] + chain:
                    for cck in self.kids(node.id, ("cc",)):
                        cc_entry = self.lookup_token(cck)
                        if cc_entry and cc_entry.target:
                            cc_word = cc_entry.target
                        self.consumed.add(cck.id)
                        self.deferred.discard(cck.id)
                for c in chain:
                    self.consumed.add(c.id)
                    self.deferred.discard(c.id)
                forms = [self.np(c.id, case, after_prep) for c in chain]
                if len(forms) == 1:
                    post.append(cc_word + " " + forms[0])
                else:
                    post.append(", " + ", ".join(forms[:-1]) + " " + cc_word + " " + forms[-1])
                continue
            if kid.kind == "punct":
                # Запятые перечисления восстановлены сборкой однородных членов.
                self.consumed.add(kid.id)
                continue

        head_form = self.nominal_form(tok, case, number, after_prep)
        if tok.pos == "PROPN":
            head_form = head_form.capitalize()
        parts = ([quant_word] if quant_word else []) + ([numeral_word] if numeral_word else []) \
            + pre + [head_form] + post
        return " ".join(p for p in parts if p)

    # --- глагольная группа ------------------------------------------------------------
    def _tense_of(self, tok: TokenData) -> str:
        """Время с учётом вспомогательных глаголов: was developing -> Past.

        У причастий (VerbForm=Part) собственный Tense означает не время
        предложения, поэтому для них время берётся только у вспомогательных:
        «is kept» -> настоящее, «was kept» -> прошедшее.
        """
        aux_past = any(k.feats.get("Tense") == "Past" for k in self.kids(tok.id, ("aux", "auxpass")))
        aux_pres = any(k.feats.get("Tense") == "Pres" for k in self.kids(tok.id, ("aux", "auxpass")))
        if tok.feats.get("VerbForm") == "Part":
            return "Past" if aux_past else "Pres"
        if tok.feats.get("Tense") == "Past":
            return "Past"
        if aux_past:
            return "Past"
        if aux_pres:
            return "Pres"
        return tok.feats.get("Tense", "Pres")

    def verb_phrase(self, tid: int) -> str:
        """Синтез сказуемого: залог, время, вид, модальность, отрицание, вопрос."""
        tok = self.by_id[tid]
        self.consumed.add(tid)
        kids = self.kids(tid)

        subj = next((k for k in kids if k.dep in ("nsubj", "nsubjpass", "csubj")), None)
        if subj is None and tok.dep == "conj":
            # Однородное сказуемое наследует подлежащее главного.
            hv = self.head(tok)
            seen = 0
            while hv is not None and hv.dep == "conj" and seen < 5:
                hv = self.head(hv)
                seen += 1
            if hv is not None:
                subj = next(iter(self.kids(hv.id, ("nsubj", "nsubjpass", "csubj"))), None)
        gender, number, person = self._subject_agreement(subj, tok)
        tense = self._tense_of(tok)

        # --- Глагол-связка be (there is / X is Y / X was Y) -------------------------
        if tok.lemma == "be":
            has_expl = any(k.dep == "expl" for k in kids)
            pred = next((k for k in kids if k.dep in ("attr", "acomp")), None)
            if has_expl:
                g, n = gender, number
                if pred is not None:
                    g = self._gender_of(self.lookup_token(pred, count_stats=False), pred)
                    n = self._number_of(pred)
                if tense == "Past":
                    phrase = morphology.verb_past("быть", g, n)
                else:
                    phrase = "имеется" if n == "sing" else "имеются"
            elif tense == "Past":
                phrase = morphology.verb_past("быть", gender, number)
            else:
                phrase = ""  # настоящая связка в русском опускается
            if phrase and self.question and not self.has_wh and tok.dep == "ROOT":
                phrase += " ли"
            self.slots[tid] = phrase
            self.translated.add(tok.id)
            return phrase

        entry = self.lookup_token(tok)
        if entry is None:
            self.slots[tid] = f"[{tok.word}]"
            return self.slots[tid]
        gram = entry.gram or {}
        inf = entry.target
        pair = gram.get("pair")
        aspect = gram.get("aspect", "impf")

        neg = any(k.dep == "neg" or k.lemma in ("not", "n't") for k in kids)
        for kid in kids:
            if kid.dep == "neg" or kid.lemma in ("not", "n't"):
                self.consumed.add(kid.id)
                self.slots.pop(kid.id, None)

        modal = next((k for k in kids if k.dep == "aux" and (k.tag == "MD" or k.lemma in MODALS)), None)
        passive = any(k.dep == "auxpass" and k.lemma == "be" for k in kids)
        perfect = any(k.dep == "aux" and k.lemma == "have" for k in kids)
        do_aux = any(k.dep == "aux" and k.lemma == "do" for k in kids)
        be_aux = any(k.dep == "aux" and k.lemma == "be" for k in kids)
        vform = tok.feats.get("VerbForm", "Fin")

        prefix = ""
        words: list[str] = []

        # Относительное придаточное: «который» + личная форма.
        if tok.dep == "relcl":
            head = self.head(tok)
            if head is not None:
                head_entry = self.lookup_token(head, count_stats=False)
                gender = self._gender_of(head_entry, head)
                number = self._number_of(head)
                person = 3
                prefix = morphology.agree_adj("который", gender, number, "nom") + " "

        def finite() -> str:
            return morphology.conjugate(inf, person, number, gram)

        def finite_of(verb: str) -> str:
            return morphology.conjugate(verb, person, number, gram)

        def past(verb: str) -> str:
            return morphology.verb_past(verb, gender, number, gram)

        # 1) Модальность (в т. ч. модальный пассив: will be examined -> «будет обследован»)
        if modal is not None:
            self.consumed.add(modal.id)
            m = modal.lemma
            pp = morphology.short_participle(pair or inf, gender, number, gram) if passive else ""
            if m == "can":
                base = "мог" if tense == "Past" else finite_of("мочь")
                words += [base, ("быть " + pp) if passive else inf]
            elif m == "could":
                words += ["мог", "бы", ("быть " + pp) if passive else inf]
            elif m in ("must", "should", "shall"):
                short = {"m": "должен", "f": "должна", "n": "должно"}.get(gender, "должен")
                words.append(short if number == "sing" else "должны")
                words.append(("быть " + pp) if passive else inf)
            elif m in ("may", "might"):
                words.append("мог бы" if (m == "might" and tense == "Past") else "может")
                words.append(("быть " + pp) if passive else inf)
            elif m in ("will", "shall") or m == "would":
                if m == "would":
                    words.append(past(pair or inf))
                    words.append("бы")
                elif passive:
                    idx = (3 if number == "plur" else 0) + person - 1
                    words += [BE_FUTURE[idx], pp]
                elif pair and aspect == "impf":
                    words.append(finite_of(pair))       # простое будущее сов. вида
                else:
                    idx = (3 if number == "plur" else 0) + person - 1
                    words += [BE_FUTURE[idx], inf]      # будущее несовершенного вида
            else:
                words.append(inf)
        # 2) Пассив: was examined -> «был обследован»; is caused -> «вызывается»
        elif passive:
            pp = morphology.short_participle(pair or inf, gender, number, gram)
            if tense == "Past" or perfect:
                words += [morphology.verb_past("быть", gender, number), pp]
            else:
                reflexive = inf if inf.endswith("ся") else inf + "ся"
                words.append(finite_of(reflexive))
        # 3) Перфект: has developed -> «развил»; с for/since — несовершенный вид
        elif perfect:
            durative = any(
                k.pos in ("ADP", "SCONJ") and k.lemma in ("for", "since") for k in kids
            )
            words.append(past(inf) if durative else past(pair or inf))
        # 4) Инфинитив (после модальных, после to, xcomp); но с do-опорой — личная форма
        elif (vform == "Inf" and not do_aux) or (tok.dep == "xcomp" and vform == "Inf"):
            words.append(inf)
        # 5) Причастия, деепричастия и прогрессив
        elif vform == "Part" and tok.tag == "VBG":
            if tok.dep == "acl":
                head = self.head(tok)
                head_entry = self.lookup_token(head, count_stats=False) if head else None
                g = self._gender_of(head_entry, head) if head else "m"
                n = self._number_of(head) if head else "sing"
                case, _ = self.case_for(head) if head else ("nom", False)
                words.append(morphology.agree_adj(self.active_participle(inf), g, n, case))
            elif tok.dep == "advcl":
                words.append(morphology.gerund(inf))
            elif be_aux or tok.dep == "ROOT":
                # Прогрессив: was developing -> «развивал» (несовершенный вид).
                words.append(past(inf) if tense == "Past" else finite())
            else:
                words.append(inf)
        elif vform == "Part" and tok.tag == "VBN":
            # Причастие-определение: согласуем с существительным (через цепочку).
            noun_head = self._modifier_noun_head(tok) or self.head(tok)
            if noun_head is not None and not any(
                    k.dep in ("aux", "auxpass") for k in kids):
                head_entry = self.lookup_token(noun_head, count_stats=False)
                g = self._gender_of(head_entry, noun_head)
                n = self._number_of(noun_head)
                case, _ = self.case_for(noun_head)
                base = inf
                if base.endswith(("ть", "сь", "чь")):
                    base = morphology.full_participle(pair or base, gram)
                words.append(morphology.agree_adj(base, g, n, case))
            else:
                head = self.head(tok)
                head_entry = self.lookup_token(head, count_stats=False) if head else None
                g = self._gender_of(head_entry, head) if head else "m"
                n = self._number_of(head) if head else "sing"
                case, _ = self.case_for(tok)
                base = inf
                if base.endswith(("ть", "сь", "чь")):
                    base = morphology.full_participle(pair or base, gram)
                words.append(morphology.agree_adj(base, g, n, case))
        # 6) Повелительное наклонение (ROOT без подлежащего)
        elif tok.dep == "ROOT" and subj is None and not self.question:
            if inf.endswith("ить"):
                words.append(inf[:-3] + "ьте")
            elif inf.endswith("овать"):
                words.append(inf[:-5] + "уйте")
            elif inf.endswith(("ать", "ять", "еть", "уть", "оть", "ыть")):
                words.append(inf[:-2] + "йте")
            else:
                words.append(inf)
        # 7) Личная форма: Past -> прошедший (сов. вид при наличии пары), иначе настоящее
        else:
            if tense == "Past":
                words.append(past(pair or inf))
            else:
                words.append(finite())

        # Вопрос общего вида: частица «ли» после сказуемого.
        if self.question and not self.has_wh and tok.dep == "ROOT" and words:
            words.append("ли")
            self.li_slot = tid

        phrase = prefix + ("не " if neg else "") + " ".join(w for w in words if w)
        self.slots[tid] = phrase
        return phrase

    # --- линейный проход ----------------------------------------------------------------
    def run_transfer(self) -> str:
        self.prepass()
        for tok in self.tokens:
            if tok.id in self.consumed:
                continue
            if tok.kind == "punct":
                self.slots[tok.id] = tok.word
                continue
            if tok.kind == "digit":
                self.translated.add(tok.id)
                self.consumed.add(tok.id)
                head_tok = self.head(tok)
                if (tok.dep in ("nummod", "npadvmod", "quantmod") and head_tok is not None
                        and head_tok.id > tok.id and head_tok.id not in self.consumed):
                    # числительное включит в себя именная группа («500 пациентов»)
                    self.deferred.add(tok.id)
                else:
                    self.slots[tok.id] = tok.word
                continue
            pos, dep = tok.pos, tok.dep

            # Определения, стоящие перед главным словом, синтезирует именная
            # группа (откладываем токен до обработки существительного).
            if dep in MODIFIER_DEPS and tok.head_id > tok.id:
                head_tok = self.by_id.get(tok.head_id)
                if (head_tok is not None and head_tok.pos in ("NOUN", "PROPN", "PRON")
                        and head_tok.id not in self.consumed):
                    self.consumed.add(tok.id)
                    self.deferred.add(tok.id)
                    continue

            # Сказуемое (в т. ч. связка be как ROOT).
            if pos in ("VERB", "AUX") or tok.tag.startswith("VB"):
                self.verb_phrase(tok.id)
                continue

            # Предлоги: русский предлог в слот, падеж — дополнению.
            if pos == "ADP" or tok.tag == "IN":
                if not self.kids(tok.id, ("pobj", "pcomp")):
                    entry = self.lookup_token(tok)
                    word = entry.target if entry else f"[{tok.word}]"
                    if (tok.pos == "SCONJ" or tok.dep == "mark" or tok.lemma == "than") \
                            and word and tok.id != self.first_word_id and word[0] not in ",;:[":
                        word = ", " + word  # «показывают, что ...»; «лучше, чем ...»
                    self.slots[tok.id] = word
                    self.consumed.add(tok.id)
                    continue
                ru_prep, _case = self.prep_info(tok)
                if tok.lemma == "than" and ru_prep and tok.id != self.first_word_id:
                    ru_prep = ", " + ru_prep   # «лучше, чем ...»
                self.slots[tok.id] = ru_prep
                self.consumed.add(tok.id)
                self.translated.add(tok.id)
                continue

            # Имена и местоимения: синтез именной группы.
            if pos in ("NOUN", "PROPN", "PRON"):
                head_tok = self.head(tok)
                if (pos == "PRON" and tok.lemma in ("who", "whom", "which", "that")
                        and head_tok is not None and head_tok.dep == "relcl"):
                    # who received -> «которые получили»: местоимение поглощает «который»
                    self.consumed.add(tok.id)
                    self.translated.add(tok.id)
                    continue
                if pos == "PRON" and tok.lemma in ("this", "that") \
                        and dep in ("nsubj", "attr", "dobj", "obj", "ROOT", "pobj"):
                    self.slots[tok.id] = "это"
                    self.consumed.add(tok.id)
                    self.translated.add(tok.id)
                    continue
                case, after_prep = self.case_for(tok)
                form = self.np(tok.id, case, after_prep)
                if dep in ("dobj", "obj") and not after_prep:
                    head_tok2 = self.head(tok)
                    if head_tok2 is not None and head_tok2.pos in ("VERB", "AUX"):
                        head_entry = lookup(head_tok2.lemma, "VERB", self.domain)
                        gov_prep = (head_entry.gram or {}).get("govprep") if head_entry else None
                        if gov_prep:
                            form = gov_prep + " " + form  # «влиять на курс»
                self.slots[tok.id] = form
                continue

            # Прилагательные.
            if pos == "ADJ":
                entry = self.lookup_token(tok)
                if entry is None:
                    self.slots[tok.id] = f"[{tok.word}]"
                    self.consumed.add(tok.id)
                    continue
                if dep == "amod":
                    head = self.head(tok)
                    if head is not None and head.id not in self.consumed:
                        # определение синтезирует именная группа главного слова
                        self.consumed.add(tok.id)
                        continue
                    # Главное слово уже поглощено оборотом — согласуем с ним
                    # и присоединяем определение к его слоту:
                    # severe [heart disease] -> «тяжёлой болезнью сердца».
                    if head is not None and self._attach_orphan(tok, head):
                        continue
                    self.slots[tok.id] = self._modifier_form(tok, "m", "sing", "nom")
                elif dep == "acomp":
                    # Именная часть сказуемого: согласуем с подлежащим; после
                    # remain/become/seem — творительный падеж («остаётся эффективной»).
                    head = self.head(tok)
                    gender, number = "m", "sing"
                    if head is not None:
                        subj = next(iter(self.kids(head.id, ("nsubj", "nsubjpass"))), None)
                        if subj is not None:
                            gender, number, _ = self._subject_agreement(subj)
                    adj_case = "inst" if (head is not None and head.lemma in COPULAR_INST_VERBS) else "nom"
                    base = entry.target
                    if entry.gram.get("comp") and tok.feats.get("Degree") == "Cmp":
                        self.slots[tok.id] = entry.gram["comp"]
                    else:
                        self.slots[tok.id] = morphology.agree_adj(base, gender, number, adj_case)
                    self.adj_feats[tok.id] = (gender, number, adj_case)
                else:
                    case, _ = self.case_for(tok)
                    gender = self._gender_of(entry, tok)
                    number = "sing"
                    # Однородное определение наследует согласование первого:
                    # «мазки быстрые и смелые».
                    conj_head = self.head(tok) if dep == "conj" else None
                    if conj_head is not None and conj_head.id in self.adj_feats:
                        gender, number, case = self.adj_feats[conj_head.id]
                    elif dep == "conj" and conj_head is not None:
                        gender = self._gender_of(
                            self.lookup_token(conj_head, count_stats=False), conj_head)
                    self.slots[tok.id] = morphology.agree_adj(entry.target, gender, number, case)
                    self.adj_feats[tok.id] = (gender, number, case)
                self.consumed.add(tok.id)
                continue

            # more/most/less при наречиях и прилагательных -> «более/наиболее/менее».
            if pos == "ADV" and tok.lemma in ("more", "most", "less") and dep == "advmod":
                self.slots[tok.id] = {"more": "более", "most": "наиболее", "less": "менее"}[tok.lemma]
                self.consumed.add(tok.id)
                self.translated.add(tok.id)
                continue

            # Определитель при поглощённом оборотом существительном.
            if pos == "DET" and tok.lemma not in ARTICLES:
                head_tok = self.head(tok)
                if head_tok is not None and self._attach_orphan(tok, head_tok):
                    continue

            # Наречия, союзы, частицы, числительные и прочее — по словарю.
            entry = self.lookup_token(tok)
            if entry is None:
                self.slots[tok.id] = f"[{tok.word}]"
            else:
                word = entry.target
                degree = tok.feats.get("Degree", "")
                if degree == "Cmp" and entry.gram.get("comp"):
                    word = entry.gram["comp"]
                elif degree == "Sup" and entry.gram.get("sup"):
                    word = entry.gram["sup"]
                if tok.pos == "PROPN":
                    word = word.capitalize()
                if pos == "SCONJ" and word and tok.id != self.first_word_id \
                        and word[0] not in ",;:[":
                    word = ", " + word  # «показывают, что ...»
                self.slots[tok.id] = word
            self.consumed.add(tok.id)

        return self.assemble()

    def assemble(self) -> str:
        items = [(t.id, self.slots.get(t.id, "")) for t in self.tokens]
        items = [(i, s) for i, s in items if s]
        # Вопрос общего вида: сказуемое с «ли» выносится в начало предложения
        # («Препарат вызывает ли...?» -> «Вызывает ли препарат...?»).
        if self.li_slot is not None:
            li_idx = next((k for k, (i, _s) in enumerate(items) if i == self.li_slot), None)
            if li_idx is not None and li_idx != 0:
                li_item = items.pop(li_idx)
                if items:
                    first = items[0][1]
                    items[0] = (items[0][0], first[0].lower() + first[1:])
                items = [li_item] + items
        text = " ".join(s for _i, s in items)
        text = _PUNCT_CLEANUP.sub(r"\1", text)
        text = re.sub(r",\s*,", ",", text)   # «победы,, в то время» -> одна запятая
        # Предлог «во» перед ф и кластерами согласных: во Флоренции, во Франции.
        text = re.sub(
            r"(?<![\w-])в (?=[фФ]|[влмнстдркгбпВЛМНСТДРКГБП](?=[^аоуеиыяюёэАОУЕИЫЯЮЁЭ\s]))",
            "во ", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        if text:
            text = text[0].upper() + text[1:]
        return text

    # --- прямой (пословный) перевод -----------------------------------------------------
    def run_literal(self) -> str:
        """Система прямого перевода: замена элементов словарными эквивалентами.

        Учитывается локальный контекст — обороты (многословные статьи словаря)
        заменяются как единое целое; морфологический синтез не выполняется.
        """
        word_tokens = [t for t in self.tokens if t.kind == "word"]
        lemmas = [t.lemma for t in word_tokens]
        i = 0
        while i < len(word_tokens):
            found = lookup_phrase(lemmas, i, self.domain)
            if found:
                entry, size = found
                self.slots[word_tokens[i].id] = _phrase_target(entry, word_tokens[i:i + size])
                for tok in word_tokens[i:i + size]:
                    self.consumed.add(tok.id)
                    self.translated.add(tok.id)
                i += size
                continue
            i += 1

        for tok in self.tokens:
            if tok.id in self.consumed:
                continue
            if tok.kind == "punct":
                self.slots[tok.id] = tok.word
                continue
            if tok.kind == "digit":
                self.slots[tok.id] = tok.word
                self.translated.add(tok.id)
                continue
            if tok.lemma in ARTICLES and tok.pos == "DET":
                self.consumed.add(tok.id)
                self.articles_skipped += 1
                continue
            if tok.tag == "POS":
                self.consumed.add(tok.id)
                continue
            entry = self.lookup_token(tok)
            if entry is None:
                self.slots[tok.id] = f"[{tok.word}]"
            else:
                word = entry.target
                if tok.pos == "PROPN":
                    word = word.capitalize()
                self.slots[tok.id] = word
            self.consumed.add(tok.id)
        return self.assemble()


def _phrase_target(entry, phrase_tokens) -> str:
    """Эквивалент оборота: форма мн. ч. из gram['pl'], если последний токен во мн. ч."""
    if phrase_tokens and phrase_tokens[-1].feats.get("Number") == "Plur":
        plural = (entry.gram or {}).get("pl")
        if plural:
            return plural
    return entry.target


def translate_sentence(sent: SentenceData, domain: str, mode: str):
    """Перевод предложения.

    Возвращает (текст перевода, множество переведённых токенов, список
    неизвестных лемм, число опущенных артиклей).
    """
    translator = SentenceTranslator(sent, domain)
    if mode == "literal":
        text = translator.run_literal()
    else:
        text = translator.run_transfer()
    return text, translator.translated, translator.unknown, translator.articles_skipped
