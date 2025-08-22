"""
Skolmaten API - Python Wrapper
A Python library for accessing school lunch menus from Skolmaten.se.
"""
import time
import re
import logging
from typing import List
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import os

# Set up logging
logger = logging.getLogger(__name__)


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
            
            # Get week title
            try:
                week_title = self.driver.find_element(
                    By.CSS_SELECTOR, ".text-2xl.font-semibold"
                ).text
                logger.info(f"Week title found: '{week_title}'")
            except Exception as e:
                logger.warning(f"Could not find week title element: {e}")
                week_title = "Unknown Week"

            # Support both Swedish and English day names
            swedish_days = ["måndag", "tisdag", "onsdag", "torsdag", "fredag"]
            english_days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
            all_days = swedish_days + english_days
            
            lines = [line.strip() for line in page_text.split("\n") if line.strip()]
            logger.info(f"Split page text into {len(lines)} lines")
            
            # Log first few lines for debugging
            if lines:
                logger.info(f"First 5 lines: {lines[:5]}")
            
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
                            if next_line and len(next_line) > 5:
                                if not re.match(r"^\d{4}-\d{2}-\d{2}$", next_line):
                                    if "Med reservation" not in next_line:
                                        menu_items.append(next_line)
                                        logger.info(f"  Added menu item: '{next_line}'")
                                else:
                                    current_date = next_line
                                    logger.info(f"  Found date: '{current_date}'")
                            j += 1
                        
                        if menu_items:
                            menu_entry = {
                                "weekday": current_day,
                                "date": current_date,
                                "week": int(week_title.split()[-1]) if week_title != "Unknown Week" and week_title.split()[-1].isdigit() else None,
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
        self, school_name: str, also_next_week: bool = False
    ) -> List[dict]:
        """
        Fetch lunch menu for a school

        Args:
            school_name: Name of the school (e.g., 'svenstorps-forskola')
            also_next_week: Whether to fetch next week's menu

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
            
            menu_list = self._parse_menu_data(school_name)
            logger.info(f"Current week menu parsed: {len(menu_list)} entries")
            
            if also_next_week:
                logger.info("Attempting to fetch next week's menu...")
                # Try both Swedish and English text for next week button
                selectors = [
                    "//*[contains(text(), 'Nästa vecka')]",  # Swedish
                    "//*[contains(text(), 'Next week')]",   # English
                    "//*[contains(text(), 'nästa vecka')]", # Swedish lowercase
                    "//*[contains(text(), 'next week')]"    # English lowercase
                ]
                
                next_week_button = None
                button_text = None
                
                for selector in selectors:
                    try:
                        next_week_button = WebDriverWait(self.driver, 1).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        button_text = next_week_button.text
                        logger.info(f"Found next week button with text: '{button_text}'")
                        break
                    except:
                        continue
                
                if next_week_button:
                    logger.info(f"Clicking next week button: '{button_text}'")
                    next_week_button.click()
                    
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.ID, "menu-container"))
                    )
                    logger.info("Next week page loaded, parsing...")
                    
                    next_week_menu = self._parse_menu_data(school_name)
                    menu_list += next_week_menu
                    logger.info(f"Next week menu parsed: {len(next_week_menu)} entries")
                    
                else:
                    logger.warning("Could not find next week button in any language (Swedish/English)")
                    # Log available buttons for debugging
                    try:
                        all_buttons = self.driver.find_elements(By.XPATH, "//button | //a | //*[@role='button']")
                        button_texts = [btn.text.strip() for btn in all_buttons if btn.text.strip()]
                        logger.info(f"Available clickable elements with text: {button_texts}")
                    except:
                        logger.warning("Could not retrieve available buttons for debugging")
            
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
    school_name: str, next_week: bool = False, headless: bool = True
) -> List[dict]:
    """
    Convenience function to get school menu

    Args:
        school_name: Name of the school
        next_week: Whether to get next week's menu (default: False)
        headless: Whether to run browser in headless mode (default: True)

    Returns:
        List of menu entries, each as a dict
    """
    with SkolmatenAPI(headless=headless) as api:
        return api.get_menu(school_name, also_next_week=next_week)
