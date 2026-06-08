from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="[storage] %(message)s")
_log = logging.getLogger("storage")

T = TypeVar("T", bound=BaseModel)

_BUNDLED_DATA = Path(__file__).resolve().parent / "data"


def _compute_data_dir() -> Path:
    env_dir = os.environ.get("DATA_DIR")
    if env_dir:
        return Path(env_dir)
    if os.environ.get("VERCEL", "") == "1":
        return Path("/tmp/data")
    return _BUNDLED_DATA


DATA_DIR = _compute_data_dir()
REDIS_URL = os.environ.get("REDIS_URL") or os.environ.get("KV_URL")

_vercel = os.environ.get("VERCEL", "")
_redacted = (REDIS_URL or "")[:30] + "..." if REDIS_URL else "<not set>"
_log.info(
    "init | VERCEL=%s | DATA_DIR=%s | REDIS_URL=%s | KV_URL=%s",
    "1" if _vercel == "1" else "0",
    DATA_DIR,
    _redacted,
    "set" if os.environ.get("KV_URL") else "<not set>",
)


def _seed_file(filename: str) -> None:
    target = DATA_DIR / filename
    if target.exists():
        return
    source = _BUNDLED_DATA / filename
    if not source.exists():
        return
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        _log.info("seeded %s from bundle", filename)
    except OSError as exc:
        _log.warning("seed %s failed: %s", filename, exc)


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
                _log.info("Redis OK (%s)", filename)
                self._seed_redis_from_bundle()
            except Exception as exc:
                _log.warning("Redis KO (%s): %s", filename, exc)
                self._redis = None

        if not self._redis:
            _seed_file(filename)

    def _seed_redis_from_bundle(self) -> None:
        try:
            existing = list(self._redis.scan_iter(match=f"{self._prefix}*"))
            if existing:
                return
        except Exception:
            return

        source = _BUNDLED_DATA / self.filename
        if not source.exists():
            return
        try:
            with open(source, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return

        if not raw:
            return
        try:
            pipe = self._redis.pipeline()
            for item_id, item in raw.items():
                pipe.set(
                    self._item_key(item_id),
                    json.dumps(item, ensure_ascii=False),
                )
            pipe.execute()
            _log.info("seeded Redis with %d items from %s", len(raw), self.filename)
        except Exception as exc:
            _log.warning("seed Redis failed for %s: %s", self.filename, exc)

    def _item_key(self, item_id: str) -> str:
        return f"{self._prefix}{item_id}"

    def load_all(self, model: type[T]) -> dict[str, T]:
        if self._redis:
            result = self._load_all_redis(model)
            _log.info("load %s -> %d items (redis)", self.filename, len(result))
            return result
        result = self._load_json(model)
        _log.info("load %s -> %d items (json)", self.filename, len(result))
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
            _log.info("save %s -> %d items (redis %s)", self.filename, len(serialized), "OK" if ok else "KO")
        else:
            self._save_json(serialized)
            _log.info("save %s -> %d items (json)", self.filename, len(serialized))

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
            _log.warning("load redis error %s: %s", self.filename, exc)
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
            _log.warning("save redis error %s: %s", exc)
            return False
