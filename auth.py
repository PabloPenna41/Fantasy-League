"""
auth.py — Autenticação JWT + bcrypt.

Segurança:
  - Senhas hasheadas com bcrypt (cost factor 12)
  - JWT com expiração configurável
  - Secret key lida de variável de ambiente em produção
"""
import os
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from jose import JWTError, jwt
except ImportError:
    class JWTError(Exception):
        """Fallback local para ambientes sem python-jose instalado."""

    def _b64url_encode(payload: bytes) -> str:
        return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")

    def _b64url_decode(payload: str) -> bytes:
        padding = "=" * (-len(payload) % 4)
        return base64.urlsafe_b64decode(payload + padding)

    class _FallbackJWT:
        @staticmethod
        def encode(payload: dict, key: str, algorithm: str = "HS256") -> str:
            if algorithm != "HS256":
                raise JWTError("Algoritmo JWT não suportado")

            normalized = payload.copy()
            if isinstance(normalized.get("exp"), datetime):
                normalized["exp"] = int(normalized["exp"].timestamp())

            header = {"alg": "HS256", "typ": "JWT"}
            header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
            payload_b64 = _b64url_encode(json.dumps(normalized, separators=(",", ":")).encode())
            signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
            signature = hmac.new(key.encode(), signing_input, hashlib.sha256).digest()
            return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"

        @staticmethod
        def decode(token: str, key: str, algorithms: list[str]) -> dict:
            if "HS256" not in algorithms:
                raise JWTError("Algoritmo JWT não suportado")

            try:
                header_b64, payload_b64, signature_b64 = token.split(".")
                signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
                expected = hmac.new(key.encode(), signing_input, hashlib.sha256).digest()
                received = _b64url_decode(signature_b64)
                if not hmac.compare_digest(expected, received):
                    raise JWTError("Assinatura inválida")

                payload = json.loads(_b64url_decode(payload_b64))
                if "exp" in payload and datetime.now(timezone.utc).timestamp() > float(payload["exp"]):
                    raise JWTError("Token expirado")
                return payload
            except (ValueError, json.JSONDecodeError, TypeError):
                raise JWTError("Token inválido")

    jwt = _FallbackJWT()
try:
    from passlib.context import CryptContext
except ImportError:
    CryptContext = None
try:
    import bcrypt as bcrypt_lib
except ImportError:
    bcrypt_lib = None
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db
from models import User

# ─── Config ──────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "worldcup-super-secret-change-in-production-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") if CryptContext and bcrypt_lib is None else None
bearer_scheme = HTTPBearer()


# ─── Password ────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Retorna o hash bcrypt da senha."""
    plain_bytes = plain.encode()
    if bcrypt_lib is not None and len(plain_bytes) <= 72:
        return bcrypt_lib.hashpw(plain_bytes, bcrypt_lib.gensalt(rounds=12)).decode()
    if pwd_context is None:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 120_000)
        return f"pbkdf2_sha256$120000${salt}${digest.hex()}"
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica senha contra hash bcrypt de forma segura (timing-safe)."""
    if hashed.startswith("pbkdf2_sha256$"):
        try:
            _, rounds, salt, expected = hashed.split("$", 3)
            digest = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), int(rounds))
            return hmac.compare_digest(digest.hex(), expected)
        except ValueError:
            return False
    if hashed.startswith(("$2a$", "$2b$", "$2y$")) and bcrypt_lib is not None:
        try:
            return bcrypt_lib.checkpw(plain.encode(), hashed.encode())
        except (TypeError, ValueError):
            return False
    if pwd_context is None:
        return False
    return pwd_context.verify(plain, hashed)


# ─── JWT ─────────────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Cria JWT com expiração."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decodifica e valida JWT. Lança HTTPException em caso de erro."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
        return payload
    except JWTError:
        raise credentials_exception


# ─── Dependency ──────────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency: extrai usuário autenticado do JWT.
    Use como parâmetro de rota para proteger endpoints.
    """
    payload = decode_token(credentials.credentials)
    username: str = payload["sub"]

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou inativo",
        )
    return user
