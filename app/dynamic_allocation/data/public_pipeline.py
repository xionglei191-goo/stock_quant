from __future__ import annotations

import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from ..config import DynamicAllocationConfig
from ..contracts import PointInTimeObservation, UpsertSummary, ensure_aware
from .public_sources import PublicSourceClient, RawPoint


FRED_SERIES = {
    "high_yield_spread": "BAMLH0A0HYM2",
    "investment_grade_spread": "BAMLC0A0CM",
    "unemployment_rate": "UNRATE",
    "initial_claims": "ICSA",
    "payroll_level": "PAYEMS",
    "cpi_level": "CPIAUCSL",
    "core_cpi_level": "CPILFESL",
    "pce_level": "PCEPI",
    "industrial_production": "INDPRO",
    "fed_balance_sheet": "WALCL",
    "treasury_general_account": "WTREGEN",
    "reverse_repo": "RRPONTSYD",
    "dollar_index": "DTWEXBGS",
    "financial_conditions": "NFCI",
    "treasury_10y": "DGS10",
    "equity_market_value": "BOGZ1FL893064105Q",
}

SOURCE_URIS = {
    "fred": "https://fred.stlouisfed.org/graph/fredgraph.csv",
    "cboe": "https://cdn.cboe.com/api/global/us_indices/daily_prices/",
    "finra": "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx",
    "yahoo": "https://query1.finance.yahoo.com/v8/finance/chart/",
}


@dataclass(frozen=True, slots=True)
class DerivedSeries:
    series_id: str
    points: tuple[RawPoint, ...]
    upstream: tuple[str, ...]
    formula: str
    proxy: bool = False


@dataclass(frozen=True, slots=True)
class PipelineResult:
    fetched_sources: tuple[str, ...]
    source_errors: Mapping[str, str]
    series_counts: Mapping[str, int]
    missing_series: tuple[str, ...]
    observations: tuple[PointInTimeObservation, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "fetched_sources": list(self.fetched_sources),
            "source_errors": dict(self.source_errors),
            "series_counts": dict(self.series_counts),
            "missing_series": list(self.missing_series),
            "observation_count": len(self.observations),
            "paper_only": True,
            "live_execution_allowed": False,
            "broker_connected": False,
        }


