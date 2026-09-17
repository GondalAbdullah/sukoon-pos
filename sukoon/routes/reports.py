"""Insights (the dashboard) and reports with CSV/PDF export (Development Spec Phase 6;
ADR-0034). Admin only. Thin: every figure comes from ``reporting_service``."""

from __future__ import annotations

from datetime import UTC, datetime

from flask import (
    Blueprint,
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required

from sukoon.routes.guards import permission_required
from sukoon.services import reporting_service as rpt
from sukoon.services import settings_service

bp = Blueprint("reports", __name__)

PRESETS = (("today", "Today"), ("week", "This week"), ("month", "This month"))


def _period_from_args(default: str = "today") -> rpt.Period:
    if request.args.get("from") or request.args.get("to"):
        return rpt.custom(request.args.get("from"), request.args.get("to"))
    name = request.args.get("preset", default)
    return rpt.preset(name if name in dict(PRESETS) else default)


def _change_words(now_paisa: int, before_paisa: int, against: str) -> str:
    """ADR-0034 §4: never a percentage change from nothing."""
    if before_paisa <= 0:
        return f"Nothing to compare with ({against})"
    change = 100 * (now_paisa - before_paisa) / before_paisa
    if abs(change) < 0.05:
        return f"The same as {against}"
    return f"{abs(change):.1f}% {'more' if change > 0 else 'less'} than {against}"


def _hour(h: int) -> str:
    return f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}"


def _chart_bars(period: rpt.Period):
    """The chart's bars as (axis label, tooltip, value in paisa, peak label), plus the peak,
    worked out here rather than in Jinja. Today: 8 AM–9 PM at least, widened to any hour
    that sold; week/month: one bar per day that sold."""
    if period.key == "today":
        found = {h: (n, v) for h, n, v in rpt.sales_by_hour(period)}
        span = range(min([8, *found]), max([21, *found]) + 1)
        bars = []
        for h in span:
            n, v = found.get(h, (0, 0))
            label = f"{_hour(h)}–{_hour((h + 1) % 24)}"
            bars.append(
                (
                    (h % 12) or 12,
                    f"{label} · {n} sale{'' if n == 1 else 's'} · {rpt.rs(v)}",
                    v,
                    label,
                )
            )
    else:
        bars = [
            (
                d.day,
                f"{d.day} {d:%b} · {n} sale{'' if n == 1 else 's'} · {rpt.rs(g)}",
                g,
                f"{d.day} {d:%b}",
            )
            for d, n, g, _r in rpt.sales_by_day(period)
        ]
    peak = max((b[2] for b in bars), default=0)
    peak_label = next((b[3] for b in bars if b[2] == peak), None) if peak > 0 else None
    return bars, peak, peak_label


@bp.route("/insights")
@login_required
@permission_required("report.view")
def insights():
    period = _period_from_args()
    now = datetime.now(UTC)
    before = rpt.comparison(period, now)
    totals = rpt.sales_totals(period)
    previous = rpt.sales_totals(before)
    owing, _credit = rpt.credit_rows(now)
    bars, peak, peak_label = _chart_bars(period)
    categories = rpt.sales_by_category(period)
    return render_template(
        "reports/insights.html",
        period=period,
        presets=PRESETS,
        totals=totals,
        change=_change_words(totals.net_paisa, previous.net_paisa, before.label),
        credit_total=sum(r.balance.amount_paisa for r in owing),
        credit_accounts=len(owing),
        profit=rpt.estimated_profit(period),
        bars=bars,
        peak=peak,
        peak_label=peak_label,
        category_total=sum(v for _n, v in categories) or 1,
        categories=categories[:5],
        recent=rpt.recent_sales(period),
        sales_count=totals.count,
        rs=rpt.rs,
        percent=rpt.percent,
    )


@bp.route("/reports")
@login_required
@permission_required("report.view")
def reports_index():
    return render_template("reports/index.html", reports=rpt.REPORTS)


def _doc(kind: str):
    if kind not in rpt.REPORTS:
        abort(404)
    ranged = rpt.REPORTS[kind][1]
    return rpt.build(kind, _period_from_args("month") if ranged else None), ranged


@bp.route("/reports/<kind>")
@login_required
@permission_required("report.view")
def report(kind: str):
    try:
        doc, ranged = _doc(kind)
    except rpt.PeriodError as exc:
        flash(str(exc), "error")
        return redirect(url_for("reports.report", kind=kind))
    return render_template(
        "reports/report.html",
        kind=kind,
        doc=doc,
        ranged=ranged,
        presets=PRESETS,
        preset=request.args.get("preset", "month") if not request.args.get("from") else None,
        date_from=request.args.get("from", ""),
        date_to=request.args.get("to", ""),
        cell_text=rpt.cell_text,
        export_args={k: v for k, v in request.args.items() if k in ("preset", "from", "to")},
    )


def _export(kind: str, ext: str):
    try:
        doc, _ranged = _doc(kind)
    except rpt.PeriodError as exc:
        flash(str(exc), "error")
        return redirect(url_for("reports.report", kind=kind))
    stem = f"sukoon-{kind}-{datetime.now(UTC):%Y%m%d}"
    if ext == "csv":
        resp = make_response(rpt.to_csv(doc))
        resp.mimetype = "text/csv"
        resp.headers["Content-Disposition"] = f'attachment; filename="{stem}.csv"'
    else:
        resp = make_response(
            rpt.to_pdf(doc, shop_name=settings_service.get("shop.name", "Al-Rehman General Store"))
        )
        resp.mimetype = "application/pdf"
        resp.headers["Content-Disposition"] = f'attachment; filename="{stem}.pdf"'
    return resp


@bp.route("/reports/<kind>.csv")
@login_required
@permission_required("report.view")
def report_csv(kind: str):
    return _export(kind, "csv")


@bp.route("/reports/<kind>.pdf")
@login_required
@permission_required("report.view")
def report_pdf(kind: str):
    return _export(kind, "pdf")
