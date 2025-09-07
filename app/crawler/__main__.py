import argparse
import logging
import sys

from app.crawler.downloader import download_if_changed
from app.core.config import settings


def main(argv=None) -> int:
    # Basic logging configuration for CLI runs
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    p = argparse.ArgumentParser(description="Download URL if changed and save to sources/")
    p.add_argument("url", nargs="?", help="Target URL to download (default: settings.CRAWL_URL)")
    p.add_argument("--prefix", default="auction_data_", help="Filename prefix (default: auction_data_)")
    p.add_argument("--ext", default="csv", help="File extension (default: csv)")
    p.add_argument("--date", default=None, help="Override YYMMDD date in filename")
    args = p.parse_args(argv)

    url = args.url or settings.CRAWL_URL
    if not url:
        p.error("No URL provided and settings.CRAWL_URL is empty")

    logging.getLogger("crawler").info("Starting crawl: %s", url)

    result = download_if_changed(
        url,
        filename_prefix=args.prefix,
        file_ext=args.ext,
        date_override=args.date,
    )
    changed = result["changed"]
    status = result["status"]
    path = result["path"]
    print({"changed": changed, "status": status, "path": path})
    if not changed and status in (200, 304):
        logging.getLogger("crawler").info("No change detected for %s", url)
    return 0 if status in (200, 304) else 1


if __name__ == "__main__":
    raise SystemExit(main())
