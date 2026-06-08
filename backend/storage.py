from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DATA_DIR = Path(
    os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent / "data"))
)
REDIS_URL = os.environ.get("REDIS_URL") or os.environ.get("KV_URL")


class Store:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self._prefix = f"calcio:{filename.removesuffix('.json')}:"
        self._redis = None
        if REDIS_URL:
            url = REDIS_URL
            if "upstash.io" in url and url.startswith("redis://"):
                url = url.replace("redis://", "rediss://", 1)
            try:
                import redis as redis_mod
                self._redis = redis_mod.from_url(
                    url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    retry_on_timeout=True,
                )
                self._redis.ping()
                print(f"[storage] Redis OK ({filename})", file=sys.stderr)
            except Exception as exc:
                print(f"[storage] Redis KO ({filename}): {exc}", file=sys.stderr)
                self._redis = None

    def _item_key(self, item_id: str) -> str:
        return f"{self._prefix}{item_id}"

    def load_all(self, model: type[T]) -> dict[str, T]:
        if self._redis:
            result = self._load_all_redis(model)
            print(f"[storage] load {self.filename} -> {len(result)} items (redis)", file=sys.stderr)
            return result
        result = self._load_json(model)
        print(f"[storage] load {self.filename} -> {len(result)} items (json)", file=sys.stderr)
        return result

    def save_one(self, item_id: str, item: BaseModel) -> None:
        serialized = item.model_dump(mode="json")
        if self._redis:
            try:
                self._redis.set(
                    self._item_key(item_id),
                    json.dumps(serialized, ensure_ascii=False),
                )
            except Exception:
                pass
        else:
            all_data = self._load_json(type(item))
            all_data[item_id] = item
            self._save_json({k: v.model_dump(mode="json") for k, v in all_data.items()})

    def save_all(self, data: dict[str, BaseModel]) -> None:
        serialized = {k: v.model_dump(mode="json") for k, v in data.items()}
        if self._redis:
            ok = self._save_all_redis(serialized)
            print(f"[storage] save {self.filename} -> {len(serialized)} items (redis {'OK' if ok else 'KO'})", file=sys.stderr)
        else:
            self._save_json(serialized)
            print(f"[storage] save {self.filename} -> {len(serialized)} items (json)", file=sys.stderr)

    # ── JSON (local dev) ──────────────────────────────────────────────

    def _load_json(self, model: type[T]) -> dict[str, T]:
        path = DATA_DIR / self.filename
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            return {sid: model.model_validate(item) for sid, item in raw.items()}
        except (json.JSONDecodeError, KeyError):
            return {}

    def _save_json(self, data: dict[str, dict]) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        try:
            with open(DATA_DIR / self.filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    # ── Redis ─────────────────────────────────────────────────────────

    def _load_all_redis(self, model: type[T]) -> dict[str, T]:
        result: dict[str, T] = {}
        try:
            for key in self._redis.scan_iter(match=f"{self._prefix}*"):
                raw = self._redis.get(key)
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                    item_id = key.removeprefix(self._prefix)
                    result[item_id] = model.model_validate(item)
                except Exception:
                    continue
        except Exception as exc:
            print(f"[storage] load redis error {self.filename}: {exc}", file=sys.stderr)
        return result

    def _save_all_redis(self, data: dict[str, dict]) -> bool:
        try:
            pipe = self._redis.pipeline()
            for item_id, item in data.items():
                pipe.set(
                    self._item_key(item_id),
                    json.dumps(item, ensure_ascii=False),
                )
            pipe.execute()
            return True
        except Exception as exc:
            print(f"[storage] save redis error {self.filename}: {exc}", file=sys.stderr)
            return False
