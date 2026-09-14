"""
Skolmaten API - Python Wrapper
A Python library for accessing school lunch menus from Skolmaten.se.
"""
import time
import re
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import os

# Set up logging
logger = logging.getLogger(__name__)

# skolmaten.se renders day headers as an abbreviated month + day, e.g. "Sep 14"
# (no year), in either English or Swedish depending on locale.
_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "maj": 5,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "okt": 10,
    "nov": 11, "dec": 12,
}
_DATE_RE = re.compile(r"^([A-Za-zÅÄÖåäö]{3})\.?\s+(\d{1,2})$")

# The "message from the school" campaign banner sometimes follows the last
# day's dishes inside #menu-container. "campaign" is the Material Symbols
# icon-font ligature for its announcement icon; once either marker is seen
# while collecting a day's courses, everything after it belongs to the
# banner, not the menu.
_BANNER_MARKERS = ("campaign",)
_BANNER_HEADING_MARKERS = ("message from the school", "meddelande från skolan")


def _resolve_menu_date(text: str) -> Optional[str]:
    """Convert a page date string like 'Sep 14' into an ISO date (YYYY-MM-DD)."""
    match = _DATE_RE.match(text)
    if not match:
        return None

    month = _MONTH_ABBR.get(match.group(1).lower())
    if month is None:
        return None
    day = int(match.group(2))

    today = datetime.now().date()
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return None

    # The page has no year. If the resulting date looks far in the past,
    # it's actually next year's date (e.g. fetching a January week in late
    # December).
    if (today - candidate).days > 180:
        candidate = date(today.year + 1, month, day)

    return candidate.isoformat()


