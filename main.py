"""
main.py — Aplicação FastAPI principal.

Rotas:
  POST /auth/register     — Cadastro de usuário
  POST /auth/login        — Login e obtenção de JWT
  GET  /auth/me           — Dados do usuário logado
  GET  /teams             — Lista todas as seleções
  GET  /teams/collection  — Lista seleções com estado de desbloqueio
  GET  /teams/{name}      — Detalhes de uma seleção
  GET  /teams/{name}/players — Elenco de uma seleção
  GET  /stickers/collection — Álbum do usuário
  POST /packs/open-team   — Abrir pacote de seleção
  POST /packs/open-player — Abrir pacote de jogadores
  GET  /wallet           — Saldo de gemas
  POST /wallet/purchase  — Compra fictícia de gemas
  POST /simulate          — Simular partida (autenticado)
  GET  /history           — Histórico de partidas (autenticado)
  DELETE /history         — Limpar histórico (autenticado)
"""
import json
import random
import uuid
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

import database
import models
import schemas
import auth
import simulation
import teams_data

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="World Cup Simulator API",
    description="Simulador de partidas da Copa do Mundo 2026 🏆",
    version="1.0.0",
    docs_url="/docs",
)

# CORS — permite acesso do frontend (ajustar origins em produção)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção: listar domínios específicos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory="assets"), name="assets")

# Cria tabelas no banco ao iniciar (em produção usar Alembic)
@app.on_event("startup")
def startup():
    models.Base.metadata.create_all(bind=database.engine)
    db = database.SessionLocal()
    try:
        migrate_user_gems(db)
        migrate_user_profile(db)
        migrate_cup_matches(db)
        migrate_player_photos(db)
        repair_uncommitted_match_simulations(db)
        seed_players(db)
        seed_admin_user(db)
    finally:
        db.close()


def migrate_user_gems(db: Session) -> None:
    """SQLite simples: adiciona gemas a bancos antigos sem Alembic."""
    columns = [row[1] for row in db.execute(text("PRAGMA table_info(users)")).fetchall()]
    if "gems" not in columns:
        db.execute(text("ALTER TABLE users ADD COLUMN gems INTEGER NOT NULL DEFAULT 100"))
        db.commit()


def migrate_user_profile(db: Session) -> None:
    """Adiciona campos de perfil a bancos SQLite antigos sem Alembic."""
    columns = [row[1] for row in db.execute(text("PRAGMA table_info(users)")).fetchall()]
    migrations = {
        "display_name": "ALTER TABLE users ADD COLUMN display_name VARCHAR(80)",
        "bio": "ALTER TABLE users ADD COLUMN bio VARCHAR(240)",
        "avatar_data": "ALTER TABLE users ADD COLUMN avatar_data VARCHAR",
        "profile_theme": "ALTER TABLE users ADD COLUMN profile_theme VARCHAR(20) NOT NULL DEFAULT 'stadium'",
        "is_admin": "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0",
        "custom_team_name": "ALTER TABLE users ADD COLUMN custom_team_name VARCHAR(80) NOT NULL DEFAULT 'Minha Seleção'",
        "custom_team_badge": "ALTER TABLE users ADD COLUMN custom_team_badge VARCHAR(30) NOT NULL DEFAULT 'star'",
        "custom_formation": "ALTER TABLE users ADD COLUMN custom_formation VARCHAR(20) NOT NULL DEFAULT '4-3-3'",
    }
    changed = False
    for column, statement in migrations.items():
        if column not in columns:
            db.execute(text(statement))
            changed = True
    if changed:
        db.commit()


def migrate_cup_matches(db: Session) -> None:
    """Garante a tabela de resultados globais da Copa."""
    models.CupMatch.__table__.create(bind=database.engine, checkfirst=True)


def migrate_player_photos(db: Session) -> None:
    """Adiciona caminho de foto aos jogadores em bancos SQLite antigos."""
    columns = [row[1] for row in db.execute(text("PRAGMA table_info(players)")).fetchall()]
    if "photo_url" not in columns:
        db.execute(text("ALTER TABLE players ADD COLUMN photo_url VARCHAR(240)"))
        db.commit()


def repair_uncommitted_match_simulations(db: Session) -> None:
    """Converte simulações antigas pendentes em histórico de partidas."""
    pending_rows = (
        db.query(models.PendingMatchSimulation)
        .filter(models.PendingMatchSimulation.committed == False)
        .all()
    )
    changed = False
    for pending in pending_rows:
        result = schemas.SimulationResult.model_validate_json(pending.result_json)
        result.simulation_id = pending.id
        if not pending.match_history_id:
            match_record = create_match_history(db, pending.user_id, result)
            db.flush()
            pending.match_history_id = match_record.id
        pending.committed = True
        pending.committed_at = datetime.utcnow()
        changed = True
    if changed:
        db.commit()


