"""Physically separated expanding-window prediction orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .engine import BacktestEngine, BacktestResult


@dataclass(frozen=True)
class WalkForwardFold:
    train_start: object
    train_end: object
    test_start: object
    test_end: object
    train_count: int
    test_count: int


@dataclass(frozen=True)
class WalkForwardResult:
    backtest: BacktestResult
    folds: tuple[WalkForwardFold, ...]


class WalkForwardBacktester:
    def __init__(self, engine: BacktestEngine | None = None) -> None:
        self.engine = engine or BacktestEngine()

    def run(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        train_size: int,
        test_size: int,
        fit: Callable[[tuple[Mapping[str, object], ...]], Callable[[Mapping[str, object]], float]],
    ) -> WalkForwardResult:
        if train_size < 1 or test_size < 1:
            raise ValueError("train_size and test_size must be positive")
        source = list(rows)
        predicted: list[dict[str, object]] = []
        folds: list[WalkForwardFold] = []
        start = train_size
        while start < len(source):
            train = tuple(source[:start])
            test = source[start : min(start + test_size, len(source))]
            predictor = fit(train)
            train_end = self.engine._date(train[-1])
            test_start = self.engine._date(test[0])
            if train_end >= test_start:
                raise ValueError("walk-forward train and test windows overlap or are not chronological")
            for row in test:
                enriched = dict(row)
                enriched["target_equity_weight"] = float(predictor(row))
                predicted.append(enriched)
            folds.append(WalkForwardFold(
                self.engine._date(train[0]), train_end, test_start, self.engine._date(test[-1]), len(train), len(test)
            ))
            start += test_size
        if not predicted:
            raise ValueError("insufficient observations for a walk-forward test window")
        return WalkForwardResult(self.engine.run(predicted), tuple(folds))
