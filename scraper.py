"""
TraceVault Scraper - runs via GitHub Actions
Scrapes TruePeopleSearch and FastPeopleSearch
Writes results to results.json
"""

import json
import re
import sys
import os
import time
import random
from datetime import datetime

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    os.system("pip install requests beautifulsoup4 lxml -q")
    import requests
    from bs4 import BeautifulSoup

HEADERS_LIST = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    }
]

def get_headers():
    return random.choice(HEADERS_LIST)

def clean_phone(raw):
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits[0] == '1':
        d = digits[1:]
        return f"({d[:3]}) {d[3:6]}-{d[6:]}"
    return None

def dedup(lst):
    seen = set()
    out = []
    for x in lst:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out

def scrape_truepeoplesearch(first, last, city="", state=""):
    result = {"source": "TruePeopleSearch", "status": "no_data", "phones": [], "emails": [], "addresses": [], "relatives": []}
    try:
        params = f"?name={first}+{last}"
        if city or state:
            params += f"&citystatezip={city}+{state}".replace(" ", "+")
        url = f"https://www.truepeoplesearch.com/results{params}"
        print(f"  Fetching: {url}")
        resp = requests.get(url, headers=get_headers(), timeout=15)
        soup = BeautifulSoup(resp.text, "lxml")

        phones = []
        emails = []
        addresses = []
        relatives = []

        # find phone numbers anywhere in page
        raw_phones = re.findall(r'\(?\d{3}\)?[\s\.\-]\d{3}[\s\.\-]\d{4}', resp.text)
        for p in raw_phones:
            cleaned = clean_phone(p)
            if cleaned:
                phones.append(cleaned)

        # find emails
        raw_emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', resp.text)
        for e in raw_emails:
            if not any(skip in e for skip in ['truepeoplesearch', 'example', 'noreply', 'support', 'info@', 'contact@']):
                emails.append(e.lower())

        # find addresses via structured data
        for span in soup.find_all("span", attrs={"itemprop": "streetAddress"}):
            addresses.append(span.text.strip())

        # find relatives
        for a_tag in soup.find_all("a", href=re.compile(r'/find/')):
            txt = a_tag.text.strip()
            if txt and len(txt) > 3 and last.lower() in txt.lower():
                relatives.append(txt)

        phones = dedup(phones)[:5]
        emails = dedup(emails)[:3]
        addresses = dedup(addresses)[:3]
        relatives = dedup(relatives)[:5]

        if phones or emails:
            result["status"] = "found"
        result["phones"] = phones
        result["emails"] = emails
        result["addresses"] = addresses
        result["relatives"] = relatives

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  TruePeopleSearch error: {e}")
    return result

def scrape_fastpeoplesearch(first, last, city="", state=""):
    result = {"source": "FastPeopleSearch", "status": "no_data", "phones": [], "emails": [], "addresses": [], "relatives": []}
    try:
        name_part = f"{first.lower()}-{last.lower()}"
        loc_part = ""
        if city and state:
            loc_part = f"_{city.lower().replace(' ', '-')}%2C+{state.upper()}"
        elif state:
            loc_part = f"_{state.upper()}"
        url = f"https://www.fastpeoplesearch.com/name/{name_part}{loc_part}"
        print(f"  Fetching: {url}")
        resp = requests.get(url, headers=get_headers(), timeout=15)

        phones = []
        emails = []
        addresses = []

        raw_phones = re.findall(r'\(?\d{3}\)?[\s\.\-]\d{3}[\s\.\-]\d{4}', resp.text)
        for p in raw_phones:
            cleaned = clean_phone(p)
            if cleaned:
                phones.append(cleaned)

        raw_emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', resp.text)
        for e in raw_emails:
            if not any(skip in e for skip in ['fastpeoplesearch', 'example', 'noreply']):
                emails.append(e.lower())

        soup = BeautifulSoup(resp.text, "lxml")
        for div in soup.find_all(class_=re.compile(r'address|location')):
            txt = div.get_text(strip=True)
            if txt and len(txt) > 10:
                addresses.append(txt)

        phones = dedup(phones)[:5]
        emails = dedup(emails)[:3]
        addresses = dedup(addresses)[:3]

        if phones or emails:
            result["status"] = "found"
        result["phones"] = phones
        result["emails"] = emails
        result["addresses"] = addresses

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  FastPeopleSearch error: {e}")
    return result

