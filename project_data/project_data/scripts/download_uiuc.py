from __future__ import annotations
import argparse
import re
import time
from dataclasses import dataclass
from typing import Iterable
import urllib.request
from pathlib import Path

OUTPUT_DIR = Path("project_data/raw_uiuc")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INDEX_URL = "https://m-selig.ae.illinois.edu/ads/coord_seligFmt/"


@dataclass(frozen=True)
class DownloadResult:
    filename: str
    status: str
    message: str = ""


def http_get(url: str, timeout_s: int) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return resp.read()


def list_dat_files(index_url: str, timeout_s: int) -> list[str]:
    html = http_get(index_url, timeout_s=timeout_s).decode("utf-8", errors="ignore")
    names = re.findall(r'href="([^"]+\.dat)"', html, flags=re.IGNORECASE)
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        base = n.split("/")[-1]
        if not base.lower().endswith(".dat"):
            continue
        if base in seen:
            continue
        seen.add(base)
        out.append(base)
    out.sort(key=lambda s: s.lower())
    return out


def download_one(base_url: str, filename: str, out_dir: Path, timeout_s: int, retries: int) -> DownloadResult:
    out_path = out_dir / filename
    if out_path.exists() and out_path.stat().st_size > 0:
        return DownloadResult(filename=filename, status="skip", message="exists")

    url = base_url.rstrip("/") + "/" + filename
    last_err: str = ""
    for _ in range(max(1, retries)):
        try:
            data = http_get(url, timeout_s=timeout_s)
            out_path.write_bytes(data)
            if out_path.stat().st_size == 0:
                out_path.unlink(missing_ok=True)
                last_err = "empty file"
                continue
            return DownloadResult(filename=filename, status="ok")
        except Exception as e:
            last_err = str(e)
            time.sleep(0.3)
            continue

    out_path.unlink(missing_ok=True)
    return DownloadResult(filename=filename, status="fail", message=last_err)


def iter_with_limit(items: list[str], limit: int) -> Iterable[str]:
    if limit <= 0:
        yield from items
        return
    for i, x in enumerate(items):
        if i >= limit:
            break
        yield x

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--index-url", type=str, default=INDEX_URL)
    parser.add_argument("--out-dir", type=str, default=str(OUTPUT_DIR))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = list_dat_files(args.index_url, timeout_s=args.timeout)
    if not files:
        raise RuntimeError(f"未能从索引页解析到 .dat 文件: {args.index_url}")

    base_url = args.index_url.rstrip("/")

    ok = 0
    fail = 0
    skip = 0
    total = min(args.limit, len(files)) if args.limit > 0 else len(files)

    for i, filename in enumerate(iter_with_limit(files, args.limit), 1):
        r = download_one(base_url, filename, out_dir=out_dir, timeout_s=args.timeout, retries=args.retries)
        if r.status == "ok":
            ok += 1
        elif r.status == "skip":
            skip += 1
        else:
            fail += 1

        if i % 25 == 0 or i == total:
            print(f"进度 {i}/{total} ok={ok} skip={skip} fail={fail}")

        if args.sleep > 0:
            time.sleep(args.sleep)

    print(f"完成 ok={ok} skip={skip} fail={fail}")
    print(f"输出目录: {out_dir.resolve()}")

if __name__ == "__main__":
    main()
