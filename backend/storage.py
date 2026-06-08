from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)

DATA_DIR = Path(
    os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent / "data"))
)


class Store:
    def __init__(self, filename: str) -> None:
        self.filename = filename

    def _json_path(self) -> Path:
        return DATA_DIR / self.filename

    def load_all(self, model: type[T]) -> dict[str, T]:
        return self._load_json(model)

    def save_all(self, data: dict[str, BaseModel]) -> None:
        serialized = {k: v.model_dump(mode="json") for k, v in data.items()}
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
