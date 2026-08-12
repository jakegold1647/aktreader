"""Portable access to the Application's small implicit runtime contracts."""

from __future__ import annotations

import atexit
from contextlib import ExitStack
from dataclasses import dataclass
from functools import cache
from importlib.resources import as_file, files
from pathlib import Path, PurePosixPath
from typing import Any


class RuntimeAssetError(ValueError):
    """Raised when a declared packaged runtime asset is unavailable."""


@dataclass(frozen=True)
class RuntimeAsset:
    """One small public contract read implicitly by a portable command."""

    name: str
    package_path: str


RUNTIME_ASSETS = (
    RuntimeAsset("act_record_schema", "schemas/act-record-2.0.0.schema.json"),
    RuntimeAsset("model_output_schema", "schemas/model-output-1.0.0.schema.json"),
    RuntimeAsset(
        "model_output_gold_map",
        "schemas/model-output-to-gold-map-1.0.0.json",
    ),
)

_ASSET_CONTEXTS = ExitStack()
atexit.register(_ASSET_CONTEXTS.close)


@cache
def runtime_asset_path(package_path: str) -> Path:
    """Materialize one declared package resource for path-based consumers."""
    relative = PurePosixPath(package_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeAssetError(f"invalid runtime asset path: {package_path!r}")
    resource = files(__name__).joinpath(*relative.parts)
    if not resource.is_file():
        raise RuntimeAssetError(f"packaged runtime asset is missing: {package_path}")
    return Path(_ASSET_CONTEXTS.enter_context(as_file(resource)))


def inspect_packaged_runtime_assets() -> dict[str, Any]:
    """Report whether every implicit runtime contract is available."""
    assets: dict[str, dict[str, Any]] = {}
    for asset in RUNTIME_ASSETS:
        try:
            path = runtime_asset_path(asset.package_path)
        except RuntimeAssetError:
            available = False
            size_bytes = None
        else:
            available = path.is_file()
            size_bytes = path.stat().st_size if available else None
        assets[asset.name] = {
            "package_path": asset.package_path,
            "available": available,
            "size_bytes": size_bytes,
        }
    missing = [
        details["package_path"]
        for details in assets.values()
        if not details["available"]
    ]
    return {
        "runtime_asset_count": len(RUNTIME_ASSETS),
        "available_runtime_asset_count": len(RUNTIME_ASSETS) - len(missing),
        "runtime_assets_available": not missing,
        "missing_runtime_assets": missing,
        "runtime_assets": assets,
    }
