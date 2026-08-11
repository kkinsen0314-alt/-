"""本地轻量 RAG：从历史报告和 Markdown 知识文档检索上下文。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from history_retriever import HistoryReportRetriever


class LocalRAG:
    """基于本地 Markdown 文档的检索增强生成上下文。"""

    def __init__(self, report_dir: Union[str, Path], knowledge_dir: Optional[Union[str, Path]] = None):
        directories = [Path(report_dir)]
        if knowledge_dir:
            directories.append(Path(knowledge_dir))
        self.retrievers = [HistoryReportRetriever(directory) for directory in directories]

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        if top_k <= 0:
            return []
        hits = []
        for retriever in self.retrievers:
            hits.extend(retriever.search(query, top_k=top_k))
        return sorted(hits, key=lambda item: (item["score"], item["path"]), reverse=True)[:top_k]

    def context(self, hits: list[dict], max_chars: int = 3000) -> str:
        return HistoryReportRetriever.build_context(hits, max_chars=max_chars)
