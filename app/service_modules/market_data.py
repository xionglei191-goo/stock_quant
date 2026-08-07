from __future__ import annotations

from datetime import date
from typing import Any, Protocol

# 市场 → EOD 取数源。`market_freshness`（`scripts/daily_market_insight.py` 的
# `market_targets`）与公司情报视图（`SystemService._latest_market_data_point`）必须
# 经同一映射解析 `(market, source_id, data_type)`，否则会出现实测问题：市场 EOD 报
# 2026-07-24 / 2026-07-27，公司活动条目 `latest_market.as_of_date=2026-05-25`，两者
# 并列展示且无解释（需求 5.6、5.7；设计 §4.9）。
# A 市场取值与 `app/services.py` 的 `PUBLIC_EOD_MARKET_DATA_SOURCE_ID` 一致，
# U 市场取值与 `scripts/daily_market_insight.py` 的 `DEFAULT_SOURCE_U` 一致。
MARKET_EOD_SOURCES: dict[str, str] = {
    "A": "public_eod_market_data",
    "U": "yahoo_chart_us_eod",
}

# 未登记市场（含空串与 H 股）回落到 A 市场公开 EOD 源，沿用
# `SystemService._market_data_source_for_market`（`app/services.py:7420`）里“非 U 市场
# 一律走 PUBLIC_EOD_MARKET_DATA_SOURCE_ID”的既有行为，避免接线时改变取数结果。
DEFAULT_EOD_SOURCE_ID = MARKET_EOD_SOURCES["A"]

DEFAULT_EOD_DATA_TYPE = "eod"

# `freshness_lag` 在 `lag_days > 0` 时必须给出其中之一（需求 5.7；设计 §4.9）。
FRESHNESS_REASON_CODES = (
    "security_not_in_latest_eod_batch",
    "security_suspended_or_delisted",
    "source_partial_coverage",
)

# 滞后原因码的中文文案，公司情报视图、每日摘要 Markdown 与 UI 共用同一套措辞
# （需求 5.7；设计 §4.9）。`freshness_lag` 的返回结构保持三键不变，文案通过
# `freshness_reason_label` / `market_freshness_annotation` 单独取用。
FRESHNESS_REASON_LABELS: dict[str, str] = {
    "security_not_in_latest_eod_batch": "该证券未进入最新一批 EOD 行情",
    "security_suspended_or_delisted": "该证券已停牌或退市",
    "source_partial_coverage": "行情源当批覆盖不全",
}

# 证券活跃口径沿用 `app/services.py` 既有的 `security.status == "active"` 判定
# （:6796、:7180）；`Security.status` 无枚举校验，因此这里只把“非空且非 active”
# 视为停牌/退市信号，空串按未知处理、不参与判定。
ACTIVE_SECURITY_STATUSES = ("active",)

# 市场侧批次覆盖率低于该阈值时，滞后归因到源覆盖不全而非单只证券。
# 与 `completeness_policy.LAYER_COVERAGE_THRESHOLDS` 的 0.9 保持同一量级。
SOURCE_COVERAGE_THRESHOLD = 0.9


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


def market_eod_key(market: str, *, data_type: str = DEFAULT_EOD_DATA_TYPE, source_id: str = "") -> dict[str, str]:
    """返回 `{"market", "source_id", "data_type"}`；`market_freshness` 与公司视图共用。

    结构与 `scripts/daily_market_insight.py:1259-1268` 现有 `market_targets` 条目一致，
    因此该脚本的 `market_targets` 与公司侧 `_latest_market_data_point` 的取数键可以由
    同一函数产出（需求 5.6）。

    解析规则：

    - `market` 归一为去空白大写；未登记市场（含空串、`H`）回落 `DEFAULT_EOD_SOURCE_ID`。
    - `source_id` 非空时按调用方显式覆盖优先，用于保留既有覆盖通路：
      `scripts/daily_market_insight.py` 的 `--source-a` / `--source-u` 参数与
      `SystemService._market_data_source_for_market` 的 `ashare_source_id` /
      `us_source_id` / `source_id` 请求字段。覆盖值不做别名归一，调用方若需要
      `SOURCE_ID_ALIASES` 归一应先自行处理（`app/services.py:154`）。
    - `data_type` 为空时回落 `DEFAULT_EOD_DATA_TYPE`。
    """

    normalized_market = str(market or "").strip().upper()
    override = str(source_id or "").strip()
    return {
        "market": normalized_market,
        "source_id": override or MARKET_EOD_SOURCES.get(normalized_market, DEFAULT_EOD_SOURCE_ID),
        "data_type": str(data_type or "").strip() or DEFAULT_EOD_DATA_TYPE,
    }


def _iso_date(value: Any) -> date | None:
    """把日期字符串解析为 `date`；无法解析返回 None（容忍带时间部分的输入）。"""

    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text, text.replace("T", " ").split(" ")[0]):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _coverage_ratio(value: Any) -> float | None:
    """把市场批次覆盖率归一到 [0, 1]；无法解析或 NaN 返回 None（该信号不参与判定）。"""

    if value is None:
        return None
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return None
    if ratio != ratio:  # NaN
        return None
    return max(0.0, min(1.0, ratio))


