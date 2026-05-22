"""
teams_data.py — Dados das 32 seleções da Copa do Mundo.

Rating: 1 (fraco) → 5 (elite)
Base nas edições recentes e ranking FIFA.
"""
from schemas import TeamInfo

import jogadores

TEAMS: dict[str, TeamInfo] = {
    # ─── Rating 5 (Elite Mundial) ─────────────────────────────────────────
    "Brasil": TeamInfo(
        name="Brasil", flag="🇧🇷", rating=5.0,
        group="G", confederation="CONMEBOL"
    ),
    "França": TeamInfo(
        name="França", flag="🇫🇷", rating=5.0,
        group="D", confederation="UEFA"
    ),
    "Argentina": TeamInfo(
        name="Argentina", flag="🇦🇷", rating=5.0,
        group="C", confederation="CONMEBOL"
    ),
    "Inglaterra": TeamInfo(
        name="Inglaterra", flag="🏴󠁧󠁢󠁥󠁮󠁧󠁿", rating=4.8,
        group="B", confederation="UEFA"
    ),
    "Espanha": TeamInfo(
        name="Espanha", flag="🇪🇸", rating=4.8,
        group="E", confederation="UEFA"
    ),

    # ─── Rating 4 (Força Mundial) ─────────────────────────────────────────
    "Alemanha": TeamInfo(
        name="Alemanha", flag="🇩🇪", rating=4.5,
        group="E", confederation="UEFA"
    ),
    "Portugal": TeamInfo(
        name="Portugal", flag="🇵🇹", rating=4.5,
        group="H", confederation="UEFA"
    ),
    "Países Baixos": TeamInfo(
        name="Países Baixos", flag="🇳🇱", rating=4.3,
        group="A", confederation="UEFA"
    ),
    "Bélgica": TeamInfo(
        name="Bélgica", flag="🇧🇪", rating=4.2,
        group="F", confederation="UEFA"
    ),
    "Croácia": TeamInfo(
        name="Croácia", flag="🇭🇷", rating=4.2,
        group="F", confederation="UEFA"
    ),
    "Uruguai": TeamInfo(
        name="Uruguai", flag="🇺🇾", rating=4.0,
        group="H", confederation="CONMEBOL"
    ),
    "Itália": TeamInfo(
        name="Itália", flag="🇮🇹", rating=4.0,
        group="C", confederation="UEFA"
    ),
    "EUA": TeamInfo(
        name="EUA", flag="🇺🇸", rating=3.8,
        group="B", confederation="CONCACAF"
    ),

    # ─── Rating 3 (Competitivos) ──────────────────────────────────────────
    "Marrocos": TeamInfo(
        name="Marrocos", flag="🇲🇦", rating=3.8,
        group="F", confederation="CAF"
    ),
    "Japão": TeamInfo(
        name="Japão", flag="🇯🇵", rating=3.5,
        group="E", confederation="AFC"
    ),
    "México": TeamInfo(
        name="México", flag="🇲🇽", rating=3.5,
        group="C", confederation="CONCACAF"
    ),
    "Senegal": TeamInfo(
        name="Senegal", flag="🇸🇳", rating=3.5,
        group="A", confederation="CAF"
    ),
    "Austrália": TeamInfo(
        name="Austrália", flag="🇦🇺", rating=3.3,
        group="D", confederation="AFC"
    ),
    "Suíça": TeamInfo(
        name="Suíça", flag="🇨🇭", rating=3.3,
        group="G", confederation="UEFA"
    ),
    "Coreia do Sul": TeamInfo(
        name="Coreia do Sul", flag="🇰🇷", rating=3.2,
        group="H", confederation="AFC"
    ),
    "Polônia": TeamInfo(
        name="Polônia", flag="🇵🇱", rating=3.2,
        group="C", confederation="UEFA"
    ),
    "Colômbia": TeamInfo(
        name="Colômbia", flag="🇨🇴", rating=3.2,
        group="H", confederation="CONMEBOL"
    ),
    "Dinamarca": TeamInfo(
        name="Dinamarca", flag="🇩🇰", rating=3.5,
        group="D", confederation="UEFA"
    ),

    # ─── Rating 2 (Estreantes / Regulares) ───────────────────────────────
    "Nigéria": TeamInfo(
        name="Nigéria", flag="🇳🇬", rating=2.8,
        group="D", confederation="CAF"
    ),
    "Irã": TeamInfo(
        name="Irã", flag="🇮🇷", rating=2.5,
        group="B", confederation="AFC"
    ),
    "Equador": TeamInfo(
        name="Equador", flag="🇪🇨", rating=2.5,
        group="A", confederation="CONMEBOL"
    ),
    "Canadá": TeamInfo(
        name="Canadá", flag="🇨🇦", rating=2.5,
        group="F", confederation="CONCACAF"
    ),
    "Gana": TeamInfo(
        name="Gana", flag="🇬🇭", rating=2.3,
        group="H", confederation="CAF"
    ),
    "Sérvia": TeamInfo(
        name="Sérvia", flag="🇷🇸", rating=2.8,
        group="G", confederation="UEFA"
    ),

    # ─── Rating 1 (Azarões) ───────────────────────────────────────────────
    "Arábia Saudita": TeamInfo(
        name="Arábia Saudita", flag="🇸🇦", rating=1.8,
        group="C", confederation="AFC"
    ),
    "Catar": TeamInfo(
        name="Catar", flag="🇶🇦", rating=1.5,
        group="A", confederation="AFC"
    ),
    "Costa Rica": TeamInfo(
        name="Costa Rica", flag="🇨🇷", rating=2.0,
        group="E", confederation="CONCACAF"
    ),
    "Tunísia": TeamInfo(
        name="Tunísia", flag="🇹🇳", rating=2.0,
        group="D", confederation="CAF"
    ),
}


def get_all_teams() -> list[TeamInfo]:
    """Retorna lista ordenada de seleções por rating decrescente."""
    return sorted(TEAMS.values(), key=lambda t: t.rating, reverse=True)


def get_team(name: str) -> TeamInfo | None:
    """Busca seleção pelo nome (case-insensitive)."""
    name_lower = name.lower()
    for key, team in TEAMS.items():
        if key.lower() == name_lower:
            return team
    return None

# ─── Players / Stickers ─────────────────────────────────────────────────────

def get_initial_players() -> list[dict]:
    """Retorna a lista inicial de jogadores para popular a tabela players."""
    return jogadores.get_initial_players()
