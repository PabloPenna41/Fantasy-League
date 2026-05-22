"""
simulation.py — Motor de simulação de partidas da Copa do Mundo.

Lógica de simulação:
  - Ratings influenciam PROBABILIDADE, não garantem resultado
  - Uma seleção nota 1 ainda pode vencer uma nota 5 (efeito azarão)
  - Placar gerado com distribuição de Poisson ponderada pelo rating
  - Narrativa gerada de forma procedural com variação contextual
"""
import random
import math
from schemas import LineupPlayer, SimulationResult, TeamInfo


# ─── Constantes de balanceamento ─────────────────────────────────────────────

BASE_GOALS_LAMBDA = 1.2        # Média de gols por jogo (estilo Copa — baixo)
RATING_GOAL_MULTIPLIER = 0.35  # Quanto o rating influencia os gols
UPSET_FACTOR = 0.18            # Chance de zebra (placar invertido pelo azarão)


# ─── Narrativas procedurais ───────────────────────────────────────────────────

OPENING_PHRASES = [
    "Num jogo eletrizante no estádio lotado",
    "Sob holofotes do mundo inteiro",
    "Em uma partida que parou o planeta",
    "Com a torcida nas arquibancadas vibrando",
    "Num duelo histórico da Copa do Mundo",
    "Em um confronto aguardado por milhões",
]

WIN_PHRASES = [
    "dominou do início ao fim e garantiu a classificação!",
    "mostrou por que é favorita e avança na competição!",
    "venceu com garra e determinação inexplicável!",
    "confirmou o favoritismo com uma atuação impecável!",
    "surpreendeu a todos com uma virada inesquecível!",
]

LOSS_PHRASES = [
    "não conseguiu superar o adversário e está eliminada.",
    "saiu de campo cabisbaixa após derrota amarga.",
    "tropeçou na Copa e tem muito o que refletir.",
    "foi superada em todos os setores do campo.",
    "jogou bem, mas o adversário foi superior no fim.",
]

DRAW_PHRASES = [
    "empatou num jogo equilibrado que vai para a decisão nos pênaltis.",
    "dividiu os pontos num duelo de alto nível.",
    "saiu satisfeita com o empate contra um adversário forte.",
    "não conseguiu a vitória mas se manteve na Copa.",
]

UPSET_PHRASES = [
    "Em uma das maiores zebras da história da Copa,",
    "O impossível aconteceu:",
    "Ninguém acreditava, mas aconteceu:",
    "A Copa do Mundo sempre reserva surpresas —",
]


def _poisson_sample(lam: float) -> int:
    """
    Amostragem de distribuição de Poisson usando método de Knuth.
    Usada para gerar número de gols com média `lam`.
    """
    lam = max(0.1, min(lam, 8.0))  # Clamp para evitar extremos
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1


def _calculate_win_probability(rating_a: float, rating_b: float) -> float:
    """
    Calcula a probabilidade de vitória da seleção A com base nos ratings.

    A função aceita ratings dinâmicos. Como o usuário pode somar bônus de
    jogadores à força base, o coeficiente é um pouco menor para evitar que uma
    média alta de figurinhas torne a partida matematicamente decidida.
    
    Ratings iguais → ~50% de chance de vitória
    """
    diff = rating_a - rating_b
    # Função logística: sigma(x) = 1 / (1 + e^(-k*x))
    prob = 1.0 / (1.0 + math.exp(-0.75 * diff))
    # Adiciona fator de imprevisibilidade da Copa
    prob = prob * (1 - UPSET_FACTOR) + (UPSET_FACTOR / 2)
    return prob


