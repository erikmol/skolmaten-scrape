"""
Skolmaten API - Python Wrapper
A Python library for accessing school lunch menus from Skolmaten.se.
"""

import re
from typing import Dict, List
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import os


class SkolmatenAPI:
    """Main class for interacting with Skolmaten.se API"""

    def __init__(self, headless: bool = True):
        """
        Initialize the Skolmaten API client

        Args:
            headless: Whether to run browser in headless mode (default: True)
        """
        self.headless = headless
        self.driver = None

    def _setup_driver(self) -> webdriver.Chrome:
        """Setup Chrome WebDriver with appropriate options"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--log-level=3")  # Suppress Chrome logs (this is not really working...)

        service = Service(
            ChromeDriverManager().install(),
            log_path=os.devnull,  # Redirect ChromeDriver logs to null device
        )
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver

    def _parse_menu_data(self, school_name: str) -> Dict[str, List[str]]:
        """
        Parse menu data from the current page

        Args:
            school_name: Name of the school

        Returns:
            Dictionary with days as keys and menu items as values
        """
        menu_data = {}

        try:
            page_text = self.driver.find_element(By.ID, "menu-container").text
            week_title = self.driver.find_element(
                By.CSS_SELECTOR, ".text-2xl.font-semibold"
            ).text

            # Look for Swedish day names
            swedish_days = ["måndag", "tisdag", "onsdag", "torsdag", "fredag"]
            lines = [line.strip() for line in page_text.split("\n") if line.strip()]

            current_day = None
            current_date = None
            for i, line in enumerate(lines):
                line_lower = line.lower()
                for day in swedish_days:
                    if day in line_lower:
                        current_day = line
                        # Collect menu items following this day
                        menu_items = []
                        j = i + 1
                        while j < len(lines) and j < i + 5:  # Look ahead max 4 lines
                            next_line = lines[j].strip()
                            if any(d in next_line.lower() for d in swedish_days):
                                break  # Hit next day
                            if next_line and len(next_line) > 5:  # Reasonable menu item
                                # Dont append if on YYYY-MM-DD format:
                                if not re.match(r"^\d{4}-\d{2}-\d{2}$", next_line):
                                    if "Med reservation" not in next_line:
                                        menu_items.append(next_line)
                                    # print(f"Found menu item: {next_line}")
                                else:
                                    current_date = next_line

                            j += 1

                        if menu_items:
                            menu_data[week_title + " " + current_day] = {
                                "items": menu_items,
                                "date": current_date,
                                "week": week_title.split()[-1],  # Extract week number
                                "day": current_day,
                            }

                        break

        except Exception as e:
            print(f"Error parsing menu data for {school_name}: {e}")

        return menu_data

    def get_menu(
        self, school_name: str, also_next_week: bool = False
    ) -> Dict[str, List[str]]:
        """
        Fetch lunch menu for a school

        Args:
            school_name: Name of the school (e.g., 'svenstorps-forskola')

        Returns:
            Dictionary with days as keys and menu items as values
        """
        url = f"https://skolmaten.se/{school_name}"

        if not self.driver:
            self.driver = self._setup_driver()

        self.driver.get(url)
        time.sleep(3)  # Allow page to load

        menu_data = self._parse_menu_data(school_name)

        if also_next_week:
            selector = "//*[contains(text(), 'Nästa vecka')]"
            try:
                next_week_button = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                next_week_button.click()
                time.sleep(3)

                menu_data.update(self._parse_menu_data(school_name))
            except Exception:
                pass

        return menu_data

    def close(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def get_school_menu(
    school_name: str, next_week: bool = False, headless: bool = True
) -> Dict[str, List[str]]:
    """
    Convenience function to get school menu

    Args:
        school_name: Name of the school
        next_week: Whether to get next week's menu (default: False)
        headless: Whether to run browser in headless mode (default: True)

    Returns:
        Dictionary with days as keys and menu items as values
    """
    with SkolmatenAPI(headless=headless) as api:
        return api.get_menu(school_name, also_next_week=next_week)
