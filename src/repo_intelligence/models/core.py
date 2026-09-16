from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """Normalized file discovered by the repository scanner."""

    path: str
    language: str
    size: int


class SymbolType(str, Enum):
    REPOSITORY = "repository"
    DIRECTORY = "directory"
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    RESOURCE = "resource"  # For K8s/Terraform concrete objects
    RESOURCE_TYPE = "resource_type"  # For Crossplane XR kinds / CRD types


class RelationType(str, Enum):
    CONTAINS = "CONTAINS"
    DEFINES = "DEFINES"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    IMPLEMENTS = "IMPLEMENTS"
    INHERITS = "INHERITS"
    REFERENCES = "REFERENCES"
    EXPOSES = "EXPOSES"
    COMPOSITES = "COMPOSITES"
    USES = "USES"
    READS = "READS"
    WRITES = "WRITES"
    DEPENDS_ON = "DEPENDS_ON"
    CREATES = "CREATES"
    RUNS = "RUNS"
    CONFIGURES = "CONFIGURES"
    DOCUMENTS = "DOCUMENTS"
    KUBERNETES_OBJECT = "KUBERNETES_OBJECT"


class Evidence(BaseModel):
    """Evidence backing a relationship or fact."""

    type: str = "static"  # e.g. static, AST, LSP, runtime, documentation
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    start_col: Optional[int] = None
    end_line: Optional[int] = None
    end_col: Optional[int] = None
    confidence: float = 1.0


class SourceLocation(BaseModel):
    file_path: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int


def make_file_id(repo_name: str, branch: str, file_path: str) -> str:
    # Commit is intentionally NOT part of the id: ids stay stable across commits so
    # re-indexing updates nodes in place instead of creating parallel duplicates.
    # The current commit is stored as a node property instead.
    return f"{repo_name}:{branch}:{file_path}"


def make_symbol_id(repo_name: str, branch: str, file_path: str, qualified_name: str) -> str:
    return f"{repo_name}:{branch}:{file_path}:{qualified_name}"


class Symbol(BaseModel):
    """A logical entity discovered in the repository."""

    id: str
    repo: str
    branch: str
    commit: str
    name: str
    symbol_type: SymbolType
    location: SourceLocation
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Relationship(BaseModel):
    """A typed relationship between two symbols."""

    source_id: str
    target_id: str
    rel_type: RelationType
    repo: str
    branch: str
    commit: str
    confidence: float = 1.0
    evidence: List[Evidence] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RepositoryModel(BaseModel):
    """Language-neutral intermediate representation of a repository snapshot."""

    repo_name: str
    root_path: str
    branch: str
    commit: str
    files: List[FileInfo] = Field(default_factory=list)
    symbols: List[Symbol] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
