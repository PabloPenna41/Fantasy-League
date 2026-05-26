"""
schemas.py — Schemas Pydantic para validação de entrada/saída da API.

Separação de responsabilidades:
  - *Request: dados que chegam do cliente (validação rigorosa)
  - *Response: dados que saem para o cliente (nunca expor senha)
"""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, field_validator, ConfigDict, Field


# ─── Auth ────────────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    """Payload de registro de novo usuário."""
    username: str
    email: str
    password: str

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username deve ter ao menos 3 caracteres")
        if len(v) > 50:
            raise ValueError("Username deve ter no máximo 50 caracteres")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username só pode conter letras, números, _ e -")
        return v

    @field_validator("email")
    @classmethod
    def email_basic_format(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.rsplit("@", 1)[-1]:
            raise ValueError("E-mail inválido")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Senha deve ter ao menos 6 caracteres")
        return v


class UserLoginRequest(BaseModel):
    """Payload de login."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT access token retornado após autenticação bem-sucedida."""
    access_token: str
    token_type: str = "bearer"
    username: str
    gems: int = 100


class UserResponse(BaseModel):
    """Dados públicos do usuário (sem senha)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    display_name: str | None = None
    bio: str | None = None
    avatar_data: str | None = None
    profile_theme: str = "stadium"
    is_admin: bool = False
    custom_team_name: str = "Minha Seleção"
    custom_team_badge: str = "star"
    custom_formation: str = "4-3-3"
    gems: int
    is_active: bool
    created_at: datetime


class UserProfileUpdateRequest(BaseModel):
    """Payload para personalização do perfil."""
    display_name: str | None = None
    email: str | None = None
    bio: str | None = None
    avatar_data: str | None = None
    profile_theme: Literal["stadium", "night", "gold", "ocean"] = "stadium"

    @field_validator("display_name")
    @classmethod
    def display_name_length(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) > 80:
            raise ValueError("Nome de exibição deve ter no máximo 80 caracteres")
        return v or None

    @field_validator("email")
    @classmethod
    def profile_email_basic_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if "@" not in v or "." not in v.rsplit("@", 1)[-1]:
            raise ValueError("E-mail inválido")
        return v

    @field_validator("bio")
    @classmethod
    def bio_length(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) > 240:
            raise ValueError("Bio deve ter no máximo 240 caracteres")
        return v or None

    @field_validator("avatar_data")
    @classmethod
    def avatar_data_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not v.startswith("data:image/"):
            raise ValueError("Foto deve ser uma imagem válida")
        if len(v) > 350_000:
            raise ValueError("Foto muito grande. Use uma imagem menor.")
        return v


class AccountDeleteRequest(BaseModel):
    """Confirmação para exclusão da conta."""
    password: str


class UserTeamSettingsRequest(BaseModel):
    """Personalização do time do usuário."""
    custom_team_name: str
    custom_team_badge: Literal["star", "ball", "trophy", "controller", "spark"] = "star"
    custom_formation: Literal["4-3-3", "4-4-2", "3-5-2", "4-2-3-1"] = "4-3-3"

    @field_validator("custom_team_name")
    @classmethod
    def team_name_length(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Nome do time deve ter ao menos 3 caracteres")
        if len(v) > 80:
            raise ValueError("Nome do time deve ter no máximo 80 caracteres")
        return v


# ─── Simulation ──────────────────────────────────────────────────────────────

class LineupPlayer(BaseModel):
    """Jogador exibido no campo tático da simulação."""
    id: int
    name: str
    rating: int
    position: str
    team_name: str
    photo_url: str | None = None
    owned: bool = False
    quantity: int = 0
    quantity_multiplier: float = 1.0
    team_boost: float = 1.0
    effective_rating: float | None = None


class SimulationRequest(BaseModel):
    """Payload para solicitar uma simulação de partida."""
    user_team: str = "Minha Seleção"
    opponent_team: str | None = None


class SimulationResult(BaseModel):
    """Resultado completo de uma simulação."""
    simulation_id: str | None = None
    user_team: str
    opponent_team: str
    user_score: int
    opponent_score: int
    result: Literal["win", "loss", "draw"]
    user_team_rating: float
    opponent_rating: float
    user_base_rating: float = 0.0
    user_player_bonus: float = 0.0
    narrative: str  # Descrição dramática da partida
    user_lineup: list["LineupPlayer"] = Field(default_factory=list)
    opponent_lineup: list["LineupPlayer"] = Field(default_factory=list)


class MatchHistoryResponse(BaseModel):
    """Histórico de uma partida para o cliente."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_team: str
    opponent_team: str
    user_score: int
    opponent_score: int
    result: str
    user_team_rating: float
    opponent_rating: float
    played_at: datetime


# ─── Teams ───────────────────────────────────────────────────────────────────

class TeamInfo(BaseModel):
    """Informações de uma seleção."""
    name: str
    flag: str        # Emoji de bandeira
    rating: float    # 1.0 – 5.0
    group: str       # Grupo na Copa
    confederation: str


# ─── Stickers / Players ─────────────────────────────────────────────────────

class PlayerResponse(BaseModel):
    """Jogador cadastrado no sistema."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rating: int
    position: str
    team_name: str
    photo_url: str | None = None


class StickerCollectionItem(BaseModel):
    """Item do álbum do usuário, incluindo quantidade possuída."""
    player: PlayerResponse
    quantity: int
    owned: bool
    selected: bool = False


class StickerCollectionResponse(BaseModel):
    """Álbum completo do usuário."""
    total_players: int
    owned_players: int
    total_copies: int
    gems: int = 0
    items: list[StickerCollectionItem]


class PackOpenResponse(BaseModel):
    """Retorno de abertura de pacote."""
    opening_id: str | None = None
    cards: list[StickerCollectionItem]
    remaining_gems: int = 0


class WalletResponse(BaseModel):
    """Saldo ilustrativo de gemas do usuário."""
    gems: int


class GemPurchaseRequest(BaseModel):
    """Compra fictícia de gemas."""
    package_id: str


class AdminUserSummary(BaseModel):
    """Resumo de conta para o painel administrativo."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    display_name: str | None = None
    is_admin: bool = False
    is_active: bool = True
    gems: int = 0
    total_players: int = 0
    owned_players: int = 0
    total_copies: int = 0
    selected_players: int = 0
    unlocked_teams: int = 0
    matches: int = 0
    created_at: datetime


class AdminUserDetailResponse(BaseModel):
    """Conta administrável com coleção completa de jogadores."""
    user: AdminUserSummary
    items: list[StickerCollectionItem]
    unlocked_teams: list[str] = Field(default_factory=list)


class AdminUserUpdateRequest(BaseModel):
    """Alterações permitidas pelo administrador em outra conta."""
    display_name: str | None = None
    email: str | None = None
    gems: int | None = Field(default=None, ge=0, le=999_999)
    is_admin: bool | None = None
    is_active: bool | None = None

    @field_validator("display_name")
    @classmethod
    def admin_display_name_length(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) > 80:
            raise ValueError("Nome de exibição deve ter no máximo 80 caracteres")
        return v or None

    @field_validator("email")
    @classmethod
    def admin_email_basic_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if "@" not in v or "." not in v.rsplit("@", 1)[-1]:
            raise ValueError("E-mail inválido")
        return v


class AdminPlayerQuantityRequest(BaseModel):
    """Quantidade de uma carta na conta administrada."""
    quantity: int = Field(ge=0, le=999)


class AdminPlayerBulkRequest(BaseModel):
    """Ação em massa para coleção de jogadores de uma conta."""
    action: Literal["grant_all", "clear_all"]


class LineupResponse(BaseModel):
    """Escalação personalizada do usuário."""
    players: list[StickerCollectionItem]
    rating: float


class LineupUpdateRequest(BaseModel):
    """IDs das cartas escolhidas para jogar."""
    player_ids: list[int]


class TeamCollectionItem(BaseModel):
    """Seleção disponível para o usuário, com estado de desbloqueio."""
    team: TeamInfo
    unlocked: bool


class TeamCollectionResponse(BaseModel):
    """Lista completa das seleções e progresso de desbloqueio."""
    total_teams: int
    unlocked_teams: int
    items: list[TeamCollectionItem]


class TeamPackOpenResponse(BaseModel):
    """Retorno do pacote que desbloqueia uma seleção."""
    team: TeamInfo
    unlocked: bool = True
    remaining_locked: int


class CupMatchRequest(BaseModel):
    """Resultado de partida global informado pelo admin."""
    home_team: str
    away_team: str
    home_score: int = Field(ge=0, le=20)
    away_score: int = Field(ge=0, le=20)


class CupMatchResponse(BaseModel):
    """Resultado global de partida da Copa."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    source: str
    played_at: datetime
    updated_at: datetime


class TeamMomentumItem(BaseModel):
    """Resumo do bônus global de uma seleção."""
    team_name: str
    wins: int
    draws: int
    losses: int
    boost: float


class TeamMomentumResponse(BaseModel):
    """Bônus globais derivados dos resultados cadastrados."""
    items: list[TeamMomentumItem]
