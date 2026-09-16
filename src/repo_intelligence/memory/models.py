from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey, Integer
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Investigation(Base):
    __tablename__ = "investigations"

    id = Column(String, primary_key=True)
    repo = Column(String)
    branch = Column(String)
    commit = Column(String)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    summary = Column(Text)
    metadata_ = Column("metadata", JSON)

    messages = relationship("InvestigationMessage", back_populates="investigation", cascade="all, delete-orphan")
    findings = relationship("InvestigationFinding", back_populates="investigation", cascade="all, delete-orphan")


class InvestigationMessage(Base):
    __tablename__ = "investigation_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investigation_id = Column(String, ForeignKey("investigations.id"))
    role = Column(String)  # user / assistant / tool
    content = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    investigation = relationship("Investigation", back_populates="messages")


class InvestigationFinding(Base):
    __tablename__ = "investigation_findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investigation_id = Column(String, ForeignKey("investigations.id"))
    kind = Column(String)  # e.g. symbol, relationship, file
    entity_id = Column(String)
    evidence = Column(JSON)
    note = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    investigation = relationship("Investigation", back_populates="findings")