def scrape_usphonebook(first, last, state=""):
    result = {"source": "USPhoneBook", "status": "no_data", "phones": [], "emails": [], "addresses": [], "relatives": []}
    try:
        url = f"https://www.usphonebook.com/{first.lower()}-{last.lower()}/{state.lower() if state else ''}"
        print(f"  Fetching: {url}")
        resp = requests.get(url, headers=get_headers(), timeout=15)

        phones = []
        raw_phones = re.findall(r'\(?\d{3}\)?[\s\.\-]\d{3}[\s\.\-]\d{4}', resp.text)
        for p in raw_phones:
            cleaned = clean_phone(p)
            if cleaned:
                phones.append(cleaned)

        phones = dedup(phones)[:5]
        if phones:
            result["status"] = "found"
        result["phones"] = phones

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  USPhoneBook error: {e}")
    return result

def run_trace(first, last, address="", city="", state="", zipcode=""):
    print(f"\nTracing: {first} {last} | {city}, {state}")
    print("=" * 50)

    source_results = []

    print("\n[1/3] TruePeopleSearch...")
    r1 = scrape_truepeoplesearch(first, last, city, state)
    source_results.append(r1)
    time.sleep(random.uniform(1.5, 2.5))

    print("\n[2/3] FastPeopleSearch...")
    r2 = scrape_fastpeoplesearch(first, last, city, state)
    source_results.append(r2)
    time.sleep(random.uniform(1.5, 2.5))

    print("\n[3/3] USPhoneBook...")
    r3 = scrape_usphonebook(first, last, state)
    source_results.append(r3)

    # aggregate
    all_phones = []
    all_emails = []
    all_addresses = []
    all_relatives = []
    hits = []

    for r in source_results:
        if r["status"] == "found":
            hits.append(r["source"])
        all_phones.extend(r.get("phones", []))
        all_emails.extend(r.get("emails", []))
        all_addresses.extend(r.get("addresses", []))
        all_relatives.extend(r.get("relatives", []))

    phones = dedup(all_phones)
    emails = dedup(all_emails)
    addresses = dedup(all_addresses)
    relatives = dedup(all_relatives)

    conf = 0
    if phones:
        conf = min(95, 40 + (len(hits) / len(source_results)) * 40 + len(phones) * 5)

    output = {
        "status": "complete",
        "timestamp": datetime.now().isoformat(),
        "subject": {
            "first": first,
            "last": last,
            "address": address,
            "city": city,
            "state": state,
            "zip": zipcode
        },
        "results": {
            "phones": phones,
            "emails": emails,
            "addresses": addresses,
            "relatives": relatives,
            "sources_hit": hits,
            "sources_queried": [r["source"] for r in source_results],
            "confidence": round(conf)
        },
        "source_details": source_results
    }

    # write results
    with open("results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Complete: {len(phones)} phones, {len(emails)} emails found")
    print(f"  Sources hit: {', '.join(hits) if hits else 'none'}")
    print(f"  Confidence: {round(conf)}%")
    return output

if __name__ == "__main__":
    # read input from trace_input.json
    try:
        with open("trace_input.json") as f:
            inp = json.load(f)
        run_trace(
            inp.get("first", ""),
            inp.get("last", ""),
            inp.get("address", ""),
            inp.get("city", ""),
            inp.get("state", ""),
            inp.get("zip", "")
        )
    except FileNotFoundError:
        print("No trace_input.json found")
        # write empty result
        with open("results.json", "w") as f:
            json.dump({"status": "no_input", "timestamp": datetime.now().isoformat()}, f)
