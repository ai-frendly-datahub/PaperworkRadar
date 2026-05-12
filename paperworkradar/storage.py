from __future__ import annotations

from pathlib import Path

from radar_core.exceptions import StorageError
from radar_core.storage import RadarStorage as _BaseRadarStorage

from .date_storage import cleanup_date_directories, snapshot_database


class RadarStorage(_BaseRadarStorage):
    """PaperworkRadar storage with daily-snapshot helpers."""

    def create_daily_snapshot(self, snapshot_dir: str | None = None) -> Path | None:
        target = Path(snapshot_dir) if snapshot_dir else None
        return snapshot_database(self.db_path, snapshot_root=target)

    def cleanup_old_snapshots(self, keep_days: int = 30) -> int:
        snapshot_root = self.db_path.parent / "daily"
        return cleanup_date_directories(snapshot_root, keep_days=keep_days)


__all__ = ["RadarStorage", "StorageError"]
