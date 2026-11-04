"""
Crawl Pages - tai cham trang san pham de dua vao extract_catalog.py.

Lich su va an toan:
  - Doc robots.txt cua tung web; URL bi cam thi bo qua.
  - Nghi giua 2 request (mac dinh 5 giay, hoac Crawl-delay cua web neu lon hon).
  - Moi lan chay toi da --max-pages trang; trang da tai thi bo qua (chay tiep lan sau).
  - Chi luu HTML vao data/crawled/ (da gitignore). Khong commit noi dung cua web khac.
  - Doc dieu khoan su dung cua tung web truoc khi crawl.

Chay:
    # danh sach URL trong file (moi dong mot URL, dong bat dau bang # bo qua)
    python scripts/crawl_pages.py --urls data/crawl_urls.txt --max-pages 50

    # lay URL tu sitemap, loc bang regex
    python scripts/crawl_pages.py --sitemap https://example.com/sitemap.xml --match "/dtdd/" --max-pages 50

Sau do:
    python scripts/extract_catalog.py --pages data/crawled --out data/catalog_crawled.jsonl --max-pages 50
    python scripts/ingest_data.py --catalog data/catalog.jsonl data/catalog_crawled.jsonl
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

USER_AGENT = "ShoppingAssistantDemoBot/0.1 (personal portfolio project)"
FIRST_ID = 1001  # tranh trung id voi 30 trang mau trong data/raw_pages


class PoliteFetcher:
    def __init__(self, delay: float, timeout: float = 20) -> None:
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_request: dict[str, float] = {}

    def _robots_for(self, url: str) -> RobotFileParser | None:
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rp = RobotFileParser()
            try:
                resp = self.session.get(f"{origin}/robots.txt", timeout=self.timeout)
                if resp.status_code >= 400:
                    # Khong co robots.txt (4xx) -> duoc phep; loi server (5xx) -> dung lai cho an toan
                    rp.parse([] if resp.status_code < 500 else ["User-agent: *", "Disallow: /"])
                else:
                    rp.parse(resp.text.splitlines())
            except requests.RequestException as exc:
                print(f"  ! Khong doc duoc robots.txt cua {origin}: {exc}")
                rp = None
            self._robots[origin] = rp
        return self._robots[origin]

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        return rp is not None and rp.can_fetch(USER_AGENT, url)

    def _wait(self, url: str) -> None:
        host = urlparse(url).netloc
        rp = self._robots.get(f"{urlparse(url).scheme}://{host}")
        crawl_delay = (rp.crawl_delay(USER_AGENT) if rp else None) or 0
        gap = max(self.delay, float(crawl_delay))
        elapsed = time.time() - self._last_request.get(host, 0)
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self._last_request[host] = time.time()

    def get(self, url: str) -> requests.Response:
        self._wait(url)
        return self.session.get(url, timeout=self.timeout)


def urls_from_file(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def urls_from_sitemap(fetcher: PoliteFetcher, url: str, pattern: str | None, limit: int) -> list[str]:
    """Doc sitemap (ho tro sitemap index long nhau), tra ve URL khop regex."""
    found: list[str] = []
    queue = [url]
    regex = re.compile(pattern) if pattern else None
    while queue and len(found) < limit:
        sm = queue.pop(0)
        if not fetcher.allowed(sm):
            print(f"  robots.txt cam: {sm}")
            continue
        resp = fetcher.get(sm)
        if resp.status_code != 200:
            print(f"  ! {resp.status_code} {sm}")
            continue
        root = ET.fromstring(resp.content)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        queue += [e.text.strip() for e in root.findall("sm:sitemap/sm:loc", ns) if e.text]
        for e in root.findall("sm:url/sm:loc", ns):
            if e.text and (regex is None or regex.search(e.text)):
                found.append(e.text.strip())
    return found[:limit]


def slugify(url: str) -> str:
    parts = urlparse(url)
    slug = re.sub(r"[^a-z0-9]+", "-", f"{parts.netloc}{parts.path}".lower()).strip("-")
    return slug[:120]


def main() -> None:
    parser = argparse.ArgumentParser(description="Tai cham trang san pham (ton trong robots.txt)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--urls", help="File danh sach URL")
    src.add_argument("--sitemap", help="URL sitemap.xml")
    parser.add_argument("--match", help="Regex loc URL trong sitemap, vd '/dtdd/'")
    parser.add_argument("--out", default="data/crawled")
    parser.add_argument("--max-pages", type=int, default=50, help="So trang toi da moi lan chay")
    parser.add_argument("--delay", type=float, default=5.0, help="Giay nghi toi thieu giua 2 request")
    args = parser.parse_args()

    if args.delay < 1:
        sys.exit("--delay toi thieu 1 giay")

    os.makedirs(args.out, exist_ok=True)
    fetcher = PoliteFetcher(delay=args.delay)

    urls = (
        urls_from_file(args.urls)
        if args.urls
        else urls_from_sitemap(fetcher, args.sitemap, args.match, limit=args.max_pages * 5)
    )

    # Trang da tai (lan truoc) -> bo qua; id tiep theo noi tiep
    existing = os.listdir(args.out)
    done_slugs = {re.sub(r"^\d+-", "", f).removesuffix(".html") for f in existing}
    ids = [int(m.group(1)) for f in existing if (m := re.match(r"(\d+)-", f))]
    next_id = max(ids, default=FIRST_ID - 1) + 1

    saved = skipped = blocked = failed = 0
    for url in urls:
        if saved >= args.max_pages:
            break
        slug = slugify(url)
        if slug in done_slugs:
            skipped += 1
            continue
        if not fetcher.allowed(url):
            blocked += 1
            print(f"  robots.txt cam: {url}")
            continue
        try:
            resp = fetcher.get(url)
        except requests.RequestException as exc:
            failed += 1
            print(f"  ! {url}: {exc}")
            continue
        if resp.status_code != 200 or "html" not in resp.headers.get("Content-Type", "html"):
            failed += 1
            print(f"  ! {resp.status_code} {url}")
            continue

        if "charset" not in resp.headers.get("Content-Type", "").lower():
            # Khong co charset: thu UTF-8 truoc (pho bien o web Viet), roi moi doan
            try:
                resp.content.decode("utf-8")
                resp.encoding = "utf-8"
            except UnicodeDecodeError:
                resp.encoding = resp.apparent_encoding

        fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path = os.path.join(args.out, f"{next_id}-{slug}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"<!-- source: {url} | fetched: {fetched} -->\n")
            f.write(resp.text)
        print(f"  [{next_id}] {url}")
        done_slugs.add(slug)
        next_id += 1
        saved += 1

    print(
        f"\nDa luu {saved} trang, bo qua {skipped} (da co), {blocked} bi robots.txt cam, "
        f"{failed} loi -> {args.out}"
    )


if __name__ == "__main__":
    main()
