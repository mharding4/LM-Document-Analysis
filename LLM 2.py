import os
import pandas as pd
from datetime import datetime
import requests
import json
from time import sleep
from sec_edgar_downloader import Downloader
from requests.exceptions import RequestException
import textwrap

# --- CONFIGURATION ---
TICKERS = [
    "AAPL", "MSFT", "TSLA", "GOOGL", "NVDA", "AMZN", "META", "NFLX", "ORCL", "INTC",
    "ADBE", "CRM", "PYPL", "CSCO", "PEP", "KO", "XOM", "CVX", "PFE", "JNJ",
    "BAC", "WFC", "UNH", "V", "MA", "T", "DIS", "MCD", "NKE", "HD"
]  # ✅ 30 tickers × 10 filings = up to 300 total
DOWNLOAD_DIR = "./sec_filings"
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "mistral:instruct"
MAX_CONTENT_CHARS = 2000
MAX_FILINGS_PER_TICKER = 10  # ⬆️ Increased to gather more data
DELAY_BETWEEN_QUERIES = 0.5  # Slight delay

# --- HELPER FUNCTION ---
def query_ollama(prompt):
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL_NAME,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": False
        }, timeout=None)  # ⏳ Infinite timeout
        response.raise_for_status()
        content = response.json()["message"]["content"]
        return content
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None

# --- DOWNLOAD FILINGS ---
downloader = Downloader("MyCompanyName", "my.email@domain.com", DOWNLOAD_DIR)
for ticker in TICKERS:
    downloader.get("8-K", ticker, limit=MAX_FILINGS_PER_TICKER)

# --- PROCESS FILINGS ---
results = []
processed = set()
for root, _, files in os.walk(DOWNLOAD_DIR):
    for file in files:
        if file.endswith(".txt") and file not in processed:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                chunks = textwrap.wrap(content, MAX_CONTENT_CHARS)
                if not chunks:
                    continue

                prompt = f"""
                From the following SEC 8-K filing, extract product release details ONLY IF a new product is announced.
                Respond in valid JSON with the following keys:
                - company_name
                - stock_name
                - filing_time
                - new_product (true/false)
                - product_description (max 180 characters)

                If no product is announced, return: {{}}

                Filing:
                {chunks[0]}
                """

                print(f"⏳ Querying LLM for {file_path}...")
                llm_output = query_ollama(prompt)
                sleep(DELAY_BETWEEN_QUERIES)
                if not llm_output:
                    raise Exception("No valid LLM output")

                data = json.loads(llm_output.strip())
                if not data or not data.get("new_product"):
                    continue  # ✅ Only keep filings with product launches

                results.append([
                    data.get("company_name", ""),
                    data.get("stock_name", ""),
                    data.get("filing_time", datetime.today().strftime("%Y-%m-%d")),
                    data.get("new_product", ""),
                    data.get("product_description", "")
                ])
                processed.add(file)

                if len(results) >= 100:
                    break

            except (RequestException, json.JSONDecodeError, Exception) as e:
                print(f"⚠️ Skipped {file_path}: {e}")
    if len(results) >= 100:
        break

# --- SAVE TO CSV ---
df = pd.DataFrame(results, columns=[
    "Company Name", "Stock Name", "Filing Time", "New Product", "Product Description"
])
df.to_csv("product_announcements.csv", sep="|", index=False)
print("✅ Done. Saved: product_announcements.csv")
