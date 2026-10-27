# -*- coding: utf-8 -*-
"""
Стоп-слова (а также числа и слова «чужой» письменности)
не учитываются при вычислении весов слов документа.
Токенизация разбивает слова по апострофам (фр. elision: l'homme -> l, homme),
поэтому элизированные формы (l, c, d, j, m, n, s, t, qu) включены в список.
"""

STOPWORDS_EN = {
    # артикли, местоимения, служебные слова
    "a", "an", "the", "i", "you", "he", "she", "it", "we", "they", "me", "him",
    "her", "us", "them", "my", "your", "his", "its", "our", "their", "mine",
    "yours", "hers", "ours", "theirs", "myself", "yourself", "himself",
    "herself", "itself", "ourselves", "themselves", "this", "that", "these",
    "those", "there", "here", "who", "whom", "whose", "which", "what", "where",
    "when", "why", "how", "all", "any", "both", "each", "few", "more", "most",
    "other", "another", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "because", "as", "until",
    "while", "of", "at", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below", "to",
    "from", "up", "down", "in", "out", "on", "off", "over", "under", "again",
    "further", "then", "once", "if", "or", "but", "and",
    # глагольные формы / модальные
    "am", "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "having", "do", "does", "did", "doing", "will", "would", "shall",
    "should", "can", "could", "may", "might", "must",
    # усечённые формы отрицаний (don't -> don, t)
    "t", "s", "re", "ve", "ll", "d", "m", "don", "doesn", "didn", "isn",
    "aren", "wasn", "weren", "won", "wouldn", "couldn", "shouldn", "hasn",
    "haven", "hadn", "cannot",
    # вводные / общие наречия
    "also", "however", "thus", "therefore", "hence", "often", "perhaps",
    "indeed", "instead", "meanwhile", "otherwise", "nevertheless",
    "nonetheless", "although", "though", "unless", "whether", "among",
    "across", "behind", "beyond", "within", "without", "along", "around",
    "upon", "per", "via", "etc", "ie", "eg", "cf", "vs", "mr", "mrs", "ms",
    "dr", "prof", "st", "al", "ed", "eds", "vol", "pp", "fig", "figs", "eq",
    "no", "nos", "one", "two", "three", "four", "five", "six", "seven",
    "eight", "nine", "ten", "many", "much", "several", "every", "either",
    "neither", "us", "let", "lets",
}

STOPWORDS_FR = {
    # артикли, местоимения, служебные слова
    "le", "la", "les", "un", "une", "des", "du", "au", "aux", "de", "d",
    "je", "j", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "me", "moi", "te", "toi", "se", "soi", "lui", "eux", "y", "en",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "notre",
    "nos", "votre", "vos", "leur", "leurs", "nôtre", "ce", "cet", "cette",
    "ces", "ceci", "cela", "celà", "ça", "celui", "celle", "ceux", "celles",
    "ci", "là", "lequel", "laquelle", "lesquels", "lesquelles", "duquel",
    "auquel", "auxquels", "auxquelles", "qui", "que", "quoi", "dont", "où",
    "quel", "quelle", "quels", "quelles", "quelque", "quelques", "chacun",
    "chacune", "tous", "tout", "toute", "toutes", "aucun", "aucune",
    "autre", "autres", "même", "mêmes", "nul", "nulle", "personne",
    # предлоги, союзы
    "à", "a", "et", "ou", "mais", "donc", "or", "ni", "car", "si", "comme",
    "dans", "sur", "sous", "par", "pour", "avec", "sans", "chez", "entre",
    "vers", "contre", "depuis", "durant", "pendant", "avant", "après",
    "près", "loin", "hors", "selon", "malgré", "grâce", "faute", "afin",
    "ainsi", "alors", "ensuite", "enfin", "donc", "parce", "que", "quand",
    "lors", "lorsque", "puisque", "quoique", "bien", "tant", "tandis",
    "sinon", "voire", "excepté", "hormis", "outre", "parmi", "envers",
    "en", "y",
    # глагольные формы (être, avoir, аллитерации)
    "suis", "es", "est", "sommes", "êtes", "sont", "serai", "seras",
    "sera", "serons", "serez", "seront", "serais", "serait", "serions",
    "seriez", "seraient", "étais", "était", "étions", "étiez", "étaient",
    "fus", "fut", "fûmes", "fûtes", "furent", "sois", "soit", "soyons",
    "soyez", "soient", "fusse", "fusses", "fût", "fussions", "fussiez",
    "fussent", "été", "étée", "étées", "étés", "étant", "ai", "as", "a",
    "avons", "avez", "ont", "avais", "avait", "avions", "aviez",
    "avaient", "eus", "eut", "eûmes", "eûtes", "eurent", "aie", "aies",
    "ait", "ayons", "ayez", "aient", "eue", "eues", "eu", "aurai",
    "auras", "aura", "aurons", "aurez", "auront", "aurais", "aurait",
    "aurions", "auriez", "auraient", "ayant",
    # элизии, отрицания, наречия, вводные
    "c", "l", "m", "n", "s", "t", "qu", "jusqu", "lorsqu", "puisqu",
    "quoiqu", "qu", "ne", "pas", "point", "plus", "moins", "guère",
    "jamais", "toujours", "souvent", "parfois", "déjà", "encore",
    "aussi", "très", "trop", "assez", "peu", "beaucoup", "combien",
    "environ", "presque", "ici", "ailleurs", "partout", "dedans",
    "dehors", "dessus", "dessous", "aujourd", "hui", "demain", "hier",
    "maintenant", "cependant", "néanmoins", "toutefois", "pourtant",
    "dès", "dés", "ès", "non", "oui", "si", "seulement", "donc",
    "ainsi", "alors", "ensuite", "enfin", "bref", "certes", "d'abord",
    "dailleurs", "d'ailleurs", "dorénavant", "désormais", "d'après",
    "selon", "quant", "quant-à-soi", "revoici", "revoilà", "voici",
    "voilà", "etc", "cf", "vs", "m", "mme", "mm", "dr", "prof", "st",
    "vol", "pp", "fig", "eq", "nos", "n°",
}

STOPWORDS = {
    "en": STOPWORDS_EN,
    "fr": STOPWORDS_FR,
}

LANG_NAMES = {
    "en": "Английский",
    "fr": "Французский",
}

DOMAIN_NAMES = {
    "cs": "Научные статьи по computer science",
    "lit": "Сочинения по литературе",
}


def get_stopwords(lang: str) -> set:
    return STOPWORDS.get(lang, set())
