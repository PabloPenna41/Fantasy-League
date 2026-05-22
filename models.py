"""
models.py — Modelos ORM do banco de dados.

Tabelas:
  - users: Usuários registrados com auth segura
  - match_history: Histórico de partidas simuladas por usuário
  - players: Jogadores disponíveis para álbum e escalações
  - user_stickers: Figurinhas coletadas pelos usuários
  - user_teams: Seleções desbloqueadas pelos usuários
"""
from datetime import datetime
from sqlalchemy import (
    Integer, String, DateTime, ForeignKey, Float, Boolean, UniqueConstraint, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class User(Base):
    """
    Usuário do sistema.
    Senha nunca é armazenada em texto plano — apenas o hash bcrypt.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(240), nullable=True)
    avatar_data: Mapped[str | None] = mapped_column(String, nullable=True)
    profile_theme: Mapped[str] = mapped_column(String(20), nullable=False, default="stadium")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    custom_team_name: Mapped[str] = mapped_column(String(80), nullable=False, default="Minha Seleção")
    custom_team_badge: Mapped[str] = mapped_column(String(30), nullable=False, default="star")
    custom_formation: Mapped[str] = mapped_column(String(20), nullable=False, default="4-3-3")
    gems: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relacionamento 1:N com histórico de partidas
    matches: Mapped[list["MatchHistory"]] = relationship(
        "MatchHistory", back_populates="user", cascade="all, delete-orphan"
    )
    stickers: Mapped[list["UserSticker"]] = relationship(
        "UserSticker", back_populates="user", cascade="all, delete-orphan"
    )
    lineup_players: Mapped[list["UserLineupPlayer"]] = relationship(
        "UserLineupPlayer", back_populates="user", cascade="all, delete-orphan"
    )
    unlocked_teams: Mapped[list["UserTeam"]] = relationship(
        "UserTeam", back_populates="user", cascade="all, delete-orphan"
    )
    pending_player_packs: Mapped[list["PendingPlayerPack"]] = relationship(
        "PendingPlayerPack", back_populates="user", cascade="all, delete-orphan"
    )
    pending_match_simulations: Mapped[list["PendingMatchSimulation"]] = relationship(
        "PendingMatchSimulation", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username!r})>"


class MatchHistory(Base):
    """
    Histórico de partidas simuladas.
    Armazena o contexto completo de cada simulação para análise futura.
    """
    __tablename__ = "match_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    user_team: Mapped[str] = mapped_column(String(80), nullable=False)
    opponent_team: Mapped[str] = mapped_column(String(80), nullable=False)
    user_score: Mapped[int] = mapped_column(Integer, nullable=False)
    opponent_score: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String(10), nullable=False)  # "win" | "loss" | "draw"
    user_team_rating: Mapped[float] = mapped_column(Float, nullable=False)
    opponent_rating: Mapped[float] = mapped_column(Float, nullable=False)
    played_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relacionamento N:1 com usuário
    user: Mapped["User"] = relationship("User", back_populates="matches")

    def __repr__(self) -> str:
        return (
            f"<Match({self.user_team} {self.user_score}x{self.opponent_score} "
            f"{self.opponent_team}, result={self.result!r})>"
        )


class Player(Base):
    """Jogador colecionável usado no álbum e nas escalações táticas.

    O campo rating usa escala inteira de 1 a 5 para calcular bônus de força.
    """
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[str] = mapped_column(String(20), nullable=False)
    team_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    photo_url: Mapped[str | None] = mapped_column(String(240), nullable=True)

    stickers: Mapped[list["UserSticker"]] = relationship(
        "UserSticker", back_populates="player", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Player({self.name!r}, {self.team_name!r}, rating={self.rating})>"


class UserSticker(Base):
    """Quantidade de uma figurinha de jogador pertencente a um usuário."""
    __tablename__ = "user_stickers"
    __table_args__ = (
        UniqueConstraint("user_id", "player_id", name="uq_user_player_sticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user: Mapped["User"] = relationship("User", back_populates="stickers")
    player: Mapped["Player"] = relationship("Player", back_populates="stickers")

    def __repr__(self) -> str:
        return f"<UserSticker(user_id={self.user_id}, player_id={self.player_id}, quantity={self.quantity})>"


class UserLineupPlayer(Base):
    """Jogador escolhido pelo usuário para jogar na seleção personalizada."""
    __tablename__ = "user_lineup_players"
    __table_args__ = (
        UniqueConstraint("user_id", "player_id", name="uq_user_lineup_player"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="lineup_players")
    player: Mapped["Player"] = relationship("Player")

    def __repr__(self) -> str:
        return f"<UserLineupPlayer(user_id={self.user_id}, player_id={self.player_id})>"


class UserTeam(Base):
    """Seleção desbloqueada por um usuário por meio de pacote de seleção."""
    __tablename__ = "user_teams"
    __table_args__ = (
        UniqueConstraint("user_id", "team_name", name="uq_user_team_unlock"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    team_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    user: Mapped["User"] = relationship("User", back_populates="unlocked_teams")

    def __repr__(self) -> str:
        return f"<UserTeam(user_id={self.user_id}, team_name={self.team_name!r})>"


class PendingPlayerPack(Base):
    """Compra de jogadores preparada para ser confirmada após a animação."""
    __tablename__ = "pending_player_packs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    cards_json: Mapped[str] = mapped_column(Text, nullable=False)
    cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remaining_gems: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    committed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="pending_player_packs")

    def __repr__(self) -> str:
        return f"<PendingPlayerPack(id={self.id!r}, user_id={self.user_id}, committed={self.committed})>"


class PendingMatchSimulation(Base):
    """Resultado de partida preparado para ser salvo após a animação."""
    __tablename__ = "pending_match_simulations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    committed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    match_history_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("match_history.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="pending_match_simulations")

    def __repr__(self) -> str:
        return f"<PendingMatchSimulation(id={self.id!r}, user_id={self.user_id}, committed={self.committed})>"


class CupMatch(Base):
    """Resultado global de uma partida da Copa informado ou gerado pelo admin."""
    __tablename__ = "cup_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    home_team: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    away_team: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    home_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    away_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    played_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<CupMatch({self.home_team} {self.home_score}x{self.away_score} {self.away_team})>"
