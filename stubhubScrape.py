#!/usr/bin/env python3
# git push -f origin main

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import email
import pandas as pd
import time
import csv
from datetime import datetime
import argparse
import re

def main():
    parser = argparse.ArgumentParser(description="A simple command-line program.")
    parser.add_argument('targetPrice', help="Your target price", type=int)
    parser.add_argument("link", help="Your URL", type=str)

    args = parser.parse_args()

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service)

    driver.get(args.link)
    element = driver.find_element(By.ID, "listings-container")
    price_pattern = r'\$\d+(?:,\d{3})*(?:\.\d{2})?'

    # Search for the first match
    match = re.search(price_pattern, element.text)

    if match:
        # Extract the price
        first_price = match.group(0)
        print("First price found:", first_price)
    else:
        print("No price found.")
        
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Open the CSV file in append mode
    with open('prices.csv', mode='a', newline='') as file:
        writer = csv.writer(file)
        
        # If the file is empty, write the header first
        if file.tell() == 0:
            writer.writerow(['Time', 'Price'])
        
        # Append the data
        writer.writerow([current_time, first_price])
    
    # if first_price == args.targetPrice:
    #     email.sendEmail(first_price)
if __name__ == "__main__":
    main()