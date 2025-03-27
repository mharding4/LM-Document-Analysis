#Mitchell Harding
#LLM Document Analysis
#AI for Fintech

import os
import re
import json
import time
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import pandas as pd

# ------------------------
# CONFIG
# ------------------------
HEADERS = {
    "User-Agent": "MitchellHardingAI/1.0 (mitchell@example.com)"
}
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "deepseek-llm"

# ------------------------
# LOAD COMPANY TICKERS
# ------------------------
with open("company_tickers.json", "r") as f:
    ticker_data = json.load(f)

cik_map = {
    str(company["cik_str"]).zfill(10): (company["title"], company["ticker"])
    for company in ticker_data.values()
}

# ------------------------
# PARSE BROWSE-EDGAR XML
# ------------------------
tree = ET.parse("browse-edgar.txt")
root = tree.getroot()
ns = {"atom": "http://www.w3.org/2005/Atom", "ns0": "http://www.w3.org/2005/Atom"}
entries = root.findall("atom:entry", ns)

results = []

# ------------------------
# FETCH FILING TEXT
# ------------------------
def extract_filing_text(index_url):
    try:
        print(f"🔗 Fetching index page: {index_url}")
        time.sleep(1.5)
        res = requests.get(index_url, headers=HEADERS)
        soup = BeautifulSoup(res.text, "html.parser")

        base_url = index_url[:index_url.rfind('/') + 1]

        # Try direct .txt file
        txt_link = soup.find("a", string=re.compile("Complete submission text file", re.IGNORECASE))
        if txt_link and txt_link.get("href"):
            txt_url = requests.compat.urljoin(base_url, txt_link["href"].lstrip("/"))
            print(f"📄 Downloading .txt: {txt_url}")
            time.sleep(1.5)
            return requests.get(txt_url, headers=HEADERS).text

        # Fallback: any .htm/.txt link
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith((".htm", ".txt")) and "xbrl" not in href.lower():
                doc_url = requests.compat.urljoin(base_url, href.lstrip("/"))
                print(f"📄 Fallback document: {doc_url}")
                time.sleep(1.5)
                return requests.get(doc_url, headers=HEADERS).text

        print("⚠️ No usable document link found.")
        return ""
    except Exception as e:
        print(f"❌ Exception fetching document: {e}")
        return ""

# ------------------------
# USE OLLAMA TO EXTRACT PRODUCT INFO
# ------------------------
def extract_product_info(text):
    prompt = f"""
You are analyzing an SEC 8-K filing.

If the company announces a new product or service, extract:
- company_name
- new_product
- product_description (max 180 characters)

Respond ONLY in valid JSON like:
{{
  "company_name": "...",
  "new_product": "...",
  "product_description": "..."
}}

Here is the 8-K text:
{text[:6000]}
""".strip()

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        })

        response.raise_for_status()
        output = response.json().get("response", "").strip()

        json_start = output.find('{')
        json_end = output.rfind('}') + 1
        if json_start == -1 or json_end == -1:
            print("⚠️ No valid JSON output")
            return None

        parsed = json.loads(output[json_start:json_end])
        return {
            "company_name": parsed.get("company_name", "").strip(),
            "stock_name": "UNKNOWN",
            "new_product": parsed.get("new_product", "").strip(),
            "product_description": parsed.get("product_description", "").strip()[:180]
        }

    except Exception as e:
        print(f"❌ LLM extract error: {e}")
        return None

# ------------------------
# MAIN LOOP
# ------------------------
for entry in entries:
    try:
        content = entry.find("atom:content", ns)
        if content is None:
            continue

        acc_el = content.find("ns0:accession-number", ns)
        date_el = content.find("ns0:filing-date", ns)
        href_el = content.find("ns0:filing-href", ns)

        if None in (acc_el, date_el, href_el):
            print("⚠️ Skipping entry — missing required fields")
            continue

        accession = acc_el.text.strip()
        filing_date = date_el.text.strip()
        filing_href = href_el.text.strip()

        # Extract CIK
        cik_match = re.search(r"/data/(\d+)/", filing_href)
        cik = cik_match.group(1).zfill(10) if cik_match else "UNKNOWN"
        company_name, stock_name = cik_map.get(cik, ("UNKNOWN", "UNKNOWN"))

        print(f"\n🏢 Processing: {company_name} ({stock_name}) | CIK: {cik}")
        filing_text = extract_filing_text(filing_href)

        if not filing_text:
            print("⚠️ No filing text found")
            continue

        parsed = extract_product_info(filing_text)
        if not parsed:
            print("🔍 No product announcement found")
            continue

        parsed.update({
            "company_name": company_name,
            "stock_name": stock_name,
            "filing_time": filing_date
        })
        results.append(parsed)

    except Exception as e:
        print(f"❌ Error processing entry: {e}")

# ------------------------
# SAVE RESULTS
# ------------------------
if results:
    df = pd.DataFrame(results)
    df.to_csv("product_announcements.csv", index=False)
    print("\n✅ Results saved to product_announcements.csv")
else:
    print("\n🚫 No product announcements extracted.")
