from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)

DATA_DIR = Path(__file__).resolve().parent / "data"
REDIS_URL = os.environ.get("REDIS_URL")


class Store:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self._redis = None
        if REDIS_URL:
            try:
                import redis as redis_mod
                self._redis = redis_mod.from_url(REDIS_URL, decode_responses=True)
            except Exception:
                pass

    def _json_path(self) -> Path:
        return DATA_DIR / self.filename

    def load_all(self, model: type[T]) -> dict[str, T]:
        if self._redis:
            return self._load_redis(model)
        return self._load_json(model)

    def save_all(self, data: dict[str, BaseModel]) -> None:
        serialized = {k: v.model_dump(mode="json") for k, v in data.items()}
        if self._redis:
            self._save_redis(serialized)
        else:
            self._save_json(serialized)

    def _load_json(self, model: type[T]) -> dict[str, T]:
        path = self._json_path()
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            return {sid: model.model_validate(item) for sid, item in raw.items()}
        except (json.JSONDecodeError, KeyError):
            return {}

    def _save_json(self, data: dict[str, dict]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(self._json_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_redis(self, model: type[T]) -> dict[str, T]:
        raw = self._redis.get(self.filename)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return {sid: model.model_validate(item) for sid, item in data.items()}
        except (json.JSONDecodeError, KeyError):
            return {}

    def _save_redis(self, data: dict[str, dict]) -> None:
        self._redis.set(self.filename, json.dumps(data, ensure_ascii=False))
