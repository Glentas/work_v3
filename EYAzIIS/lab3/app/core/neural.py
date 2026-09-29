# -*- coding: utf-8 -*-
"""Нейросетевой метод (замена технологии OSTIS в варианте 7).

Нейросетевые эмбеддинги предложений используются для:
  1) семантического уточнения отбора предложений (MMR: значимость - избыточность);
  2) семантической группировки ключевых слов в иерархический список;
  3) оценки качества реферата (косинусная близость реферат <-> документ).

Бэкенды:
  * transformers-onnx - многоязычный трансформер
    paraphrase-multilingual-MiniLM-L12-v2 в квантованном ONNX-виде
    (onnxruntime, без torch; поддерживает fr и en);
  * transformers - та же сеть через sentence-transformers (torch);
  * skipgram     - собственная реализация нейросети skip-gram negative sampling
    (numpy), обучается на тестовой коллекции, работает полностью офлайн.
Выбор: env NEURAL_BACKEND = auto | onnx | transformers | skipgram | none.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

import numpy as np

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", ".cache")
TRANSFORMER_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
HF_REPO_ID = "sentence-transformers/" + TRANSFORMER_MODEL


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class NeuralBackend:
    name = "base"

    def embed(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError


class NoneBackend(NeuralBackend):
    name = "none"

    def embed(self, texts):
        return np.zeros((len(texts), 8), dtype=np.float32)


class TransformerBackend(NeuralBackend):
    """Многоязычный трансформер (sentence-transformers)."""
    name = "transformers"

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(TRANSFORMER_MODEL)

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.model.get_sentence_embedding_dimension()),
                            dtype=np.float32)
        vecs = self.model.encode(texts, batch_size=32, show_progress_bar=False,
                                 normalize=False)
        return np.asarray(vecs, dtype=np.float32)


ONNX_DIR = os.path.join(CACHE_DIR, "st_onnx")
ONNX_FILES = {
    "model_quint8_avx2.onnx": f"https://huggingface.co/{HF_REPO_ID}/resolve/main/onnx/model_quint8_avx2.onnx",
    "model_O4.onnx": f"https://huggingface.co/{HF_REPO_ID}/resolve/main/onnx/model_O4.onnx",
    "tokenizer.json": f"https://huggingface.co/{HF_REPO_ID}/resolve/main/tokenizer.json",
    "config.json": f"https://huggingface.co/{HF_REPO_ID}/resolve/main/config.json",
}


class OnnxTransformerBackend(NeuralBackend):
    """Многоязычный трансформер в квантованном ONNX-виде (onnxruntime, без torch).

    Та же нейросеть paraphrase-multilingual-MiniLM-L12-v2, но инференс
    выполняется движком onnxruntime (int8-квантование, ~4x меньше памяти).
    Пулинг - среднее по токенам с маской внимания (как в sentence-transformers).
    """
    name = "transformers-onnx"
    MAX_SEQ = 128

    def __init__(self):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        os.makedirs(ONNX_DIR, exist_ok=True)
        for fn in ("tokenizer.json", "config.json"):
            self._ensure_file(fn)
        self.tokenizer = Tokenizer.from_file(os.path.join(ONNX_DIR,
                                                          "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=self.MAX_SEQ)
        self.tokenizer.enable_padding(length=None, pad_id=1,
                                      pad_token="<pad>")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.inter_op_num_threads = 2
        opts.enable_cpu_mem_arena = False   # экономия памяти в sandbox/на слабых ПК
        opts.enable_mem_pattern = False
        # статически квантованная модель (int8, AVX2); fallback - динамическая O4
        model_file = os.path.join(ONNX_DIR, "model_quint8_avx2.onnx")
        try:
            self._ensure_file("model_quint8_avx2.onnx")
            self.sess = ort.InferenceSession(model_file, sess_options=opts,
                                             providers=["CPUExecutionProvider"])
        except Exception:
            self._ensure_file("model_O4.onnx")
            model_file = os.path.join(ONNX_DIR, "model_O4.onnx")
            self.sess = ort.InferenceSession(model_file, sess_options=opts,
                                             providers=["CPUExecutionProvider"])
        self.input_names = [i.name for i in self.sess.get_inputs()]

    @staticmethod
    def _ensure_file(fn: str) -> str:
        path = os.path.join(ONNX_DIR, fn)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        try:
            from huggingface_hub import hf_hub_download
            import shutil
            sub = f"onnx/{fn}" if fn.endswith(".onnx") else fn
            got = hf_hub_download(HF_REPO_ID, sub,
                                  cache_dir=os.path.join(ONNX_DIR, "hf"))
            shutil.copyfile(got, path)
        except Exception:
            import urllib.request
            urllib.request.urlretrieve(ONNX_FILES[fn], path + ".part")
            os.replace(path + ".part", path)
        return path

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        outs = []
        batch = 16   # мини-батчи: ограничиваем пик памяти активаций ORT
        for i in range(0, len(texts), batch):
            part = texts[i:i + batch]
            encs = self.tokenizer.encode_batch(part)
            input_ids = np.array([e.ids for e in encs], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
            feeds = {"input_ids": input_ids, "attention_mask": mask}
            if "token_type_ids" in self.input_names:
                feeds["token_type_ids"] = np.zeros_like(input_ids)
            out = self.sess.run(None, feeds)[0]        # (B, L, H)
            m = mask[:, :, None].astype(np.float32)
            summed = (out * m).sum(axis=1)
            counts = m.sum(axis=1)
            counts[counts == 0] = 1.0
            outs.append((summed / counts).astype(np.float32))
        return np.vstack(outs)


class SkipGramBackend(NeuralBackend):
    """Собственная нейросеть: skip-gram с negative sampling (numpy).

    Одно скрытое слой-проекция размера dim; обучается SGD на корпусе.
    Эмбеддинг предложения = средневзвешенное (по tf-idf) векторов слов.
    """
    name = "skipgram"
    DIM = 64

    def __init__(self, corpus_texts: list[str], epochs: int = 6,
                 window: int = 3, neg: int = 5, lr: float = 0.03,
                 cache_key: str = "default"):
        self.dim = self.DIM
        self.vocab, self.counts = self._build_vocab(corpus_texts)
        cache_path = os.path.join(CACHE_DIR, f"skipgram_{cache_key}.npz")
        if os.path.exists(cache_path):
            z = np.load(cache_path)
            self.W_in = z["W_in"]
            self.W_out = z["W_out"]
        else:
            self._train(corpus_texts, epochs, window, neg, lr)
            os.makedirs(CACHE_DIR, exist_ok=True)
            np.savez_compressed(cache_path, W_in=self.W_in, W_out=self.W_out)

    @staticmethod
    def _build_vocab(corpus_texts):
        from .tokenizer import WORD_RE
        counts: dict = {}
        for text in corpus_texts:
            for w in WORD_RE.findall(text.lower()):
                counts[w] = counts.get(w, 0) + 1
        vocab = [w for w, c in counts.items() if c >= 2]
        return {w: i for i, w in enumerate(vocab)}, counts

    def _train(self, corpus_texts, epochs, window, neg, lr):
        from .tokenizer import WORD_RE
        rng = np.random.default_rng(42)
        V = len(self.vocab)
        if V == 0:
            self.W_in = np.zeros((1, self.dim), np.float32)
            self.W_out = np.zeros((1, self.dim), np.float32)
            return
        self.W_in = (rng.random((V, self.dim)) - 0.5) / self.dim
        self.W_out = (rng.random((V, self.dim)) - 0.5) / self.dim
        # унимодальное распределение для negative sampling
        freq = np.array([self.counts.get(w, 1) ** 0.75
                         for w in sorted(self.vocab, key=self.vocab.get)],
                        dtype=np.float64)
        freq /= freq.sum()
        for ep in range(epochs):
            cur_lr = lr * (1 - ep / (epochs + 1))
            for text in corpus_texts:
                ids = [self.vocab[w] for w in WORD_RE.findall(text.lower())
                       if w in self.vocab]
                for i, center in enumerate(ids):
                    lo = max(0, i - window)
                    hi = min(len(ids), i + window + 1)
                    for j in range(lo, hi):
                        if j == i:
                            continue
                        ctx = ids[j]
                        negs = rng.choice(V, size=neg, p=freq)
                        targets = np.concatenate([[ctx], negs])
                        labels = np.concatenate([[1.0], np.zeros(neg)])
                        emb = self.W_in[center]
                        scores = self.W_out[targets] @ emb
                        sig = 1.0 / (1.0 + np.exp(-np.clip(scores, -6, 6)))
                        grad = (labels - sig)[:, None] * self.W_out[targets]
                        self.W_in[center] += cur_lr * grad.sum(axis=0)
                        self.W_out[targets] += cur_lr * grad
        self.W_in = self.W_in.astype(np.float32)

    def embed(self, texts: list[str]) -> np.ndarray:
        from .tokenizer import WORD_RE
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            ids = [self.vocab[w] for w in WORD_RE.findall(text.lower())
                   if w in self.vocab]
            if ids:
                out[i] = self.W_in[ids].mean(axis=0)
        return out


_backend: NeuralBackend | None = None


def get_backend(corpus_texts: list[str] | None = None,
                force: str | None = None) -> NeuralBackend:
    """Возвращает нейросетевой бэкенд (singleton с кэшем)."""
    global _backend
    pref = force or os.environ.get("NEURAL_BACKEND", "auto")
    if _backend is not None and (force in (None, "auto") or _backend.name == pref):
        return _backend
    chosen: NeuralBackend | None = None
    if pref in ("auto", "onnx"):
        try:
            chosen = OnnxTransformerBackend()
        except Exception as e:  # нет onnxruntime/файлов/сети -> дальше
            if pref == "onnx":
                raise
            print(f"[neural] onnx-трансформер недоступен ({e})")
    if chosen is None and pref in ("auto", "transformers"):
        try:
            chosen = TransformerBackend()
        except Exception as e:  # нет torch/модели/памяти -> резервный бэкенд
            if pref == "transformers":
                raise
            print(f"[neural] transformers недоступен ({e}); использую skip-gram")
    if chosen is None and pref in ("auto", "skipgram"):
        try:
            key = hashlib.md5("\n".join(corpus_texts or []).encode()).hexdigest()[:10]
            chosen = SkipGramBackend(corpus_texts or [], cache_key=key)
        except Exception as e:
            print(f"[neural] skip-gram недоступен ({e}); использую none")
    if chosen is None:
        chosen = NoneBackend()
    _backend = chosen
    return _backend


def reset_backend():
    global _backend
    _backend = None


# ---------------------------------------------------------------------------
# Нейросетевое уточнение отбора предложений (MMR) и группировка ключевых слов
# ---------------------------------------------------------------------------

def mmr_select(scored: list, n: int, backend: NeuralBackend,
               lam: float = 0.75) -> list:
    """Maximal Marginal Relevance: значимость - семантическая избыточность.

    scored: list[SentenceScore]; возвращает выбранные SentenceScore.
    """
    pool = [sc for sc in scored if sc.weight > 0]
    if not pool:
        pool = scored[: n * 3]
    pool = sorted(pool, key=lambda sc: sc.weight, reverse=True)[: max(3 * n, 25)]
    max_w = max(sc.weight for sc in pool) or 1.0
    texts = [sc.sentence.text for sc in pool]
    embs = backend.embed(texts)
    chosen: list = []
    chosen_embs: list[np.ndarray] = []
    remaining = list(range(len(pool)))
    while remaining and len(chosen) < n:
        best_i, best_val = None, -1e9
        for i in remaining:
            rel = pool[i].weight / max_w
            if chosen_embs:
                red = max(cosine(embs[i], c) for c in chosen_embs)
            else:
                red = 0.0
            val = lam * rel - (1 - lam) * red
            if val > best_val:
                best_i, best_val = i, val
        remaining.remove(best_i)
        chosen.append(pool[best_i])
        chosen_embs.append(embs[best_i])
    return chosen


def chunk_text(text: str, chunk_chars: int = 400) -> list[str]:
    """Разбиение длинного текста на куски (~100 токенов) для эмбеддинга."""
    import re as _re
    parts = _re.split(r"(?<=[.!?…])\s+", text.strip())
    chunks, cur = [], ""
    for p in parts:
        if len(cur) + len(p) > chunk_chars and cur:
            chunks.append(cur.strip())
            cur = ""
        cur += p + " "
    if cur.strip():
        chunks.append(cur.strip())
    return chunks or [text[:chunk_chars]]


def embed_long(backend: NeuralBackend, text: str) -> np.ndarray:
    """Средний эмбеддинг длинного текста по чанкам (без потери хвоста)."""
    chunks = chunk_text(text)
    embs = backend.embed(chunks)
    if len(embs) == 0:
        return np.zeros((1, 8), np.float32)[0]
    return embs.mean(axis=0)


def doc_similarity(backend: NeuralBackend, summary_text: str,
                   full_text: str) -> float:
    """Семантическая близость реферата исходному документу (оценка качества)."""
    a = embed_long(backend, summary_text)
    b = embed_long(backend, full_text)
    return cosine(a, b)