class SkolmatenAPI:
    """Main class for interacting with Skolmaten.se API"""

    def __init__(self):
        """
        Initialize the Skolmaten API client
        
        Always runs in headless mode for container environments.
        """
        self.driver = None

    def _setup_driver(self) -> webdriver.Chrome:
        """Setup Chrome WebDriver with appropriate options"""
        chrome_options = Options()
        
        # Always use headless in Docker containers
        chrome_options.add_argument("--headless=new")
        
        # Docker container specific flags
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-field-trial-config")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-component-update")
        chrome_options.add_argument("--disable-client-side-phishing-detection")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-translate")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--no-pings")
        chrome_options.add_argument("--no-zygote")
        chrome_options.add_argument("--single-process")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--silent")
        
        # Set window size for headless mode
        chrome_options.add_argument("--window-size=1920,1080")
        
        # User agent to avoid detection
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

        # Check if we're running in Docker/Alpine Linux
        chrome_binary = os.environ.get('CHROME_BIN')
        chromedriver_path = os.environ.get('CHROME_DRIVER')
        
        if chrome_binary and os.path.exists(chrome_binary):
            chrome_options.binary_location = chrome_binary
        
        if chromedriver_path and os.path.exists(chromedriver_path):
            service = Service(chromedriver_path, log_path=os.devnull)
        else:
            # Fallback to webdriver-manager
            service = Service(
                ChromeDriverManager().install(),
                log_path=os.devnull,
            )
        
        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info(f"Chrome driver started successfully")
            
            # Get Chrome version info
            capabilities = driver.capabilities
            chrome_version = capabilities.get('browserVersion', 'Unknown')
            driver_version = capabilities.get('chrome', {}).get('chromedriverVersion', 'Unknown')
            logger.info(f"Chrome version: {chrome_version}")
            logger.info(f"ChromeDriver version: {driver_version}")
            
            return driver
        except Exception as e:
            logger.error(f"Failed to start Chrome driver: {e}")
            raise

    def __enter__(self):
        """Context manager entry: setup driver"""
        self.driver = self._setup_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: close driver"""
        self.close()

    def close(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def _parse_menu_data(self, school_name: str) -> List[dict]:
        """
        Parse menu data from the current page

        Args:
            school_name: Name of the school

        Returns:
            List of menu entries, each as a dict with keys: items, date, week, day
        """
        menu_list = []
        try:
            logger.info(f"Starting menu parsing for {school_name}")
            
            # Ensure menu container is present
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "menu-container"))
            )
            time.sleep(2)  # Allow time for the page to fully render
            # Get page text
            page_text = self.driver.find_element(By.ID, "menu-container").text
            logger.info(f"Menu container text length: {len(page_text)} characters")
            
            if len(page_text) < 50:  # Suspiciously short
                logger.warning(f"Menu container text is very short: '{page_text}'")
            
            # Support both Swedish and English day names
            swedish_days = ["måndag", "tisdag", "onsdag", "torsdag", "fredag"]
            english_days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
            all_days = swedish_days + english_days

            lines = [line.strip() for line in page_text.split("\n") if line.strip()]
            logger.info(f"Split page text into {len(lines)} lines")

            # Log first few lines for debugging
            if lines:
                logger.info(f"First 5 lines: {lines[:5]}")

            # Get week number. Rather than hunting for the current markup's
            # (brittle, Tailwind-arbitrary-value) class name, pull it out of
            # the container text we already have, since "Vecka 38"/"Week 38"
            # is part of it.
            week_number = None
            week_match = re.search(r"(?:vecka|week)\s+(\d+)", page_text, re.IGNORECASE)
            if week_match:
                week_number = int(week_match.group(1))
                logger.info(f"Week title found: week {week_number}")
            else:
                logger.warning("Could not find week title in menu container text")

            current_day = None
            current_date = None
            
            for i, line in enumerate(lines):
                line_lower = line.lower()
                for day in all_days:
                    if day in line_lower:
                        current_day = line
                        logger.info(f"Found day: '{current_day}' at line {i}")
                        
                        menu_items = []
                        j = i + 1
                        while j < len(lines):
                            next_line = lines[j].strip()
                            if any(d in next_line.lower() for d in all_days):
                                break
                            next_line_lower = next_line.lower()
                            if next_line_lower in _BANNER_MARKERS or any(
                                marker in next_line_lower for marker in _BANNER_HEADING_MARKERS
                            ):
                                logger.info(f"  Reached school message banner at '{next_line}', stopping")
                                break
                            if next_line:
                                resolved_date = _resolve_menu_date(next_line)
                                if resolved_date:
                                    current_date = resolved_date
                                    logger.info(f"  Found date: '{current_date}' (from '{next_line}')")
                                elif len(next_line) > 5 and "Med reservation" not in next_line:
                                    menu_items.append(next_line)
                                    logger.info(f"  Added menu item: '{next_line}'")
                            j += 1
                        
                        if menu_items:
                            menu_entry = {
                                "weekday": current_day,
                                "date": current_date,
                                "week": week_number,
                                "courses": menu_items,
                            }
                            menu_list.append(menu_entry)
                            logger.info(f"  Created menu entry for {current_day}: {len(menu_items)} courses")
                        else:
                            logger.warning(f"  No menu items found for {current_day}")
                        break
            
            logger.info(f"Menu parsing completed. Found {len(menu_list)} days with menus")
            
        except Exception as e:
            logger.error(f"Error parsing menu data for {school_name}: {e}")
            # Log some page source for debugging
            try:
                page_source_snippet = self.driver.page_source[:1000]
                logger.error(f"Page source snippet: {page_source_snippet}")
            except:
                logger.error("Could not retrieve page source snippet")
                
        return menu_list

    def get_menu(
        self, school_name: str, n_weeks: int = 1
    ) -> List[dict]:
        """
        Fetch lunch menu for a school

        Args:
            school_name: Name of the school (e.g., 'svenstorps-forskola')
            n_weeks: Number of weeks to fetch (1 = current week, 2 = current + next, etc.)

        Returns:
            List of menu entries, each as a dict
        """
        url = f"https://skolmaten.se/{school_name}"
        logger.info(f"Navigating to: {url}")
        
        try:
            self.driver.get(url)
            logger.info(f"Navigation completed, waiting for page load...")
            
            # Check page title and URL
            page_title = self.driver.title
            current_url = self.driver.current_url
            logger.info(f"Page loaded - Title: '{page_title}', URL: '{current_url}'")
            
            # Wait for menu container
            logger.info("Waiting for menu-container element...")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "menu-container"))
            )
            logger.info("Menu container found!")
            
            # Check if we got a valid school page
            if "404" in page_title.lower() or "not found" in page_title.lower():
                logger.warning(f"Possible 404 page detected. Title: '{page_title}'")
            
            # Start with current week menu
            menu_list = self._parse_menu_data(school_name)
            logger.info(f"Week 1 menu parsed: {len(menu_list)} entries")
            
            # Fetch additional weeks by navigating directly to
            # ?week=<n>&year=<y>. This is a real page load rather than an
            # in-app click, so it sidesteps the SPA's async content swap
            # entirely (see history of this function) — the driver just
            # loads a fresh document and `presence_of_element_located`
            # actually means something again.
            today = datetime.now().date()
            for week_num in range(2, n_weeks + 1):
                target_date = today + timedelta(weeks=week_num - 1)
                target_year, target_week, _ = target_date.isocalendar()
                week_url = f"https://skolmaten.se/{school_name}?week={target_week}&year={target_year}"
                logger.info(f"Fetching week {week_num} ({target_year}-W{target_week}): {week_url}")

                self.driver.get(week_url)

                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.ID, "menu-container"))
                    )
                except TimeoutException:
                    logger.warning(
                        f"menu-container not found for week {week_num} at {week_url}; "
                        f"stopping at week {week_num - 1}"
                    )
                    break

                if "404" in self.driver.title.lower() or "not found" in self.driver.title.lower():
                    logger.warning(f"Possible 404 page for week {week_num} at {week_url}; stopping")
                    break

                week_menu = self._parse_menu_data(school_name)
                menu_list += week_menu
                logger.info(f"Week {week_num} menu parsed: {len(week_menu)} entries")
            
            logger.info(f"Total menu entries found: {len(menu_list)}")
            return menu_list
            
        except Exception as e:
            logger.error(f"Navigation or page loading failed: {e}")
            # Log page source for debugging if we can get it
            try:
                page_source_length = len(self.driver.page_source)
                logger.info(f"Page source length: {page_source_length} characters")
                if page_source_length < 1000:
                    logger.warning(f"Page source seems too short: {self.driver.page_source[:500]}...")
            except:
                logger.error("Could not retrieve page source for debugging")
            raise


def get_school_menu(
    school_name: str, n_weeks: int = 1
) -> List[dict]:
    """
    Convenience function to get school menu

    Args:
        school_name: Name of the school
        n_weeks: Number of weeks to fetch (1 = current week, 2 = current + next, etc.)

    Returns:
        List of menu entries, each as a dict
    """
    with SkolmatenAPI() as api:
        return api.get_menu(school_name, n_weeks=n_weeks)
