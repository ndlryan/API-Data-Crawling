"""
Step 1:
- Ensure auto resume if program accidentally crashed 
- Supervisord
"""

# ----- Create config (bash)-----

nano ~/supervisord.conf

# ----- In which -----

[supervisord]
logfile=/Users/mac/supervisord.log
pidfile=/Users/mac/supervisord.pid
childlogdir=/Users/mac/

[program:tiki_scraper]
command=/usr/local/bin/python3 /Users/mac/Project2.py
directory=/Users/mac/
autostart=true
autorestart=true
stderr_logfile=/Users/mac/Project2.err.log
stdout_logfile=/Users/mac/Project2.out.log


#!/usr/bin/env python3
"""
Step 2:
- Get data from API
- Standardized name/description columns
- Save results into .tsv file
- Save "exceptions" into erros.log for later check
- Deduplicate twice (begin & after)
- Check point (resume where it stopped)
- Progress bar
"""

import asyncio
import aiohttp
import pandas as pd
from tqdm import tqdm #progress bar
import logging
import os
import csv
import re

# ----- SET UP -----
INPUT_FILE = "product_id.xlsx" #https://1drv.ms/u/s!AukvlU4z92FZgp4xIlzQ4giHVa5Lpw?e=qDXctn
OUTPUT_FILE = "product_results.tsv"
LOG_FILE = "errors.log"
API_URL = "https://api.tiki.vn/product-detail/api/v1/products/{}"

RETRIES = 5
CONCURRENNT = 20
BATCH_SIZE = 5000

FIELDS = ["id", "name", "url_key", "price", "description", "image_url", "missing_fields"]

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ----- STANDARDIZATION -----
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\b(p|img|id|style|src)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[^a-zA-Z0-9À-ỹà-ỹ\s.,!?():;\"'-]", " ", text)
    text = text.lower()
    text = " ".join(text.split())
    return text

# ----- LOAD ID & REMOVE DUPLICATES -----
def load_product_ids():
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")

    df = pd.read_excel(INPUT_FILE)
    df.columns = df.columns.str.strip().str.lower()
    if "id" in df.columns:
        ids = df["id"].dropna().astype(int).tolist()
    else:
        ids = df.iloc[:, 0].dropna().astype(int).tolist()

    before = len(ids)                   # Count total IDs before deduplication
    ids = list(dict.fromkeys(ids))      # Remove duplicates, keep order
    after = len(ids)                    # Count after deduplication
    if before != after:                 # Warn if duplicates were removed
        print(f"⚠️ Removed {before - after} duplicate IDs at input stage.")
    return ids

# ----- Fetch Product -----
async def fetch_product(session: aiohttp.ClientSession, pid: int, semaphore: asyncio.Semaphore) -> dict:
    url = API_URL.format(pid)

    async with semaphore:      # Limit concurrent requests
        for attempt in range(1, RETRIES + 1):   # Retry loop
            try:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = {              # Extract required fields
                            "id": pid,
                            "name": clean_text(data.get("name")),
                            "url_key": data.get("url_key"),
                            "price": data.get("price"),
                            "description": clean_text(data.get("description")),
                            "image_url": (data.get("images", [{}])[0].get("base_url") if data.get("images") else None)
                        }
                        # Track missing fields for this product
                        missing = [k for k, v in result.items() if k != "id" and (v is None or v == "")]
                        result["missing_fields"] = ",".join(missing) if missing else ""
                        return result           # Return cleaned result

                    elif resp.status in (429, 500, 502, 503, 504):
                        # Temporary errors → retry
                        await asyncio.sleep(2 * attempt)  # Exponential backoff
                    else:
                        logging.error(f"FAILED {pid}, status {resp.status}")  # Log permanent failure
                        break
            except Exception as e:              # Handle exceptions (timeout, network error, etc.)
                logging.error(f"EXCEPTION {pid}, error {e}")

        # If all retries fail, return "empty row" with only ID
        return {field: None if field != "id" else pid for field in FIELDS}

# ----- Process Batches -----
async def process_batch(batch_ids, semaphore):
    results = []
    connector = aiohttp.TCPConnector(limit=CONCURRENNT)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_product(session, pid, semaphore) for pid in batch_ids]
        for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Batch"):
            result = await coro
            results.append(result)
    return results

