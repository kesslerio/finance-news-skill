"""Watchlist resolution (PORTFOLIOS_DIR) and empty-watchlist behaviour."""
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

import fetch_news
import summarize
import utils

HEADER = "symbol,name,category,notes\n"
REPO_ROOT = Path(__file__).parent.parent


def _watchlist(tmp_path: Path, body: str = "") -> Path:
    path = tmp_path / "watchlists" / "portfolio.csv"
    path.parent.mkdir(parents=True)
    path.write_text(HEADER + body)
    return path


def test_resolver_uses_portfolios_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIOS_DIR", str(tmp_path))
    assert utils.get_portfolio_file() == tmp_path / "watchlists" / "portfolio.csv"


def test_resolver_falls_back_to_config(monkeypatch):
    monkeypatch.delenv("PORTFOLIOS_DIR", raising=False)
    assert utils.get_portfolio_file() == (REPO_ROOT / "config" / "portfolio.csv").resolve()


def test_shipped_example_watchlist_is_header_only():
    assert (REPO_ROOT / "config" / "portfolio.csv.example").read_text() == HEADER


def test_portfolio_and_earnings_read_the_resolved_file(tmp_path, monkeypatch):
    path = _watchlist(tmp_path, "ZZZZ,Test Co,Test,\n")
    monkeypatch.setenv("PORTFOLIOS_DIR", str(tmp_path))
    import earnings
    import portfolio

    try:
        assert importlib.reload(portfolio).PORTFOLIO_FILE == path
        assert importlib.reload(earnings).PORTFOLIO_FILE == path
        assert [row["symbol"] for row in portfolio.load_portfolio()] == ["ZZZZ"]
    finally:
        monkeypatch.delenv("PORTFOLIOS_DIR")
        importlib.reload(portfolio)
        importlib.reload(earnings)


def test_fetch_news_symbols_and_metadata_honor_portfolios_dir(tmp_path, monkeypatch):
    _watchlist(tmp_path, "zzzz,Test Co,Test,\n")
    monkeypatch.setenv("PORTFOLIOS_DIR", str(tmp_path))

    assert fetch_news.get_portfolio_symbols() == ["ZZZZ"]
    assert fetch_news.get_portfolio_metadata()["ZZZZ"]["name"] == "Test Co"


@pytest.mark.parametrize("create_file", [True, False], ids=["header-only", "missing"])
def test_empty_watchlist_reads_as_no_symbols(tmp_path, monkeypatch, create_file):
    if create_file:
        _watchlist(tmp_path)
    monkeypatch.setenv("PORTFOLIOS_DIR", str(tmp_path))

    assert fetch_news.get_portfolio_symbols() == []
    assert fetch_news.get_portfolio_metadata() == {}
    assert fetch_news.get_portfolio_movers()["movers"] == []
    with pytest.raises(fetch_news.PortfolioError, match="Watchlist is empty"):
        fetch_news.get_portfolio_news()


def test_briefing_with_empty_watchlist_omits_portfolio_section(tmp_path, monkeypatch, capsys):
    _watchlist(tmp_path)
    monkeypatch.setenv("PORTFOLIOS_DIR", str(tmp_path))

    def fake_market_news(*_args, **_kwargs):
        return {
            "headlines": [
                {"source": "CNBC", "title": "Headline one", "link": "https://example.com/1"},
                {"source": "Yahoo", "title": "Headline two", "link": "https://example.com/2"},
            ],
            "markets": {
                "us": {
                    "name": "US Markets",
                    "indices": {"^GSPC": {"name": "S&P 500", "data": {"price": 100, "change_percent": 1.0}}},
                }
            },
        }

    def fail_quote_fetch(*_args, **_kwargs):
        raise AssertionError("an empty watchlist must not fetch portfolio quotes")

    monkeypatch.setattr(summarize, "get_market_news", fake_market_news)
    monkeypatch.setattr(fetch_news, "_fetch_via_yfinance", fail_quote_fetch)
    monkeypatch.setattr(summarize, "summarize_with_ornith", lambda *_a, **_k: "## Märkte\n\nAlles ruhig.")
    monkeypatch.setattr(summarize, "validate_briefing_structure", lambda *_a, **_k: (True, []))

    args = type(
        "Args",
        (),
        {
            "lang": "de",
            "style": "briefing",
            "time": "morning",
            "model": "ornith",
            "json": True,
            "research": False,
            "deadline": None,
            "fast": True,
            "llm": False,
            "debug": False,
        },
    )()

    summarize.generate_briefing(args)
    data = json.loads(capsys.readouterr().out)
    assert data["portfolio_message"] == ""
    assert data["raw_data"]["portfolio"] is None
    assert data["macro_message"]
