#!/usr/bin/env python3
import argparse
import csv
import re
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import logging

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# --- Logging Setup ---
# (Keep the existing logging setup)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('WDM').setLevel(logging.WARNING)
logging.getLogger('selenium.webdriver.remote.remote_connection').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)


# --- Custom Expected Condition (Keep as is) ---
class text_to_match_regex_in_element:
    """
    An expected condition for waiting until the text of an element, found by locator,
    matches the given regular expression pattern.
    Returns the regex match object if successful, False otherwise.
    """
    def __init__(self, locator, pattern):
        self.locator = locator
        self.pattern = pattern # The compiled regex pattern

    def __call__(self, driver):
        try:
            element = driver.find_element(*self.locator)
            element_text = element.text
            if element_text:
                match = self.pattern.search(element_text)
                if match:
                    logging.debug(f"Found match '{match.group(0)}' in element {self.locator}")
                    return match
            return False
        except NoSuchElementException:
            return False
        except Exception as e:
            logging.debug(f"Exception in custom wait condition for {self.locator}: {e}")
            return False


# Record the start time
start_time = time.time()

# --- setup_driver function (Keep as is) ---
def setup_driver():
    """Sets up the Chrome WebDriver."""
    try:
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-images")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logging.error(f"Failed to set up WebDriver: {e}")
        raise

