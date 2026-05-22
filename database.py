"""
database.py — Configuração do banco de dados com SQLAlchemy.
Usa SQLite para desenvolvimento; troque DATABASE_URL por postgres em produção.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from typing import Generator

DATABASE_URL = "sqlite:///./worldcup.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Necessário para SQLite + FastAPI async
    echo=False,  # True para debug SQL
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base declarativa para todos os modelos ORM."""
    pass


def get_db() -> Generator[Session, None, None]:
    """
    Dependency injection do FastAPI para obter a sessão do banco.
    Garante fechamento mesmo em caso de erro.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
