from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple
from tree_sitter import Language, Parser
from repo_intelligence.models.core import Symbol, Relationship, make_symbol_id, make_file_id


@dataclass
class ParserContext:
    """Repository context supplied to every parser."""

    repo_name: str
    root_path: str
    branch: str
    commit: str


class BaseParser(ABC):
    def __init__(self, language: Language, context: ParserContext):
        self.parser = Parser(language)
        self.context = context

    @abstractmethod
    def parse(self, file_path: str, source_code: bytes) -> Tuple[List[Symbol], List[Relationship]]:
        """Parse source code and return symbols and relationships."""
        pass

    def _make_symbol_id(self, file_path: str, qualified_name: str) -> str:
        return make_symbol_id(
            self.context.repo_name, self.context.branch, file_path, qualified_name
        )

    def _make_file_id(self, file_path: str) -> str:
        return make_file_id(
            self.context.repo_name, self.context.branch, file_path
        )
