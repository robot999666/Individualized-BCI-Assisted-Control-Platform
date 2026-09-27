"""面向小型中文项目资料的本地 TF-IDF 检索索引。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


@dataclass(frozen=True)
class KnowledgeChunk:
    title: str
    section: str
    text: str
    source_path: str


@dataclass(frozen=True)
class SearchResult:
    chunk: KnowledgeChunk
    score: float


class ProjectKnowledgeIndex:
    """启动时构建一次、进程内复用的轻量中文检索索引。"""

    def __init__(self, repo_dir: Path) -> None:
        self.repo_dir = repo_dir.resolve()
        self.documents: list[Path] = []
        self.chunks: list[KnowledgeChunk] = []
        self.error: str | None = None
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None
        self._build()

    @property
    def ready(self) -> bool:
        return bool(self.chunks and self._matrix is not None and not self.error)

    def _candidate_paths(self) -> list[Path]:
        # Only reviewed public knowledge: exclude deployment/runbooks and private runtime files.
        candidates = []
        docs_dir = self.repo_dir / "docs" / "rag"
        if docs_dir.is_dir():
            candidates.extend(sorted(docs_dir.rglob("*.md")))
        return [path for path in candidates if path.is_file()]

    def _build(self) -> None:
        try:
            self.documents = self._candidate_paths()
            for path in self.documents:
                self.chunks.extend(self._chunk_markdown(path))
            if not self.chunks:
                raise RuntimeError("未发现可索引的项目文档")
            self._vectorizer = TfidfVectorizer(
                analyzer="char",
                ngram_range=(2, 4),
                min_df=1,
                sublinear_tf=True,
                norm="l2",
            )
            self._matrix = self._vectorizer.fit_transform(
                [chunk.text for chunk in self.chunks]
            )
        except Exception as exc:  # 索引故障由 health 暴露，应用仍可启动
            self.error = f"{type(exc).__name__}: {exc}"
            self._vectorizer = None
            self._matrix = None

    def _chunk_markdown(self, path: Path) -> list[KnowledgeChunk]:
        raw = path.read_text(encoding="utf-8")
        raw = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)
        title_match = re.search(r"^#\s+(.+)$", raw, flags=re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem
        relative = path.relative_to(self.repo_dir).as_posix()

        sections: list[tuple[str, str]] = []
        current_section = "概述"
        buffer: list[str] = []
        for line in raw.splitlines():
            heading = re.match(r"^#{2,6}\s+(.+)$", line)
            if heading:
                if buffer:
                    sections.append((current_section, "\n".join(buffer)))
                current_section = heading.group(1).strip()
                buffer = []
            elif not line.startswith("# "):
                buffer.append(line)
        if buffer:
            sections.append((current_section, "\n".join(buffer)))

        chunks: list[KnowledgeChunk] = []
        for section, body in sections:
            cleaned = self._clean_markdown(body)
            for text in self._split_text(cleaned):
                if len(text) < 20:
                    continue
                chunks.append(
                    KnowledgeChunk(
                        title=title,
                        section=section,
                        text=f"{title}\n{section}\n{text}",
                        source_path=relative,
                    )
                )
        return chunks

    @staticmethod
    def _clean_markdown(text: str) -> str:
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        text = re.sub(r"!\[[^]]*]\([^)]*\)", " ", text)
        text = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", text)
        text = re.sub(r"[`*_>|]", "", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _split_text(text: str, target: int = 500, overlap: int = 80) -> list[str]:
        if len(text) <= 620:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            upper = min(start + 620, len(text))
            end = upper
            if upper < len(text):
                boundary = max(
                    text.rfind(mark, start + 300, upper)
                    for mark in ("\n", "。", "；", "！", "？")
                )
                if boundary >= start + 300:
                    end = boundary + 1
                else:
                    end = min(start + target, len(text))
            chunks.append(text[start:end].strip())
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
        return chunks

    def search(self, question: str, top_k: int = 5) -> list[SearchResult]:
        if not self.ready or self._vectorizer is None or self._matrix is None:
            return []
        normalized = self._normalize_query(question)
        if len(normalized) < 2:
            return []
        query = self._vectorizer.transform([normalized])
        scores = np.asarray((self._matrix @ query.T).toarray()).ravel()
        ranked = np.argsort(scores)[::-1]
        results: list[SearchResult] = []
        strongest = float(scores[ranked[0]]) if len(ranked) else 0.0
        cutoff = max(0.045, strongest * 0.5)
        for index in ranked:
            score = float(scores[index])
            if score < cutoff:
                break
            results.append(SearchResult(chunk=self.chunks[int(index)], score=score))
            if len(results) >= top_k:
                break
        return results

    @staticmethod
    def _normalize_query(question: str) -> str:
        query = re.sub(r"[\s，。！？、：；,.!?:;（）()\[\]]+", "", question)
        for phrase in (
            "请问",
            "我想知道",
            "能不能",
            "可以介绍一下",
            "介绍一下",
            "分别是",
            "是什么",
            "有什么",
            "怎么样",
            "怎么",
        ):
            query = query.replace(phrase, "")

        expansions: list[str] = [query]
        if "项目" in query and any(word in query for word in ("解决", "目标", "作用")):
            expansions.append("项目定位目标ALS BCI运动障碍意图识别")
        if "四分类" in query:
            expansions.append("四分类意图左转右转直行停止")
        if "数字孪生" in query or "3D" in query.upper():
            expansions.append("3D数字孪生演示运动想象脑电轮椅指令")
        if "校准" in query or "校正" in query:
            expansions.append("个体化校准EA对齐个人CSP LDA同源数据")
        if "EOG" in query.upper() or "眼电" in query or "眨眼" in query:
            expansions.append("EOG眼电SVM双眨眼确认候选安全")
        return " ".join(expansions)
