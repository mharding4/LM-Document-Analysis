import os
import pandas as pd
from datetime import datetime
import requests
import json
from time import sleep
from sec_edgar_downloader import Downloader
from requests.exceptions import RequestException, Timeout
import textwrap

# --- CONFIGURATION ---
TICKERS = ["AAPL"]  # ✅ Try one ticker at a time
DOWNLOAD_DIR = "./sec_filings"
OLLAMA_URL = "http://localhost:11434/api/generate"  # ✅ Fixed endpoint
MODEL_NAME = "mistral:instruct"  # ✅ Updated to chat-capable model
MAX_CONTENT_CHARS = 300  # 🔻 Reduce content for faster LLM response
MAX_FILINGS_PER_TICKER = 3
RETRY_COUNT = 1
TIMEOUT_SECONDS = 20  # ⏱️ Shorter timeout
DELAY_BETWEEN_QUERIES = 2  # 💤 Small delay
MOCK_MODE = True  # ✅ Set to False to use real LLM

# --- HELPER FUNCTION ---
def query_ollama(prompt, retries=RETRY_COUNT):
    if MOCK_MODE:
        return json.dumps({
            "company_name": "Example Corp",
            "stock_name": "EXMPL",
            "filing_time": datetime.now().strftime("%Y-%m-%d"),
            "new_product": "Product X",
            "product_description": "An AI-powered analytics engine for real-time decision making."
        })
    for attempt in range(retries + 1):
        try:
            response = requests.post(OLLAMA_URL, json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False
            }, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json().get("response", "")
        except Timeout:
            print(f"⏳ Timeout. Retrying... ({attempt + 1}/{retries})")
            sleep(1)
        except Exception as e:
            print(f"❌ Request failed: {e}")
            break
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
                Extract new product info from this SEC 8-K filing. Reply ONLY in JSON with:
                company_name, stock_name, filing_time, new_product, product_description (<=180 chars).

                Filing:
                {chunks[0]}
                """

                llm_output = query_ollama(prompt)
                sleep(DELAY_BETWEEN_QUERIES)
                if not llm_output:
                    raise Exception("No valid LLM output")

                data = json.loads(llm_output.strip())
                results.append([
                    data.get("company_name", ""),
                    data.get("stock_name", ""),
                    data.get("filing_time", datetime.today().strftime("%Y-%m-%d")),
                    data.get("new_product", ""),
                    data.get("product_description", "")
                ])
                processed.add(file)

            except (RequestException, json.JSONDecodeError, Exception) as e:
                print(f"⚠️ Skipped {file_path}: {e}")

# --- SAVE TO CSV ---
df = pd.DataFrame(results, columns=[
    "Company Name", "Stock Name", "Filing Time", "New Product", "Product Description"
])
df.to_csv("product_announcements.csv", sep="|", index=False)
print("✅ Done. Saved: product_announcements.csv")