def _freshness_reason_code(*, security_status: str, source_coverage_ratio: Any) -> str:
    """滞后原因码的默认推断规则，返回值必属 `FRESHNESS_REASON_CODES`。

    判定依据与优先级（前者命中即返回）：

    1. `security_suspended_or_delisted`：`security_status` 非空且不在
       `ACTIVE_SECURITY_STATUSES` 中。调用方传 `Security.status` 即可区分；
       停牌/退市对该证券是持续性解释，优先级最高。
    2. `source_partial_coverage`：`source_coverage_ratio` 可解析且低于
       `SOURCE_COVERAGE_THRESHOLD`。调用方传市场侧批次覆盖率
       （如 `market_data_backfill_coverage` 的 `coverage`，即
       `covered_count / security_count`）即可区分；这是市场级系统性缺口。
    3. `security_not_in_latest_eod_batch`：默认值。证券本身活跃、市场批次覆盖率
       正常或未提供时，滞后只能解释为该证券未进入最新一批 EOD 数据。
    """

    status = str(security_status or "").strip().lower()
    if status and status not in ACTIVE_SECURITY_STATUSES:
        return "security_suspended_or_delisted"
    ratio = _coverage_ratio(source_coverage_ratio)
    if ratio is not None and ratio < SOURCE_COVERAGE_THRESHOLD:
        return "source_partial_coverage"
    return "security_not_in_latest_eod_batch"


def freshness_lag(
    *,
    company_as_of_date: str,
    market_eod_date: str,
    security_status: str = "",
    source_coverage_ratio: float | None = None,
) -> dict[str, Any]:
    """返回 `{"lag_days", "reason_code", "is_lagging"}`（需求 5.7；设计 §4.9）。

    - `lag_days` 为精确日历差 `market_eod_date - company_as_of_date`（自然日，不跳过
      非交易日），因此实测的 `2026-05-25` 对市场 EOD `2026-07-24` 得 60。
    - `lag_days > 0` → `is_lagging=True`，`reason_code` 属 `FRESHNESS_REASON_CODES`，
      由 `_freshness_reason_code` 按可选信号推断（见该函数 docstring）。
    - `lag_days == 0` → `reason_code=""`、`is_lagging=False`。
    - 公司日期晚于市场 EOD 日期时 `lag_days` 为负（保留精确差值供调用方发现异常），
      同样按“不滞后”处理：`reason_code=""`、`is_lagging=False`。
    - 任一日期缺失或无法解析（例如公司尚无任何本地行情）时返回
      `lag_days=0`、`reason_code=""`、`is_lagging=False`；这种情况不是滞后，调用方应
      单独呈现“行情待补”，不要据此标注滞后天数。

    `security_status` 与 `source_coverage_ratio` 为可选信号，缺省时按默认推断规则
    落到 `security_not_in_latest_eod_batch`，因此只传两个必填日期也可用。
    """

    company_date = _iso_date(company_as_of_date)
    market_date = _iso_date(market_eod_date)
    if company_date is None or market_date is None:
        return {"lag_days": 0, "reason_code": "", "is_lagging": False}
    lag_days = (market_date - company_date).days
    if lag_days <= 0:
        return {"lag_days": lag_days, "reason_code": "", "is_lagging": False}
    return {
        "lag_days": lag_days,
        "reason_code": _freshness_reason_code(
            security_status=security_status,
            source_coverage_ratio=source_coverage_ratio,
        ),
        "is_lagging": True,
    }


def freshness_reason_label(reason_code: str) -> str:
    """把滞后原因码翻译为中文文案；空串或未登记原因码返回空串（调用方则不展示说明）。"""

    return FRESHNESS_REASON_LABELS.get(str(reason_code or "").strip(), "")


def market_freshness_annotation(
    *,
    market: str,
    company_as_of_date: str,
    market_eod_date: str,
    data_type: str = DEFAULT_EOD_DATA_TYPE,
    source_id: str = "",
    security_status: str = "",
    source_coverage_ratio: float | None = None,
) -> dict[str, Any]:
    """公司视图的滞后标注：把 `market_eod_key` 的三元键与 `freshness_lag` 的判定合并输出。

    这是需求 5.6 与 5.7 的唯一组合入口：调用方（`app/services.py` 的公司情报与
    行情覆盖报告、`scripts/daily_market_insight.py` 的公司活动条目）只负责取数与
    透传，市场→源解析、滞后天数与原因码判定都留在本模块。

    返回键：`market` / `source_id` / `data_type`（与 `market_freshness` 同键）、
    `company_as_of_date` / `market_eod_date`（并列展示的两个日期）、
    `lag_days` / `reason_code` / `reason_label` / `is_lagging`（滞后标注）。
    """

    key = market_eod_key(market, data_type=data_type, source_id=source_id)
    lag = freshness_lag(
        company_as_of_date=company_as_of_date,
        market_eod_date=market_eod_date,
        security_status=security_status,
        source_coverage_ratio=source_coverage_ratio,
    )
    return {
        **key,
        "company_as_of_date": str(company_as_of_date or ""),
        "market_eod_date": str(market_eod_date or ""),
        **lag,
        "reason_label": freshness_reason_label(lag["reason_code"]),
    }
