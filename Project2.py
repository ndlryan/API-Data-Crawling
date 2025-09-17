#!/usr/bin/env python3
"""
Tiki Product Scraper
- Scrapes product data from Tiki API
- Cleans name and description (Vietnamese, lowercase, HTML removed)
- Tracks missing fields but counts products as complete
- Outputs tab-delimited .tsv file for Excel
"""

import asyncio
import aiohttp
import pandas as pd
from tqdm import tqdm
import logging
import os
import csv
import re
from collections import Counter

# -------------------- Configuration --------------------
INPUT_FILE = "product_id.xlsx"            # Input Excel file with product IDs
OUTPUT_FILE = "product_results.tsv"       # Output TSV file
LOG_FILE = "errors.log"                   # Log file for failed requests
API_URL = "https://api.tiki.vn/product-detail/api/v1/products/{}"

RETRIES = 5           # Number of retries for failed requests
CONCURRENT = 20       # Maximum number of concurrent requests
BATCH_SIZE = 5000     # Number of products processed per batch

FIELDS = ["id", "name", "url_key", "price", "description", "image_url", "missing_fields"]

# Setup logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -------------------- Text Cleaning --------------------
def clean_text(text: str) -> str:
    """Clean text completely: remove HTML, leftover attributes, nonsense chars, lowercase, normalize spaces"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)  # Remove all HTML tags
    text = re.sub(r"\b(p|img|id|style|src)\b", " ", text, flags=re.IGNORECASE)  # Remove leftover attribute words
    text = re.sub(r"[^a-zA-Z0-9À-ỹà-ỹ\s.,!?():;\"'-]", " ", text)  # Keep letters, numbers, punctuation
    text = text.lower()  # Convert to lowercase
    text = " ".join(text.split())  # Normalize spaces
    return text

# -------------------- Load Product IDs --------------------
def load_product_ids():
    """Load product IDs from Excel"""
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")

    df = pd.read_excel(INPUT_FILE)
    df.columns = df.columns.str.strip().str.lower()
    if "id" in df.columns:
        return df["id"].tolist()
    return df.iloc[:, 0].tolist()

# -------------------- Fetch Product Data --------------------
async def fetch_product(session: aiohttp.ClientSession, pid: int, semaphore: asyncio.Semaphore) -> dict:
    """Fetch product data asynchronously with retries, clean text, track missing fields"""
    url = API_URL.format(pid)

    async with semaphore:
        for attempt in range(1, RETRIES + 1):
            try:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = {
                            "id": pid,
                            "name": clean_text(data.get("name")),
                            "url_key": data.get("url_key"),
                            "price": data.get("price"),
                            "description": clean_text(data.get("description")),
                            "image_url": (data.get("images", [{}])[0].get("base_url") if data.get("images") else None)
                        }
                        # Track missing fields (but still count as complete)
                        missing = [k for k, v in result.items() if k != "id" and (v is None or v == "")]
                        result["missing_fields"] = ",".join(missing) if missing else ""
                        return result

                    elif resp.status in (429, 500, 502, 503, 504):
                        await asyncio.sleep(2 * attempt)  # Retry
                    else:
                        logging.error(f"FAILED {pid}, status {resp.status}")
                        break
            except Exception as e:
                logging.error(f"EXCEPTION {pid}, error {e}")

        # Return empty product for failed requests (counted as fail)
        return {field: None if field != "id" else pid for field in FIELDS}

# -------------------- Process Batches --------------------
async def process_batch(batch_ids, semaphore):
    """Process a batch of product IDs asynchronously"""
    results = []
    connector = aiohttp.TCPConnector(limit=CONCURRENT)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_product(session, pid, semaphore) for pid in batch_ids]
        for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Batch"):
            result = await coro
            results.append(result)
    return results

# -------------------- Main Function --------------------
async def main():
    product_ids = load_product_ids()
    done_ids = set()

    # Resume previous run if file exists
    if os.path.exists(OUTPUT_FILE):
        df_done = pd.read_csv(OUTPUT_FILE, sep="\t")
        done_ids = set(df_done["id"].tolist())
    else:
        df_done = pd.DataFrame(columns=FIELDS)

    todo_ids = [pid for pid in product_ids if pid not in done_ids]
    print(f"Total IDs: {len(product_ids)} | Already done: {len(done_ids)} | Remaining: {len(todo_ids)}")

    semaphore = asyncio.Semaphore(CONCURRENT)
    write_header = not os.path.exists(OUTPUT_FILE)

    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        if write_header:
            writer.writeheader()

        # Process in batches
        for i in range(0, len(todo_ids), BATCH_SIZE):
            batch_ids = todo_ids[i:i + BATCH_SIZE]
            print(f"\n🚀 Processing batch {i//BATCH_SIZE + 1} ({len(batch_ids)} items)...")
            results = await process_batch(batch_ids, semaphore)
            for row in results:
                writer.writerow(row)

    # ---------- Crawl Summary ----------
    df = pd.read_csv(OUTPUT_FILE, sep="\t", encoding="utf-8-sig")
    # Fail = products where all fields except ID are None
    fail_mask = df[['name', 'url_key', 'price', 'description', 'image_url']].isna().all(axis=1)
    fail_count = fail_mask.sum()
    complete_count = len(df) - fail_count
    missing_fields_count = df['missing_fields'].apply(lambda x: bool(x.strip())).sum()

    # Count HTTP errors
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            errors = f.readlines()
        error_codes = [line.split()[-1] for line in errors if "FAILED" in line]
        error_summary = Counter(error_codes)
    except FileNotFoundError:
        error_summary = Counter()

    # Print summary
    print("\n========== Crawl Summary ==========")
    print(f"Total products: {len(df)}")
    print(f"✅ Complete: {complete_count}")
    print(f"❌ Failures: {fail_count}")
    print(f"Products with missing fields (still counted as complete): {missing_fields_count}")
    print("\nError summary (HTTP codes):")
    if error_summary:
        for code, count in error_summary.items():
            print(f"{code}: {count}")
    else:
        print("No HTTP errors logged.")
    print("==================================\n")

# -------------------- Run Script --------------------
if __name__ == "__main__":
    asyncio.run(main())