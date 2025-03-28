#!/usr/bin/env python3
import argparse
import csv
import re
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

import time  # Import the time module

# Record the start time
start_time = time.time()

def setup_driver():
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-images")  # Disable images
    return webdriver.Chrome(service=service, options=options)

def extract_event_details(driver, url):
    event_title, event_date, event_location, price = "N/A", "N/A", "N/A", None

    try:
        driver.get(url)

        # --- Extract event title (using JS) ---
        try:
            event_title_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="event-detail-header"]/div/div/div[1]/div[2]/a/h6'))
            )
            event_title = driver.execute_script("return arguments[0].textContent;", event_title_element).strip()

            print(f"🎟️ Event Title: {event_title}")
        except TimeoutException:
            print(f"⚠️ Event title not found on {url}")

        # --- Extract event date ---
        try:
            event_date_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="event-detail-header"]/div/div/div[1]/div[2]/div/div/div[1]/div/span'))
            )
            event_date = event_date_element.text.strip()
            print(f"📅 Event Date: {event_date}")
        except TimeoutException:
            print(f"⚠️ Event date not found on {url}")

        # --- Extract event location ---
        try:
            location_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[1]/div/div/div[1]/div[2]/div/div/div[2]/button'))
            )
            event_location = location_element.text.strip()
            print(f"📍 Event Location: {event_location}")
        except TimeoutException:
            print(f"⚠️ Event location not found on {url}")

        # --- Attempt to click the modal button (if necessary) ---
        short_wait = 3
        try:
            button_xpath = '//*[@id="modal-root"]/div/div/div/div[2]/div[3]/button'
            button = WebDriverWait(driver, short_wait).until(
                EC.element_to_be_clickable((By.XPATH, button_xpath))
            )
            driver.execute_script("arguments[0].click();", button)  # Use JS to click
            print(f"✅ Clicked a potential modal button on {url}")

        except TimeoutException:
            print(f"ℹ️ Modal button ({button_xpath}) not found or not clickable within {short_wait}s on {url}. Continuing...")
        except Exception as e:
            print(f"⚠️ Error interacting with modal button on {url}: {e}. Continuing...")

        # --- Extract price ---
        try:
            price_container_xpath = '//*[@id="listings-container"]/div[1]/div'
            price_element_container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, price_container_xpath))
            )
            page_text = price_element_container.text.strip()

            price_pattern = re.compile(r'\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?')  # Compile regex
            match = price_pattern.search(page_text)
            if match:
                price = match.group(0)
                print(f"💰 Price Found: {price}")
            else:
                print(f"⚠️ Price pattern not found in container text on {url}")

        except TimeoutException:
            print(f"❌ Price container ({price_container_xpath}) not found after waiting on {url}")
        except Exception as e:
            print(f"❌ Error extracting price on {url}: {e}")

        return event_title, event_date, event_location, price

    except Exception as e:
        print(f"SEVERE: An unexpected error occurred processing {url}: {e}")
        return "N/A", "N/A", "N/A", None

def save_price_to_csv(url, event_title, event_date, event_location, price):
    """Appends event details including the date to a CSV file."""
    file_path = Path("/Users/cr7/Desktop/scripts/stubhubScraper/pricesHistory.csv")  # Use absolute path
    write_header = not file_path.exists()

    with file_path.open("a", newline='') as file:
        fieldnames = ["Time", "Event Title", "Date", "Location", "Price", "URL"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if write_header:
            writer.writeheader()
        
        writer.writerow({
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Event Title": event_title,
            "Date": event_date,
            "Location": event_location,
            "Price": price or "N/A",
            "URL": url
        })

def update_csv(csv_file, scraped_data, csv_rows, prices_history_file):
    """Updates an existing CSV file with new event data, including the all-time low price,
       while preserving other rows.
    """
    file_path = Path(csv_file)
    if not file_path.exists():
        print(f"CSV file {csv_file} not found.")
        return

    all_time_lows = get_all_time_lows(prices_history_file)

    updated_rows = []
    for row in csv_rows:
        url = row["URL"]
        # Update with scraped data
        for data in scraped_data:
            if url == data["URL"]:
                row['Time'] = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
                row["Event Title"] = data["Event Title"]
                row["Date"] = data["Date"]
                row["Location"] = data["Location"]
                row["Price"] = data["Price"]

        # Update all-time low price
        if url in all_time_lows:
            row["All Time Low Price"] = all_time_lows[url]  # Add the all-time low to the row
        else:
            row["All Time Low Price"] = "N/A"  # Or some default if not found

        updated_rows.append(row)

    # Write the updated data back to the CSV
    with file_path.open("w", newline='') as file:
        fieldnames = ["Time", "Event Title", "Date", "Location", "Price", "URL", "All Time Low Price"] # Add new field
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_rows)

    print(f"✅ CSV file {csv_file} updated successfully.")

