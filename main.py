#!/usr/bin/env python3
"""Forecast a game launch day's Twitch category viewers, hours 2-24.

Reads every *.in case file (schema makefun/twitch-ccu-case/v1) from
$MAKEFUN_INPUT_DIR (else /input) and writes one <id>.out per case to
$MAKEFUN_OUTPUT_DIR (else /output): for each hour 2..24, the 0.05, 0.25,
0.5, 0.75 and 0.95 quantiles of that hour's viewer count.

Model: work in log space. For every comparable launch in the case file,
form the log-ratios r_c(h) = ln(viewers at hour h of its release day /
viewers at hour 1). Pool those ratios per horizon h with Gaussian kernel
weights on the distance between the case's and the comparable's log
hour-1 level (bandwidth 1.0): launches whose first hour was of similar
scale sit in the same launch regime (already unlocked and huge, or tiny
because the unlock is still hours away) and dominate the pool. Each
pooled sample's weight is spread over a small neighbourhood in log-ratio
space (kernel smoothing of the weighted distribution, half-width 0.5),
the five quantiles are read off the smoothed weighted distribution per
hour, each quantile curve is smoothed across neighbouring hours, and the
result is mapped back with q = p * exp(r), p the case's hour-1 print.
Model selection and constants come from a leave-one-out backtest over
the comparable launches (see BACKTEST.md in the working notes).

Fallbacks: if the comparable pool is missing or degenerate, use the
house-baseline shape (flat median at p, spread 0.15*sqrt(h-1) in log
space). The program never raises on a well-formed case file and always
emits the exact output shape.

Standard library only, no network, fully deterministic.
"""

import json
import math
import os
import sys
from datetime import datetime

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
KERNEL_BW = 1.0          # bandwidth on log hour-1 level distance
VALUE_BW = 0.5           # value-space smoothing half-width (log-ratio)
# (offset in units of VALUE_BW, relative weight) for the value kernel
VALUE_KERNEL = [(-1.0, 0.25), (-0.5, 0.5), (0.0, 1.0), (0.5, 0.5), (1.0, 0.25)]
LOG_RATIO_MIN = -3.0     # clamp for pooled log-ratios
LOG_RATIO_MAX = 7.5
Q_MAX = 1_000_000_000.0
Q_MIN = 0.01


def parse_ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def is_prerelease(comp):
    """The GTA VI category's own pre-release series is not a launch."""
    name = (comp.get("name") or "").lower()
    unlock = (comp.get("unlock") or "").lower()
    return "before release" in name or unlock.startswith("not a launch")


def day_ratios(comp):
    """(hour-1 viewers, [log-ratio for hours 2..24]) or None.

    Uses only the comparable's release-day hourly points; requires the
    full 24 hours and a positive hour-1 value.
    """
    try:
        day_start = parse_ts(comp["day_start"])
    except Exception:
        return None
    day = {}
    for pt in comp.get("hourly") or []:
        try:
            t = parse_ts(pt["from"])
            v = float(pt["viewers"])
        except Exception:
            continue
        if t.date() == day_start.date():
            day[t.hour] = max(v, 1.0)
    if len(day) != 24:
        return None
    p = day[0]
    if p <= 0:
        return None
    ratios = [math.log(day[h] / p) for h in range(1, 24)]
    return p, ratios