def seed_admin_user(db: Session) -> None:
    """Cria/atualiza o perfil administrador padrão."""
    admin = db.query(models.User).filter(models.User.username == "admin").first()
    if admin:
        admin.is_admin = True
        admin.display_name = admin.display_name or "Administrador"
        db.commit()
        grant_all_players(db, admin.id)
        grant_starter_lineup(db, admin.id)
        db.commit()
        return

    admin = models.User(
        username="admin",
        email="admin@local.game",
        hashed_password=auth.hash_password("admin"),
        display_name="Administrador",
        is_admin=True,
        gems=9999,
        custom_team_name="Admin FC",
        custom_team_badge="trophy",
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    grant_all_players(db, admin.id)
    grant_starter_lineup(db, admin.id)
    db.commit()


def seed_players(db: Session) -> None:
    """Popula/atualiza jogadores iniciais sem apagar inventários existentes."""
    seed = teams_data.get_initial_players()
    existing = {
        (player.team_name, player.name): player
        for player in db.query(models.Player).all()
    }

    for data in seed:
        clean_data = {key: value for key, value in data.items() if not key.startswith("_")}
        lookup_key = (
            data.get("_match_team_name", clean_data["team_name"]),
            data.get("_match_name", clean_data["name"]),
        )
        key = (clean_data["team_name"], clean_data["name"])
        player = existing.get(lookup_key) or existing.get(key)
        if player:
            player.name = clean_data["name"]
            player.team_name = clean_data["team_name"]
            player.position = clean_data["position"]
            player.rating = clean_data["rating"]
            if "photo_url" in clean_data:
                player.photo_url = clean_data["photo_url"]
        else:
            db.add(models.Player(**clean_data))

    valid_keys = {(data["team_name"], data["name"]) for data in seed}
    obsolete_players = [
        player
        for player in db.query(models.Player).all()
        if (player.team_name, player.name) not in valid_keys
    ]
    for player in obsolete_players:
        db.query(models.UserLineupPlayer).filter(models.UserLineupPlayer.player_id == player.id).delete()
        db.query(models.UserSticker).filter(models.UserSticker.player_id == player.id).delete()
        db.delete(player)

    # Banco legado podia ter jogadores com rating 80+. Mantemos o registro,
    # mas normalizamos para a nova escala 1-5.
    for player in db.query(models.Player).all():
        if player.rating < 1:
            player.rating = 1
        elif player.rating > 5:
            player.rating = 5

    db.commit()


def grant_starter_players(db: Session, user_id: int) -> None:
    """Garante os 11 jogadores básicos iniciais para o usuário."""
    starters = db.query(models.Player).filter(models.Player.team_name == "Base").all()
    for player in starters:
        existing = (
            db.query(models.UserSticker)
            .filter(
                models.UserSticker.user_id == user_id,
                models.UserSticker.player_id == player.id,
            )
            .first()
        )
        if not existing:
            db.add(models.UserSticker(user_id=user_id, player_id=player.id, quantity=1))
    grant_starter_lineup(db, user_id)
    db.commit()


def grant_all_players(db: Session, user_id: int) -> None:
    """Garante pelo menos uma cópia de todos os jogadores para o usuário."""
    players = db.query(models.Player).all()
    existing_stickers = {
        sticker.player_id: sticker
        for sticker in db.query(models.UserSticker)
        .filter(models.UserSticker.user_id == user_id)
        .all()
    }

    for player in players:
        sticker = existing_stickers.get(player.id)
        if sticker:
            if sticker.quantity < 1:
                sticker.quantity = 1
        else:
            db.add(models.UserSticker(user_id=user_id, player_id=player.id, quantity=1))

    db.commit()


def grant_starter_lineup(db: Session, user_id: int) -> None:
    """Preenche a escalação inicial com jogadores Base quando ela estiver vazia."""
    has_lineup = db.query(models.UserLineupPlayer).filter(models.UserLineupPlayer.user_id == user_id).first()
    if not has_lineup:
        starters = db.query(models.Player).filter(models.Player.team_name == "Base").all()
        for player in starters:
            db.add(models.UserLineupPlayer(user_id=user_id, player_id=player.id))


def player_rarity(player: models.Player) -> str:
    """Converte rating 1-5 nas raridades usadas pela roleta de jogadores."""
    if player.rating >= 5:
        return "legendary"
    if player.rating >= 4:
        return "epic"
    if player.rating >= 3:
        return "rare"
    return "common"


def draw_gacha_player(players: list[models.Player]) -> models.Player:
    roll = random.random() * 100
    if roll <= 5:
        rarity = "legendary"
    elif roll <= 15:
        rarity = "epic"
    elif roll <= 40:
        rarity = "rare"
    else:
        rarity = "common"

    rarity_pool = [player for player in players if player_rarity(player) == rarity]
    if not rarity_pool:
        rarity_pool = players
    return random.choice(rarity_pool)


def gacha_cost(amount: int) -> int:
    return 90 if amount == 10 else 10


def selected_lineup_ids(db: Session, user_id: int) -> set[int]:
    rows = db.query(models.UserLineupPlayer).filter(models.UserLineupPlayer.user_id == user_id).all()
    return {row.player_id for row in rows}


def collection_item(
    player: models.Player,
    quantity: int = 0,
    selected: bool = False,
) -> schemas.StickerCollectionItem:
    return schemas.StickerCollectionItem(
        player=schemas.PlayerResponse.model_validate(player),
        quantity=quantity,
        owned=quantity > 0,
        selected=selected,
    )


def serialize_collection_items(items: list[schemas.StickerCollectionItem]) -> str:
    return json.dumps([item.model_dump(mode="json") for item in items])


def deserialize_collection_items(payload: str) -> list[schemas.StickerCollectionItem]:
    return [schemas.StickerCollectionItem.model_validate(item) for item in json.loads(payload)]


def increment_user_stickers(
    db: Session,
    user_id: int,
    cards: list[schemas.StickerCollectionItem],
) -> None:
    counts: dict[int, int] = {}
    for card in cards:
        counts[card.player.id] = counts.get(card.player.id, 0) + 1

    for player_id, amount in counts.items():
        sticker = (
            db.query(models.UserSticker)
            .filter(
                models.UserSticker.user_id == user_id,
                models.UserSticker.player_id == player_id,
            )
            .first()
        )
        if sticker:
            sticker.quantity += amount
        else:
            db.add(models.UserSticker(user_id=user_id, player_id=player_id, quantity=amount))


def owned_quantities(db: Session, user_id: int) -> dict[int, int]:
    stickers = db.query(models.UserSticker).filter(models.UserSticker.user_id == user_id).all()
    return {sticker.player_id: sticker.quantity for sticker in stickers}


def unlocked_team_names(db: Session, user_id: int) -> set[str]:
    """Retorna as seleções desbloqueadas pelo usuário."""
    rows = db.query(models.UserTeam).filter(models.UserTeam.user_id == user_id).all()
    return {row.team_name for row in rows}


def is_team_unlocked(db: Session, user_id: int, team_name: str) -> bool:
    """Checa se o usuário pode usar a seleção informada."""
    return (
        db.query(models.UserTeam)
        .filter(
            models.UserTeam.user_id == user_id,
            models.UserTeam.team_name == team_name,
        )
        .first()
        is not None
    )


def require_admin(current_user: models.User = Depends(auth.get_current_user)) -> models.User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso de administrador necessário")
    return current_user


def get_admin_target_user(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
    return user


def has_other_active_admin(db: Session, user_id: int) -> bool:
    return (
        db.query(models.User)
        .filter(
            models.User.id != user_id,
            models.User.is_admin == True,
            models.User.is_active == True,
        )
        .first()
        is not None
    )


def admin_user_summary(db: Session, user: models.User) -> schemas.AdminUserSummary:
    stickers = db.query(models.UserSticker).filter(models.UserSticker.user_id == user.id).all()
    return schemas.AdminUserSummary(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        gems=user.gems,
        total_players=db.query(models.Player).count(),
        owned_players=sum(1 for sticker in stickers if sticker.quantity > 0),
        total_copies=sum(max(sticker.quantity, 0) for sticker in stickers),
        selected_players=db.query(models.UserLineupPlayer)
        .filter(models.UserLineupPlayer.user_id == user.id)
        .count(),
        unlocked_teams=db.query(models.UserTeam)
        .filter(models.UserTeam.user_id == user.id)
        .count(),
        matches=db.query(models.MatchHistory)
        .filter(models.MatchHistory.user_id == user.id)
        .count(),
        created_at=user.created_at,
    )


def admin_user_detail(db: Session, user: models.User) -> schemas.AdminUserDetailResponse:
    players = (
        db.query(models.Player)
        .order_by(models.Player.team_name.asc(), models.Player.rating.desc(), models.Player.name.asc())
        .all()
    )
    quantities = owned_quantities(db, user.id)
    selected = selected_lineup_ids(db, user.id)
    teams = sorted(unlocked_team_names(db, user.id))
    return schemas.AdminUserDetailResponse(
        user=admin_user_summary(db, user),
        items=[
            collection_item(player, quantities.get(player.id, 0), player.id in selected)
            for player in players
        ],
        unlocked_teams=teams,
    )


def cup_team_records(db: Session) -> dict[str, dict[str, int]]:
    records = {team.name: {"wins": 0, "draws": 0, "losses": 0} for team in teams_data.get_all_teams()}
    for match in db.query(models.CupMatch).all():
        if match.home_team not in records:
            records[match.home_team] = {"wins": 0, "draws": 0, "losses": 0}
        if match.away_team not in records:
            records[match.away_team] = {"wins": 0, "draws": 0, "losses": 0}
        if match.home_score > match.away_score:
            records[match.home_team]["wins"] += 1
            records[match.away_team]["losses"] += 1
        elif match.away_score > match.home_score:
            records[match.away_team]["wins"] += 1
            records[match.home_team]["losses"] += 1
        else:
            records[match.home_team]["draws"] += 1
            records[match.away_team]["draws"] += 1
    return records


def team_boost_for(db: Session, team_name: str) -> float:
    record = cup_team_records(db).get(team_name, {"wins": 0, "draws": 0})
    return 1.0 + record["wins"] * 0.05 + record["draws"] * 0.015


def quantity_multiplier(quantity: int) -> float:
    return 1.0 + min(max(quantity - 1, 0), 15) * 0.03


def build_lineup(db: Session, team_name: str, user_id: int) -> list[schemas.LineupPlayer]:
    quantities = owned_quantities(db, user_id)
    boost = team_boost_for(db, team_name)
    players = (
        db.query(models.Player)
        .filter(models.Player.team_name == team_name)
        .order_by(models.Player.rating.desc())
        .all()
    )
    return [
        schemas.LineupPlayer(
            id=player.id,
            name=player.name,
            rating=player.rating,
            position=player.position,
            team_name=player.team_name,
            photo_url=player.photo_url,
            owned=quantities.get(player.id, 0) > 0,
            quantity=quantities.get(player.id, 0),
            quantity_multiplier=quantity_multiplier(quantities.get(player.id, 0)),
            team_boost=boost,
            effective_rating=player.rating * quantity_multiplier(quantities.get(player.id, 0)) * boost,
        )
        for player in players
    ]


def build_user_lineup(db: Session, user_id: int) -> list[schemas.LineupPlayer]:
    quantities = owned_quantities(db, user_id)
    lineup_ids = selected_lineup_ids(db, user_id)
    selected_players = (
        db.query(models.Player)
        .filter(models.Player.id.in_(list(lineup_ids)))
        .order_by(models.Player.position.asc(), models.Player.rating.desc(), models.Player.name.asc())
        .all()
        if lineup_ids
        else []
    )

    return [
        (lambda quantity, boost: schemas.LineupPlayer(
            id=player.id,
            name=player.name,
            rating=player.rating,
            position=player.position,
            team_name=player.team_name,
            photo_url=player.photo_url,
            owned=True,
            quantity=quantity,
            quantity_multiplier=quantity_multiplier(quantity),
            team_boost=boost,
            effective_rating=player.rating * quantity_multiplier(quantity) * boost,
        ))(quantities.get(player.id, 0), team_boost_for(db, player.team_name))
        for player in selected_players
        if quantities.get(player.id, 0) > 0
    ]


def user_lineup_rating(lineup: list[schemas.LineupPlayer]) -> float:
    if not lineup:
        return 1.0
    return sum(player.effective_rating or player.rating for player in lineup) / len(lineup)


def create_match_history(
    db: Session,
    user_id: int,
    result: schemas.SimulationResult,
) -> models.MatchHistory:
    match_record = models.MatchHistory(
        user_id=user_id,
        user_team=result.user_team,
        opponent_team=result.opponent_team,
        user_score=result.user_score,
        opponent_score=result.opponent_score,
        result=result.result,
        user_team_rating=result.user_team_rating,
        opponent_rating=result.opponent_rating,
    )
    db.add(match_record)
    return match_record


def build_random_opponent_lineup(db: Session) -> list[schemas.LineupPlayer]:
    players = db.query(models.Player).filter(models.Player.team_name != "Base").all()
    by_position: dict[str, list[models.Player]] = {}
    for player in players:
        by_position.setdefault(player.position, []).append(player)

    shape = {"Goleiro": 1, "Zagueiro": 4, "Meio-Campo": 3, "Atacante": 3}
    selected: list[models.Player] = []
    used: set[int] = set()
    for position, amount in shape.items():
        pool = by_position.get(position, [])
        picks = random.sample(pool, min(amount, len(pool)))
        selected.extend(picks)
        used.update(player.id for player in picks)

    if len(selected) < 11:
        leftovers = [player for player in players if player.id not in used]
        selected.extend(random.sample(leftovers, min(11 - len(selected), len(leftovers))))

    return [
        (lambda boost: 
        schemas.LineupPlayer(
            id=player.id,
            name=player.name,
            rating=player.rating,
            position=player.position,
            team_name=player.team_name,
            photo_url=player.photo_url,
            owned=False,
            quantity=0,
            quantity_multiplier=1.0,
            team_boost=boost,
            effective_rating=player.rating * boost,
        ))(team_boost_for(db, player.team_name))
        for player in selected[:11]
    ]


def calculate_effective_rating(
    db: Session,
    team: schemas.TeamInfo,
    user_id: int,
) -> tuple[float, float]:
    """Calcula força efetiva = rating base + média dos jogadores possuídos."""
    quantities = owned_quantities(db, user_id)
    owned_players = (
        db.query(models.Player)
        .filter(models.Player.team_name == team.name, models.Player.id.in_(list(quantities.keys())))
        .all()
        if quantities
        else []
    )

    if not owned_players:
        return team.rating, 0.0

    player_bonus = sum(player.rating for player in owned_players) / len(owned_players)
    return team.rating + player_bonus, player_bonus


def prepare_simulation_result(
    db: Session,
    current_user: models.User,
) -> schemas.SimulationResult:
    grant_starter_players(db, current_user.id)
    user_lineup = build_user_lineup(db, current_user.id)
    if len(user_lineup) != 11:
        raise HTTPException(status_code=400, detail="Salve uma escalação com exatamente 11 jogadores antes de simular")
    user_effective_rating = user_lineup_rating(user_lineup)
    player_bonus = max(0.0, user_effective_rating - 1.0)
    opponent_lineup = build_random_opponent_lineup(db)
    opponent_rating = user_lineup_rating(opponent_lineup)
    opponent_names = [player.team_name for player in opponent_lineup if player.team_name != "Base"]
    opponent_label = random.choice(opponent_names) if opponent_names else "Rival"
    user_team = schemas.TeamInfo(
        name=current_user.custom_team_name or "Minha Seleção",
        flag=current_user.custom_team_badge or "star",
        rating=1.0,
        group="Custom",
        confederation="Custom",
    )
    opponent = schemas.TeamInfo(
        name=f"{random.choice(['Rival FC', 'United', 'Athletic', 'City'])} {opponent_label}",
        flag=random.choice(["controller", "ball", "trophy", "spark"]),
        rating=opponent_rating,
        group="Online",
        confederation="Online",
    )

    return simulation.simulate_match(
        user_team,
        opponent,
        user_lineup=user_lineup,
        opponent_lineup=opponent_lineup,
        user_effective_rating=user_effective_rating,
        opponent_effective_rating=opponent_rating,
        user_player_bonus=player_bonus,
    )


# ─── Auth endpoints ──────────────────────────────────────────────────────────

@app.post(
    "/auth/register",
    response_model=schemas.TokenResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Auth"],
    summary="Cadastrar novo usuário",
)
def register(payload: schemas.UserRegisterRequest, db: Session = Depends(database.get_db)):
    # Verifica username duplicado
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username já está em uso",
        )
    # Verifica email duplicado
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-mail já cadastrado",
        )

    user = models.User(
        username=payload.username,
        email=payload.email,
        hashed_password=auth.hash_password(payload.password),
        gems=100,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    grant_starter_players(db, user.id)

    token = auth.create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return schemas.TokenResponse(access_token=token, username=user.username, gems=user.gems)


@app.post(
    "/auth/login",
    response_model=schemas.TokenResponse,
    tags=["Auth"],
    summary="Login e obter JWT",
)
def login(payload: schemas.UserLoginRequest, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()

    if not user or not auth.verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conta desativada")
    if user.gems is None:
        user.gems = 100
        db.commit()
    grant_starter_players(db, user.id)

    token = auth.create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return schemas.TokenResponse(access_token=token, username=user.username, gems=user.gems)


@app.get(
    "/auth/me",
    response_model=schemas.UserResponse,
    tags=["Auth"],
    summary="Dados do usuário autenticado",
)
def me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@app.put(
    "/auth/me",
    response_model=schemas.UserResponse,
    tags=["Auth"],
    summary="Atualizar perfil do usuário autenticado",
)
def update_me(
    payload: schemas.UserProfileUpdateRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if payload.email and payload.email != current_user.email:
        existing_email = (
            db.query(models.User)
            .filter(models.User.email == payload.email, models.User.id != current_user.id)
            .first()
        )
        if existing_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado")

    current_user.display_name = payload.display_name
    if payload.email:
        current_user.email = payload.email
    current_user.bio = payload.bio
    current_user.avatar_data = payload.avatar_data
    current_user.profile_theme = payload.profile_theme
    db.commit()
    db.refresh(current_user)
    return current_user


@app.delete(
    "/auth/me",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Auth"],
    summary="Excluir conta do usuário autenticado",
)
def delete_me(
    payload: schemas.AccountDeleteRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not auth.verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Senha incorreta")
    db.delete(current_user)
    db.commit()


@app.get(
    "/user/team-settings",
    response_model=schemas.UserResponse,
    tags=["User"],
    summary="Configurações do time personalizado",
)
def get_team_settings(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@app.put(
    "/user/team-settings",
    response_model=schemas.UserResponse,
    tags=["User"],
    summary="Atualizar nome, escudo e formação do time",
)
def update_team_settings(
    payload: schemas.UserTeamSettingsRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    current_user.custom_team_name = payload.custom_team_name
    current_user.custom_team_badge = payload.custom_team_badge
    current_user.custom_formation = payload.custom_formation
    db.commit()
    db.refresh(current_user)
    return current_user


# ─── Teams endpoints ─────────────────────────────────────────────────────────

@app.get(
    "/teams",
    response_model=list[schemas.TeamInfo],
    tags=["Teams"],
    summary="Listar todas as seleções",
)
def list_teams():
    return teams_data.get_all_teams()


@app.get(
    "/teams/collection",
    response_model=schemas.TeamCollectionResponse,
    tags=["Teams"],
    summary="Listar seleções com estado de desbloqueio",
)
def get_team_collection(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    unlocked = unlocked_team_names(db, current_user.id)
    teams = teams_data.get_all_teams()
    items = [
        schemas.TeamCollectionItem(team=team, unlocked=team.name in unlocked)
        for team in teams
    ]
    return schemas.TeamCollectionResponse(
        total_teams=len(items),
        unlocked_teams=sum(1 for item in items if item.unlocked),
        items=items,
    )


@app.get(
    "/teams/{name}",
    response_model=schemas.TeamInfo,
    tags=["Teams"],
    summary="Detalhes de uma seleção",
)
def get_team(name: str):
    team = teams_data.get_team(name)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seleção não encontrada")
    return team


@app.get(
    "/teams/{name}/players",
    response_model=list[schemas.PlayerResponse],
    tags=["Teams"],
    summary="Listar jogadores de uma seleção",
)
def get_team_players(
    name: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    team = teams_data.get_team(name)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seleção não encontrada")

    return (
        db.query(models.Player)
        .filter(models.Player.team_name == team.name)
        .order_by(models.Player.rating.desc())
        .all()
    )


# ─── Packs / Stickers endpoints ─────────────────────────────────────────────

@app.post(
    "/packs/open-team",
    response_model=schemas.TeamPackOpenResponse,
    tags=["Packs"],
    summary="Abrir pacote e desbloquear uma seleção",
)
def open_team_pack(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    unlocked = unlocked_team_names(db, current_user.id)
    locked_teams = [team for team in teams_data.get_all_teams() if team.name not in unlocked]

    if not locked_teams:
        raise HTTPException(status_code=400, detail="Todas as seleções já foram desbloqueadas")

    drawn_team = random.choice(locked_teams)
    db.add(models.UserTeam(user_id=current_user.id, team_name=drawn_team.name))
    db.commit()

    return schemas.TeamPackOpenResponse(
        team=drawn_team,
        remaining_locked=len(locked_teams) - 1,
    )

@app.get(
    "/stickers/collection",
    response_model=schemas.StickerCollectionResponse,
    tags=["Stickers"],
    summary="Álbum de figurinhas do usuário",
)
def get_sticker_collection(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    players = (
        db.query(models.Player)
        .order_by(models.Player.team_name.asc(), models.Player.rating.desc())
        .all()
    )
    quantities = owned_quantities(db, current_user.id)
    selected = selected_lineup_ids(db, current_user.id)
    items = [
        collection_item(player, quantities.get(player.id, 0), player.id in selected)
        for player in players
    ]

    return schemas.StickerCollectionResponse(
        total_players=len(players),
        owned_players=sum(1 for item in items if item.owned),
        total_copies=sum(item.quantity for item in items),
        gems=current_user.gems,
        items=items,
    )


@app.get(
    "/lineup",
    response_model=schemas.LineupResponse,
    tags=["Lineup"],
    summary="Escalação personalizada do usuário",
)
def get_lineup(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    grant_starter_players(db, current_user.id)
    quantities = owned_quantities(db, current_user.id)
    lineup = build_user_lineup(db, current_user.id)
    players_by_id = {
        player.id: player
        for player in db.query(models.Player)
        .filter(models.Player.id.in_([player.id for player in lineup]))
        .all()
    }
    items = [
        collection_item(
            players_by_id[player.id],
            quantities.get(player.id, 0),
            True,
        )
        for player in lineup
    ]
    return schemas.LineupResponse(players=items, rating=user_lineup_rating(lineup))


@app.put(
    "/lineup",
    response_model=schemas.LineupResponse,
    tags=["Lineup"],
    summary="Salvar escalação personalizada",
)
def update_lineup(
    payload: schemas.LineupUpdateRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    player_ids = list(dict.fromkeys(payload.player_ids))
    if len(player_ids) != 11:
        raise HTTPException(status_code=400, detail="Escolha exatamente 11 jogadores para a escalação")

    quantities = owned_quantities(db, current_user.id)
    if any(player_id not in quantities or quantities[player_id] <= 0 for player_id in player_ids):
        raise HTTPException(status_code=400, detail="A escalação só pode usar cartas que você possui")

    players = db.query(models.Player).filter(models.Player.id.in_(player_ids)).all()
    if len(players) != 11:
        raise HTTPException(status_code=400, detail="Jogador inválido na escalação")

    positions = {}
    for player in players:
        positions[player.position] = positions.get(player.position, 0) + 1
    if positions.get("Goleiro", 0) != 1:
        raise HTTPException(status_code=400, detail="A escalação precisa ter exatamente 1 goleiro")

    db.query(models.UserLineupPlayer).filter(models.UserLineupPlayer.user_id == current_user.id).delete()
    for player_id in player_ids:
        db.add(models.UserLineupPlayer(user_id=current_user.id, player_id=player_id))
    db.commit()

    return get_lineup(db=db, current_user=current_user)


@app.get(
    "/wallet",
    response_model=schemas.WalletResponse,
    tags=["Wallet"],
    summary="Saldo de gemas do usuário",
)
def get_wallet(current_user: models.User = Depends(auth.get_current_user)):
    return schemas.WalletResponse(gems=current_user.gems)


@app.post(
    "/wallet/purchase",
    response_model=schemas.WalletResponse,
    tags=["Wallet"],
    summary="Compra fictícia de gemas",
)
def purchase_gems(
    payload: schemas.GemPurchaseRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    packages = {
        "starter": 120,
        "value": 280,
        "elite": 650,
    }
    if payload.package_id not in packages:
        raise HTTPException(status_code=400, detail="Pacote de gemas inválido")

    current_user.gems += packages[payload.package_id]
    db.commit()
    db.refresh(current_user)
    return schemas.WalletResponse(gems=current_user.gems)


@app.post(
    "/packs/open-player",
    response_model=schemas.PackOpenResponse,
    tags=["Packs"],
    summary="Abrir roleta de jogadores",
)
def open_player_pack(
    amount: int = Query(1, ge=1, le=10),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    players = db.query(models.Player).filter(models.Player.team_name != "Base").all()
    if not players:
        raise HTTPException(status_code=500, detail="Nenhum jogador cadastrado para sortear")
    cost = gacha_cost(amount)
    if current_user.gems < cost:
        raise HTTPException(status_code=400, detail="Gemas insuficientes")

    drawn = [draw_gacha_player(players) for _ in range(amount)]
    cards: list[schemas.StickerCollectionItem] = []
    projected_quantities = owned_quantities(db, current_user.id)
    for player in drawn:
        projected_quantities[player.id] = projected_quantities.get(player.id, 0) + 1
        cards.append(collection_item(player, projected_quantities[player.id]))

    opening_id = str(uuid.uuid4())
    db.query(models.PendingPlayerPack).filter(
        models.PendingPlayerPack.user_id == current_user.id,
        models.PendingPlayerPack.committed == False,
    ).delete()
    pending = models.PendingPlayerPack(
        id=opening_id,
        user_id=current_user.id,
        cards_json=serialize_collection_items(cards),
        cost=cost,
        remaining_gems=current_user.gems - cost,
        committed=True,
        committed_at=datetime.utcnow(),
    )
    db.add(pending)
    increment_user_stickers(db, current_user.id, cards)
    current_user.gems -= cost
    pending.remaining_gems = current_user.gems
    db.commit()
    return schemas.PackOpenResponse(opening_id=opening_id, cards=cards, remaining_gems=current_user.gems)


@app.post(
    "/packs/open-player/{opening_id}/commit",
    response_model=schemas.PackOpenResponse,
    tags=["Packs"],
    summary="Confirmar roleta de jogadores após a animação",
)
def commit_player_pack(
    opening_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    pending = (
        db.query(models.PendingPlayerPack)
        .filter(
            models.PendingPlayerPack.id == opening_id,
            models.PendingPlayerPack.user_id == current_user.id,
        )
        .first()
    )
    if not pending:
        raise HTTPException(status_code=404, detail="Compra pendente não encontrada")

    cards = deserialize_collection_items(pending.cards_json)
    if pending.committed:
        return schemas.PackOpenResponse(opening_id=opening_id, cards=cards, remaining_gems=current_user.gems)
    if current_user.gems < pending.cost:
        raise HTTPException(status_code=400, detail="Gemas insuficientes para confirmar a compra")

    increment_user_stickers(db, current_user.id, cards)
    current_user.gems -= pending.cost
    pending.remaining_gems = current_user.gems
    pending.committed = True
    pending.committed_at = datetime.utcnow()
    db.commit()
    return schemas.PackOpenResponse(opening_id=opening_id, cards=cards, remaining_gems=current_user.gems)


@app.post(
    "/stickers/open-pack",
    response_model=schemas.PackOpenResponse,
    tags=["Stickers"],
    summary="Alias legado: abrir roleta de jogador",
)
def open_sticker_pack(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return open_player_pack(amount=1, db=db, current_user=current_user)


# ─── Admin ──────────────────────────────────────────────────────────────────

@app.get(
    "/admin/users",
    response_model=list[schemas.AdminUserSummary],
    tags=["Admin"],
    summary="Listar contas administráveis",
)
def list_admin_users(
    q: str = Query("", max_length=80),
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(require_admin),
):
    del admin_user
    users = db.query(models.User).order_by(models.User.created_at.desc(), models.User.id.desc()).all()
    query = q.strip().lower()
    if query:
        users = [
            user for user in users
            if query in user.username.lower()
            or query in user.email.lower()
            or query in (user.display_name or "").lower()
        ]
    return [admin_user_summary(db, user) for user in users]


@app.get(
    "/admin/users/{user_id}",
    response_model=schemas.AdminUserDetailResponse,
    tags=["Admin"],
    summary="Detalhar uma conta administrável",
)
def get_admin_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(require_admin),
):
    del admin_user
    return admin_user_detail(db, get_admin_target_user(db, user_id))


@app.patch(
    "/admin/users/{user_id}",
    response_model=schemas.AdminUserDetailResponse,
    tags=["Admin"],
    summary="Atualizar uma conta pelo painel administrativo",
)
def update_admin_user(
    user_id: int,
    payload: schemas.AdminUserUpdateRequest,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(require_admin),
):
    target = get_admin_target_user(db, user_id)
    fields = payload.model_fields_set

    if target.id == admin_user.id:
        if payload.is_admin is False:
            raise HTTPException(status_code=400, detail="Você não pode remover seu próprio acesso admin")
        if payload.is_active is False:
            raise HTTPException(status_code=400, detail="Você não pode desativar sua própria conta")

    losing_active_admin = (
        target.is_admin
        and target.is_active
        and (
            ("is_admin" in fields and payload.is_admin is False)
            or ("is_active" in fields and payload.is_active is False)
        )
    )
    if losing_active_admin and not has_other_active_admin(db, target.id):
        raise HTTPException(status_code=400, detail="Mantenha pelo menos um administrador ativo")

    if "email" in fields and payload.email and payload.email != target.email:
        existing_email = (
            db.query(models.User)
            .filter(models.User.email == payload.email, models.User.id != target.id)
            .first()
        )
        if existing_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado")
        target.email = payload.email
    if "display_name" in fields:
        target.display_name = payload.display_name
    if "gems" in fields and payload.gems is not None:
        target.gems = payload.gems
    if "is_admin" in fields and payload.is_admin is not None:
        target.is_admin = payload.is_admin
    if "is_active" in fields and payload.is_active is not None:
        target.is_active = payload.is_active

    db.commit()
    db.refresh(target)
    return admin_user_detail(db, target)


@app.delete(
    "/admin/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Admin"],
    summary="Apagar uma conta pelo painel administrativo",
)
def delete_admin_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(require_admin),
):
    target = get_admin_target_user(db, user_id)
    if target.id == admin_user.id:
        raise HTTPException(status_code=400, detail="Use a tela de perfil para excluir sua própria conta")
    if target.is_admin and target.is_active and not has_other_active_admin(db, target.id):
        raise HTTPException(status_code=400, detail="Mantenha pelo menos um administrador ativo")
    db.delete(target)
    db.commit()


@app.put(
    "/admin/users/{user_id}/players/{player_id}",
    response_model=schemas.AdminUserDetailResponse,
    tags=["Admin"],
    summary="Alterar quantidade de uma carta de jogador",
)
def update_admin_player_quantity(
    user_id: int,
    player_id: int,
    payload: schemas.AdminPlayerQuantityRequest,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(require_admin),
):
    del admin_user
    target = get_admin_target_user(db, user_id)
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jogador não encontrado")

    sticker = (
        db.query(models.UserSticker)
        .filter(
            models.UserSticker.user_id == target.id,
            models.UserSticker.player_id == player.id,
        )
        .first()
    )
    if payload.quantity <= 0:
        if sticker:
            db.delete(sticker)
        db.query(models.UserLineupPlayer).filter(
            models.UserLineupPlayer.user_id == target.id,
            models.UserLineupPlayer.player_id == player.id,
        ).delete()
    elif sticker:
        sticker.quantity = payload.quantity
    else:
        db.add(models.UserSticker(user_id=target.id, player_id=player.id, quantity=payload.quantity))

    db.commit()
    db.refresh(target)
    return admin_user_detail(db, target)


@app.post(
    "/admin/users/{user_id}/bulk-players",
    response_model=schemas.AdminUserDetailResponse,
    tags=["Admin"],
    summary="Aplicar ação em massa na coleção de jogadores",
)
def bulk_admin_player_action(
    user_id: int,
    payload: schemas.AdminPlayerBulkRequest,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(require_admin),
):
    del admin_user
    target = get_admin_target_user(db, user_id)

    if payload.action == "clear_all":
        db.query(models.UserLineupPlayer).filter(models.UserLineupPlayer.user_id == target.id).delete()
        db.query(models.UserSticker).filter(models.UserSticker.user_id == target.id).delete()
    elif payload.action == "grant_all":
        players = db.query(models.Player).all()
        existing_stickers = {
            sticker.player_id: sticker
            for sticker in db.query(models.UserSticker)
            .filter(models.UserSticker.user_id == target.id)
            .all()
        }
        for player in players:
            sticker = existing_stickers.get(player.id)
            if sticker:
                sticker.quantity = max(sticker.quantity, 1)
            else:
                db.add(models.UserSticker(user_id=target.id, player_id=player.id, quantity=1))

    db.commit()
    db.refresh(target)
    return admin_user_detail(db, target)


# ─── Copa real simulada ─────────────────────────────────────────────────────

@app.get(
    "/cup/momentum",
    response_model=schemas.TeamMomentumResponse,
    tags=["Cup"],
    summary="Bônus globais por resultados cadastrados",
)
def get_cup_momentum(db: Session = Depends(database.get_db)):
    records = cup_team_records(db)
    return schemas.TeamMomentumResponse(
        items=[
            schemas.TeamMomentumItem(
                team_name=team_name,
                wins=record["wins"],
                draws=record["draws"],
                losses=record["losses"],
                boost=1.0 + record["wins"] * 0.05 + record["draws"] * 0.015,
            )
            for team_name, record in sorted(records.items())
        ]
    )


@app.get(
    "/cup/matches",
    response_model=list[schemas.CupMatchResponse],
    tags=["Cup"],
    summary="Resultados globais da Copa",
)
def list_cup_matches(db: Session = Depends(database.get_db)):
    return db.query(models.CupMatch).order_by(models.CupMatch.played_at.desc(), models.CupMatch.id.desc()).all()


@app.post(
    "/admin/cup/matches",
    response_model=schemas.CupMatchResponse,
    tags=["Admin"],
    summary="Cadastrar resultado global da Copa",
)
def create_cup_match(
    payload: schemas.CupMatchRequest,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(require_admin),
):
    del admin_user
    if payload.home_team == payload.away_team:
        raise HTTPException(status_code=400, detail="Escolha duas seleções diferentes")
    if not teams_data.get_team(payload.home_team) or not teams_data.get_team(payload.away_team):
        raise HTTPException(status_code=400, detail="Seleção inválida")
    match = models.CupMatch(
        home_team=payload.home_team,
        away_team=payload.away_team,
        home_score=payload.home_score,
        away_score=payload.away_score,
        source="manual",
        played_at=datetime.utcnow(),
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return match


@app.put(
    "/admin/cup/matches/{match_id}",
    response_model=schemas.CupMatchResponse,
    tags=["Admin"],
    summary="Modificar resultado global da Copa",
)
def update_cup_match(
    match_id: int,
    payload: schemas.CupMatchRequest,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(require_admin),
):
    del admin_user
    match = db.query(models.CupMatch).filter(models.CupMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partida não encontrada")
    if payload.home_team == payload.away_team:
        raise HTTPException(status_code=400, detail="Escolha duas seleções diferentes")
    if not teams_data.get_team(payload.home_team) or not teams_data.get_team(payload.away_team):
        raise HTTPException(status_code=400, detail="Seleção inválida")
    match.home_team = payload.home_team
    match.away_team = payload.away_team
    match.home_score = payload.home_score
    match.away_score = payload.away_score
    match.source = "manual"
    match.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(match)
    return match


@app.delete(
    "/admin/cup/matches/{match_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Admin"],
    summary="Apagar resultado global da Copa",
)
def delete_cup_match(
    match_id: int,
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(require_admin),
):
    del admin_user
    match = db.query(models.CupMatch).filter(models.CupMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partida não encontrada")
    db.delete(match)
    db.commit()


@app.post(
    "/admin/cup/matches/generate",
    response_model=list[schemas.CupMatchResponse],
    tags=["Admin"],
    summary="Gerar resultados automáticos da Copa",
)
def generate_cup_matches(
    amount: int = Query(8, ge=1, le=64),
    db: Session = Depends(database.get_db),
    admin_user: models.User = Depends(require_admin),
):
    del admin_user
    teams = teams_data.get_all_teams()
    created: list[models.CupMatch] = []
    for _ in range(amount):
        home, away = random.sample(teams, 2)
        home_edge = home.rating - away.rating
        home_goals = max(0, int(random.gauss(1.4 + home_edge * 0.25, 1.0)))
        away_goals = max(0, int(random.gauss(1.2 - home_edge * 0.18, 1.0)))
        match = models.CupMatch(
            home_team=home.name,
            away_team=away.name,
            home_score=min(home_goals, 9),
            away_score=min(away_goals, 9),
            source="auto",
            played_at=datetime.utcnow(),
        )
        db.add(match)
        created.append(match)
    db.commit()
    for match in created:
        db.refresh(match)
    return created


# ─── Simulation endpoint ─────────────────────────────────────────────────────

@app.post(
    "/simulate",
    response_model=schemas.SimulationResult,
    tags=["Simulation"],
    summary="Simular partida (requer autenticação)",
)
def simulate(
    payload: schemas.SimulationRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    del payload
    simulation_id = str(uuid.uuid4())
    result = prepare_simulation_result(db, current_user)
    result.simulation_id = simulation_id
    db.query(models.PendingMatchSimulation).filter(
        models.PendingMatchSimulation.user_id == current_user.id,
        models.PendingMatchSimulation.committed == False,
    ).delete()
    match_record = create_match_history(db, current_user.id, result)
    db.flush()
    db.add(models.PendingMatchSimulation(
        id=simulation_id,
        user_id=current_user.id,
        result_json=result.model_dump_json(),
        committed=True,
        committed_at=datetime.utcnow(),
        match_history_id=match_record.id,
    ))
    db.commit()

    return result


@app.post(
    "/simulate/{simulation_id}/commit",
    response_model=schemas.SimulationResult,
    tags=["Simulation"],
    summary="Confirmar partida simulada após a animação",
)
def commit_simulation(
    simulation_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    pending = (
        db.query(models.PendingMatchSimulation)
        .filter(
            models.PendingMatchSimulation.id == simulation_id,
            models.PendingMatchSimulation.user_id == current_user.id,
        )
        .first()
    )
    if not pending:
        raise HTTPException(status_code=404, detail="Simulação pendente não encontrada")

    result = schemas.SimulationResult.model_validate_json(pending.result_json)
    result.simulation_id = simulation_id
    if pending.committed:
        return result

    match_record = create_match_history(db, current_user.id, result)
    db.flush()
    pending.match_history_id = match_record.id
    pending.committed = True
    pending.committed_at = datetime.utcnow()
    db.commit()
    return result


# ─── History endpoints ───────────────────────────────────────────────────────

@app.get(
    "/history",
    response_model=list[schemas.MatchHistoryResponse],
    tags=["History"],
    summary="Histórico de partidas do usuário",
)
def get_history(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    matches = (
        db.query(models.MatchHistory)
        .filter(models.MatchHistory.user_id == current_user.id)
        .order_by(models.MatchHistory.played_at.desc())
        .limit(50)
        .all()
    )
    return matches


@app.delete(
    "/history",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["History"],
    summary="Limpar histórico do usuário",
)
def clear_history(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    db.query(models.MatchHistory).filter(
        models.MatchHistory.user_id == current_user.id
    ).delete()
    db.commit()


# ─── Health check ────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"], summary="Health check")
def health():
    return {"status": "ok", "version": "1.0.0"}
