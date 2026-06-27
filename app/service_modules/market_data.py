from __future__ import annotations

from typing import Protocol


class CorporateActionLike(Protocol):
    action_id: str
    action_type: str
    ex_date: str
    ratio: float
    cash_amount: float


class MarketDataPointLike(Protocol):
    as_of_date: str


def corporate_action_price_factor(action: CorporateActionLike, *, adjustment_mode: str) -> float:
    ratio = float(action.ratio or 1.0)
    if ratio <= 0:
        return 1.0
    if action.action_type == "split":
        return (1.0 / ratio) if adjustment_mode == "backward" else ratio
    if action.action_type == "reverse_split":
        return ratio if adjustment_mode == "backward" else (1.0 / ratio)
    if action.action_type == "stock_dividend":
        base = 1.0 + ratio
        return (1.0 / base) if adjustment_mode == "backward" else base
    return 1.0


def market_data_adjustment_factor(
    point: MarketDataPointLike,
    actions: list[CorporateActionLike],
    *,
    adjustment_mode: str,
) -> tuple[float, list[str]]:
    if adjustment_mode == "raw":
        return 1.0, []
    factor = 1.0
    event_ids: list[str] = []
    for action in actions:
        applies = action.ex_date > point.as_of_date if adjustment_mode == "backward" else action.ex_date <= point.as_of_date
        if not applies:
            continue
        event_factor = corporate_action_price_factor(action, adjustment_mode=adjustment_mode)
        if event_factor == 1.0:
            continue
        factor *= event_factor
        event_ids.append(action.action_id)
    return factor, event_ids