# --- extract_event_details function (MODIFIED WAIT STRATEGY) ---
def extract_event_details(driver, url):
    """Extracts event details from a given URL, waiting for the page AND
       key elements like the listings container to load before scraping."""
    event_title, event_date, event_location, price = "N/A", "N/A", "N/A", None

    # --- Wait Times ---
    # Wait for initial document ready state
    READY_STATE_WAIT = 10
    # Wait for the main listings container (key indicator of dynamic content load)
    PAGE_LOAD_WAIT_TIME = 25 # <<-- Increased timeout for overall page dynamic content
    # Wait for individual header elements (can be shorter once PAGE_LOAD_WAIT succeeds)
    DETAIL_ELEMENT_WAIT = 7  # <<-- Reduced slightly
    # Wait specifically for the price pattern to appear within its container
    PRICE_PATTERN_WAIT_TIME = 20 # <<-- Can keep this relatively long or slightly reduced

    try:
        logging.info(f"Navigating to {url}")
        driver.get(url)

        # === STAGE 1: Wait for Basic Page Load (readyState) ===
        try:
            WebDriverWait(driver, READY_STATE_WAIT).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            logging.info(f"Page readyState is complete for {url}")
        except TimeoutException:
            # Log a warning but proceed to wait for the key element anyway
            logging.warning(f"Page {url} did not reach readyState 'complete' within {READY_STATE_WAIT}s. Will still wait for key element...")

        # === STAGE 2: Wait for Key Dynamic Content Element (Listings Container) ===
        try:
            # This is our main gatekeeper wait
            key_element_xpath = '//*[@id="listings-container"]'
            logging.info(f"Waiting up to {PAGE_LOAD_WAIT_TIME}s for key element ({key_element_xpath}) to be visible...")
            WebDriverWait(driver, PAGE_LOAD_WAIT_TIME).until(
                EC.visibility_of_element_located((By.XPATH, key_element_xpath))
            )
            logging.info(f"Key element ({key_element_xpath}) is visible. Page likely loaded, proceeding with scraping details.")
        except TimeoutException:
            # If this fails, the page likely didn't load correctly for scraping
            logging.error(f"❌ Key page element ({key_element_xpath}) did not become visible within {PAGE_LOAD_WAIT_TIME}s for {url}. Aborting detail extraction for this URL.")
            # Return N/A for everything as the page is considered unloaded/broken
            return "N/A", "N/A", "N/A", None
        except Exception as e:
             # Catch other errors during the key element wait
             logging.error(f"❌ Error waiting for key element on {url}: {e}", exc_info=True)
             return "N/A", "N/A", "N/A", None

        # === STAGE 3: Extract Details (Now that page is likely loaded) ===
        # Proceed only if the key element wait was successful

        # --- Extract event title (wait for visibility) ---
        try:
            title_xpath = '//*[@id="event-detail-header"]/div/div/div[1]/div[2]/a/h6'
            event_title_element = WebDriverWait(driver, DETAIL_ELEMENT_WAIT).until(
                EC.visibility_of_element_located((By.XPATH, title_xpath))
            )
            event_title = driver.execute_script("return arguments[0].textContent;", event_title_element).strip()
            logging.info(f"🎟️ Event Title: {event_title}")
        except TimeoutException:
            logging.warning(f"⚠️ Event title not found or not visible within {DETAIL_ELEMENT_WAIT}s on {url} (after main page load wait).")
        except Exception as e:
            logging.error(f"Error extracting title on {url}: {e}")

        # --- Extract event date (wait for visibility) ---
        try:
            date_xpath = '//*[@id="event-detail-header"]/div/div/div[1]/div[2]/div/div/div[1]/div/span'
            event_date_element = WebDriverWait(driver, DETAIL_ELEMENT_WAIT).until(
                EC.visibility_of_element_located((By.XPATH, date_xpath))
            )
            event_date = event_date_element.text.strip()
            logging.info(f"📅 Event Date: {event_date}")
        except TimeoutException:
            logging.warning(f"⚠️ Event date not found or not visible within {DETAIL_ELEMENT_WAIT}s on {url}.")
        except Exception as e:
            logging.error(f"Error extracting date on {url}: {e}")

        # --- Extract event location (wait for visibility) ---
        try:
            location_xpath = '/html/body/div[1]/div[1]/div/div/div[1]/div[2]/div/div/div[2]/button'
            location_element = WebDriverWait(driver, DETAIL_ELEMENT_WAIT).until(
                EC.visibility_of_element_located((By.XPATH, location_xpath))
            )
            event_location = location_element.text.strip()
            logging.info(f"📍 Event Location: {event_location}")
        except TimeoutException:
            logging.warning(f"⚠️ Event location not found or not visible within {DETAIL_ELEMENT_WAIT}s on {url}.")
        except Exception as e:
            logging.error(f"Error extracting location on {url}: {e}")

        # --- Attempt to click the modal button (if necessary) ---
        # Keep this wait short, it's opportunistic
        modal_wait = 3
        try:
            button_xpath = '//*[@id="modal-root"]/div/div/div/div[2]/div[3]/button'
            button = WebDriverWait(driver, modal_wait).until(
                EC.element_to_be_clickable((By.XPATH, button_xpath))
            )
            driver.execute_script("arguments[0].click();", button)
            logging.info(f"✅ Clicked a potential modal button on {url}")
        except TimeoutException:
            logging.info(f"ℹ️ Modal button not found/clickable within {modal_wait}s on {url}. Continuing...")
        except Exception as e:
            logging.warning(f"⚠️ Error interacting with modal button on {url}: {e}. Continuing...")

        # --- Extract price (using custom wait for pattern) ---
        price = None
        price_container_xpath = '//*[@id="listings-container"]/div[1]/div'
        price_pattern = re.compile(r'\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)')
        try:
            logging.info(f"Waiting up to {PRICE_PATTERN_WAIT_TIME}s for price pattern in container {price_container_xpath}...")
            price_match = WebDriverWait(driver, PRICE_PATTERN_WAIT_TIME).until(
                text_to_match_regex_in_element((By.XPATH, price_container_xpath), price_pattern)
            )
            if price_match:
                price_value = price_match.group(1).replace(',', '')
                price = f"${float(price_value):,.2f}"
                logging.info(f"💰 Price Pattern Matched: {price}")

        except TimeoutException:
            logging.warning(f"❌ Price pattern not found within {PRICE_PATTERN_WAIT_TIME}s in {price_container_xpath} on {url}.")
            # Fallback check for Sold Out
            try:
                final_container = driver.find_element(By.XPATH, price_container_xpath)
                final_text = final_container.text.strip().lower()
                if "sold out" in final_text:
                    logging.info(f"ℹ️ Container text indicates 'Sold Out' on {url} after timeout.")
                    price = "Sold Out"
                # Add other checks if necessary (e.g., "check back soon")
                else:
                     logging.warning(f"⚠️ Final text in price container ('{final_text[:50]}...') did not match pattern or known alternatives.")
            except NoSuchElementException:
                logging.warning(f"❌ Price container ({price_container_xpath}) was not found during fallback check on {url}.")
            except Exception as e_final:
                logging.error(f"Error during final check for price container text on {url} after timeout: {e_final}")

        except Exception as e:
            logging.error(f"❌ Unexpected error during price extraction on {url}: {e}", exc_info=True)

        return event_title, event_date, event_location, price

    except WebDriverException as e:
        # Catch WebDriver errors that might occur during navigation or initial waits
        logging.error(f"WebDriverException occurred processing {url}: {e}")
        return "N/A", "N/A", "N/A", None
    except Exception as e:
        # Catch any other unexpected errors during the overall process
        logging.critical(f"SEVERE: An unexpected error occurred processing {url}: {e}", exc_info=True)
        return "N/A", "N/A", "N/A", None

