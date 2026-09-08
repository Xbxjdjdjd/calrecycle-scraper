# VERSION: REFRESH-COOKIES-V1
import requests, csv, json, sys, re, threading
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

print("=== VERSION: REFRESH-COOKIES-V1 ===")

BASE        = "https://www2.calrecycle.ca.gov"
DETAIL_URL  = f"{BASE}/BevContainer/RecyclingCenters/Details"
OUTPUT_CSV  = "calrecycle_rvm.csv"
OUTPUT_JSON = "calrecycle_rvm.json"
ID_START    = 1
ID_END      = 100000

def get_cookies():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
    driver = webdriver.Chrome(options=options)
    driver.get(f"{DETAIL_URL}?AccountLocationID=361")
    time.sleep(5)
    cookies = driver.get_cookies()
    driver.quit()
    return cookies

def apply_cookies(session, cookies):
    session.cookies.clear()
    for cookie in cookies:
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.calrecycle.ca.gov'))

# Step 1: Initial cookie harvest
print("Step 1: Harvesting cookies...")
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})
cookies = get_cookies()
apply_cookies(session, cookies)
print(f"  Got {len(cookies)} cookies")

# Verify known IDs work immediately
print("Step 2: Verifying known IDs...")
for test_id in [361, 79492, 80925]:
    r = session.get(f"{DETAIL_URL}?AccountLocationID={test_id}", timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    h1s = [h.text.strip() for h in soup.find_all("h1") if "Details for" in h.text]
    full_text = soup.get_text(" ", strip=True)
    rvm_match = re.search(r"Reverse Vending Machines:\s*(\w+)", full_text)
    print(f"  ID {test_id}: h1={h1s} rvm={rvm_match.group(1) if rvm_match else 'NOT FOUND'}")

# Cookie refresh thread
cookie_lock = threading.Lock()
last_refresh = [time.time()]

def refresh_cookies_periodically():
    while True:
        time.sleep(240)  # refresh every 4 minutes
        print("  [Cookie refresh...]")
        new_cookies = get_cookies()
        with cookie_lock:
            apply_cookies(session, new_cookies)
        last_refresh[0] = time.time()
        print("  [Cookies refreshed]")

refresher = threading.Thread(target=refresh_cookies_periodically, daemon=True)
refresher.start()

# Step 3: Scrape
def scrape(loc_id):
    try:
        with cookie_lock:
            r = session.get(f"{DETAIL_URL}?AccountLocationID={loc_id}", timeout=15)
        if "Details for" not in r.text:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        h1s = soup.find_all("h1")
        name = ""
        for h in h1s:
            if "Details for" in h.text:
                name = h.text.replace("Recycling Center Details for", "").strip()
                break
        if not name:
            return None
        full_text = soup.get_text(" ", strip=True)
        match = re.search(r"Reverse Vending Machines:\s*(\w+)", full_text)
        rvm = match.group(1) if match else None
        return {"AccountLocationID": loc_id, "Name": name, "HasRVM": rvm}
    except:
        return None

print(f"\nStep 3: Scanning IDs {ID_START}-{ID_END} with 15 workers...")
all_centers = []
rvm_centers = []
checked = 0

with ThreadPoolExecutor(max_workers=15) as ex:
    futures = {ex.submit(scrape, i): i for i in range(ID_START, ID_END + 1)}
    for future in as_completed(futures):
        result = future.result()
        checked += 1
        if result:
            all_centers.append(result)
            if (result.get("HasRVM") or "").strip().lower() == "yes":
                rvm_centers.append(result)
        if checked % 1000 == 0:
            print(f"  {checked}/{ID_END} | {len(all_centers)} centers | {len(rvm_centers)} RVM=Yes")

print(f"\nDone! {len(all_centers)} centers, {len(rvm_centers)} RVM=Yes")
print(f"Sample: {all_centers[:3]}")

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["AccountLocationID", "Name", "HasRVM"])
    w.writeheader()
    w.writerows(rvm_centers)

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(rvm_centers, f, indent=2)

print(f"✅ Saved {len(rvm_centers)} RVM centers.")
