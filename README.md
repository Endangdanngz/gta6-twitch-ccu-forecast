# GTA VI Twitch CCU forecast — make.fun entry

Forecasts a game launch day's Twitch category viewers for hours 2–24 of
the release day (UTC), five quantiles (0.05, 0.25, 0.5, 0.75, 0.95) per
hour, scored by pinball loss on the log scale.

## Run

```
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `*.in` case file (schema `makefun/twitch-ccu-case/v1`) and
writes one `<id>.out` per case. Python 3.13, standard library only, no
network, deterministic (same input → byte-identical output), far under
the 8 s per-case limit.

## Model

Work in log space. Each comparable launch in the case file contributes
log-ratios `ln(viewers at hour h / viewers at hour 1)` for its release
day. Those ratios are pooled per horizon with Gaussian kernel weights on
the distance between the case's and the comparable's log hour-1 level
(bandwidth 1.0) — hour-1 scale is the regime signal: a launch whose
first hour is already huge is on the "unlocked, decaying gently" path,
while a tiny first hour means the main unlock is still ahead and the day
explodes upward. The weighted distribution is kernel-smoothed in value
space (half-width 0.5), its five quantiles are read off per hour, the
quantile curves are smoothed across neighbouring hours, and the result
is mapped back with `q = p * exp(r)`. If the comparable pool is missing
or degenerate, the program falls back to the house-baseline shape and
still emits a valid forecast.

Model and constants were selected by a leave-one-out backtest over the
37 comparable launches inside the practice case files (each launch
forecast from the others, scored with the exact competition formula):
chosen model 0.398 mean pinball loss vs 0.930 for the house-baseline
formula and 1.142 for a flat forecast on the same pseudo-cases, with
90% coverage of 0.890.
