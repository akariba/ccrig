"""Market-data feature computation from the bundled REAL public price CSVs.

Preserves signed information (BUILD_MANDATE section 10): we never collapse
correlation to abs(). Positive and negative co-movement are kept as separate
channels so the scoring layer can treat them as different economic signals
(e.g. an oil major and an airline can be strongly *negatively* related,
which is itself informative for CCR).
"""
import math
from datetime import date, timedelta
from .config import ROLLING_WINDOW_DAYS, STRESS_WINDOW_DAYS
from .data import STORE


def _returns(ticker):
    rows = STORE.prices.get(ticker)
    if not rows or len(rows) < 3:
        return None
    dates = [r[0] for r in rows]
    closes = [r[1] for r in rows]
    rets = {}
    for i in range(1, len(closes)):
        if closes[i - 1] == 0:
            continue
        rets[dates[i]] = (closes[i] / closes[i - 1]) - 1.0
    return rets


_RETURNS_CACHE = {}


def get_returns(ticker):
    if ticker not in _RETURNS_CACHE:
        _RETURNS_CACHE[ticker] = _returns(ticker)
    return _RETURNS_CACHE[ticker]


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def aligned_returns(ticker_a, ticker_b, window_days=None):
    ra = get_returns(ticker_a)
    rb = get_returns(ticker_b)
    if not ra or not rb:
        return None, None
    common_dates = sorted(set(ra.keys()) & set(rb.keys()))
    if window_days:
        common_dates = common_dates[-window_days:]
    if len(common_dates) < 5:
        return None, None
    return [ra[d] for d in common_dates], [rb[d] for d in common_dates]


def signed_correlation(entity_a, entity_b):
    """Returns dict with full-sample, rolling, and stress-window signed
    Pearson correlation of daily returns, plus derived positive/negative
    channels. Returns None if either entity lacks real market data."""
    ea, eb = STORE.entity(entity_a), STORE.entity(entity_b)
    if not ea or not eb:
        return None
    ta, tb = ea.get("ticker"), eb.get("ticker")
    if not ta or not tb or not ea.get("has_market_data") or not eb.get("has_market_data"):
        return None
    xs, ys = aligned_returns(ta, tb)
    if xs is None:
        return None
    full_corr = pearson(xs, ys)
    xs_r, ys_r = aligned_returns(ta, tb, window_days=ROLLING_WINDOW_DAYS)
    rolling_corr = pearson(xs_r, ys_r) if xs_r else None
    xs_s, ys_s = aligned_returns(ta, tb, window_days=STRESS_WINDOW_DAYS)
    stress_corr = pearson(xs_s, ys_s) if xs_s else None
    if full_corr is None:
        return None
    return {
        "full_sample_corr": round(full_corr, 4),
        "rolling_corr": round(rolling_corr, 4) if rolling_corr is not None else None,
        "rolling_window_days": ROLLING_WINDOW_DAYS,
        "stress_window_corr": round(stress_corr, 4) if stress_corr is not None else None,
        "stress_window_days": STRESS_WINDOW_DAYS,
        "n_obs": len(xs),
        "positive_channel": max(full_corr, 0.0),
        "negative_channel": max(-full_corr, 0.0),
        "source": "REAL_PUBLIC_PRICE_CSV",
    }


def aligned_returns_asof(ticker_a, ticker_b, asof_date, window_days=None):
    """Same as aligned_returns but restricted to observations strictly
    before/at asof_date - used by the Backtest Lab so market-derived
    features cannot see post-event-date data (no look-ahead by design)."""
    ra = get_returns(ticker_a)
    rb = get_returns(ticker_b)
    if not ra or not rb:
        return None, None
    common_dates = sorted(d for d in (set(ra.keys()) & set(rb.keys())) if d <= asof_date)
    if window_days:
        common_dates = common_dates[-window_days:]
    if len(common_dates) < 5:
        return None, None
    return [ra[d] for d in common_dates], [rb[d] for d in common_dates]


def signed_correlation_asof(entity_a, entity_b, asof_date):
    """Look-ahead-safe variant of signed_correlation for backtesting."""
    ea, eb = STORE.entity(entity_a), STORE.entity(entity_b)
    if not ea or not eb:
        return None
    ta, tb = ea.get("ticker"), eb.get("ticker")
    if not ta or not tb or not ea.get("has_market_data") or not eb.get("has_market_data"):
        return None
    xs, ys = aligned_returns_asof(ta, tb, asof_date)
    if xs is None:
        return None
    corr = pearson(xs, ys)
    if corr is None:
        return None
    return {"asof_corr": round(corr, 4), "n_obs": len(xs), "asof_date": asof_date.isoformat(),
            "positive_channel": max(corr, 0.0), "negative_channel": max(-corr, 0.0)}


