"""Load test (spec section 4): 200 people at once, browsing and rushing one event.

usage: python rush.py BASE_URL SETUP_JSON [--browse-seconds 30] [--think-seconds 0]

SETUP_JSON is what `manage.py prepare_load_test` prints. Two phases:
1. Browse: every user loads the main pages over and over for a while, with an
   optional pause between pages, as a reader would (0 is the hardest case).
2. Rush: every user opens the event, then all press "register" at the same moment.
Prints status codes and response times. The seat count is checked afterwards in
the database (docs/LAUNCH.md). Needs only httpx.
"""

import argparse
import json
import re
import statistics
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx

PAGES = ["/", "/services/", "/events/", "/blog/", "/shop/", "/booking/", "/about/"]


def percentile(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * share))] if ordered else 0


def report(title, results):
    codes = Counter(code for code, _ in results)
    times = [seconds for _, seconds in results]
    print(f"\n{title}: {len(results)} requests")
    print(f"  status codes: {dict(sorted(codes.items()))}")
    if times:
        print(
            f"  time: median {statistics.median(times):.2f}s, "
            f"95% under {percentile(times, 0.95):.2f}s, slowest {max(times):.2f}s"
        )


def timed(client, method, url, **kwargs):
    started = time.perf_counter()
    try:
        response = client.request(method, url, **kwargs)
        return response, (response.status_code, time.perf_counter() - started)
    except httpx.HTTPError as exc:
        return None, (type(exc).__name__, time.perf_counter() - started)


def browse(base, session, until, think, results, lock):
    with httpx.Client(base_url=base, cookies={"sessionid": session}, timeout=60) as client:
        index = 0
        while time.monotonic() < until:
            _, outcome = timed(client, "GET", PAGES[index % len(PAGES)])
            with lock:
                results.append(outcome)
            index += 1
            time.sleep(think)


def rush(base, session, event, barrier, results, lock):
    with httpx.Client(base_url=base, cookies={"sessionid": session}, timeout=60) as client:
        page, outcome = timed(client, "GET", event)
        token = (
            re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text) if page else None
        )
        barrier.wait()  # everyone presses the button together
        if token is None:
            with lock:
                results.append(("no form", outcome[1]))
            return
        # The CSRF cookie is HTTPS-only in production settings; on a plain-HTTP test
        # copy the client would not send it back, so it is passed on explicitly
        csrf = page.cookies.get("csrftoken", "")
        _, outcome = timed(
            client,
            "POST",
            f"{event}register/",
            data={"csrfmiddlewaretoken": token.group(1)},
            headers={
                "Referer": f"{base}{event}",
                "Cookie": f"sessionid={session}; csrftoken={csrf}",
            },
        )
        with lock:
            results.append(outcome)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("setup")
    parser.add_argument("--browse-seconds", type=int, default=30)
    parser.add_argument("--think-seconds", type=float, default=0)
    args = parser.parse_args()
    with open(args.setup, encoding="utf-8") as file:
        setup = json.load(file)
    sessions, base, lock = setup["sessions"], args.base.rstrip("/"), threading.Lock()

    results = []
    until = time.monotonic() + args.browse_seconds
    if args.browse_seconds:
        with ThreadPoolExecutor(max_workers=len(sessions)) as pool:
            for session in sessions:
                pool.submit(browse, base, session, until, args.think_seconds, results, lock)
        report(
            f"Browse ({len(sessions)} users, {args.browse_seconds}s, "
            f"{args.think_seconds}s between pages)",
            results,
        )

    results = []
    barrier = threading.Barrier(len(sessions))
    with ThreadPoolExecutor(max_workers=len(sessions)) as pool:
        for session in sessions:
            pool.submit(rush, base, session, setup["event"], barrier, results, lock)
    report(f"Registration rush ({len(sessions)} users, {setup['capacity']} seats)", results)


if __name__ == "__main__":
    main()
