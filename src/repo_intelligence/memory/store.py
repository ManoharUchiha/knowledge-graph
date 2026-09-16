from __future__ import annotations
from contextlib import contextmanager
from typing import Optional, List
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from repo_intelligence.memory.models import Base, Investigation, InvestigationMessage, InvestigationFinding


class InvestigationStore:
    """SQLite-backed persistent store for investigation sessions and findings."""

    def __init__(self, database_url: str = "sqlite:///repo_intel_memory.db"):
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    @contextmanager
    def session(self):
        s = self.Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def create_investigation(
        self,
        repo: Optional[str] = None,
        branch: Optional[str] = None,
        commit: Optional[str] = None,
    ) -> str:
        investigation_id = str(uuid.uuid4())
        with self.session() as s:
            s.add(Investigation(
                id=investigation_id,
                repo=repo,
                branch=branch,
                commit=commit,
            ))
        return investigation_id

    def add_message(
        self,
        investigation_id: str,
        role: str,
        content: str,
    ) -> None:
        with self.session() as s:
            s.add(InvestigationMessage(
                investigation_id=investigation_id,
                role=role,
                content=content,
            ))

    def add_finding(
        self,
        investigation_id: str,
        kind: str,
        entity_id: str,
        note: str = "",
        evidence: Optional[dict] = None,
    ) -> None:
        with self.session() as s:
            s.add(InvestigationFinding(
                investigation_id=investigation_id,
                kind=kind,
                entity_id=entity_id,
                note=note,
                evidence=evidence or {},
            ))

    def get_investigation(self, investigation_id: str) -> Optional[dict]:
        with self.session() as s:
            inv = s.query(Investigation).filter_by(id=investigation_id).first()
            if not inv:
                return None
            return {
                "id": inv.id,
                "repo": inv.repo,
                "branch": inv.branch,
                "commit": inv.commit,
                "started_at": inv.started_at,
                "summary": inv.summary,
                "messages": [
                    {"role": m.role, "content": m.content, "created_at": m.created_at}
                    for m in inv.messages
                ],
                "findings": [
                    {
                        "kind": f.kind,
                        "entity_id": f.entity_id,
                        "note": f.note,
                        "evidence": f.evidence,
                        "created_at": f.created_at,
                    }
                    for f in inv.findings
                ],
            }

    def list_investigations(self, limit: int = 50) -> List[dict]:
        with self.session() as s:
            rows = s.query(Investigation).order_by(Investigation.started_at.desc()).limit(limit).all()
            return [
                {
                    "id": inv.id,
                    "repo": inv.repo,
                    "branch": inv.branch,
                    "commit": inv.commit,
                    "started_at": inv.started_at,
                    "summary": inv.summary,
                }
                for inv in rows
            ]
