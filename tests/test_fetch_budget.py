import sys
import unittest
import urllib.error
import subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_news as fetch

class FetchBudgetTests(unittest.TestCase):
    def test_terminal_http_errors_do_not_retry(self):
        for status in (404, 429):
            with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
                    "https://example.com", status, "unavailable", {}, None)) as request:
                self.assertEqual(fetch.fetch_rss("https://example.com"), [])
                self.assertEqual(request.call_count, 1)

    def test_stalled_yahoo_batch_is_bounded(self):
        with patch("fetch_news._run_fetch_process", side_effect=subprocess.TimeoutExpired("yahoo", 1)) as run:
            self.assertEqual(fetch._fetch_via_yfinance(["TWTR", "AAPL"], 30, None), {})
            self.assertLessEqual(run.call_args.kwargs["timeout"], 10)

    def test_successful_batch_is_preserved(self):
        with patch("fetch_news._run_fetch_process", return_value=subprocess.CompletedProcess(
                [], 0, '{"AAPL": {"price": 123}}')):
            self.assertEqual(fetch._fetch_via_yfinance(["AAPL"], 30, None),
                             {"AAPL": {"price": 123}})

    def test_process_timeout_kills_descendants(self):
        import time
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            fetch._run_fetch_process(
                [sys.executable, "-c",
                 "import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); time.sleep(30)"],
                timeout=0.2, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertLess(time.monotonic() - started, 3)

    def test_exhausted_quote_budget_does_not_start_more_fetches(self):
        with (
            patch.object(fetch, "QUOTE_JOB_DEADLINE", 100),
            patch.object(fetch, "QUOTE_DEADLINE", 50),
            patch.object(fetch, "time_left", return_value=0),
            patch.object(fetch, "_fetch_via_openbb") as quote,
            patch.object(fetch, "_fetch_via_yfinance") as fallback,
        ):
            self.assertEqual(fetch.fetch_market_data(["TWTR", "AAPL"], deadline=100), {})
            quote.assert_not_called()
            fallback.assert_not_called()
