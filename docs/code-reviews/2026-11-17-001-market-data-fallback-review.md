---
title: "Code review: market-data fallback fix"
date: 2026-11-17
run_id: cr-20261117-001
plan: docs/plans/2026-11-17-001-fix-market-data-openbb-fallback-plan.md
status: passed
---

# Code review: market-data fallback fix

Scope: `scripts/fetch_news.py`, `tests/test_fetch_news.py`, `Dockerfile` on
`fix/market-quote-fallback` versus `main` (uncommitted work included).
`scripts/summarize.py` and `scripts/translate_portfolio.py` were in scope as
context only — their diffs belong to a separate route change.

Intent: restore a populated market block by not treating `openbb-quote`'s
in-band error payload as data, and by pinning the image's openbb to the
known-good 4.7.2 line.

Coverage: correctness of the error path and the budget interaction, test
adequacy, container reproducibility. Cross-model peer review: not run for this
change.

## Actionable Findings

None.

## Advisory findings (report-only, not applied)

- **low — scripts/fetch_news.py:208** — `_disable_openbb_provider` is a
  check-then-set over a module global called from worker threads; two
  concurrent failures can print the fallback warning twice. Cosmetic only (the
  flag itself is set once), so no lock was added.
- **low — scripts/fetch_news.py:194** — `OPENBB_PROVIDER_DISABLED` is never
  reset. Correct for the one-shot briefing process; a long-lived caller that
  later regains a healthy provider would keep skipping it.
- **info — Dockerfile:12** — `finance-news-image.sh:ensure_finance_news_image`
  returns early when the image already exists, so a Dockerfile change does not
  reach the deployed image without a manual rebuild. That helper lives in
  `mama-automations`, outside this repo; recorded here rather than changed.

## Verification reviewed

- `tests/test_fetch_news.py::test_openbb_error_payload_falls_back_to_yfinance`
  and `::test_openbb_error_payload_disables_provider_for_the_run` fail against
  the pre-fix `scripts/fetch_news.py` (observed: 2 provider spawns, no
  fallback) and pass after.
- Targeted suite: 21 passed (`test_fetch_news.py`, `test_fetch_budget.py`).
- Live: rebuilt image yields `openbb 4.7.2` + `openbb-equity 1.6.2`, a quote in
  3.7s, and all three regions from `get_market_news` in 19.5s.

## Verdict

Pass. No blocker, no `settled_conflict` stamps.
