from __future__ import annotations

from dataclasses import dataclass

from .models import SelectedStock, StockAsset, StockVariant


class StockSelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class OutputGeometry:
    width: int
    height: int

    @property
    def orientation(self) -> str:
        return "landscape" if self.width >= self.height else "portrait"


class StockSelector:
    """Prefer exact output size, then the nearest adequate variant, without a 4K bias."""

    @staticmethod
    def _variant_rank(variant: StockVariant, target: OutputGeometry) -> tuple[float, ...]:
        exact = variant.width == target.width and variant.height == target.height
        adequate = variant.width >= target.width and variant.height >= target.height
        same_orientation = (variant.width >= variant.height) == (target.width >= target.height)
        target_ratio = target.width / target.height
        ratio_error = abs((variant.width / variant.height) - target_ratio)
        area_delta = abs(variant.width * variant.height - target.width * target.height)
        tier = 0 if exact else 1 if adequate and same_orientation else 2 if same_orientation else 3
        return (tier, ratio_error, area_delta)

    def best_variant(self, asset: StockAsset, target: OutputGeometry) -> StockVariant | None:
        variants = [item for item in asset.variants if item.url and item.width > 0 and item.height > 0]
        return min(variants, key=lambda item: self._variant_rank(item, target)) if variants else None

    def select_candidate(
        self,
        assets: list[StockAsset],
        *,
        target: OutputGeometry,
        minimum_duration: float,
        used_ids: set[int] | None = None,
    ) -> SelectedStock:
        used = used_ids or set()
        ranked: list[tuple[tuple[float, ...], StockAsset, StockVariant]] = []
        for asset in assets:
            if asset.duration + 1e-6 < minimum_duration:
                continue
            variant = self.best_variant(asset, target)
            if variant is None:
                continue
            repeat_penalty = 1 if asset.asset_id in used else 0
            ranked.append(((repeat_penalty, *self._variant_rank(variant, target)), asset, variant))
        if not ranked:
            raise StockSelectionError(
                f"No stock candidate is long enough for a {minimum_duration:.3f}s timeline slot"
            )
        _, asset, variant = min(ranked, key=lambda item: item[0])
        return SelectedStock(asset, variant)