def weighted_quantile(pairs, q):
    """Weighted quantile of (value, weight) pairs, linear interpolation
    on the weighted CDF."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    target = q * total
    cum = 0.0
    prev_v, prev_c = pairs[0][0], 0.0
    for v, w in pairs:
        cum += w
        if cum >= target:
            if cum == prev_c:
                return v
            frac = (target - prev_c) / (cum - prev_c)
            return prev_v + frac * (v - prev_v)
        prev_v, prev_c = v, cum
    return pairs[-1][0]


def baseline_rows(p):
    """House-baseline shape: flat median, log spread 0.15*sqrt(h-1)."""
    rows = []
    for h in range(2, 25):
        s = 0.15 * math.sqrt(h - 1)
        rows.append([p * math.exp(z * s) for z in Z])
    return rows


def model_rows(p, pool):
    """pool: list of (hour-1 viewers, [log-ratios hours 2..24]).

    Weighted quantiles of the pooled log-ratios per horizon, with the
    weighted distribution kernel-smoothed in value space; quantile
    curves are then smoothed across neighbouring horizons before being
    mapped back to viewer counts.
    """
    log_p = math.log(p)
    weights = [
        math.exp(-0.5 * ((log_p - math.log(pc)) / KERNEL_BW) ** 2)
        for pc, _ in pool
    ]
    wsum = sum(w for _, w in VALUE_KERNEL)
    raw = []  # raw[h_idx][level_idx] log-ratio quantiles
    for idx in range(23):  # idx 0 -> hour 2
        pairs = []
        for (_, ratios), w in zip(pool, weights):
            r = ratios[idx]
            for off, ow in VALUE_KERNEL:
                pairs.append((r + off * VALUE_BW, w * ow / wsum))
        raw.append([weighted_quantile(pairs, t) for t in LEVELS])
    # smooth each level's curve across neighbouring horizons
    smoothed = []
    for idx in range(23):
        row = []
        for li in range(5):
            vals = [raw[j][li] for j in (idx - 1, idx, idx + 1)
                    if 0 <= j < 23]
            row.append(sum(vals) / len(vals))
        smoothed.append(row)
    rows = []
    for qs in smoothed:
        for i in range(1, 5):  # enforce non-decreasing across levels
            qs[i] = max(qs[i], qs[i - 1])
        rows.append([p * math.exp(min(max(r, LOG_RATIO_MIN), LOG_RATIO_MAX))
                     for r in qs])
    return rows


def clean_rows(rows):
    """Clamp every quantile into (0, 1e9], keep rows non-decreasing,
    round to 2 decimals (rounding can only shrink gaps of >= 0.01, and
    the cummax pass afterwards restores monotonicity exactly)."""
    out = []
    for row in rows:
        vals = []
        for q in row:
            if not math.isfinite(q):
                q = Q_MIN
            vals.append(min(max(q, Q_MIN), Q_MAX))
        for i in range(1, 5):
            vals[i] = max(vals[i], vals[i - 1])
        vals = [round(v, 2) for v in vals]
        for i in range(1, 5):
            vals[i] = max(vals[i], vals[i - 1])
        out.append(vals)
    return out


def hour1_print(case):
    for row in case.get("known") or []:
        try:
            v = float(row["viewers"])
        except Exception:
            continue
        if v and v > 0:
            return v
    return None


def forecast_case(case):
    p = hour1_print(case)
    if p is None:
        p = 1.0
    p = max(p, 1.0)
    pool = []
    for comp in case.get("comparables") or []:
        if is_prerelease(comp):
            continue
        got = day_ratios(comp)
        if got is not None:
            pool.append(got)
    if len(pool) >= 5:
        rows = model_rows(p, pool)
    else:
        rows = baseline_rows(p)
    rows = clean_rows(rows)
    return {"hours": [{"hour": h, "q": rows[h - 2]} for h in range(2, 25)]}


def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    try:
        names = sorted(n for n in os.listdir(in_dir) if n.endswith(".in"))
    except OSError:
        names = []
    for name in names:
        case_id = name[: -len(".in")]
        try:
            with open(os.path.join(in_dir, name), "r", encoding="utf-8") as fh:
                case = json.load(fh)
            result = forecast_case(case)
        except Exception:
            # Never leave a case without an output file: emit the
            # degenerate-but-valid flat forecast at 1 viewer.
            result = {"hours": [{"hour": h, "q": [1.0] * 5}
                                for h in range(2, 25)]}
        text = json.dumps(result, separators=(",", ":"))
        with open(os.path.join(out_dir, case_id + ".out"), "w",
                  encoding="utf-8") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
