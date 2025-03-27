import os
import time
import csv
import json
import requests
from datetime import datetime
from sec_edgar_downloader import Downloader

# CONFIGURATION
TICKERS = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]  # Add more tickers if needed
MAX_ENTRIES = 100
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "deepseek-llm"  # or mistral
DOWNLOAD_DIR = "./sec_filings"
CSV_OUTPUT = "product_announcements.csv"

# Initialize SEC downloader
dl = Downloader("MyCompany", "my.email@example.com", DOWNLOAD_DIR)

# Prepare CSV
with open(CSV_OUTPUT, mode="w", newline="") as file:
    writer = csv.writer(file, delimiter="|")
    writer.writerow(["Company Name", "Stock Name", "Filing Time", "New Product", "Product Description"])

    extracted = 0
    for ticker in TICKERS:
        print(f"\n🔎 Processing ticker: {ticker}")
        dl.get("8-K", ticker, limit=15)

        folder = os.path.join(DOWNLOAD_DIR, "sec-edgar-filings", ticker, "8-K")
        if not os.path.exists(folder):
            continue

        for filing in os.listdir(folder):
            filing_path = os.path.join(folder, filing, "full-submission.txt")
            if not os.path.exists(filing_path):
                continue

            try:
                with open(filing_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw_text = f.read()

                chunk = raw_text[:2000]

                # LLM prompt
                prompt = (
                    "You are an SEC 8-K analyst. Extract any new product announcements from the filing text below. "
                    "Respond ONLY in the following JSON format:\n\n"
                    "{\n"
                    '  "company_name": "Example Corp",\n'
                    '  "stock_name": "EXMPL",\n'
                    '  "filing_time": "2025-01-01",\n'
                    '  "new_product": "Product X",\n'
                    '  "product_description": "Short summary of new product (under 180 characters)"\n'
                    "}\n\n"
                    f"FILING TEXT:\n{chunk}"
                )

                # Send to Ollama
                response = requests.post(
                    OLLAMA_URL,
                    json={"model": MODEL, "prompt": prompt, "stream": False},
                    timeout=120,
                )
                response.raise_for_status()
                output = response.json()["response"].strip()

                # Try to parse LLM output
                parsed = json.loads(output)
                if not all(key in parsed for key in ["company_name", "stock_name", "filing_time", "new_product", "product_description"]):
                    raise ValueError("Incomplete JSON")

                writer.writerow([
                    parsed["company_name"],
                    parsed["stock_name"],
                    parsed["filing_time"],
                    parsed["new_product"],
                    parsed["product_description"][:180],
                ])
                extracted += 1
                print(f"✅ Extracted product: {parsed['new_product']}")

            except Exception as e:
                print(f"⚠️ Skipped {filing_path}: {e}")

            if extracted >= MAX_ENTRIES:
                print("\n✅ Reached 100 entries.")
                break

        if extracted >= MAX_ENTRIES:
            break

print(f"\n🎯 Extraction complete. {extracted} entries saved to {CSV_OUTPUT}")
