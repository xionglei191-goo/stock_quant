"""Streamlit entrypoint for the API-backed dynamic allocation dashboard."""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path
from typing import Any, Mapping

import plotly.graph_objects as go
import streamlit as st

REPOSITORY_ROOT = str(Path(__file__).resolve().parents[3])
if REPOSITORY_ROOT in sys.path:
    sys.path.remove(REPOSITORY_ROOT)
sys.path.insert(0, REPOSITORY_ROOT)

from app.dynamic_allocation.dashboard.api_client import (  # noqa: E402
    DynamicAllocationApiClient,
    DynamicAllocationApiError,
)
from app.dynamic_allocation.dashboard.presentation import (  # noqa: E402
    CurrentView,
    as_number,
    first,
    normalize_backtest,
    normalize_backtest_runs,
    normalize_current,
    normalize_health,
    normalize_history,
)


REGIME_COLORS = {
    "Risk On": "#0f8a5f",
    "Recovery": "#2563eb",
    "Late Cycle": "#a86500",
    "Risk Off": "#c2413d",
    "Crisis": "#991b1b",
}


def _env(name: str, default: str) -> str:
    return str(os.environ.get(name, default)).strip() or default


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_dashboard_bundle(
    base_url: str,
    actor: str,
    role: str,
    token: str,
    history_limit: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    client = DynamicAllocationApiClient(base_url, actor=actor, role=role, token=token)
    return (
        client.get_current(),
        client.get_history(limit=history_limit),
        client.get_data_health(),
        client.get_backtests(limit=50),
    )


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_backtest(base_url: str, actor: str, role: str, token: str, run_id: str) -> dict[str, Any]:
    client = DynamicAllocationApiClient(base_url, actor=actor, role=role, token=token)
    return client.get_backtest(run_id)


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def _metric_value(metrics: Mapping[str, Any], *keys: str, percent: bool = False) -> str:
    value = first(metrics, *keys)
    number = as_number(value)
    if number is None:
        return str(value) if value not in {None, ""} else "-"
    if percent:
        normalized = number / 100 if abs(number) > 1 else number
        return f"{normalized:.1%}"
    return f"{number:.2f}"


def _apply_style() -> None:
    st.markdown(
        """
        <style>
          :root { color-scheme: light; }
          .stApp { background: #f7f8fa; color: #111827; }
          .block-container { max-width: 1320px; padding-top: 1.25rem; padding-bottom: 3rem; }
          h1, h2, h3, p, label, [data-testid="stMetricLabel"] { letter-spacing: 0 !important; }
          h1 { font-size: 1.65rem !important; line-height: 1.25 !important; }
          h2 { font-size: 1.1rem !important; margin-top: 1.3rem !important; }
          h3 { font-size: .95rem !important; }
          [data-testid="stMetric"] {
            min-height: 112px;
            padding: 14px 16px;
            border: 1px solid #e1e6ee;
            border-radius: 8px;
            background: #ffffff;
          }
          [data-testid="stMetricValue"] { font-size: 1.65rem; }
          [data-testid="stSidebar"] { border-right: 1px solid #e1e6ee; background: #fbfcfd; }
          .boundary-strip {
            display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
            padding: 8px 0 14px; color: #5b6676; font-size: 13px;
          }
          .boundary-strip span { min-width: 0; max-width: 100%; overflow-wrap: anywhere; }
          .boundary-badge {
            display: inline-flex; min-height: 26px; align-items: center; padding: 0 9px;
            border: 1px solid #c7ead8; border-radius: 8px; background: #eefbf4;
            color: #0f8a5f; font-weight: 700;
          }
          .source-meta { color: #5b6676; font-size: 12px; overflow-wrap: anywhere; }
          .factor-row {
            display: grid; grid-template-columns: minmax(92px, 1fr) minmax(160px, 4fr) 56px;
            gap: 12px; align-items: center; padding: 8px 0;
          }
          .factor-track { height: 9px; overflow: hidden; border-radius: 5px; background: #e9edf3; }
          .factor-fill { height: 100%; background: #2563eb; }
          .factor-score { text-align: right; font-variant-numeric: tabular-nums; font-weight: 700; }
          .empty-state {
            padding: 18px; border: 1px dashed #c9d2df; border-radius: 8px;
            background: #ffffff; color: #5b6676;
          }
          div[data-testid="stPlotlyChart"] { border: 1px solid #e1e6ee; border-radius: 8px; background: #fff; }
          button:focus-visible, input:focus-visible { outline: 3px solid rgba(37,99,235,.2) !important; }
          @media (max-width: 640px) {
            .block-container { padding-left: .8rem; padding-right: .8rem; }
            .factor-row { grid-template-columns: 80px minmax(100px, 1fr) 44px; gap: 8px; }
            [data-testid="stMetric"] { min-height: 96px; padding: 10px 12px; }
            [data-testid="stMetricValue"] { font-size: 1.3rem; }
          }
          @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _empty(message: str) -> None:
    st.markdown(f'<div class="empty-state">{message}</div>', unsafe_allow_html=True)


def _render_header(current: CurrentView) -> None:
    title_col, asof_col = st.columns([3, 1])
    with title_col:
        st.title("动态资产配置与风险控制")
    with asof_col:
        st.caption("数据时点")
        st.markdown(f"**{current.as_of}**")
    boundary_ok = current.paper_only and not current.live_execution_allowed and not current.broker_connected
    boundary_text = "仅研究 / 纸面模拟" if boundary_ok else "边界异常"
    badge_class = "boundary-badge"
    st.markdown(
        f'<div class="boundary-strip"><span class="{badge_class}">{boundary_text}</span>'
        f'<span>配置 {html.escape(current.config_hash, quote=True)}</span>'
        f'<span>数据 freshness: {html.escape(current.freshness, quote=True)}</span></div>',
        unsafe_allow_html=True,
    )
    if not boundary_ok:
        st.error("纸面模拟边界校验失败。已停止展示仓位解释，请检查 API 响应。", icon=":material/error:")


def _render_summary(current: CurrentView) -> None:
    columns = st.columns(4)
    regime_color = REGIME_COLORS.get(current.regime, "#5b6676")
    with columns[0]:
        st.metric("市场状态", current.regime)
        st.markdown(f'<div style="height:3px;background:{regime_color};border-radius:2px"></div>', unsafe_allow_html=True)
    columns[1].metric("目标股票仓位", _pct(current.equity_allocation))
    sgov = current.allocations.get("SGOV")
    if sgov is None and current.equity_allocation is not None:
        sgov = max(0.0, 1.0 - current.equity_allocation)
    columns[2].metric("SGOV 仓位", _pct(sgov))
    columns[3].metric("可用因子", f"{sum(item.score is not None for item in current.factors)}/{len(current.factors) or 8}")

    if current.allocations:
        allocation_fig = go.Figure(
            go.Bar(
                x=list(current.allocations.keys()),
                y=[value * 100 for value in current.allocations.values()],
                marker_color=["#2563eb" if key != "SGOV" else "#0f8a5f" for key in current.allocations],
                text=[f"{value:.0%}" for value in current.allocations.values()],
                textposition="outside",
                hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
            )
        )
        allocation_fig.update_layout(
            title="目标资产权重",
            height=300,
            margin=dict(l=20, r=20, t=55, b=30),
            yaxis=dict(title="仓位 (%)", range=[0, 105], gridcolor="#e9edf3"),
            xaxis_title="",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font=dict(family="Inter, system-ui, sans-serif", color="#111827"),
            showlegend=False,
        )
        st.plotly_chart(allocation_fig, width="stretch", config={"displayModeBar": False})


def _render_factors(current: CurrentView) -> None:
    st.subheader("因子评分")
    if not current.factors:
        _empty("当前 API 未返回因子结果。")
        return
    for factor in current.factors:
        score = factor.score
        width = max(0.0, min(100.0, score or 0.0))
        score_text = "缺失" if score is None else f"{score:.0f}"
        escaped_label = html.escape(factor.label, quote=True)
        st.markdown(
            f'<div class="factor-row"><strong>{escaped_label}</strong>'
            f'<div class="factor-track" title="{escaped_label} {score_text}"><div class="factor-fill" style="width:{width:.1f}%"></div></div>'
            f'<div class="factor-score">{score_text}</div></div>',
            unsafe_allow_html=True,
        )
        detail_label = f"{factor.label}明细 · coverage {factor.coverage:.0f}% · {factor.freshness}" if factor.coverage is not None else f"{factor.label}明细 · {factor.freshness}"
        with st.expander(detail_label):
            if factor.warnings:
                st.warning("；".join(factor.warnings), icon=":material/warning:")
            if factor.contributions:
                st.caption("分项贡献")
                st.table(factor.contributions)
            if factor.provenance:
                st.caption("来源与时点")
                st.table(factor.provenance)
            if not factor.contributions and not factor.provenance:
                _empty("当前因子未返回分项贡献或来源明细。")


def _render_caps(current: CurrentView) -> None:
    st.subheader("仓位裁剪解释")
    available = [(label, value) for label, value in current.caps.items() if value is not None]
    if not available:
        _empty("当前 API 未返回评分、Kelly 或风险上限明细。")
        return
    columns = st.columns(len(available))
    for column, (label, value) in zip(columns, available, strict=False):
        column.metric(label, _pct(value))
    if current.kelly_input:
        details = current.kelly_input
        source_label = "历史估计" if details.get("source") == "estimated" else "显式输入"
        with st.expander("Kelly 输入与样本"):
            st.table([
                {
                    "来源": source_label,
                    "样本数": details.get("sample_size", "-"),
                    "样本区间": f"{details.get('sample_start', '-')} - {details.get('sample_end', '-')}",
                    "预期收益": _pct(details.get("expected_return")),
                    "年化波动": _pct(details.get("volatility")),
                    "置信收缩": _pct(details.get("confidence")),
                }
            ])
            if details.get("explanation"):
                st.caption(str(details["explanation"]))


def _render_warnings(current: CurrentView) -> None:
    st.subheader("风险警告")
    if not current.warnings:
        st.success("当前没有未处理的动态配置风险警告。", icon=":material/check_circle:")
        return
    visible_warnings = current.warnings[:8]
    for warning in visible_warnings:
        st.warning(warning, icon=":material/warning:")
    if len(current.warnings) > len(visible_warnings):
        st.caption(f"另有 {len(current.warnings) - len(visible_warnings)} 条数据与模型警告，请在因子明细和数据质量页核对。")


def _render_history(rows: list[dict[str, Any]]) -> None:
    st.subheader("历史仓位")
    chart_rows = [row for row in rows if row.get("timestamp") != "-" and row.get("equity_allocation") is not None]
    if chart_rows:
        figure = go.Figure(
            go.Scatter(
                x=[row["timestamp"] for row in chart_rows],
                y=[row["equity_allocation"] * 100 for row in chart_rows],
                mode="lines+markers",
                line=dict(color="#2563eb", width=2, shape="hv"),
                marker=dict(size=5),
                text=[row["regime"] for row in chart_rows],
                hovertemplate="%{x}<br>股票仓位 %{y:.0f}%<br>%{text}<extra></extra>",
            )
        )
        figure.update_layout(
            height=360,
            margin=dict(l=20, r=20, t=30, b=35),
            xaxis_title="",
            yaxis=dict(title="股票仓位 (%)", range=[0, 100], gridcolor="#e9edf3"),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font=dict(family="Inter, system-ui, sans-serif", color="#111827"),
        )
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
    else:
        _empty("尚无可绘制的历史仓位记录。")

    nav_rows = [row for row in rows if row.get("timestamp") != "-" and row.get("nav") is not None]
    if nav_rows:
        nav_figure = go.Figure(
            go.Scatter(
                x=[row["timestamp"] for row in nav_rows],
                y=[row["nav"] for row in nav_rows],
                mode="lines",
                line=dict(color="#0f8a5f", width=2),
                hovertemplate="%{x}<br>净值 %{y:.3f}<extra></extra>",
            )
        )
        nav_figure.update_layout(
            title="纸面组合净值",
            height=330,
            margin=dict(l=20, r=20, t=55, b=35),
            yaxis=dict(title="净值", gridcolor="#e9edf3"),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font=dict(family="Inter, system-ui, sans-serif", color="#111827"),
        )
        st.plotly_chart(nav_figure, width="stretch", config={"displayModeBar": False})
    if rows:
        with st.expander("历史决策明细"):
            st.table(rows[-100:])


def _curve_points(rows: list[dict[str, Any]]) -> tuple[list[str], list[float]]:
    x_values: list[str] = []
    y_values: list[float] = []
    for row in rows:
        x = first(row, "timestamp", "date", "as_of")
        y = as_number(first(row, "value", "nav", "equity", "cumulative_return"))
        if x is not None and y is not None:
            x_values.append(str(x))
            y_values.append(y)
    return x_values, y_values


def _render_backtest(backtest: dict[str, Any] | None) -> None:
    st.subheader("回测结果")
    if not backtest:
        _empty("输入回测 run ID 后显示策略、基准、回撤和压力期结果。")
        return
    metrics = backtest["metrics"]
    metric_specs = [
        ("CAGR", ("cagr", "annual_return"), True),
        ("最大回撤", ("maximum_drawdown", "max_drawdown"), True),
        ("Sharpe", ("sharpe", "sharpe_ratio"), False),
        ("Sortino", ("sortino", "sortino_ratio"), False),
        ("Calmar", ("calmar", "calmar_ratio"), False),
        ("换手率", ("turnover",), True),
    ]
    columns = st.columns(3)
    for index, (label, keys, percent) in enumerate(metric_specs):
        columns[index % 3].metric(label, _metric_value(metrics, *keys, percent=percent))
    benchmark_metrics = backtest.get("benchmark_metrics", {})
    if benchmark_metrics:
        benchmark_rows = [{"策略": "dynamic_allocation", **metrics}]
        benchmark_rows.extend({"策略": name, **values} for name, values in benchmark_metrics.items())
        st.caption("策略与基准指标")
        st.table(benchmark_rows)

    curves = backtest["curves"]
    figure = go.Figure()
    palette = ["#2563eb", "#0f8a5f", "#a86500", "#7c3aed", "#5b6676"]
    for index, (name, points) in enumerate(curves.items()):
        x_values, y_values = _curve_points(points)
        if x_values:
            figure.add_trace(
                go.Scatter(
                    x=x_values,
                    y=y_values,
                    mode="lines",
                    name=name,
                    line=dict(color=palette[index % len(palette)], width=2 if index == 0 else 1.5),
                    hovertemplate=f"{name}<br>%{{x}}<br>%{{y:.3f}}<extra></extra>",
                )
            )
    if figure.data:
        figure.update_layout(
            title="策略与基准净值",
            height=390,
            margin=dict(l=20, r=20, t=55, b=35),
            yaxis=dict(title="净值", gridcolor="#e9edf3"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font=dict(family="Inter, system-ui, sans-serif", color="#111827"),
        )
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
    else:
        _empty("此回测 run 没有可绘制的策略或基准曲线。")

    drawdown_x, drawdown_y = _curve_points(backtest["drawdown"])
    if drawdown_x:
        drawdown_figure = go.Figure(
            go.Scatter(
                x=drawdown_x,
                y=drawdown_y,
                mode="lines",
                fill="tozeroy",
                line=dict(color="#c2413d", width=1.5),
                fillcolor="rgba(194,65,61,.16)",
                hovertemplate="%{x}<br>回撤 %{y:.2%}<extra></extra>",
            )
        )
        drawdown_figure.update_layout(
            title="策略回撤",
            height=300,
            margin=dict(l=20, r=20, t=55, b=35),
            yaxis=dict(title="回撤", tickformat=".0%", gridcolor="#e9edf3"),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font=dict(family="Inter, system-ui, sans-serif", color="#111827"),
        )
        st.plotly_chart(drawdown_figure, width="stretch", config={"displayModeBar": False})
    if backtest["stress_periods"]:
        st.caption("压力年份切片")
        st.table(backtest["stress_periods"])
    if backtest["leakage_checks"]:
        st.caption("Point-in-time / 未来函数检查")
        st.table(backtest["leakage_checks"])
    for warning in backtest["warnings"]:
        st.warning(warning, icon=":material/warning:")


def _render_health(rows: list[dict[str, Any]]) -> None:
    st.subheader("数据质量与 freshness")
    if not rows:
        _empty("当前 API 未返回数据健康序列。")
        return
    proxy_count = sum(row.get("Proxy") == "是" for row in rows)
    stale_count = sum(str(row.get("Freshness", "")).lower() in {"stale", "expired", "过期"} for row in rows)
    summary = st.columns(3)
    summary[0].metric("序列数", len(rows))
    summary[1].metric("过期序列", stale_count)
    summary[2].metric("Proxy 序列", proxy_count)
    st.table(rows)


def main() -> None:
    st.set_page_config(
        page_title="动态资产配置与风险控制",
        page_icon=":material/monitoring:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _apply_style()

    with st.sidebar:
        st.subheader("数据连接")
        base_url = st.text_input("API 地址", value=_env("AI_QUANT_API_BASE_URL", "http://127.0.0.1:8000"))
        actor = st.text_input("操作人", value=_env("AI_QUANT_DYNAMIC_ALLOCATION_ACTOR", "dashboard_user"))
        role = st.selectbox("身份", options=["analyst", "cio", "pm", "risk_compliance", "platform"], index=0)
        token = st.text_input("访问令牌", value="", type="password")
        history_limit = st.select_slider("历史记录", options=[30, 90, 180, 365, 730], value=180)
        if st.button("刷新数据", icon=":material/refresh:", width="stretch"):
            st.cache_data.clear()
            st.rerun()
        st.caption("HTTP API · 只读研究页面")

    try:
        with st.spinner("正在读取动态配置数据..."):
            current_payload, history_payload, health_payload, backtest_list_payload = _fetch_dashboard_bundle(
                base_url, actor, role, token, history_limit
            )
        current = normalize_current(current_payload)
        history = normalize_history(history_payload)
        health = normalize_health(health_payload)
        backtest_runs = normalize_backtest_runs(backtest_list_payload)
    except (DynamicAllocationApiError, ValueError) as exc:
        st.title("动态资产配置与风险控制")
        st.error(str(exc), icon=":material/error:")
        st.info("检查 API 地址、服务状态和访问权限后，使用侧边栏刷新数据。", icon=":material/info:")
        return

    with st.sidebar:
        if backtest_runs:
            run_ids = [item["run_id"] for item in backtest_runs]
            run_labels = {
                item["run_id"]: f"{item['run_id']} · {item['created_at']}" for item in backtest_runs
            }
            run_id = st.selectbox("回测 run", options=run_ids, index=0, format_func=lambda value: run_labels[value])
        else:
            run_id = ""
            st.caption("暂无回测 run")

    _render_header(current)
    summary_tab, history_tab, health_tab = st.tabs(["当前配置", "历史与回测", "数据质量"])
    with summary_tab:
        _render_summary(current)
        _render_factors(current)
        _render_caps(current)
        _render_warnings(current)
    with history_tab:
        _render_history(history)
        backtest = None
        if run_id.strip():
            try:
                with st.spinner("正在读取回测结果..."):
                    backtest = normalize_backtest(_fetch_backtest(base_url, actor, role, token, run_id.strip()))
            except (DynamicAllocationApiError, ValueError) as exc:
                st.error(str(exc), icon=":material/error:")
        _render_backtest(backtest)
    with health_tab:
        _render_health(health)
        st.markdown(
            f'<p class="source-meta">API trace: {html.escape(current.trace_id or "-", quote=True)} · '
            f'config: {html.escape(current.config_hash, quote=True)}</p>',
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