# ----- Main Function -----
async def main():
    product_ids = load_product_ids()
    done_ids = set()

    # Resume previous run if file exists
    if os.path.exists(OUTPUT_FILE):
        df_done = pd.read_csv(OUTPUT_FILE, sep="\t")  # Load finished rows
        done_ids = set(df_done["id"].tolist())       # Extract IDs already processed
    else:
        df_done = pd.DataFrame(columns=FIELDS)

    # Filter out IDs already processed
    todo_ids = [pid for pid in product_ids if pid not in done_ids]
    print(f"Total IDs: {len(product_ids)} | Already done: {len(done_ids)} | Remaining: {len(todo_ids)}")

    semaphore = asyncio.Semaphore(CONCURRENNT)
    write_header = not os.path.exists(OUTPUT_FILE)

    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        if write_header:
            writer.writeheader()

        # Process in batches
        for i in range(0, len(todo_ids), BATCH_SIZE):
            batch_ids = todo_ids[i:i + BATCH_SIZE]  # Slice current batch
            print(f"\n🚀 Processing batch {i//BATCH_SIZE + 1} ({len(batch_ids)} items)...")
            results = await process_batch(batch_ids, semaphore)
            for row in results:                 # Loop through all rows in the current batch
                writer.writerow(row)            # Checkpoint: Write each row immediately into the output file

# ----- Cleanup & Deduplicate 2nd time -----
    df = pd.read_csv(OUTPUT_FILE, sep="\t", encoding="utf-8-sig")  # Reload full results

    # Deduplicate: keep row with fewer missing fields
    def missing_count(row):
        if pd.isna(row["missing_fields"]) or str(row["missing_fields"]).strip() == "":
            return 0
        return len(str(row["missing_fields"]).split(","))

    df["missing_count"] = df.apply(missing_count, axis=1)
    df = df.sort_values(by=["id", "missing_count"])
    df = df.drop_duplicates(subset="id", keep="first").drop(columns=["missing_count"])
    # Remove duplicate IDs, keep best record

    df.to_csv(OUTPUT_FILE, sep="\t", index=False, encoding="utf-8-sig")

# ----- Summary -----
    fail_mask = df[['name', 'url_key', 'price', 'description', 'image_url']].isna().all(axis=1)
    # Failures: rows where all fields except id are empty
    fail_count = fail_mask.sum()                       # Count failed rows
    complete_count = len(df) - fail_count              # Count successful rows
    missing_fields_count = df['missing_fields'].apply(
        lambda x: bool(str(x).strip()) and str(x).lower() != 'nan'
    ).sum()                                            # Count rows with missing fields

    # Print summary
    print("\n========== Crawl Summary ==========")
    print(f"Total products: {len(df)}")
    print(f"✅ Complete: {complete_count}")
    print(f"❌ Failures: {fail_count}")
    print(f"Products with missing fields (still counted as complete): {missing_fields_count}")
    print("==================================\n")

# ----- Run Script -----
if __name__ == "__main__":
    asyncio.run(main())         # Run the main() coroutine


#!/usr/bin/env python3
"""
Step 3:
- Work with exceptions using errors.log file
- Ensure no valid record left behind
"""

import re
import panda as pd

LOG_FILE = "errors.log"
OUTPUT_FILE = "failed_ids.xlsx"

pattern = re.compile(r"(?:FAILED|EXCEPTION)\s+(\d+)")

failed_ids = []

with open(LOG_FILE, "r", encoding="utf-8") as f:
    for line in f:
        match = pattern.search(line)       # Look for FAILED or EXCEPTION + number
        if match:
            failed_ids.append(int(match.group(1)))  # Extract the ID as integer

# ----- Deduplicate Once More -----
failed_ids = list(sorted(set(failed_ids)))
print(f"✅ Extracted {len(failed_ids)} unique failed IDs from {LOG_FILE}")

if failed_ids:
    df = pd.DataFrame(failed_ids, columns=["id"])
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"💾 Saved IDs to {OUTPUT_FILE}")
else:
    print("⚠️ No failed IDs found in the log. Nothing to save.")

"""
Step 4:
- Rerun on main script with INPUT_FILE = "failed_ids.xlsx"
- If there's any valid record, chances will be applied to "product_results.tsv"
- Orelse, nothing happenn
"""