# --- save_price_to_csv function (Keep as is) ---
def save_price_to_csv(url, event_title, event_date, event_location, price, history_file_path):
    """Appends event details including the date to the history CSV file."""
    file_path = Path(history_file_path)
    write_header = not file_path.exists() or file_path.stat().st_size == 0
    try:
        with file_path.open("a", newline='', encoding='utf-8') as file:
            fieldnames = ["Time", "Event Title", "Date", "Location", "Price", "URL"]
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow({
                "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Event Title": event_title,
                "Date": event_date,
                "Location": event_location,
                "Price": price if price is not None else "N/A",
                "URL": url
            })
        # Removed redundant logging here, main loop logs success/failure
    except IOError as e:
        logging.error(f"Failed to write to history CSV {history_file_path}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error saving to history CSV {history_file_path}: {e}")

# --- update_csv function (Keep as is) ---
def update_csv(csv_file, scraped_data, csv_rows, prices_history_file):
    """Updates an existing CSV file (pricesSheet.csv) with new event data,
       including the all-time low price, while preserving other rows.
    """
    main_csv_path = Path(csv_file)
    if not main_csv_path.exists():
        logging.error(f"Main CSV file {csv_file} not found. Cannot update.")
        return

    all_time_lows = get_all_time_lows(prices_history_file)
    updated_rows = []
    urls_in_main_csv = {row.get('URL', '').strip() for row in csv_rows if row.get('URL')} # Robust check

    # Process existing rows
    for row in csv_rows:
        url = row.get("URL", "").strip()
        if not url:
            logging.warning(f"Skipping row in {csv_file} due to missing/empty URL: {row}")
            updated_rows.append(row)
            continue

        found_update = False
        for data in scraped_data:
             # Ensure comparison is between stripped URLs if necessary
            if url == data.get("URL", "").strip():
                row['Time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                row["Event Title"] = data.get("Event Title", row.get("Event Title", "N/A")) # Keep old if new is N/A?
                row["Date"] = data.get("Date", row.get("Date", "N/A"))
                row["Location"] = data.get("Location", row.get("Location", "N/A"))
                # Only update price if a valid new one was found (not None/Error)
                new_price = data.get("Price")
                if new_price is not None and new_price != "Error":
                     row["Price"] = new_price if new_price is not None else "N/A"
                elif "Price" not in row: # Ensure Price column exists
                     row["Price"] = "N/A"
                # else: keep the old price

                found_update = True
                break

        # Update all-time low price (always do this for existing rows)
        if url in all_time_lows:
            row["All Time Low Price"] = f"${all_time_lows[url]:,.2f}"
        elif "All Time Low Price" not in row: # Add column if missing
            row["All Time Low Price"] = "N/A"
        # else: keep potentially existing N/A or old value if no history found

        updated_rows.append(row)

    # Add new URLs not originally in the main CSV
    scraped_urls = {data.get('URL', '').strip() for data in scraped_data if data.get('URL')}
    new_urls = scraped_urls - urls_in_main_csv
    for url in new_urls:
        for data in scraped_data:
            if url == data.get("URL", "").strip():
                new_row = {
                    "Time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "Event Title": data.get("Event Title", "N/A"),
                    "Date": data.get("Date", "N/A"),
                    "Location": data.get("Location", "N/A"),
                    "Price": data.get("Price") if data.get("Price") is not None else "N/A",
                    "All Time Low Price": f"${all_time_lows[url]:,.2f}" if url in all_time_lows else "N/A",
                    "URL": url
                }
                updated_rows.append(new_row)
                logging.info(f"Added new URL {url} to {csv_file}")
                break

    # Write back to CSV
    try:
        # Determine fieldnames dynamically but prioritize standard ones
        fieldnames_std = ["Time", "Event Title", "Date", "Location", "Price", "All Time Low Price", "URL"]
        all_keys = set().union(*(d.keys() for d in updated_rows)) if updated_rows else set(fieldnames_std)
        # Ensure standard fields come first, then any others alphabetically
        final_fieldnames = [f for f in fieldnames_std if f in all_keys]
        final_fieldnames += sorted([k for k in all_keys if k not in fieldnames_std])

        # Ensure all standard fields are present even if no rows exist yet
        if not final_fieldnames: final_fieldnames = fieldnames_std

        with main_csv_path.open("w", newline='', encoding='utf-8') as file:
            # Use restval='' to write empty string for missing keys, ignore extras
            writer = csv.DictWriter(file, fieldnames=final_fieldnames, restval='', extrasaction='ignore')
            writer.writeheader()
            writer.writerows(updated_rows)
        logging.info(f"✅ CSV file {csv_file} updated successfully.")
    except IOError as e:
        logging.error(f"Failed to write updated data to {csv_file}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error updating {csv_file}: {e}", exc_info=True)


# --- get_all_time_lows function (Keep as is) ---
def get_all_time_lows(prices_history_file):
    """Reads the pricesHistory.csv file and returns a dictionary mapping URL
       to its lowest recorded numeric price.
    """
    all_time_lows = {}
    file_path = Path(prices_history_file)
    if not file_path.exists():
        logging.warning(f"Prices history file {prices_history_file} not found. Cannot calculate all-time lows.")
        return all_time_lows
    try:
        with file_path.open("r", newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for i, row in enumerate(reader):
                try:
                    url = row.get("URL", "").strip()
                    price_str = row.get("Price")
                    if not url or not price_str or price_str.lower() in ["n/a", "sold out", "error"]:
                        continue
                    cleaned_price = price_str.replace('$', '').replace(',', '').strip()
                    numeric_price = float(cleaned_price)
                    current_low = all_time_lows.get(url)
                    if current_low is None or numeric_price < current_low:
                        all_time_lows[url] = numeric_price
                except (ValueError, TypeError) as ve:
                    logging.warning(f"Could not parse price '{price_str}' as number in {prices_history_file} at row ~{i+2}. Skipping. Error: {ve}")
                except KeyError as e:
                    logging.warning(f"Missing expected column header '{e}' in {prices_history_file} at row ~{i+2}.")
                except Exception as e:
                     logging.error(f"Unexpected error processing row ~{i+2} in {prices_history_file}: {e}", exc_info=True)
    except IOError as e:
        logging.error(f"Failed to read prices history file {prices_history_file}: {e}")
    except Exception as e:
         logging.error(f"Unexpected error reading {prices_history_file}: {e}", exc_info=True)
    logging.info(f"Calculated all-time lows for {len(all_time_lows)} URLs from {prices_history_file}")
    return all_time_lows


# --- process_url function (Keep as is) ---
def process_url(url, history_file_path):
    """Sets up a driver, processes a single URL, saves to history, and closes driver."""
    driver = None
    scraped_data = {"URL": url, "Event Title": "Error", "Date": "Error", "Location": "Error", "Price": None} # Default error state
    try:
        driver = setup_driver()
        event_title, event_date, event_location, price = extract_event_details(driver, url)
        # Update scraped_data with actual results
        scraped_data.update({
            "Event Title": event_title,
            "Date": event_date,
            "Location": event_location,
            "Price": price # Can be price string, "Sold Out", or None
        })
        # Save raw scrape data regardless of price found
        save_price_to_csv(url, event_title, event_date, event_location, price, history_file_path)

        if price and price not in ["N/A", "Sold Out", None]:
            logging.info(f"✅ Price found for '{event_title or url}': {price}")
        elif price == "Sold Out":
             logging.info(f"ℹ️ Event '{event_title or url}' is Sold Out.")
        else:
            # This covers price being None or N/A from extraction failure
            logging.warning(f"❌ No valid price data obtained for '{event_title or url}' ({url}). Recorded N/A.")

        return scraped_data # Return the dictionary
    except Exception as e:
        logging.error(f"Critical error processing URL {url} in process_url: {e}", exc_info=True)
        # Save N/A state to history if a critical error happened before save_price_to_csv
        save_price_to_csv(url, "Error", "Error", "Error", None, history_file_path)
        return scraped_data # Return the default error state dictionary
    finally:
        if driver:
            try:
                driver.quit()
                logging.debug(f"Closed WebDriver for {url}")
            except Exception as e:
                logging.error(f"Error quitting WebDriver for {url}: {e}")

# --- main function (Keep mostly as is, adjust worker default potentially) ---
def main():
    parser = argparse.ArgumentParser(description="StubHub Price Tracker for Multiple URLs")
    parser.add_argument("links", nargs="*", help="One or more StubHub event URLs to scrape")
    parser.add_argument("--file", type=str, help="Path to a TXT file containing URLs (one per line)")
    parser.add_argument("--csv", type=str, help="Path to the main CSV file to update (e.g., pricesSheet.csv)")
    parser.add_argument("--history", type=str, default="/Users/malachyayala/Desktop/scripts/stubhubScraper/pricesHistory.csv", help="Path to the price history CSV (pricesHistory.csv)")
    # Consider keeping default workers low (2 or 3) due to resource intensity
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel threads (default: 4)")

    args = parser.parse_args()
    urls_to_process = set() # Initialize empty set
    # Add command line links first
    for link in args.links:
        stripped_link = link.strip()
        if stripped_link: urls_to_process.add(stripped_link)

    # Read from TXT file
    if args.file:
        file_path = Path(args.file)
        if file_path.exists():
            try:
                with file_path.open("r", encoding='utf-8') as f:
                    initial_count = len(urls_to_process)
                    for line in f:
                        stripped_line = line.strip()
                        if stripped_line and not stripped_line.startswith('#'):
                            urls_to_process.add(stripped_line)
                    logging.info(f"Loaded {len(urls_to_process) - initial_count} new unique URLs from {args.file}. Total: {len(urls_to_process)}")
            except Exception as e:
                 logging.error(f"Error reading TXT file {args.file}: {e}", exc_info=True)
        else:
            logging.warning(f"TXT file {args.file} not found.")

    # Read from main CSV file
    csv_rows = []
    main_csv_path = None
    if args.csv:
        main_csv_path = Path(args.csv)
        if main_csv_path.exists():
            try:
                with main_csv_path.open("r", newline='', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    # Check header robustness
                    if not reader.fieldnames:
                         logging.warning(f"Main CSV file {args.csv} appears to be empty or has no header.")
                    elif "URL" not in reader.fieldnames:
                         logging.error(f"Main CSV file {args.csv} is missing the required 'URL' column header. Cannot process URLs from it.")
                    else:
                        initial_count = len(urls_to_process)
                        temp_rows = list(reader) # Read all rows first
                        csv_rows = temp_rows # Store for update function
                        urls_from_csv = 0
                        for row in temp_rows:
                            url = row.get("URL", "").strip()
                            if url:
                                if url not in urls_to_process:
                                    urls_to_process.add(url)
                                    urls_from_csv += 1
                        logging.info(f"Loaded {urls_from_csv} new unique URLs from {args.csv}. Total: {len(urls_to_process)}")

            except Exception as e:
                 logging.error(f"Error reading main CSV file {args.csv}: {e}", exc_info=True)
        else:
            logging.warning(f"Main CSV file {args.csv} not found. It may be created by the update function if data is scraped.")
            csv_rows = []

    if not urls_to_process:
        logging.error("No valid URLs provided or found. Exiting.")
        return

    history_file_path = Path(args.history).resolve()
    logging.info(f"Using history file: {history_file_path}")
    try:
        history_file_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
         logging.error(f"Could not create directory for history file {history_file_path.parent}: {e}")
         return # Stop if we can't ensure history dir exists

    urls_list = list(urls_to_process)
    logging.info(f"Processing {len(urls_list)} unique URLs with {args.workers} workers...")

    all_results = []
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            # Pass history path using lambda or functools.partial
            results_iterator = executor.map(lambda url: process_url(url, history_file_path), urls_list)
            all_results = list(results_iterator) # Collect results
    except Exception as e:
         logging.error(f"Error occurred during parallel execution: {e}", exc_info=True)

    valid_results = [r for r in all_results if isinstance(r, dict)] # Ensure results are dicts
    logging.info(f"Finished processing. Received {len(valid_results)} results (out of {len(urls_list)} URLs).")

    # Update main CSV if specified and results exist
    if args.csv:
        if valid_results:
            if main_csv_path:
                 update_csv(str(main_csv_path), valid_results, csv_rows, str(history_file_path))
            else:
                 logging.error("Cannot update main CSV: path was not determined (file likely didn't exist initially).")
        else:
            logging.warning("No valid scraping results obtained; skipping update of main CSV file.")
    else:
        logging.info("No main CSV file specified (--csv), skipping update.")

    end_time = time.time()
    total_runtime = end_time - start_time
    logging.info(f"⏱️ Total runtime: {total_runtime:.2f} seconds")

if __name__ == "__main__":
    main()