# Tiki API Data Crawler

[![Python](https://img.shields.io/badge/Built%20With-Python-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Data Source](https://img.shields.io/badge/API-Tiki-orange)](https://tiki.vn/)
[![Process Manager](https://img.shields.io/badge/Managed%20By-Supervisor-lightgrey)](http://supervisord.org/)

---

## Overview

This repository provides a **Python-based crawler** (`Tiki_Crawler.py`) that collects large-scale product data from the **Tiki API**.  
It is designed for **stability, resumption, and scalability** — capable of handling hundreds of thousands of API calls while maintaining fault tolerance.

---

## Features

- 🔄 Reads product IDs directly from an Excel input file  
- 🚀 Extracts live product data from Tiki API endpoints  
- 🧾 Saves output in **TSV** (tab-separated) format  
- ⚠️ Logs all failed or retried requests to a separate log file  
- ♻️ Supports resuming partially completed runs  
- ⚙️ Compatible with **Supervisord** for continuous background operation  

---

## Project Structure

| File | Description |
|------|--------------|
| `Tiki_Crawler.py` | Main Python crawler script |
| `product_id.xlsx` | Input list of product IDs (download [here](https://1drv.ms/u/s!AukvlU4z92FZgp4xIlzQ4giHVa5Lpw?e=qDXctn)) |
| `product_results.tsv` | Output file containing scraped results |
| `errors.log` | Log file capturing failed requests and exceptions |

---

## Installation

Clone the repository:

```bash
git clone https://github.com/ndlryan/API-Data-Crawling.git
cd API-Data-Crawling
```

Install dependencies (if any) listed in requirements.txt:
```bash
pip install -r requirements.txt
```

---

## Running the Crawler

Run directly from terminal:

```bash
python Tiki_Crawler.py
```

This will:
1. Load product IDs from product_id.xlsx
2. Crawl Tiki API for product details
3. Write results to product_results.tsv
4. Record any failed IDs or exceptions in errors.log

---

## Process Management with Supervisord
For long-running or auto-restarting crawls, you can manage the crawler with Supervisord.

### 1. Install Supervisor

```bash
pip install supervisor
```

### 2. Create Configuration File

```ini
[unix_http_server]
file=/tmp/supervisor.sock

[supervisord]
logfile=supervisord.log
pidfile=/tmp/supervisord.pid
childlogdir=./logs

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix:///tmp/supervisor.sock

[program:tiki_crawler]
command=python3 /path/to/API-Data-Crawling/Tiki_Crawler.py
directory=/path/to/API-Data-Crawling
autostart=true
autorestart=true
stderr_logfile=./logs/tiki_crawler.err.log
stdout_logfile=./logs/tiki_crawler.out.log
```
  - 🔧 Replace /path/to/API-Data-Crawling with your actual project path.

### 3. Start and Monitor

```bash
supervisord -c supervisord.conf
supervisorctl -c supervisord.conf status
```

Restart or stop the crawler anytime:
```bash
supervisorctl -c supervisord.conf restart tiki_crawler
supervisorctl -c supervisord.conf stop tiki_crawler
```

---

## Logs and Outputs

Main output: product_results.tsv — product metadata

Log file: errors.log — failed IDs, API errors, exceptions

Supervisor logs: stored under ./logs/ when using supervisord.conf

---

## Notes

Always verify your input file product_id.xlsx for valid IDs.

Avoid excessive API calls; introduce short delays between requests if needed.

For continuous operation, use Supervisor to prevent downtime or data loss.

---

## Author

**Ryan**  
[GitHub Profile](https://github.com/ndlryan)

A resilient, fault-tolerant Tiki API crawler — lightweight, automated, and built for production.