class PublicDataPipeline:
    """Build all configured factor inputs from governed, no-key public data."""

    def __init__(self, config: DynamicAllocationConfig, client: PublicSourceClient | None = None):
        self.config = config
        self.client = client or PublicSourceClient()

    def collect(
        self,
        *,
        as_of: datetime | None = None,
        market_start: date = date(2000, 1, 1),
    ) -> PipelineResult:
        acquired_at = _stable_acquisition_time(as_of or datetime.now(timezone.utc))
        end = acquired_at.date()
        market_end = _last_completed_market_date(as_of or datetime.now(timezone.utc))
        jobs = {
            "fred:batch": (self.client.fred_batch, list(FRED_SERIES.values())),
            "cboe:VIX": (self.client.cboe, "VIX"),
            "cboe:VIX3M": (self.client.cboe, "VIX3M"),
            "yahoo:SPY": (self.client.yahoo_adjusted_close, "SPY", market_start, market_end),
            "yahoo:HYG": (self.client.yahoo_adjusted_close, "HYG", market_start, market_end),
            "yahoo:RSP": (self.client.yahoo_adjusted_close, "RSP", market_start, market_end),
            "finra:margin": (self.client.finra_margin_debt,),
        }
        raw: dict[str, list[RawPoint]] = {}
        errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(func, *args): name for name, (func, *args) in jobs.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    response = future.result()
                    if name == "fred:batch":
                        for logical_name, fred_id in FRED_SERIES.items():
                            points = [point for point in response.get(fred_id, ()) if point.observation_date <= end]
                            if points:
                                raw[f"fred:{logical_name}"] = sorted(points, key=lambda item: item.observation_date)
                            else:
                                source_errors = getattr(self.client, "source_errors", {})
                                errors[f"fred:{logical_name}"] = str(
                                    source_errors.get(fred_id, "ValueError: batch returned no usable observations")
                                )
                        continue
                    points = [point for point in response if point.observation_date <= end]
                    if not points:
                        raise ValueError("source returned no usable observations")
                    raw[name] = sorted(points, key=lambda item: item.observation_date)
                except Exception as exc:
                    errors[name] = f"{type(exc).__name__}: {exc}"

        derived = self._derive(raw)
        observations = tuple(
            observation
            for series in derived
            for observation in self._observations(series, acquired_at)
        )
        counts = {series.series_id: len(series.points) for series in derived if series.points}
        missing = tuple(sorted(set(self.config.series) - set(counts)))
        return PipelineResult(
            tuple(sorted(raw)), errors, dict(sorted(counts.items())), missing, observations,
        )

    def ingest(self, repository: Any, **kwargs: Any) -> tuple[PipelineResult, UpsertSummary]:
        result = self.collect(**kwargs)
        return result, repository.upsert(result.observations)

    def ingest_strict(
        self,
        repository: Any,
        **kwargs: Any,
    ) -> tuple[PipelineResult, UpsertSummary]:
        """Collect all governed sources before mutating the strict daily store."""

        result = self.collect(**kwargs)
        if result.missing_series or result.source_errors:
            return result, UpsertSummary(len(result.observations), 0, 0, 0)
        writer = getattr(repository, "upsert_with_revisions", repository.upsert)
        return result, writer(result.observations)

    def _derive(self, raw: Mapping[str, Sequence[RawPoint]]) -> list[DerivedSeries]:
        result: list[DerivedSeries] = []

        def add(series_id: str, points: Iterable[RawPoint], upstream: Sequence[str], formula: str, proxy: bool = False) -> None:
            cleaned = tuple(_month_end([point for point in points if math.isfinite(point.value)]))
            if cleaned and series_id in self.config.series:
                result.append(DerivedSeries(series_id, cleaned, tuple(upstream), formula, proxy))

        spy = list(raw.get("yahoo:SPY", ()))
        hyg = list(raw.get("yahoo:HYG", ()))
        rsp = list(raw.get("yahoo:RSP", ()))
        monthly_spy = _month_end(spy)

        add("price_to_ma_50", _rolling_ratio(spy, 50), ("Yahoo SPY adjusted close",), "SPY / 50-day moving average")
        add("price_to_ma_100", _rolling_ratio(spy, 100), ("Yahoo SPY adjusted close",), "SPY / 100-day moving average")
        add("price_to_ma_200", _rolling_ratio(spy, 200), ("Yahoo SPY adjusted close",), "SPY / 200-day moving average")
        add("return_3m", _period_return(spy, 63), ("Yahoo SPY adjusted close",), "63-session SPY total return")
        add("return_6m", _period_return(spy, 126), ("Yahoo SPY adjusted close",), "126-session SPY total return")
        add("return_12m", _period_return(spy, 252), ("Yahoo SPY adjusted close",), "252-session SPY total return")
        add("distance_from_high", _distance_from_high(spy, 252), ("Yahoo SPY adjusted close",), "SPY / trailing 252-session high - 1")
        add("hyg_return", _period_return(hyg, 63), ("Yahoo HYG adjusted close",), "63-session HYG total return")

        forward_pe = _scaled_price_to_average(monthly_spy, 60, 20.0)
        cape = _scaled_price_to_average(monthly_spy, 120, 20.0)
        earnings_yield = [RawPoint(point.observation_date, 100.0 / point.value) for point in forward_pe if point.value > 0]
        add("forward_pe", forward_pe, ("Yahoo SPY adjusted close",), "20 * SPY / trailing 60-month average; valuation-cycle proxy", True)
        add("cape", cape, ("Yahoo SPY adjusted close",), "20 * SPY / trailing 120-month average; CAPE proxy without earnings revisions", True)
        add("earnings_yield", earnings_yield, ("forward_pe proxy",), "100 / forward_pe proxy", True)
        add("free_cash_flow_yield", [RawPoint(p.observation_date, p.value * 0.8) for p in earnings_yield], ("earnings_yield proxy",), "0.8 * earnings_yield proxy", True)
        rates = list(raw.get("fred:treasury_10y", ()))
        add("equity_risk_premium", _subtract_prior(earnings_yield, rates), ("earnings_yield proxy", "FRED DGS10"), "earnings_yield proxy - 10-year Treasury yield", True)

        vix = list(raw.get("cboe:VIX", ()))
        vix3m = list(raw.get("cboe:VIX3M", ()))
        add("vix_level", vix, ("Cboe VIX",), "VIX close")
        add("vix_change_speed", _period_return(vix, 20), ("Cboe VIX",), "20-session VIX change")
        add("vix_term_structure", _ratio_prior(vix3m, vix), ("Cboe VIX3M", "Cboe VIX"), "VIX3M / VIX")

        for output, fred_name in (
            ("high_yield_spread", "high_yield_spread"),
            ("investment_grade_spread", "investment_grade_spread"),
            ("unemployment_rate", "unemployment_rate"),
            ("initial_claims", "initial_claims"),
            ("fed_balance_sheet", "fed_balance_sheet"),
            ("treasury_general_account", "treasury_general_account"),
            ("reverse_repo", "reverse_repo"),
            ("dollar_index", "dollar_index"),
            ("financial_conditions", "financial_conditions"),
        ):
            fred_id = FRED_SERIES[fred_name]
            add(output, raw.get(f"fred:{fred_name}", ()), (f"FRED {fred_id}",), f"direct {fred_id} observation")

        add("payroll_growth", _year_over_year(raw.get("fred:payroll_level", ()), 12), ("FRED PAYEMS",), "PAYEMS year-over-year percent change")
        add("cpi", _year_over_year(raw.get("fred:cpi_level", ()), 12), ("FRED CPIAUCSL",), "CPIAUCSL year-over-year percent change")
        add("core_cpi", _year_over_year(raw.get("fred:core_cpi_level", ()), 12), ("FRED CPILFESL",), "CPILFESL year-over-year percent change")
        add("pce", _year_over_year(raw.get("fred:pce_level", ()), 12), ("FRED PCEPI",), "PCEPI year-over-year percent change")
        industrial = list(raw.get("fred:industrial_production", ()))
        add("pmi", _growth_diffusion_proxy(industrial, 3), ("FRED INDPRO",), "50 + annualized 3-month INDPRO growth; PMI proxy", True)
        add("ism", _growth_diffusion_proxy(industrial, 12), ("FRED INDPRO",), "50 + year-over-year INDPRO growth; ISM manufacturing proxy", True)

        debt = list(raw.get("finra:margin", ()))
        market_value = list(raw.get("fred:equity_market_value", ()))
        add("margin_debt_level", debt, ("FINRA customer margin balances",), "debit balances in customer securities margin accounts, USD millions")
        add("margin_debt_to_market_cap", _ratio_prior(debt, market_value), ("FINRA margin debt", "FRED BOGZ1FL893064105Q"), "FINRA margin debt / US equity market value")
        add("margin_debt_growth", _year_over_year(debt, 12), ("FINRA margin debt",), "margin debt year-over-year percent change")
        add("deleveraging_speed", _period_return(debt, 1), ("FINRA margin debt",), "margin debt month-over-month change")

        add("stocks_above_200ma", _rolling_ratio(rsp, 200), ("Yahoo RSP adjusted close",), "RSP / 200-day average; equal-weight breadth proxy", True)
        add("new_highs_lows", _distance_from_high(rsp, 252), ("Yahoo RSP adjusted close",), "RSP distance from trailing high; new-highs/new-lows proxy", True)
        add("advance_decline", _relative_return(rsp, spy, 20), ("Yahoo RSP", "Yahoo SPY"), "20-session RSP return minus SPY return; advance/decline proxy", True)
        return result

    def _observations(self, series: DerivedSeries, acquired_at: datetime) -> list[PointInTimeObservation]:
        definition = self.config.series[series.series_id]
        upstream_text = "|".join(series.upstream).lower()
        source_uri = (
            SOURCE_URIS["finra"] if "finra" in upstream_text else
            SOURCE_URIS["cboe"] if "cboe" in upstream_text else
            SOURCE_URIS["fred"] if "fred" in upstream_text else
            SOURCE_URIS["yahoo"]
        )
        rights = {
            "access": "public-no-key",
            "automation_allowed": True,
            "training_allowed": False,
            "paper_research_only": True,
            "vintage_method": "current-vintage-backfill",
            "release_date_method": "local-acquisition-date",
            "backtest_eligible": False,
            "proxy": series.proxy,
            "formula": series.formula,
            "upstream": list(series.upstream),
            "storage_sampling": "monthly-last-plus-current",
        }
        observations = []
        for point in series.points:
            material = {
                "series_id": series.series_id,
                "observation_date": point.observation_date.isoformat(),
                "value": round(point.value, 12),
                "source_id": definition.source_id,
                "source_uri": source_uri,
                "rights_tag": rights,
                "vintage_date": acquired_at.date().isoformat(),
            }
            payload_hash = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            observations.append(PointInTimeObservation(
                observation_id=f"dyn-{payload_hash[:24]}",
                series_id=series.series_id,
                observation_date=point.observation_date,
                value=point.value,
                release_date=acquired_at.date(),
                available_at=acquired_at,
                vintage_date=acquired_at.date(),
                revision_seq=0,
                source_id=definition.source_id,
                source_uri=source_uri,
                ingested_at=acquired_at,
                rights_tag=rights,
                quality_flags=(),
                payload_hash=payload_hash,
            ))
        return observations


