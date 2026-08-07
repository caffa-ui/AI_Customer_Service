from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserCredential:
    user_id: str
    password_hash: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int
