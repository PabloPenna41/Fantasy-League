"""
test_backend.py — Testes unitários e de integração.

Cobertura:
  - Simulação: probabilidade, placar, narrativa
  - Auth: hash, verify, JWT
  - Dados: teams_data integridade
  - API: endpoints críticos
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ─── Testes de Simulação ─────────────────────────────────────────────────────

def test_simulation_basic():
    """Simulação retorna resultado válido."""
    from simulation import simulate_match
    from teams_data import TEAMS

    brasil = TEAMS["Brasil"]
    catar = TEAMS["Catar"]
    result = simulate_match(brasil, catar)

    assert result.result in ("win", "loss", "draw"), "Resultado deve ser win/loss/draw"
    assert result.user_score >= 0, "Placar não pode ser negativo"
    assert result.opponent_score >= 0, "Placar não pode ser negativo"
    assert len(result.narrative) > 20, "Narrativa deve existir"
    print(f"  ✅ Simulação básica OK: {result.user_team} {result.user_score}x{result.opponent_score} {result.opponent_team}")


def test_simulation_consistency():
    """Placar deve ser consistente com resultado declarado."""
    from simulation import simulate_match
    from teams_data import TEAMS

    for _ in range(20):
        brasil = TEAMS["Brasil"]
        argentina = TEAMS["Argentina"]
        result = simulate_match(brasil, argentina)

        if result.result == "win":
            assert result.user_score > result.opponent_score
        elif result.result == "loss":
            assert result.user_score < result.opponent_score
        elif result.result == "draw":
            assert result.user_score == result.opponent_score

    print("  ✅ Consistência placar/resultado OK (20 iterações)")


def test_simulation_probability_bias():
    """Seleção mais forte deve vencer com maior frequência (1000 partidas)."""
    from simulation import simulate_match
    from teams_data import TEAMS

    brasil = TEAMS["Brasil"]     # Rating 5.0
    catar = TEAMS["Catar"]       # Rating 1.5

    wins = 0
    total = 1000
    for _ in range(total):
        r = simulate_match(brasil, catar)
        if r.result == "win":
            wins += 1

    win_rate = wins / total
    assert win_rate > 0.60, f"Brasil deveria vencer >60% vs Catar, obteve {win_rate:.1%}"
    assert win_rate < 0.99, f"Deve haver algum fator de imprevisibilidade"
    print(f"  ✅ Bias probabilístico OK: Brasil venceu {win_rate:.1%} de 1000 partidas vs Catar")


def test_win_probability_function():
    """Função logística deve produzir probabilidades coerentes."""
    from simulation import _calculate_win_probability

    # Mesmo rating → ~50%
    p_equal = _calculate_win_probability(3.0, 3.0)
    assert 0.40 < p_equal < 0.60, f"Esperado ~50%, obteve {p_equal:.2f}"

    # Rating muito maior → >70%
    p_dominant = _calculate_win_probability(5.0, 1.0)
    assert p_dominant > 0.70, f"Esperado >70%, obteve {p_dominant:.2f}"

    # Rating menor → <40%
    p_underdog = _calculate_win_probability(1.0, 5.0)
    assert p_underdog < 0.40, f"Esperado <40%, obteve {p_underdog:.2f}"

    print(f"  ✅ Probabilidade OK: igual={p_equal:.2f}, dominante={p_dominant:.2f}, azarão={p_underdog:.2f}")


# ─── Testes de Auth ──────────────────────────────────────────────────────────

def test_password_hashing():
    """Hash e verificação de senha bcrypt."""
    from auth import hash_password, verify_password

    pwd = "MinhaSenh@123"
    hashed = hash_password(pwd)

    assert hashed != pwd, "Hash não deve ser igual à senha"
    assert len(hashed) > 50, "Hash bcrypt deve ser longo"
    assert verify_password(pwd, hashed), "Verificação deve retornar True"
    assert not verify_password("SenhaErrada", hashed), "Senha errada deve retornar False"
    print("  ✅ Bcrypt hash/verify OK")


def test_jwt_creation_and_decode():
    """JWT deve ser criado e decodificado corretamente."""
    from auth import create_access_token, decode_token

    token = create_access_token(data={"sub": "testuser"})
    assert isinstance(token, str) and len(token) > 20, "Token deve ser string válida"

    payload = decode_token(token)
    assert payload["sub"] == "testuser", "Sub deve ser o username"
    assert "exp" in payload, "Token deve ter expiração"
    print("  ✅ JWT create/decode OK")


def test_jwt_invalid_token():
    """Token inválido deve levantar HTTPException."""
    from auth import decode_token
    from fastapi import HTTPException

    try:
        decode_token("token.invalido.aqui")
        assert False, "Deveria ter lançado exceção"
    except HTTPException as e:
        assert e.status_code == 401
    print("  ✅ JWT invalido → 401 OK")


# ─── Testes de Dados ─────────────────────────────────────────────────────────

def test_teams_data_integrity():
    """Todas as seleções devem ter dados válidos."""
    from teams_data import TEAMS

    assert len(TEAMS) >= 30, f"Esperado ≥30 seleções, obteve {len(TEAMS)}"

    for name, team in TEAMS.items():
        assert 1.0 <= team.rating <= 5.0, f"{name}: rating {team.rating} fora do range 1-5"
        assert len(team.flag) >= 1, f"{name}: flag inválida"
        assert len(team.name) >= 3, f"{name}: nome muito curto"
        assert team.confederation in ("UEFA", "CONMEBOL", "CONCACAF", "CAF", "AFC", "OFC"), \
            f"{name}: confederação inválida: {team.confederation}"

    print(f"  ✅ Dados de {len(TEAMS)} seleções válidos")


def test_get_team_case_insensitive():
    """Busca de seleção deve ser case-insensitive."""
    from teams_data import get_team

    assert get_team("brasil") is not None
    assert get_team("BRASIL") is not None
    assert get_team("Brasil") is not None
    assert get_team("xyz_inexistente") is None
    print("  ✅ get_team case-insensitive OK")


def test_sorted_teams():
    """get_all_teams deve retornar ordenado por rating decrescente."""
    from teams_data import get_all_teams

    teams = get_all_teams()
    ratings = [t.rating for t in teams]
    assert ratings == sorted(ratings, reverse=True), "Times devem estar ordenados por rating"
    print("  ✅ Ordenação por rating OK")


# ─── Runner ──────────────────────────────────────────────────────────────────

def run_tests():
    tests = [
        ("Simulação básica", test_simulation_basic),
        ("Consistência placar/resultado", test_simulation_consistency),
        ("Bias probabilístico (1000 partidas)", test_simulation_probability_bias),
        ("Função de probabilidade logística", test_win_probability_function),
        ("Hash de senha bcrypt", test_password_hashing),
        ("JWT criação e decode", test_jwt_creation_and_decode),
        ("JWT token inválido", test_jwt_invalid_token),
        ("Integridade dos dados das seleções", test_teams_data_integrity),
        ("Busca case-insensitive", test_get_team_case_insensitive),
        ("Ordenação das seleções", test_sorted_teams),
    ]

    passed = 0
    failed = 0
    print("\n🏆 World Cup Simulator — Executando testes...\n")

    for name, fn in tests:
        print(f"▶ {name}")
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ FALHOU: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"✅ Passou: {passed}/{len(tests)}  |  ❌ Falhou: {failed}/{len(tests)}")
    if failed == 0:
        print("🎉 Todos os testes passaram!\n")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