def get_all_time_lows(prices_history_file):
    """
    Reads the pricesHistory.csv file and returns a dictionary of all-time low prices
    for each URL.
    """
    all_time_lows = {}
    file_path = Path(prices_history_file)

    if not file_path.exists():
        print(f"Prices history file {prices_history_file} not found.")
        return all_time_lows  # Return empty dict

    with file_path.open("r", newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            try:
                url = row["URL"]
                price = row["Price"]
                if price and price != "N/A":
                    # Remove the dollar sign and convert to float
                    price = float(price.replace('$', '').replace(',', ''))
                    if url not in all_time_lows or price < all_time_lows[url]:
                        all_time_lows[url] = price
            except ValueError:
                print(f"Warning: Could not parse price '{row['Price']}' in {prices_history_file}")
                continue
            except KeyError as e:
                 print(f"KeyError: {e} - Check if your CSV has the correct headers.")
                 continue
    return all_time_lows

def process_url(url):
    """Processes a single URL by extracting event details."""
    driver = setup_driver()

    try:
        event_title, event_date, event_location, price = extract_event_details(driver, url)
        if price:
            print(f"✅ Price found for {event_title} on {event_date} at {event_location}: {price}")
            save_price_to_csv(url, event_title, event_date, event_location, price)
        else:
            print(f"❌ No price found for {event_title} on {event_date} at {event_location}.")
        return {"URL": url, "Event Title": event_title, "Date": event_date, "Location": event_location, "Price": price or "N/A"}
    finally:
        driver.quit()

def main():
    parser = argparse.ArgumentParser(description="Price Tracker for Multiple URLs")
    parser.add_argument("links", nargs="*", help="One or more URLs to scrape")
    parser.add_argument("--file", type=str, help="Path to a file containing URLs (one per line)")
    parser.add_argument("--csv", type=str, help="Path to a CSV file containing URLs in the 'URL' column (pricesSheet.csv)")
    parser.add_argument("--history", type=str, default="/Users/cr7/Desktop/scripts/stubhubScraper/pricesHistory.csv", help="Path to the price history CSV (pricesHistory.csv)")

    args = parser.parse_args()

    urls = args.links

    # Read from a TXT file
    if args.file:
        file_path = Path(args.file)
        if file_path.exists():
            with file_path.open("r") as f:
                urls.extend(line.strip() for line in f.readlines() if line.strip())

    # Read from a CSV file
    csv_rows = []
    if args.csv:
        csv_path = Path(args.csv)
        if csv_path.exists():
            with csv_path.open("r", newline='') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row.get("URL"):  # Ensure the URL column exists
                        urls.append(row["URL"].strip())
                        csv_rows.append(row)  # Store full row for updating later

    if not urls:
        print("No URLs provided. Please specify at least one URL.")
        return

    # Process URLs in parallel
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(process_url, urls)

    # If using a CSV, update it with new data
    if args.csv:
        update_csv(args.csv, list(results), csv_rows, args.history) # Pass history file path

    # Display the total runtime
    end_time = time.time()
    total_runtime = end_time - start_time
    print(f"⏱️ Total runtime: {total_runtime:.2f} seconds")

if __name__ == "__main__":
    main()