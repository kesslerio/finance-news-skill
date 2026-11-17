---
title: "fix: Restore market quotes when the openbb provider fails"
type: fix
date: 2026-11-17
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan
---

# fix: Restore market quotes when the openbb provider fails

## Goal Capsule

- **Objective**: the Börse morning-finance briefing again carries a populated
  *Märkte* block (US, Europe, Japan indices with price and change) instead of
  "US-Daten fehlen; S&P 500 nicht verfügbar. Europa/Japan ohne Angaben."
- **Means**: stop treating `openbb-quote`'s in-band error payload as market
  data, so the existing yfinance fallback runs; stop a broken provider from
  spending the shared 30s quote budget; pin the image's openbb to the
  known-good 4.7.2 line; raise the per-call LLM timeout that the current
  resident model needs.
- **Authority**: repo code and tests own the fix; the rebuilt container image
  is the deployed artifact; the systemd drop-in is host-local configuration on
  mama.
- **Stop conditions**: if the rebuilt image still yields fewer than one index
  per requested region, stop and report rather than shipping.

## Product Contract

### Requirements

- R1. An `openbb-quote` payload carrying `error` is not market data. It must
  not be recorded as a quote result.
- R2. When the primary provider fails, the briefing still gets index quotes
  from the yfinance fallback for every requested region.
- R3. A provider that fails must not consume the shared 30s quote budget, so
  later symbols are not starved.
- R4. The deployed image must contain a working openbb: `obb.equity` present,
  and a per-symbol cost that fits the 30s shared budget.
- R5. Regression tests cover the error-payload path and the provider-disable
  path.
- R6. The scheduled job must complete inside its 500s deadline with the
  currently served model.

### Actors and flows

The scheduled unit `lobster-morning-finance.timer` on mama runs
`run-market-briefing-deliver.sh morning-finance`, which runs
`scripts/briefing.py` inside the `finance-news-briefing` image and delivers via
the household Hermes bridge. `fetch_news.get_market_news` fetches indices
before headlines; `summarize.build_briefing_summary` renders only indices that
carry both `price` and `change_percent`.

### Acceptance examples

- Given a broken openbb that returns
  `[{"symbol": "^GSPC", "error": "..."}]`, when `fetch_market_data(["^GSPC"])`
  runs, then the result comes from yfinance and carries `price` and
  `change_percent`.
- Given the deployed image, when `get_market_news` runs for us/europe/japan,
  then each region yields at least one index.

## Planning Contract

### Key Technical Decisions

- **KTD1 (session-settled)**: reject in-band error payloads inside
  `_fetch_via_openbb` and disable the provider for the remainder of the run,
  rather than only repairing the image. Rejected alternative: pin the image and
  leave the code untouched. Reason: a version pin alone leaves the next
  provider breakage silently blank, which is exactly the failure being fixed.
- **KTD2 (session-settled)**: pin `openbb==4.7.2` / `openbb-yfinance==1.6.3`
  rather than installing `openbb-equity` alongside 5.0.0. Rejected alternative:
  add `openbb-equity` to 5.0.0. Reason: measured 9.8s/symbol on 5.0.0 leaves
  only `^GSPC` inside the 30s budget; 4.7.2 measured 3.7s/symbol and fills all
  regions.
- **KTD3 (session-settled)**: raise `FINANCE_NEWS_LLM_TIMEOUT` to 180 via a
  systemd drop-in rather than lowering the job's model or its deadline.
  Rejected alternative: keep the 60s default. Reason: every translation and the
  summary timed out at 60s with `mama-resident`, and the job then failed
  outright.
- **KTD4**: keep the existing 30s shared quote budget and the yfinance batch
  bound from #140 unchanged; the fix must fit them, not retune them.
- **KTD5**: commit scope is `scripts/fetch_news.py`, `tests/test_fetch_news.py`
  and `Dockerfile` (including the pre-existing `mama-resident` ENV line);
  `scripts/summarize.py` and `scripts/translate_portfolio.py` stay uncommitted
  because they belong to a separate route change.