def forward_move(entity_id, from_date, horizon_days=5):
    """Real, unlabelled-truth proxy used ONLY as the backtest's post-hoc
    observed-outcome column: absolute close-to-close return from the
    trading day on/after from_date to horizon_days trading days later.
    This is a return-based proxy, not verified causal ground truth."""
    e = STORE.entity(entity_id)
    if not e or not e.get("has_market_data"):
        return None
    rows = STORE.prices.get(e["ticker"])
    if not rows:
        return None
    idx_start = None
    for i, (d, _c) in enumerate(rows):
        if d >= from_date:
            idx_start = i
            break
    if idx_start is None or idx_start + horizon_days >= len(rows):
        return None
    p0 = rows[idx_start][1]
    p1 = rows[idx_start + horizon_days][1]
    if p0 == 0:
        return None
    ret = (p1 / p0) - 1.0
    return {"entity_id": entity_id, "from_date": rows[idx_start][0].isoformat(),
            "to_date": rows[idx_start + horizon_days][0].isoformat(),
            "return": round(ret, 5), "abs_return": round(abs(ret), 5)}


def window_return(entity_id, t0, horizon_days=5, max_gap_days=3):
    """Strict event window for the corrected backtest: close-to-close return
    from the T0 close to the close `horizon_days` trading days later.

    Unlike forward_move() (kept as-is for the legacy procedure) this never
    silently shifts the window: the series must have a close ON the last
    trading day at or before T0 (no more than `max_gap_days` earlier) and a
    close `horizon_days` trading days after it. Otherwise the entity is
    reported as ineligible with the reason, so every compared entity is
    measured over the SAME window.

    Returns {"status": "OK", ...} or {"status": <reason>}.
    """
    e = STORE.entity(entity_id)
    if not e or not e.get("has_market_data"):
        return {"status": "NO_PRICE_HISTORY"}
    rows = STORE.prices.get(e["ticker"])
    if not rows:
        return {"status": "NO_PRICE_HISTORY"}
    idx_start = None
    for i, (d, _c) in enumerate(rows):
        if d <= t0:
            idx_start = i
        else:
            break
    if idx_start is None:
        return {"status": "HISTORY_STARTS_AFTER_T0", "first_date": rows[0][0].isoformat()}
    if (t0 - rows[idx_start][0]).days > max_gap_days:
        return {"status": "NO_CLOSE_AT_T0", "last_date_before_t0": rows[idx_start][0].isoformat()}
    if idx_start + horizon_days >= len(rows):
        return {"status": "INSUFFICIENT_FORWARD_DATA"}
    p0, p1 = rows[idx_start][1], rows[idx_start + horizon_days][1]
    if not p0:
        return {"status": "NO_PRICE_HISTORY"}
    ret = (p1 / p0) - 1.0
    return {"status": "OK", "entity_id": entity_id, "from_date": rows[idx_start][0].isoformat(),
            "to_date": rows[idx_start + horizon_days][0].isoformat(), "return": ret}


def price_series(entity_id):
    e = STORE.entity(entity_id)
    if not e or not e.get("ticker") or not e.get("has_market_data"):
        return None
    rows = STORE.prices.get(e["ticker"])
    if not rows:
        return None
    return [{"date": d.isoformat(), "close": c} for d, c in rows]


def market_neighbors(entity_id, top_k):
    """Cheap candidate-generation source: rank other market-data entities by
    |correlation| using full-sample returns (fast, used only for CANDIDATE
    generation, not the final signed score)."""
    e = STORE.entity(entity_id)
    if not e or not e.get("has_market_data"):
        return []
    ta = e["ticker"]
    scored = []
    for other_id in STORE.issuer_ids:
        if other_id == entity_id:
            continue
        eo = STORE.entity(other_id)
        if not eo.get("has_market_data"):
            continue
        xs, ys = aligned_returns(ta, eo["ticker"])
        if xs is None:
            continue
        c = pearson(xs, ys)
        if c is None:
            continue
        scored.append((other_id, abs(c)))
    scored.sort(key=lambda x: -x[1])
    return [eid for eid, _ in scored[:top_k]]
