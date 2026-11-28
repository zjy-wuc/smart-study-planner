"""Seed Manifest：记录演示数据批次、主键与归属。

清单只包含数据库主键、归属关系与数量，不包含密码、Token 或连接信息。
默认写入仓库之外的受保护目录，可通过 SSP_SEED_MANIFEST_DIR 覆盖。
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def default_manifest_dir() -> Path:
    configured = os.environ.get("SSP_SEED_MANIFEST_DIR")
    if configured:
        return Path(configured)
    return Path(r"D:\ssp_seed_manifests")


class SeedManifest:
    def __init__(self, database: str, batch_id: str, generator: str):
        self.database = database
        self.batch_id = batch_id
        self.generator = generator
        self.generated_at = datetime.now(timezone.utc).isoformat()
        self.special_accounts: dict[str, dict] = {}
        self.demo_user_ids: list[int] = []
        self.tables: dict[str, dict] = {}
        self.notes: list[str] = []

    def add(self, table: str, row_id, owner=None) -> None:
        entry = self.tables.setdefault(table, {"ids": [], "owners": {}})
        entry["ids"].append(row_id)
        if owner is not None:
            entry["owners"][str(row_id)] = owner

    def add_special(self, key: str, user_id: int, username: str, role: str, email: str) -> None:
        self.special_accounts[key] = {
            "user_id": user_id,
            "username": username,
            "role": role,
            "email": email,
        }

    def add_demo_user(self, user_id: int) -> None:
        self.demo_user_ids.append(user_id)

    def ids(self, table: str) -> list:
        return list(self.tables.get(table, {}).get("ids", []))

    def counts(self) -> dict[str, int]:
        return {table: len(entry["ids"]) for table, entry in sorted(self.tables.items())}

    def to_dict(self) -> dict:
        return {
            "manifest_version": 1,
            "database": self.database,
            "batch_id": self.batch_id,
            "generator": self.generator,
            "generated_at": self.generated_at,
            "special_accounts": self.special_accounts,
            "demo_user_ids": self.demo_user_ids,
            "counts": self.counts(),
            "tables": self.tables,
            "notes": self.notes,
        }

    def write(self, directory: Path | None = None) -> Path:
        target_dir = Path(directory) if directory else default_manifest_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"seed_manifest_{self.database}_{self.batch_id}.json"
        path = target_dir / filename
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        path.write_text(payload, encoding="utf-8")
        return path


def latest_manifest_for(database: str, directory: Path | None = None) -> Path | None:
    target_dir = Path(directory) if directory else default_manifest_dir()
    if not target_dir.exists():
        return None
    candidates = sorted(
        target_dir.glob(f"seed_manifest_{database}_*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_manifest(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))