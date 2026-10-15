from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StockVariant:
    url: str
    width: int
    height: int
    fps: float | None = None
    file_type: str = "video/mp4"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StockVariant":
        return cls(
            url=str(value["url"]),
            width=int(value["width"]),
            height=int(value["height"]),
            fps=float(value["fps"]) if value.get("fps") else None,
            file_type=str(value.get("file_type") or "video/mp4"),
        )


@dataclass(frozen=True)
class StockAsset:
    asset_id: int
    query: str
    duration: float
    variants: tuple[StockVariant, ...]
    page_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StockAsset":
        return cls(
            asset_id=int(value["asset_id"]),
            query=str(value["query"]),
            duration=float(value["duration"]),
            variants=tuple(StockVariant.from_dict(item) for item in value["variants"]),
            page_url=value.get("page_url"),
        )


@dataclass(frozen=True)
class SelectedStock:
    asset: StockAsset
    variant: StockVariant


@dataclass(frozen=True)
class LocalStock:
    selection: SelectedStock
    path: Path
