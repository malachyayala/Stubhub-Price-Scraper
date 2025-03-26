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
    """Extracts the event title and price from the webpage."""
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

        # Attempt to click button (if necessary)
        try:
            button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="modal-root"]/div/div/div/div[2]/div[3]/button'))
            )
            button.click()
            print(f"✅ Clicked the button on {url}")
            time.sleep(5)  # Allow modal content to load
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

        return event_title, price

    except TimeoutException:
        print(f"Timeout while extracting details from {url}")
        return "N/A", None
    except NoSuchElementException:
        print(f"Price element not found on {url}")
        return "N/A", None
    except Exception as e:
        print(f"Error extracting details from {url}: {e}")
        return "N/A", None

def save_price_to_csv(url, event_title, price):
    """Appends event title, price, and timestamp to a CSV file."""
    file_path = Path("/Users/cr7/Desktop/scripts/stubhubScraper/prices.csv")  # Use absolute path
    write_header = not file_path.exists()

    with file_path.open(mode='a', newline='') as file:
        fieldnames = ['Time', 'Event Title', 'Price', 'URL']
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if write_header:
            writer.writeheader()
        
        writer.writerow({
            'Time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'Event Title': event_title,
            'Price': price or "N/A",
            'URL': url
        })

def process_url(url):
    """Processes a single URL by extracting event title and price, then saving them."""
    driver = setup_driver()
    
    try:
        event_title, price = extract_event_details(driver, url)
        if price:
            print(f"✅ Price found for {event_title}: {price}")
            save_price_to_csv(url, event_title, price)
        else:
            print(f"❌ No price found for {event_title}.")
    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Price Tracker for Multiple URLs")
    parser.add_argument("links", nargs="*", help="One or more URLs to scrape")
    parser.add_argument("--file", type=str, help="Path to a file containing URLs (one per line)")

    args = parser.parse_args()

    # Read URLs from file if provided
    urls = args.links
    if args.file:
        file_path = Path(args.file)
        if file_path.exists():
            with file_path.open("r") as f:
                urls.extend(line.strip() for line in f.readlines() if line.strip())

    if not urls:
        print("No URLs provided. Please specify at least one URL.")
        return

    # Run scraping tasks in parallel for efficiency
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(process_url, urls)


if __name__ == "__main__":
    main()