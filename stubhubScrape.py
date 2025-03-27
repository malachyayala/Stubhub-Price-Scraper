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

def setup_driver():
    """Sets up and returns a Selenium WebDriver instance."""
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run in headless mode for efficiency
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")  # Reduce logging verbosity
    return webdriver.Chrome(service=service, options=options)

def extract_event_details(driver, url):
    """Extracts the event title, date, location, and price from the webpage."""
    event_title, event_date, event_location, price = "N/A", "N/A", "N/A", None  # Initialize variables

    try:
        driver.get(url)

        # --- Extract event title ---
        try:
            event_title_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="event-detail-header"]/div/div/div[1]/div[2]/a/h6'))
            )
            event_title = event_title_element.text.strip()
            print(f"🎟️ Event Title: {event_title}")
        except TimeoutException:
            print(f"⚠️ Event title not found on {url}")
            # event_title remains "N/A"

        # --- Extract event date ---
        try:
            event_date_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="event-detail-header"]/div/div/div[1]/div[2]/div/div/div[1]/div/span'))
            )
            event_date = event_date_element.text.strip()
            print(f"📅 Event Date: {event_date}")
        except TimeoutException:
            print(f"⚠️ Event date not found on {url}")
            # event_date remains "N/A"

        # --- Extract event location ---
        try:
            location_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[1]/div/div/div[1]/div[2]/div/div/div[2]/button'))
            )
            event_location = location_element.text.strip()
            print(f"📍 Event Location: {event_location}")
        except TimeoutException:
            print(f"⚠️ Event location not found on {url}")
            # event_location remains "N/A"

        # --- Attempt to click the modal button (if necessary) ---
        # Use a shorter timeout (e.g., 2-3 seconds) as we don't want to wait long if it's irrelevant
        short_wait = 3
        try:
            # More robust selector for a button within the modal, if possible
            # Example: Look for a button with specific text or data attribute
            # If the XPath remains the only option:
            button_xpath = '//*[@id="modal-root"]/div/div/div/div[2]/div[3]/button'

            # Wait briefly for the button to be present and clickable
            button = WebDriverWait(driver, short_wait).until(
                EC.element_to_be_clickable((By.XPATH, button_xpath))
            )
            button.click()
            print(f"✅ Clicked a potential modal button on {url}")
            # Instead of time.sleep(), maybe wait for the button to disappear?
            # Or better yet, rely on the subsequent wait for the price element.
            # Optional: Wait for invisibility if the button should disappear after click
            # try:
            #    WebDriverWait(driver, 5).until(
            #        EC.invisibility_of_element_located((By.XPATH, button_xpath))
            #    )
            #    print(f"✅ Modal button disappeared after click on {url}")
            # except TimeoutException:
            #    print(f"⚠️ Modal button did not disappear after click on {url}")

        except TimeoutException:
            # Button not found/clickable within the short timeout. This is often OK.
            print(f"ℹ️ Modal button ({button_xpath}) not found or not clickable within {short_wait}s on {url}. Continuing...")
        except Exception as e:
            # Catch other potential exceptions during click, like ElementClickInterceptedException
            print(f"⚠️ Error interacting with modal button on {url}: {e}. Continuing...")

        # --- Extract price ---
        # Now, wait for the actual price element. This wait handles page loading
        # regardless of whether the button was clicked or not.
        try:
            # Use a more robust locator for the price if possible!
            price_container_xpath = '//*[@id="listings-container"]/div[1]/div'
            # Wait up to 10 seconds for the element containing price info
            price_element_container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, price_container_xpath))
            )
            page_text = price_element_container.text.strip()

            # Use regex to find the first price pattern
            price_pattern = r'\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?'
            match = re.search(price_pattern, page_text)
            if match:
                price = match.group(0)
                print(f"💰 Price Found: {price}")
            else:
                print(f"⚠️ Price pattern not found in container text on {url}")
                # price remains None

        except TimeoutException:
            print(f"❌ Price container ({price_container_xpath}) not found after waiting on {url}")
            # price remains None
        except Exception as e:
            print(f"❌ Error extracting price on {url}: {e}")
            # price remains None

        # Return all collected details
        return event_title, event_date, event_location, price

    except Exception as e:
        print(f"SEVERE: An unexpected error occurred processing {url}: {e}")
        # Return default values in case of a major failure early on
        return "N/A", "N/A", "N/A", None

    # REMOVE the redundant except blocks that were previously at the end here.
    # The final return is handled within the main try block,
    # and the outer except Exception catches broader issues.

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

def update_csv(csv_file, scraped_data, csv_rows):
    """Updates an existing CSV file with new event data while preserving other rows."""
    file_path = Path(csv_file)
    if not file_path.exists():
        print(f"CSV file {csv_file} not found.")
        return

    updated_rows = []
    for row in csv_rows:
        for data in scraped_data:
            if row["URL"] == data["URL"]:
                row['Time'] = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
                row["Event Title"] = data["Event Title"]
                row["Date"] = data["Date"]
                row["Location"] = data["Location"]
                row["Price"] = data["Price"]
        updated_rows.append(row)

    # Write the updated data back to the CSV
    with file_path.open("w", newline='') as file:
        fieldnames = ["Time", "Event Title", "Date", "Location", "Price", "URL"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_rows)
    
    print(f"✅ CSV file {csv_file} updated successfully.")

def process_url(url):
    """Processes a single URL by extracting event details and updating/saving them."""
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
    parser.add_argument("--csv", type=str, help="Path to a CSV file containing URLs in the 'URL' column")

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
        update_csv(args.csv, list(results), csv_rows)

if __name__ == "__main__":
    main()