#!/usr/bin/env python3
import argparse
import csv
import re
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


def setup_driver():
    """Sets up and returns a Selenium WebDriver instance."""
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run in headless mode for efficiency
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=service, options=options)


def extract_price(driver, url):
    """Extracts the first price found on the webpage using regex."""
    driver.get(url)
    
    try:
        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "listings-container"))
        )
        price_pattern = r'\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?'
        match = re.search(price_pattern, element.text)
        return match.group(0) if match else None
    except Exception as e:
        print(f"Error extracting price from {url}: {e}")
        return None


def save_price_to_csv(url, price):
    """Appends price and timestamp to a CSV file."""
    file_path = Path("prices.csv")
    write_header = not file_path.exists()

    with file_path.open(mode='a', newline='') as file:
        writer = csv.writer(file)
        if write_header:
            writer.writerow(['Time', 'URL', 'Price'])
        writer.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), url, price])


def process_url(driver, url):
    """Processes a single URL by extracting its price and saving it."""
    price = extract_price(driver, url)
    if price:
        print(f"Price found for {url}: {price}")
        save_price_to_csv(url, price)
    else:
        print(f"No price found for {url}.")


def main():
    parser = argparse.ArgumentParser(description="Price Tracker for Multiple URLs")
    parser.add_argument("links", nargs="+", help="One or more URLs to scrape")
    parser.add_argument("--file", type=str, help="Path to a file containing URLs (one per line)")

    args = parser.parse_args()

    # Read URLs from file if provided
    urls = args.links
    if args.file:
        with open(args.file, "r") as f:
            urls.extend(line.strip() for line in f.readlines() if line.strip())

    # Initialize WebDriver once and reuse it
    driver = setup_driver()

    try:
        # Run scraping tasks in parallel for efficiency
        with ThreadPoolExecutor(max_workers=5) as executor:
            for url in urls:
                executor.submit(process_url, driver, url)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
