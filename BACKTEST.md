# Backtest report — gta6-twitch-ccu-forecast-01

## Method (exactly the mandated design)

Leave-one-out over the comparables inside each practice input file. For
each of the 37 launch comparables with a complete release day (the GTA VI
pre-release series is excluded — it is not a launch), a pseudo-case is
built: hour-1 print = the launch's viewers at its day_start hour, the
analog pool = the other 36 launches in the same file, forecast hours
2–24 scored against the launch's actual hourly viewers with the exact
competition formula (log-scale pinball, mean over hours × 5 levels).

The comparables pool is byte-identical in all four practice files (each
file excludes the four practice launches, which are never in any pool),
so per-file results are identical; they are reported per file anyway,
plus pooled over the 148 pseudo-case runs. Reference forecasts (house
baseline formula, flat = hour-1 print) are computed in the same harness
on the same pseudo-cases.

Caveat on levels: the house baseline scores ≈ 0.387 on the four real
practice cases, but 0.930 on these comparable pseudo-cases. The
pseudo-case population is harder and more diverse — it includes many
launches whose main unlock falls late in the UTC day (hour-1 prints of a
few hundred viewers that later explode 100–2000×), a regime the four
rolling-midnight practice cases barely contain. Relative comparisons
within the harness are the valid signal; the GTA-like subset below is
the closest analog of the final case.

## Results — pooled over 148 pseudo-case runs (37 per file)

Per file (p00 = p01 = p02 = p03, identical pools): chosen model 0.3975,
house baseline 0.9297, flat 1.1421, pooled unweighted 0.7159,
kernel (g, f, ln p) 0.4480.

| variant | mean loss | 90% coverage |
|---|---|---|
| flat (all quantiles = hour-1 print) | 1.1421 | 0.000 |
| house baseline formula | 0.9297 | 0.624 |
| pooled log-ratio quantiles, unweighted | 0.7159 | 0.887 |
| kernel-weighted (ramp g, baseline f, log-level) | 0.4480 | 0.741 |
| unlock-aligned pooling, honest case offset | 0.5562 | 0.643 |
| kernel on log hour-1 level only (bw 1.0) | 0.4100 | 0.864 |
| + smoothing of quantile curves across hours | 0.4085 | 0.866 |
| + value-space smoothing 0.35 | 0.3986 | 0.879 |
| **CHOSEN: + value-space smoothing 0.5** | **0.3975** | **0.890** |

Chosen model, per-quantile mean losses (pooled): tau 0.05 → 0.1663,
0.25 → 0.4725, 0.5 → 0.5977, 0.75 → 0.5067, 0.95 → 0.2443. The median
remains the largest single contributor, driven by irreducible
unlock-timing variance inside the late-unlock regime.

Calibration checks: widening all spreads ×1.3 lifts coverage to 0.900
but worsens loss (0.4185); blending the weighted pool 50/50 with the
unweighted pool reaches coverage 0.902 at loss 0.4519. The chosen
configuration sits at coverage 0.890 with the best loss — width is spent
only where the backtest says it pays.

## GTA-like subset

Pseudo-cases whose hour-1 print is already ≥ 25% of their release-day
maximum (the wave substantially arrived by hour 1 — the final case's
regime, since GTA VI's hour 1 follows the NZ and EU unlocks), n = 24:
chosen model 0.2084 vs house baseline 0.2652. The model beats the
baseline in the regime the final will actually be in, by ~21% relative.

## What did not work (kept out)

- History-derived features g (ramp into launch: median viewers in the
  last 6 h vs 12–24 h before day_start) and f (hour-1 vs recent
  baseline) looked principled but added noise: for small categories the
  pre-launch series is sparse and spiky, so both features are unstable,
  and every kernel that included them scored worse than log-level alone.
- Unlock alignment (pooling shapes in hours-since-estimated-unlock)
  scored 0.4528 when the case's own unlock offset was estimated from its
  full curve — that estimate leaks the answer, so it was discarded. With
  an honest kernel-predicted case offset it scored 0.5562: the offset
  prediction is too noisy to help.
- kNN-adaptive bandwidths (k = 8/12) were much worse (0.54–0.61): the
  adaptive radius couples to regime density in the wrong way here.

## Chosen model (what main.py implements)

Pool the comparables' release-day log-ratios per horizon; weight each
comparable by a Gaussian kernel on |ln p_case − ln p_comparable|
(bandwidth 1.0); kernel-smooth the weighted distribution in value space
(half-width 0.5, weights 0.25/0.5/1/0.5/0.25); read the five quantiles;
smooth each quantile curve across neighbouring hours (3-hour moving
average); enforce monotonicity across levels; clamp log-ratios to
[−3, 7.5]; map back with q = p · exp(r), clamp to (0, 1e9]. If the pool
has fewer than 5 usable launches, fall back to the house-baseline shape.
Constants are round and few on purpose: with 37 pseudo-cases the
standard error of a mean loss is ≈ 0.08, so differences below ~0.01
between the top variants are noise and were not chased.

## Validation of the submitted program

- Runs on all four practice inputs: every output valid (23 rows, hours
  2–24 once each, exactly the keys `hour` and `q`, five finite quantiles,
  0 < q ≤ 1e9, non-decreasing, ≤ 65,536 bytes — actual ≈ 1.5 KB).
- Determinism: two runs of every case byte-identical (sha256 match).
- Equivalence: main.py's forecast on a synthetic Elden Ring pseudo-case
  matches the backtest harness's chosen model to 1.9e-08 max relative
  deviation (2-decimal rounding).
- Runtime: ≈ 0.15 s for all four cases together (~0.04 s per case),
  limit 8 s per case. Standard library only; no network, randomness or
  clock use.
- Degenerate inputs (no comparables, missing/zero hour-1 print, missing
  fields, hour-1 print of ~1e9) all produce valid output, never a crash.

## Honest weaknesses and risks for the final case

1. **The real bar is unknown.** Prizes require beating the better of the
   house baseline and the house *model* forecast (an AI model given the
   rules and the case's history, but not hour 1). Our backtest margin is
   measured against the baseline formula only. The model forecast's
   ratios are anchored to hour 1 just like ours, so the race is about
   shape quality; our data-driven shape should be competitive, but
   there is no way to verify this locally.
2. **Measurement mismatch.** Backtest prints are SullyGnome hourly
   averages; the final's prints are means of per-minute Twitch reads.
   Close, not identical; minute means are smoother, which mildly favours
   our smooth quantile curves.
3. **GTA's scale is off the training map.** The category's pre-release
   premiere peaked at ~1.42M viewers; its nearest kernel neighbours are
   Elden Ring / Cyberpunk / Diablo-class launches (hour-1 0.5–0.9M). If
   GTA's release-day shape is unlike all of them — e.g. the 05:00Z and
   08:00Z US unlocks drive a second, higher peak late in the UTC day
   beyond what rolling-launch analogs show — the pooled shape will
   under-rise mid-day. The kernel adapts the regime to the realised
   hour-1 print, which is the main hedge available.
4. **Late-unlock variance is irreducible from hour 1.** In the
   pseudo-case population the worst losses (up to 1.65) are launches
   whose unlock landed at an unusual UTC hour; no hour-1 information
   separates them. The final is a rolling-midnight launch, the
   best-represented regime in the pool, which mitigates this.
5. **Small-sample tuning risk.** All constants were picked on 37
   pseudo-cases; the top few variants are within noise of each other.
   The simplest variant family (one kernel dimension, round constants)
   was deliberately preferred for that reason.