def _generate_score(winner_rating: float, loser_rating: float) -> tuple[int, int]:
    """
    Gera placar onde winner_score > loser_score.
    Gols do vencedor escalados pelo rating; gols do perdedor sempre menores.
    """
    winner_lambda = BASE_GOALS_LAMBDA + (winner_rating - 3.0) * RATING_GOAL_MULTIPLIER
    loser_lambda = BASE_GOALS_LAMBDA - (winner_rating - loser_rating) * 0.2

    winner_goals = max(1, _poisson_sample(winner_lambda))
    loser_goals = _poisson_sample(max(0.3, loser_lambda))

    # Garante que vencedor tem mais gols
    if loser_goals >= winner_goals:
        loser_goals = max(0, winner_goals - 1)

    return winner_goals, loser_goals


def _generate_draw_score() -> tuple[int, int]:
    """Gera placar empatado."""
    goals = _poisson_sample(BASE_GOALS_LAMBDA)
    return goals, goals


def _build_narrative(
    user_team: TeamInfo,
    opponent: TeamInfo,
    result: str,
    user_score: int,
    opp_score: int,
    user_effective_rating: float,
    opponent_effective_rating: float,
    user_player_bonus: float,
) -> str:
    """Constrói narrativa textual da partida."""
    opening = random.choice(OPENING_PHRASES)
    is_upset = (
        result == "win" and user_effective_rating < opponent_effective_rating - 1.5 or
        result == "loss" and opponent_effective_rating < user_effective_rating - 1.5
    )

    prefix = f"{random.choice(UPSET_PHRASES)} " if is_upset else ""

    if result == "win":
        outcome = f"{user_team.name} {random.choice(WIN_PHRASES)}"
    elif result == "loss":
        outcome = f"{user_team.name} {random.choice(LOSS_PHRASES)}"
    else:
        outcome = f"{user_team.name} {random.choice(DRAW_PHRASES)}"

    score_text = f"Placar final: {user_team.name} {user_score} x {opp_score} {opponent.name}."
    rating_text = (
        f"(Força efetiva: {user_team.name} {user_effective_rating:.1f} "
        f"+ bônus figurinhas {user_player_bonus:.1f} | "
        f"{opponent.name} {opponent_effective_rating:.1f})"
    )

    return f"{prefix}{opening}, {outcome} {score_text} {rating_text}"


# ─── Interface pública ────────────────────────────────────────────────────────

def simulate_match(
    user_team: TeamInfo,
    opponent: TeamInfo,
    user_lineup: list[LineupPlayer] | None = None,
    opponent_lineup: list[LineupPlayer] | None = None,
    user_effective_rating: float | None = None,
    opponent_effective_rating: float | None = None,
    user_player_bonus: float = 0.0,
) -> SimulationResult:
    """
    Simula uma partida entre duas seleções.
    
    Args:
        user_team: Seleção escolhida pelo usuário
        opponent: Seleção adversária
    
    Returns:
        SimulationResult com placar, resultado e narrativa
    """
    user_rating = user_effective_rating if user_effective_rating is not None else user_team.rating
    opponent_rating = opponent_effective_rating if opponent_effective_rating is not None else opponent.rating

    win_prob = _calculate_win_probability(user_rating, opponent_rating)
    roll = random.random()

    if roll < win_prob * 0.9:
        # Vitória do usuário
        user_score, opp_score = _generate_score(user_rating, opponent_rating)
        result = "win"
    elif roll < win_prob * 0.9 + 0.12:
        # Empate (12% de chance base)
        user_score, opp_score = _generate_draw_score()
        result = "draw"
    else:
        # Derrota do usuário
        opp_score, user_score = _generate_score(opponent_rating, user_rating)
        result = "loss"

    narrative = _build_narrative(
        user_team,
        opponent,
        result,
        user_score,
        opp_score,
        user_rating,
        opponent_rating,
        user_player_bonus,
    )

    return SimulationResult(
        user_team=user_team.name,
        opponent_team=opponent.name,
        user_score=user_score,
        opponent_score=opp_score,
        result=result,
        user_team_rating=user_rating,
        opponent_rating=opponent_rating,
        user_base_rating=user_team.rating,
        user_player_bonus=user_player_bonus,
        narrative=narrative,
        user_lineup=user_lineup or [],
        opponent_lineup=opponent_lineup or [],
    )
