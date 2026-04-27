from __future__ import annotations

from pathlib import Path

from radar_core.exceptions import StorageError
from radar_core.storage import RadarStorage as _RadarStorage

from .date_storage import cleanup_date_directories, snapshot_database


class RadarStorage(_RadarStorage):
    def create_daily_snapshot(self, snapshot_dir: str | None = None):
        snapshot_root = Path(snapshot_dir) if snapshot_dir else self.db_path.parent / "daily"
        return snapshot_database(self.db_path, snapshot_root=snapshot_root)

    def cleanup_old_snapshots(self, keep_days: int) -> int:
        return cleanup_date_directories(self.db_path.parent / "daily", keep_days=keep_days)


__all__ = ["RadarStorage", "StorageError"]
