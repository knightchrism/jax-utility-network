"""Polite HTTP for third-party data sites (modeled on geoknight-openatlas/etl/openatlas_etl/polite.py).

Rules: honest User-Agent, robots.txt checked before each new host, >= 20 s between requests,
no retries: the first error or block raises Blocked and the caller must stop.
Use estimate(n_requests) before a run; it warns when a run would exceed 4 hours (> 720 requests).
"""
import sys, time, urllib.robotparser
from urllib.parse import urlparse

import requests

USER_AGENT = "GeoKnightGIS-bot/1.0 (+https://geoknightgis.com; info@geoknightgis.com)"
MIN_DELAY = 20.0
MAX_HOURS = 4.0
MAX_REQUESTS = int(MAX_HOURS * 3600 / MIN_DELAY)  # 720


class Blocked(RuntimeError):
    """Raised on the first block/error. Callers must stop, not retry."""


def estimate(n_requests, delay=MIN_DELAY, label="run", stream=sys.stderr):
    """Print a pre-run estimate; warn if the run would take more than 4 hours (> 720 requests).
    Returns estimated hours."""
    delay = max(MIN_DELAY, delay)
    hours = n_requests * delay / 3600
    print(f"[polite] {label}: ~{n_requests} requests x {delay:.0f} s = ~{hours:.1f} h", file=stream)
    if n_requests > MAX_REQUESTS:
        print(f"[polite] WARNING: {label} would take more than {MAX_HOURS:.0f} hours "
              f"({n_requests} > {MAX_REQUESTS} requests). Narrow the run or split it before starting.", file=stream)
    return hours


class PoliteClient:
    def __init__(self, delay=None, user_agent=USER_AGENT):
        self.delay = max(MIN_DELAY, delay or MIN_DELAY)
        self.ua = user_agent
        self.s = requests.Session()
        self.s.headers["User-Agent"] = user_agent
        self._last = 0.0
        self._robots = {}
        self.requests_made = 0

    def _wait(self):
        gap = time.monotonic() - self._last
        if self._last and gap < self.delay:
            time.sleep(self.delay - gap)

    def check_robots(self, url):
        p = urlparse(url); base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            self._wait()
            try:
                r = self.s.get(base + "/robots.txt", timeout=30)
            except requests.RequestException as e:
                raise Blocked(f"robots.txt request failed: {e!r}") from e
            finally:
                self._last = time.monotonic(); self.requests_made += 1
            rp = urllib.robotparser.RobotFileParser()
            if r.status_code == 200 and "text" in r.headers.get("content-type", ""):
                rp.parse(r.text.splitlines())
            elif r.status_code in (401, 403, 429):
                raise Blocked(f"robots.txt returned {r.status_code}")
            else:
                rp.parse([])  # no robots.txt published -> allowed
            self._robots[base] = rp
        if not self._robots[base].can_fetch(self.ua, url):
            raise Blocked(f"robots.txt disallows {url}")

    def request(self, method, url, timeout=120, **kw):
        """One request; raises Blocked on any network error or non-200 status."""
        self.check_robots(url)
        self._wait()
        try:
            r = self.s.request(method, url, timeout=timeout, **kw)
        except requests.RequestException as e:
            raise Blocked(f"request failed: {e!r}") from e
        finally:
            self._last = time.monotonic(); self.requests_made += 1
        if r.status_code != 200:
            raise Blocked(f"HTTP {r.status_code} from {url}")
        return r

    def get(self, url, params=None, **kw):
        return self.request("GET", url, params=params, **kw)

    def get_json(self, url, params=None, **kw):
        r = self.get(url, params=params, **kw)
        try:
            j = r.json()
        except ValueError as e:
            raise Blocked(f"non-JSON response from {url}") from e
        if isinstance(j, dict) and "error" in j:
            raise Blocked(f"ArcGIS error: {j['error']}")
        return j

    def get_bytes(self, url, params=None, **kw):
        return self.get(url, params=params, **kw).content
