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
    try:
        driver.get(url)

        # Extract event title
        try:
            event_title_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="event-detail-header"]/div/div/div[1]/div[2]/a/h6'))
            )
            event_title = event_title_element.text.strip()
            print(f"🎟️ Event Title: {event_title}")
        except TimeoutException:
            print(f"⚠️ Event title not found on {url}")
            event_title = "N/A"

        # Extract event date
        try:
            event_date_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="event-detail-header"]/div/div/div[1]/div[2]/div/div/div[1]/div/span'))
            )
            event_date = event_date_element.text.strip()
            print(f"📅 Event Date: {event_date}")
        except TimeoutException:
            print(f"⚠️ Event date not found on {url}")
            event_date = "N/A"

        # Extract event location
        try:
            location_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div[1]/div/div/div[1]/div[2]/div/div/div[2]/button'))
            )
            event_location = location_element.text.strip()
            print(f"📍 Event Location: {event_location}")
        except TimeoutException:
            print(f"⚠️ Event location not found on {url}")
            event_location = "N/A"

        # Attempt to click button (if necessary)
        try:
            button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="modal-root"]/div/div/div/div[2]/div[3]/button'))
            )
            button.click()
            print(f"✅ Clicked the button on {url}")
        except TimeoutException:
            print(f"⚠️ Button not found or not clickable on {url}. Continuing without clicking.")

        # Extract price
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="listings-container"]/div[1]/div'))
        )
        element = driver.find_element(By.XPATH, '//*[@id="listings-container"]/div[1]/div')
        page_text = element.text.strip()

        price_pattern = r'\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?'
        match = re.search(price_pattern, page_text)
        price = match.group(0) if match else None

        return event_title, event_date, event_location, price

    except TimeoutException:
        print(f"Timeout while extracting details from {url}")
        return "N/A", "N/A", "N/A", None
    except NoSuchElementException:
        print(f"Price element not found on {url}")
        return "N/A", "N/A", "N/A", None
    except Exception as e:
        print(f"Error extracting details from {url}: {e}")
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