"""
Justdial WhatsApp Scraper (new approach)
- Reuses Chrome profile to avoid repeated login
- Injects JS hook to capture API paginated data (docid + scd)
- Smooth-scrolls using provided smooth_scroll() method until all docids are collected
- For each (docid, scd) constructs cwaxp url and resolves redirect to get final WhatsApp number
- Saves data to an .xlsx file
"""
import os.path
import time
import json
import re
import random
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

from undetected_chromedriver import Chrome
from selenium.webdriver import ChromeOptions


LOGFILE = "scraper.log"
logging.basicConfig(
    filename=LOGFILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logger.addHandler(console)


# -------------------------
# Configuration
# -------------------------
INPUT_FILE = "justdial_urls.txt"          # corrected filename (you said correct typo)
OUTPUT_XLSX = f"justdial_whatsapp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
CHROME_PROFILE_DIR = os.path.join(os.getcwd(), "chrome_profiless")  # change if you want to reuse a specific profile
WAIT_FOR_LOGIN_SECONDS = 300              # how long to wait for user to login (0 => exit immediately if not logged in)
SCROLL_PAUSE = 1.5                        # pause between scrolls
MAX_SCROLLS = 200                         # safety cap
RESOLVE_DELAY = (0.25, 0.6)               # random sleep between resolving cwaxp links (avoid rate-limit)
FETCH_TIMEOUT = 15                        # seconds for JS fetch fallback timeouts
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"


# -------------------------
# Helper: Create driver
# -------------------------
def create_driver(profile_dir: str, headless: bool = False):
    """Create a Chrome driver, reusing the given profile folder. Prefer undetected_chromedriver if available."""
    chrome_options = ChromeOptions()
    chrome_options.add_argument('--user-data-dir=' + CHROME_PROFILE_DIR)
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-popup-blocking")
    driver = Chrome(options=chrome_options)
    driver.maximize_window()
    return driver

# -------------------------
# Smooth scroll (your exact function)
# -------------------------
def smooth_scroll(driver, pixels: int):
    """Perform smooth scrolling (preserve original stepping and delays)."""
    if not isinstance(pixels, int) or pixels <= 0:
        return
    current = 0
    step = 50
    while current < pixels:
        scroll_amount = min(step, pixels - current)
        try:
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        except WebDriverException:
            logger.debug("execute_script failed while scrolling.")
            break
        current += scroll_amount
        time.sleep(random.uniform(0.1, 0.2))


# -------------------------
# JS hook injector
# -------------------------
HOOK_JS = r"""
(function() {
    if (window.jdHookInstalled) return;
    window.jdHookInstalled = true;
    window.jdWhatsappsMap = window.jdWhatsappsMap || {}; // { docid: scd }

    function seedFromNextData() {
        try {
            const nd = document.getElementById("__NEXT_DATA__");
            if (!nd || !nd.textContent) return;
            const data = JSON.parse(nd.textContent);
            const results = data?.props?.pageProps?.listData?.results;
            if (!results) return;
            const cols = results.columns || [];
            const docidIndex = cols.indexOf("docid");
            const scdIndex = cols.indexOf("scd");
            if (docidIndex === -1 || scdIndex === -1) return;
            (results.data || []).forEach(row => {
                const docid = row[docidIndex];
                const scd = row[scdIndex];
                if (docid && scd) {
                    window.jdWhatsappsMap[docid] = scd;
                }
            });
        } catch (e) {
            // ignore parse errors
        }
    }

    // seed initial page data immediately
    seedFromNextData();

    // patch fetch
    const origFetch = window.fetch;
    window.fetch = async function(...args) {
        const response = await origFetch.apply(this, args);
        try {
            const url = args[0] && args[0].toString ? args[0].toString() : "";
            if (url.includes("/api/resultsPageListing")) {
                // clone response and parse
                const clone = response.clone();
                clone.json().then(data => {
                    try {
                        const cols = data?.results?.columns || [];
                        const docidIndex = cols.indexOf("docid");
                        const scdIndex = cols.indexOf("scd");
                        if (docidIndex !== -1 && scdIndex !== -1) {
                            (data.results.data || []).forEach(row => {
                                const docid = row[docidIndex];
                                const scd = row[scdIndex];
                                if (docid && scd) window.jdWhatsappsMap[docid] = scd;
                            });
                        }
                    } catch(e){}
                }).catch(()=>{});
            }
        } catch(e){}
        return response;
    };

    // patch XHR
    const origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        this.addEventListener("load", function() {
            try {
                if (url && url.includes("/api/resultsPageListing")) {
                    const data = JSON.parse(this.responseText || "{}");
                    const cols = data?.results?.columns || [];
                    const docidIndex = cols.indexOf("docid");
                    const scdIndex = cols.indexOf("scd");
                    if (docidIndex !== -1 && scdIndex !== -1) {
                        (data.results.data || []).forEach(row => {
                            const docid = row[docidIndex];
                            const scd = row[scdIndex];
                            if (docid && scd) window.jdWhatsappsMap[docid] = scd;
                        });
                    }
                }
            } catch(e){}
        });
        return origOpen.call(this, method, url, ...rest);
    };

    // expose helper to return collected entries as an array
    window.getJDWhatsappsArray = function() {
        const out = [];
        for (const k in window.jdWhatsappsMap) {
            out.push({docid: k, scd: window.jdWhatsappsMap[k]});
        }
        return out;
    };

})();
"""


# -------------------------
# Utility functions
# -------------------------
def read_urls(filename: str) -> List[str]:
    urls = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for ln in f:
                s = ln.strip()
                if not s or s.startswith("#"):
                    continue
                if "justdial.com" in s.lower() and s.startswith(("http://", "https://")):
                    urls.append(s)
                else:
                    logger.warning("Skipping invalid URL: %s", s)
    except FileNotFoundError:
        logger.error("Input file not found: %s", filename)
        # create sample file
        with open(filename, "w", encoding="utf-8") as f:
            f.write("# Put one Justdial search URL per line e.g.\n")
            f.write("https://www.justdial.com/Thane/Supermarkets-in-Shanti-Nagar-Mira-Road-East/nct-10463784\n")
        logger.info("Sample file created. Please add URLs and run again.")
    return urls


def is_logged_in(driver) -> bool:
    """Detect login via presence of known Justdial cookies (common keys)."""
    try:
        cookies = driver.get_cookies()
        keys = {c["name"] for c in cookies}
        # common Justdial cookie names we can accept as 'logged in'
        check_keys = {"JDTID", "JDSID", "sid", "jd_sid", "JDINF"}
        present = bool(keys & check_keys)
        logger.debug("Cookies present: %s; login keys intersection: %s", keys, keys & check_keys)
        return present
    except Exception as e:
        logger.exception("Error reading cookies to detect login: %s", e)
        return False


def wait_for_login(driver, max_attempts: int = 3) -> bool:
    """Wait for user to login manually in opened browser. Returns True if logged in, else False."""

    if is_logged_in(driver):
        logger.info("Detected login via cookies.")
        return True

    if max_attempts <= 0:
        raise Exception("You need to login into Justdial, to extract the whatsapp numbers")

    input("Please login into JustDial and then press enter to continue. \n")
    return wait_for_login(driver, max_attempts-1)


def parse_nextdocid_count_from_page(driver) -> int:
    """Read __NEXT_DATA__ and return number of docids (split by comma)."""
    try:
        nd_text = driver.execute_script("return document.getElementById('__NEXT_DATA__') && document.getElementById('__NEXT_DATA__').textContent")
        if not nd_text:
            return 0
        parsed = json.loads(nd_text)
        nextdocid_str = parsed["props"]["pageProps"]["listData"].get("nextdocid", "") or ""
        if nextdocid_str.strip() == "":
            return 0
        return len(nextdocid_str.split(","))
    except Exception as e:
        logger.exception("Failed to parse nextdocid from page: %s", e)
        return 0


def get_collected_pairs(driver) -> List[Dict[str, str]]:
    """Return array of {docid, scd} from browser hook (deduped)."""
    try:
        arr = driver.execute_script("return window.getJDWhatsappsArray ? window.getJDWhatsappsArray() : []")
        # filter out entries missing scd
        filtered = [x for x in arr if x.get("docid")]
        return filtered
    except Exception as e:
        logger.exception("Error fetching collected pairs from browser: %s", e)
        return []


def build_cwaxp_url(docid: str, scd: str) -> str:
    return f"https://www.justdial.com/webmain/cwaxp.php?dd={docid}&wp={scd}"


def extract_phone_from_url(wa_url: str) -> Optional[str]:
    if not wa_url:
        return None
    # Try digits pattern (10-15 digits)
    m = re.search(r"(\d{10,15})", wa_url)
    if m:
        return m.group(1)
    # fallback: parse query param phone
    try:
        from urllib.parse import urlparse, parse_qs
        parts = urlparse(wa_url)
        q = parse_qs(parts.query)
        for k in ("phone", "phoneNumber", "text"):
            if k in q and q[k]:
                m2 = re.search(r"(\d{10,15})", q[k][0])
                if m2:
                    return m2.group(1)
    except Exception:
        pass

    return None


def resolve_cwaxp_with_requests(url: str, cookies: Dict[str, str], headers: Dict[str, str]) -> Optional[str]:
    """Fallback resolver using Python requests (no redirects)."""
    try:
        s = requests.Session()
        s.headers.update(headers)
        # set cookies
        s.cookies.update(cookies)
        r = s.get(url, allow_redirects=False, timeout=10)
        if r.status_code in (301, 302, 307, 308):
            return r.headers.get("Location")
        # sometimes response is 200 with meta redirect - unlikely; return None
        logger.debug("Requests resolver returned status %s for %s", r.status_code, url)
        return None
    except Exception as e:
        logger.exception("resolve_cwaxp_with_requests failed: %s", e)
        return None


def driver_cookies_to_dict(driver) -> Dict[str, str]:
    try:
        return {c["name"]: c["value"] for c in driver.get_cookies()}
    except Exception:
        return {}


# -------------------------
# Main scraping logic
# -------------------------
def process_url(driver, url: str, wait_for_login_flag: bool = True) -> List[Dict]:
    """Process a single Just dial listing/search URL and return enriched rows."""
    logger.info("Processing: %s", url)
    driver.get(url)
    time.sleep(3)  # let initial resources load

    # check login
    if not is_logged_in(driver):
        wait_for_login(driver)

    # parse expected count from __NEXT_DATA__
    expected = parse_nextdocid_count_from_page(driver)
    if expected <= 0:
        logger.warning("Could not parse expected docid count from page (nextdocid). Will use best-effort stopping.")
    else:
        logger.info("Found expected docid count = %d", expected)

    # Inject hook
    try:
        driver.execute_script(HOOK_JS)
    except Exception:
        logger.exception("Failed to inject JS hook.")
        return []

    # smooth scroll loop using your smooth_scroll
    collected = []
    for i in range(MAX_SCROLLS):
        smooth_scroll(driver, 600)  # 500px per iteration
        time.sleep(SCROLL_PAUSE)

        collected = get_collected_pairs(driver)
        uniq_count = len({p['docid'] for p in collected})
        logger.info("Scroll %d: collected %d unique pairs (expected %s)", i + 1, uniq_count, expected or "unknown")

        if expected and uniq_count >= expected:
            logger.info("Collected expected number of docids; stopping scroll.")
            break

    # final pull
    collected = get_collected_pairs(driver)
    # dedupe by docid (keep first)
    dedup: Dict[str, str] = {}
    for item in collected:
        did = item.get("docid")
        scd = item.get("scd")
        if did and scd and did not in dedup:
            dedup[did] = scd

    logger.info("Total deduped pairs collected: %d", len(dedup))

    # resolve each cwaxp url to whatsapp url and extract number
    results = []
    cookies = driver_cookies_to_dict(driver)
    headers = {"User-Agent": USER_AGENT, "Referer": url, "Origin": "https://www.justdial.com"}

    idx = 0
    for docid, scd in dedup.items():
        idx += 1
        cwaxp = build_cwaxp_url(docid, scd)
        logger.info("[%d/%d] Resolving cwaxp: %s", idx, len(dedup), cwaxp)

        data = get_product_details(driver, docid)

        wa_url = resolve_cwaxp_with_requests(cwaxp, cookies, headers)

        data["phone"] = extract_phone_from_url(wa_url or "")
        results.append(data)

        time.sleep(random.uniform(*RESOLVE_DELAY))

    return results


def get_product_details(driver, doc_id):
    product = driver.find_element(By.ID, doc_id)
    anchor_tag = product.find_element(By.TAG_NAME, "a")
    title = anchor_tag.get_attribute("title")
    url = anchor_tag.get_attribute("href")
    ratings = product.find_element(By.CSS_SELECTOR, "li[class*='resultbox_totalrate']").text
    address = product.find_element(By.TAG_NAME, "address").text
    return {
        "title": title,
        "url": url,
        "ratings": ratings,
        "address": address
    }


def save_to_excel(rows, is_partial: bool = False):
    # Save to Excel
    filename = OUTPUT_XLSX

    df = pd.DataFrame(rows)
    if is_partial:
        filename = f"partial_{OUTPUT_XLSX}"

    df.to_excel(filename)
    logger.info("Saved output to %s", OUTPUT_XLSX)


def main():
    urls = read_urls(INPUT_FILE)
    if not urls:
        logger.error("No URLs to process. Please edit %s and add URLs.", INPUT_FILE)
        return

    driver = create_driver(CHROME_PROFILE_DIR, headless=False)
    try:
        # give browser time to fully initialize
        time.sleep(2)
        all_rows = []
        for url in urls:
            rows = process_url(driver, url, wait_for_login_flag=True)
            all_rows.extend(rows)
            save_to_excel(rows, is_partial=True)

            # small pause between different search URLs
            time.sleep(random.uniform(1.0, 2.5))

        if not all_rows:
            logger.warning("No data collected across all URLs.")
            return

        save_to_excel(all_rows)

    finally:
        try:
            driver.quit()
        except Exception:
            logger.debug("driver.quit() failed.")


if __name__ == "__main__":
    main()
