# VERSION: DEBUG-HTML-V2
import requests, csv, json, sys
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

print("=== VERSION: DEBUG-HTML-V2 ===")

BASE       = "https://www2.calrecycle.ca.gov"
DETAIL_URL = f"{BASE}/BevContainer/RecyclingCenters/Details"

# Step 1: Use Selenium to harvest cookies
print("Step 1: Launching browser...")
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
driver = webdriver.Chrome(options=options)
driver.get(f"{DETAIL_URL}?AccountLocationID=361")
time.sleep(5)
print(f"  Title: {driver.title}")
cookies = driver.get_cookies()
print(f"  Cookies: {[c['name'] for c in cookies]}")
driver.quit()

# Step 2: Transfer cookies to requests
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})
for cookie in cookies:
    session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.calrecycle.ca.gov'))

# Step 3: Inspect known IDs
for test_id in [361, 812, 51322]:
    r = session.get(f"{DETAIL_URL}?AccountLocationID={test_id}", timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    print(f"\n--- ID {test_id} ---")
    print(f"  Status: {r.status_code}")
    print(f"  Title: {soup.title.text.strip() if soup.title else 'none'}")
    print(f"  H1s: {[h.text.strip() for h in soup.find_all('h1')]}")
    print(f"  Bold tags: {[b.text.strip() for b in soup.find_all('b')][:15]}")
    full_text = soup.get_text()
    rvm_idx = full_text.lower().find("reverse vending")
    if rvm_idx >= 0:
        print(f"  RVM context: '{full_text[rvm_idx:rvm_idx+80]}'")
    else:
        print("  'reverse vending' NOT FOUND in page text")

print("\nDone — debug only, no scan.")