### Assumptions

- The yfinance batch remains reachable from the image (verified: four indices
  in 0.9s).
- The rollback image `finance-news-briefing:rollback-20260921` is a valid
  reference for the known-good dependency set.
- The mama-resident route is the served model and stays permitted.

## Implementation Units

### U1 — Reject in-band provider errors and disable the provider for the run

- **Files**: `scripts/fetch_news.py`
- **Approach**: add `OPENBB_PROVIDER_DISABLED` and `_disable_openbb_provider`;
  return `None` from `_fetch_via_openbb` when `OPENBB_PROVIDER_DISABLED` is set
  or the parsed payload carries `error`. `fetch_market_data` already routes a
  `None` result into `failed_symbols`, which reaches the yfinance fallback.
- **Verification**: targeted pytest for the fallback and disable paths.

### U2 — Pin the image's openbb to the known-good line

- **Files**: `Dockerfile`
- **Approach**: replace the unpinned install with
  `openbb==4.7.2 openbb-yfinance==1.6.3` and record why in a comment.
- **Verification**: rebuild, then `pip list` shows `openbb 4.7.2` and
  `openbb-equity 1.6.2`; `scripts/openbb-quote ^GSPC` returns a quote.

### U3 — Regression tests

- **Files**: `tests/test_fetch_news.py`
- **Approach**: one test asserting an error payload falls back to yfinance and
  yields price/change_percent; one asserting the second symbol does not spawn
  the provider again.
- **Verification**: full suite passes (excluding the two pre-existing failures
  owned by the uncommitted route change).

### U4 — Raise the per-call LLM timeout

- **Files**: host-local
  `~/.config/systemd/user/lobster-morning-finance.service.d/15-llm-timeout.conf`
- **Approach**: `Environment=FINANCE_NEWS_LLM_TIMEOUT=180`, then
  `systemctl --user daemon-reload`.
- **Verification**: `systemctl --user show` reports the variable, and a full
  briefing run completes and contains the *Märkte* block.

## Verification Contract

- `python3 -m pytest -q` inside the rebuilt image: the new tests pass and no
  new failure appears. Known pre-existing failures:
  `tests/test_summarize.py::test_scheduled_model_defaults_are_ornith_only` and
  `tests/test_translate_portfolio.py::test_translate_headlines_calls_ornith_directly`.
- Data check: `get_market_news(10, regions=["us","europe","japan"], ...)` yields
  at least one index per region.
- Render check: `build_briefing_summary(...)` emits the `### Markets` block with
  prices and changes.
- End-to-end: the producer run completes and the JSON `macro_message` contains
  the *Märkte* section with all three regions.

## Definition of Done

- R1–R6 hold, with the tests above green apart from the named pre-existing
  failures.
- The image is rebuilt and tagged; the previous image remains available as
  `finance-news-briefing:before-openbb-pin-20261117`.
- The fix-owned files are committed on a feature branch; the two route-change
  files remain uncommitted.
- A briefing run produces a populated market block end to end.

## Appendix

Measured evidence (2026-11-17, mama):

| Image | openbb | `openbb-quote ^GSPC` | `get_market_news` |
| --- | --- | --- | --- |
| `latest` before fix | 5.0.0, no `openbb-equity` | `{"error": "'App' object has no attribute 'equity'"}` in 9–24s | us `^GSPC` only, Europe/Japan empty |
| `latest` + `openbb-equity` | 5.0.0 + equity 2.0.0 | quote in 9.8s | us `^GSPC` only (30s budget starved) |
| `rollback-20260921` | 4.7.2 + equity 1.6.2 | quote in 4.7s | all regions in 28.7s |
| rebuilt after fix | 4.7.2 + equity 1.6.2 | quote in 3.7s | all regions in 19.5s |

yfinance fallback inside the same image: four indices in 0.9s.
