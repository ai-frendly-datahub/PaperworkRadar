from __future__ import annotations

import sys
from importlib import import_module


_MODULE_ALIASES = {
    "analyzer": "paperworkradar.analyzer",
    "collector": "paperworkradar.collector",
    "exceptions": "paperworkradar.exceptions",
    "models": "paperworkradar.models",
    "nl_query": "paperworkradar.nl_query",
    "search_index": "paperworkradar.search_index",
    "storage": "paperworkradar.storage",
}

for _module_name, _target in _MODULE_ALIASES.items():
    sys.modules[f"{__name__}.{_module_name}"] = import_module(_target)


RadarStorage = import_module("paperworkradar.storage").RadarStorage


__all__ = ["RadarStorage"]