def _stable_acquisition_time(value: datetime) -> datetime:
    aware = ensure_aware(value, "as_of")
    return datetime.combine(aware.date(), datetime.min.time(), timezone.utc)


def _last_completed_market_date(value: datetime) -> date:
    local = ensure_aware(value, "as_of").astimezone(ZoneInfo("America/New_York"))
    if (local.hour, local.minute) < (16, 15):
        return local.date() - timedelta(days=1)
    return local.date()


def _month_end(points: Sequence[RawPoint]) -> list[RawPoint]:
    result: dict[tuple[int, int], RawPoint] = {}
    for point in points:
        result[(point.observation_date.year, point.observation_date.month)] = point
    return list(result.values())


def _rolling_ratio(points: Sequence[RawPoint], periods: int) -> list[RawPoint]:
    return [RawPoint(points[i].observation_date, points[i].value / _mean(points[i-periods+1:i+1])) for i in range(periods - 1, len(points)) if _mean(points[i-periods+1:i+1])]


def _scaled_price_to_average(points: Sequence[RawPoint], periods: int, scale: float) -> list[RawPoint]:
    return [RawPoint(points[i].observation_date, scale * points[i].value / _mean(points[i-periods+1:i+1])) for i in range(periods - 1, len(points)) if _mean(points[i-periods+1:i+1])]


