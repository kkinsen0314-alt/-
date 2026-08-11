"""本地历史报告检索器：无外部向量库依赖的轻量级 RAG。"""

import re
from collections import Counter
from pathlib import Path
from typing import Union


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


class HistoryReportRetriever:
    def __init__(self, report_dir: Union[str, Path]):
        self.report_dir = Path(report_dir)

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        query_terms = Counter(_tokens(query))
        if not query_terms or not self.report_dir.exists():
            return []

        hits = []
        for path in sorted(self.report_dir.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
            text = path.read_text(encoding="utf-8", errors="ignore")
            document_terms = Counter(_tokens(text))
            overlap = sum(min(query_terms[term], document_terms[term]) for term in query_terms)
            if overlap == 0:
                continue
            score = round(overlap / max(1, sum(query_terms.values())), 4)
            title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")), path.stem)
            snippet = self._snippet(text, list(query_terms))
            hits.append({"path": str(path), "title": title, "score": score, "snippet": snippet})
        return sorted(hits, key=lambda item: (item["score"], item["path"]), reverse=True)[:max(1, top_k)]

    @staticmethod
    def _snippet(text: str, terms: list[str], max_length: int = 500) -> str:
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if any(term in line.lower() for term in terms):
                start = max(0, index - 1)
                return " ".join(lines[start:index + 3])[:max_length]
        return " ".join(lines[:5])[:max_length]

    @staticmethod
    def build_context(hits: list[dict], max_chars: int = 2500) -> str:
        if not hits:
            return ""
        chunks = [f"历史报告：{hit['title']}\n{hit['snippet']}" for hit in hits]
        return "\n\n".join(chunks)[:max_chars]
