import logging
import time
import random
from datetime import datetime
from typing import List, Optional, Dict

import pandas as pd
import undetected_chromedriver as uc_orig
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    NoSuchElementException,
    WebDriverException,
)


class Chrome(uc_orig.Chrome):
    def __init__(self, **kwargs):
        # Keep constructor signature and behavior same as original
        super().__init__(**kwargs)

    def __del__(self):
        # Suppress destructor exceptions like original
        try:
            if hasattr(self, "service") and getattr(self.service, "process", None):
                try:
                    self.service.process.kill()
                except Exception:
                    pass
            try:
                self.quit()
            except Exception:
                pass
        except Exception:
            pass


# ----------------------------
# Logging config (preserve filename)
# ----------------------------
LOGFILE = "scraper.log"
logging.basicConfig(
    filename=LOGFILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ----------------------------
# Main scraper
# ----------------------------
class JustdialScraper:
    def __init__(self, chunk_size: int = 50):
        """
        chunk_size: how many records to accumulate before writing a partial file (to avoid total data loss)
        """
        self.driver = None
        self.wait = None
        self.action = None
        self.chunk_size = max(1, int(chunk_size))
        self._partial_save_counter = 0  # internal counter for naming partial files
        self.setup_driver()

    def setup_driver(self):
        """Initialize Chrome driver with appropriate options."""
        try:
            self.driver = Chrome(use_subprocess=False)
            # maximize_window can fail in headless/no-display env; guard it
            try:
                self.driver.maximize_window()
            except Exception:
                logger.debug("Couldn't maximize window (environment may not support it).")
            self.wait = WebDriverWait(self.driver, 15)  # 15s timeout like original
            self.action = ActionChains(self.driver)
            logger.info("Browser initialized successfully")
        except Exception as e:
            logger.exception("Failed to initialize browser.")
            raise

    def validate_url(self, url: str) -> bool:
        """Validate if the URL is a valid Justdial URL (same logic as original)."""
        if not isinstance(url, str):
            return False
        return "justdial.com" in url.lower() and url.startswith(("http://", "https://"))

    def read_urls(self, filename: str) -> List[str]:
        """Read and validate URLs from the input file. Behavior preserved (creates sample file if missing)."""
        valid_urls: List[str] = []
        try:
            with open(filename, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    url = line.strip()
                    if not url or url.startswith("#"):
                        continue
                    if self.validate_url(url):
                        valid_urls.append(url)
                    else:
                        logger.warning(f"Invalid URL skipped at line {line_num}: {url}")
        except FileNotFoundError:
            logger.error(f"Input file {filename} not found.")
            # Create sample file (preserve original sample content)
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write("# Add one Justdial URL per line\n")
                    f.write("# Example: https://www.justdial.com/Mumbai/Restaurants\n")
                logger.info(f"Created sample {filename} file. Please add URLs and run again.")
            except Exception:
                logger.exception("Failed to create sample input file.")
        except Exception:
            logger.exception("Unexpected error while reading URLs.")
        return valid_urls

    def smooth_scroll(self, pixels: int):
        """Perform smooth scrolling (preserve original stepping and delays)."""
        if not isinstance(pixels, int) or pixels <= 0:
            return
        current = 0
        step = 50
        while current < pixels:
            scroll_amount = min(step, pixels - current)
            try:
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            except WebDriverException:
                # If script execution fails, exit gracefully
                logger.debug("execute_script failed while scrolling.")
                break
            current += scroll_amount
            time.sleep(random.uniform(0.1, 0.2))

    def random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """Random delay helper (same behavior as original)."""
        try:
            if min_seconds < 0:
                min_seconds = 0
            if max_seconds < min_seconds:
                max_seconds = min_seconds
            time.sleep(random.uniform(min_seconds, max_seconds))
        except Exception:
            # If time.sleep fails for some reason, ignore; not critical
            logger.debug("random_delay failed, ignoring.")

    # commented original popup handler kept commented to preserve code visibility
    # def handle_popup(self):
    #     ...

    def check_and_close_deal_popup(self):
        """Find and close the Justdial 'best deal' popup if present (preserve original behavior)."""
        try:
            best_deal = self.driver.find_element(By.CSS_SELECTOR, 'div[class*="bestdeal_right"]')
        except NoSuchElementException:
            return
        except Exception:
            # Any other issue — we don't want this to crash scraping
            logger.debug("Unexpected error while locating bestdeal element (ignored).")
            return

        try:
            close_button = best_deal.find_element(By.CSS_SELECTOR, '[aria-label="Best deal Modal Close Icon"]')
            close_button.click()
            logger.info("Closed popup window.")
            # original waited between 2-4s after closing
            self.random_delay(2, 4)
        except Exception:
            logger.debug("Failed to close popup (possibly already closed).")

    def get_product_details(self, product, url: str) -> Optional[Dict]:
        """
        Extract details from a product element.
        Signature kept identical to original (product, url) even though original overwrote url.
        """
        try:
            # Extract title anchor
            anchor_tag = product.find_element(By.CSS_SELECTOR, 'a[class*="resultbox_title_anchorbox"]')

            # original code got href & title from anchor_tag and rating/address from product
            product_url = anchor_tag.get_attribute("href")
            title = anchor_tag.get_attribute("title") or ""
            try:
                rating = product.find_element(By.CSS_SELECTOR, 'li[class*="resultbox_totalrate"]').text.strip()
            except NoSuchElementException:
                rating = ""
            try:
                address = product.find_element(By.TAG_NAME, "address").text.strip()
            except NoSuchElementException:
                address = ""

            # Get phone number (may involve clicking)
            phone = self.get_phone_number(product)

            product_data = {
                "product_title": title,
                "name": anchor_tag.text,
                "rating": rating,
                "address": address,
                "phone": phone,
                "url": product_url,
                "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            logger.info(f"Successfully scraped product: {title}")
            return product_data

        except Exception as e:
            # Mirror original behavior: check popup then log and return None
            self.check_and_close_deal_popup()
            logger.exception(f"Failed to extract product details: {e}")
            return None

    def get_phone_number(self, product):
        """Extract phone number from product (preserve original DOM interactions)."""
        self.random_delay(2,3)
        try:
            phone_button = product.find_element(By.CSS_SELECTOR, '[class*="greenfill_animate"]')
            button_text = phone_button.text.strip()
            if "Show Number" in button_text:
                # Click the button and wait briefly for popup content
                try:
                    phone_button.click()
                except Exception:
                    logger.debug("Clicking phone button raised an exception (continuing).")
                self.random_delay()

                # original used a driver-level XPath to fetch the contact number
                phone = "N/A"
                phone_locators = {By.ID: "listing_call_button", By.XPATH: '//div[text()="Contact Information"]/following-sibling::div[1]'}
                for selector, locator in phone_locators.items():
                    try:
                        phone_elem = self.driver.find_element(
                           selector, locator
                        )
                        phone = phone_elem.text.strip()
                        break
                    except NoSuchElementException:
                        continue

                # attempt to close popup using selectors from original code
                if selector == "xpath":
                    close_selectors = ['div[class*="jdmart_modal_close"]:nth-of-type(1)', 'div[class*="jd_modal_close"]']
                    for locator in close_selectors:
                        try:
                            close_button = self.driver.find_element(By.CSS_SELECTOR, locator)
                            try:
                                close_button.click()
                            except Exception:
                                pass
                            break
                        except NoSuchElementException:
                            continue

                self.random_delay(0.5, 1.0)
            else:
                phone = button_text or "N/A"

            return phone
        except NoSuchElementException:
            # If there's no phone element, return N/A
            logger.debug("Phone button not found for this product.")
            return "N/A"
        except Exception as e:
            # preserve original pattern: check popup and return N/A
            self.check_and_close_deal_popup()
            logger.exception(f"Failed to get phone number: {e}")
            return "N/A"


    def scrape_products(self, url: str) -> List[Dict]:
        """
        Scrape products from a single URL.
        Behavior kept consistent with original loop/termination logic.
        """
        products_data: List[Dict] = []
        scroll_attempts = 0
        max_scroll_attempts = 50
        last_count = 0

        try:
            # Navigate to URL (original used driver.get and small delay)
            self.driver.get(url)
            self.random_delay()
            logger.info(f"Started scraping URL: {url}")

            while scroll_attempts < max_scroll_attempts:
                # close popup if present
                try:
                    self.check_and_close_deal_popup()
                except Exception:
                    logger.debug("check_and_close_deal_popup raised exception (ignored).")

                products = self.driver.find_elements(By.CSS_SELECTOR, 'div[class*="resultbox_info"]')
                current_count = len(products)

                # Process newly discovered products (original sliced by last_count)
                try:
                    for product in products[last_count:]:
                        # check if there is any login popup
                        try:
                            self.driver.find_element(By.ID, "login-modal-title")
                            raise Exception("There is a login popup, which cannot be bypassed. Please retry..")
                        except NoSuchElementException:
                            pass

                        details = self.get_product_details(product, url)
                        if details:
                            details["product_index"] = len(products_data) + 1
                            products_data.append(details)

                            # Partial save in chunks: this is an improvement but doesn't change core behavior
                            if len(products_data) % self.chunk_size == 0:
                                try:
                                    self._partial_save_counter += 1
                                    self._save_partial(products_data, url, self._partial_save_counter)
                                except Exception:
                                    logger.exception("Partial save failed; continuing scraping.")
                except Exception as e:
                    # keep consistent: check popup and log
                    self.check_and_close_deal_popup()
                    logger.exception(f"Exception while iterating products on page: {e}")

                # Update last_count per original logic (note: original had a check that effectively breaks early.
                # To preserve behavior we keep the same condition and update.)
                if last_count == current_count:
                    logger.info("Scrapped all the records..")
                    break

                last_count = current_count

                # Scroll down and wait as original did
                self.smooth_scroll(800)
                scroll_attempts += 1

                # small random delay as original
                self.random_delay(2.0, 5.0)
                # attempt close popup once more before next iteration
                self.check_and_close_deal_popup()

            logger.info(f"Completed scraping URL: {url}. Total products: {len(products_data)}")

        except Exception as e:
            # preserve original pattern: check popup and log error
            try:
                self.check_and_close_deal_popup()
            except Exception:
                logger.debug("check_and_close_deal_popup in exception path failed.")
            logger.exception(f"Error scraping URL {url}: {e}")

        return products_data

    def _save_partial(self, data: List[Dict], source_url: str, counter: int):
        """
        Save a partial chunk to an Excel file.
        This is additive and shouldn't break original expectations.
        Partial filenames include counter so they don't overwrite final export.
        """
        if not data:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "justdial_results_partial"
        filename = f"{safe_name}_{counter}_{timestamp}.xlsx"
        try:
            df = pd.DataFrame(data)
            columns = ["product_index", "product_title", "name", "rating", "address", "phone", "url", "scraped_at"]
            df = df.reindex(columns=columns)
            df.to_excel(filename, index=False)
            logger.info(f"Partial data saved to {filename} (source: {source_url})")
        except Exception:
            logger.exception("Failed to save partial data to Excel.")

    def save_to_excel(self, data: List[Dict]):
        """
        Save scraped data to Excel file with timestamp.
        Kept signature and behavior compatible with original.
        """
        if not data:
            logger.warning("No data to save to Excel")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"justdial_results_{timestamp}.xlsx"

        try:
            df = pd.DataFrame(data)
            columns = ["product_index", "product_title", "name", "rating", "address", "phone", "url", "scraped_at"]
            df = df.reindex(columns=columns)
            df.to_excel(filename, index=False)
            logger.info(f"Data saved successfully to {filename}")
        except Exception:
            logger.exception("Error saving data to Excel.")

    def run(self):
        """Main method to run the scraper. Preserves original flow and filename usage."""
        try:
            urls = self.read_urls("justdail_urls.txt")  # keep original filename usage
            if not urls:
                logger.error("No valid URLs found in input file")
                return

            all_products: List[Dict] = []
            for url in urls:
                logger.info(f"Processing URL: {url}")
                products = self.scrape_products(url)
                all_products.extend(products)
                # preserve original inter-URL delay behavior
                self.random_delay(1.2, 2.8)

            # final save (same as original)
            self.save_to_excel(all_products)

        except Exception as e:
            logger.exception(f"Scraper failed: {e}")
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    logger.debug("driver.quit() raised exception during cleanup.")


if __name__ == "__main__":
    try:
        scraper = JustdialScraper()
        scraper.run()
    except Exception:
        logger.exception("Application error (fatal).")