def _period_return(points: Sequence[RawPoint], periods: int) -> list[RawPoint]:
    return [RawPoint(points[i].observation_date, points[i].value / points[i-periods].value - 1.0) for i in range(periods, len(points)) if points[i-periods].value]


def _distance_from_high(points: Sequence[RawPoint], periods: int) -> list[RawPoint]:
    return [RawPoint(points[i].observation_date, points[i].value / max(item.value for item in points[i-periods+1:i+1]) - 1.0) for i in range(periods - 1, len(points))]


def _year_over_year(points: Sequence[RawPoint], periods: int) -> list[RawPoint]:
    items = list(points)
    return [RawPoint(items[i].observation_date, (items[i].value / items[i-periods].value - 1.0) * 100.0) for i in range(periods, len(items)) if items[i-periods].value]


def _growth_diffusion_proxy(points: Sequence[RawPoint], periods: int) -> list[RawPoint]:
    items = list(points)
    annualizer = 12.0 / periods
    return [RawPoint(items[i].observation_date, max(0.0, min(100.0, 50.0 + (items[i].value / items[i-periods].value - 1.0) * 100.0 * annualizer))) for i in range(periods, len(items)) if items[i-periods].value]


def _prior_values(points: Sequence[RawPoint], references: Sequence[RawPoint]) -> Iterable[tuple[RawPoint, RawPoint]]:
    refs = sorted(references, key=lambda item: item.observation_date)
    index = -1
    for point in sorted(points, key=lambda item: item.observation_date):
        while index + 1 < len(refs) and refs[index + 1].observation_date <= point.observation_date:
            index += 1
        if index >= 0:
            yield point, refs[index]


def _ratio_prior(numerators: Sequence[RawPoint], denominators: Sequence[RawPoint]) -> list[RawPoint]:
    return [RawPoint(left.observation_date, left.value / right.value) for left, right in _prior_values(numerators, denominators) if right.value]


def _subtract_prior(points: Sequence[RawPoint], references: Sequence[RawPoint]) -> list[RawPoint]:
    return [RawPoint(left.observation_date, left.value - right.value) for left, right in _prior_values(points, references)]


def _relative_return(left: Sequence[RawPoint], right: Sequence[RawPoint], periods: int) -> list[RawPoint]:
    left_returns = {point.observation_date: point.value for point in _period_return(left, periods)}
    right_returns = {point.observation_date: point.value for point in _period_return(right, periods)}
    return [RawPoint(day, left_returns[day] - right_returns[day]) for day in sorted(left_returns.keys() & right_returns.keys())]


def _mean(points: Sequence[RawPoint]) -> float:
    return sum(point.value for point in points) / len(points) if points else 0.0
