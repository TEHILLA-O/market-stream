"""Process configuration. Licence material is never given a default value."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MARKETSTREAM_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    host: str = "127.0.0.1"
    port: int = 8000
    seed: int = 42
    speed: float = 4.0
    warmup_pulses: int = 240
    active_symbols: str = "ATHR,BRDL,NL100,HLX,LUMN"
    starting_cash: str = "1000000"
    api_token: str | None = None
    q_host: str = "127.0.0.1"
    q_port: int = 5001
    q_enabled: bool = True
    build_demos: bool = True
    ws_max_clients: int = 32
    log_level: str = "INFO"

    @property
    def symbols(self) -> list[str]:
        return [part.strip().upper() for part in self.active_symbols.split(",") if part.strip()]


def project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "q").is_dir() and (parent / "backend").is_dir():
            return parent
    return here.parents[3]
