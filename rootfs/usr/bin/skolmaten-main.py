#!/usr/bin/env python3
"""
Home Assistant Add-on for Skolmaten School Menu
"""

import json
import logging
import os
import time
from datetime import datetime, date
from typing import Dict, List, Optional

import requests
from skolmaten import get_school_menu

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HomeAssistantAPI:
    """Interface for communicating with Home Assistant"""
    
    def __init__(self):
        self.supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
        # Try different API endpoints for Home Assistant add-ons
        self.ha_url = "http://supervisor/core"
        self.headers = {
            "Authorization": f"Bearer {self.supervisor_token}",
            "Content-Type": "application/json"
        }
        
        # Debug logging for authentication
        if self.supervisor_token:
            token_length = len(self.supervisor_token)
            logger.info(f"SUPERVISOR_TOKEN found, length: {token_length} characters")
            logger.info(f"Token starts with: {self.supervisor_token[:10]}...")
        else:
            logger.error("SUPERVISOR_TOKEN environment variable not found!")
            
        logger.info(f"Home Assistant API URL: {self.ha_url}")
        logger.info(f"Authorization header: Bearer {self.supervisor_token[:20] if self.supervisor_token else 'None'}...")
    
    def create_sensor(self, entity_id: str, state: str, attributes: Dict):
        """Create or update a Home Assistant sensor"""
        try:
            data = {
                "state": state,
                "attributes": attributes
            }
            
            api_url = f"{self.ha_url}/api/states/{entity_id}"
            logger.info(f"Attempting to update sensor {entity_id} at URL: {api_url}")
            logger.info(f"Request data keys: {list(data.keys())}")
            
            response = requests.post(
                api_url,
                headers=self.headers,
                json=data,
                timeout=10
            )
            
            logger.info(f"Response status code: {response.status_code}")
            
            if response.status_code == 200 or response.status_code == 201:
                logger.info(f"Successfully updated sensor {entity_id}")
                return True
            else:
                logger.error(f"Failed to update sensor {entity_id}: {response.status_code}")
                
                # Log detailed error information
                try:
                    response_text = response.text
                    logger.error(f"Response body: {response_text}")
                    logger.error(f"Response headers: {dict(response.headers)}")
                except:
                    logger.error("Could not retrieve response details")
                    
                # Try to get more specific error info
                if response.status_code == 401:
                    logger.error("Authentication failed. Checking token and API endpoint...")
                    logger.error(f"Current token length: {len(self.supervisor_token) if self.supervisor_token else 0}")
                    logger.error(f"Current API URL: {api_url}")
                elif response.status_code == 404:
                    logger.error("API endpoint not found. May need different URL.")
                elif response.status_code == 403:
                    logger.error("Forbidden. Add-on may need additional permissions.")
                    
                return False
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error updating sensor {entity_id}: {e}")
            logger.error("This may indicate the Home Assistant API endpoint is unreachable")
            return False
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout error updating sensor {entity_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating sensor {entity_id}: {e}")
            return False

class SkolmatenAddon:
    """Main addon class"""
    
    def __init__(self):
        self.ha_api = HomeAssistantAPI()
        self.schools = self._load_config()
        self.update_interval = int(os.environ.get('UPDATE_INTERVAL', 3600))
        self.n_weeks = int(os.environ.get('N_WEEKS', 1))
    
    def _load_config(self) -> List[Dict]:
        """Load school configuration"""
        try:
            schools_json = os.environ.get('SCHOOLS', '[]')
            if not schools_json or schools_json == '[]':
                logger.error("No schools configured in SCHOOLS environment variable")
                return []
            
            schools = json.loads(schools_json)
            logger.info(f"Loaded {len(schools)} schools from configuration")
            
            # Validate school configuration
            valid_schools = []
            for school in schools:
                if isinstance(school, dict) and 'name' in school and 'slug' in school:
                    valid_schools.append(school)
                else:
                    logger.warning(f"Invalid school configuration: {school}")
            
            return valid_schools
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing SCHOOLS JSON: {e}")
            return []
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return []
    
    def _get_current_menu(self, menu_data: List[Dict]) -> Optional[Dict]:
        """Get today's menu from the menu data"""
        today = date.today().isoformat()
        
        for menu_item in menu_data:
            if menu_item.get('date') == today:
                return menu_item
        
        return None
    
    def _create_calendar_structure(self, menu_data: List[Dict]) -> Dict[str, List[Dict]]:
        """Convert menu data to calendar structure organized by week"""
        calendar = {}
        
        for menu_item in menu_data:
            week = str(menu_item.get('week', 'Unknown'))
            
            if week not in calendar:
                calendar[week] = []
            
            calendar[week].append({
                "weekday": menu_item.get('weekday'),
                "date": menu_item.get('date'),
                "week": menu_item.get('week'),
                "courses": menu_item.get('courses', [])
            })
        
        return calendar
    
    def _create_sensor_attributes(self, menu_data: List[Dict], current_menu: Optional[Dict]) -> Dict:
        """Create sensor attributes from menu data"""
        # Create calendar structure organized by week
        calendar = self._create_calendar_structure(menu_data)
        
        attributes = {
            "icon": "mdi:food",
            "friendly_name": "School Menu",
            "unit_of_measurement": None,
            "device_class": None,
            "calendar": calendar
        }
        
        if current_menu:
            attributes.update({
                "today_date": current_menu.get('date'),
                "today_weekday": current_menu.get('weekday'),
                "today_week": current_menu.get('week'),
                "today_courses": current_menu.get('courses', []),
                "courses_count": len(current_menu.get('courses', []))
            })
        else:
            attributes.update({
                "today_date": None,
                "today_weekday": None,
                "today_week": None,
                "today_courses": [],
                "courses_count": 0
            })
        
        return attributes
    
    def update_school_sensor(self, school: Dict):
        """Update sensor for a single school"""
        school_name = school.get('name', 'Unknown School')
        school_slug = school.get('slug')
        
        if not school_slug:
            logger.error(f"No slug provided for school {school_name}")
            return False
        
        logger.info(f"Updating menu for {school_name} ({school_slug})")
        
        try:
            # Fetch menu data with error handling
            try:
                menu_data = get_school_menu(
                    school_slug, 
                    n_weeks=self.n_weeks
                )
            except Exception as selenium_error:
                logger.error(f"Selenium error for {school_name}: {selenium_error}")
                # Create a sensor with error state
                entity_id = f"sensor.skolmaten_{school_slug.replace('-', '_')}"
                error_attributes = {
                    "icon": "mdi:alert-circle",
                    "friendly_name": f"Menu - {school_name}",
                    "last_updated": datetime.now().isoformat(),
                    "error": str(selenium_error),
                    "calendar": {}
                }
                return self.ha_api.create_sensor(entity_id, "Error fetching menu", error_attributes)
            
            if not menu_data:
                logger.warning(f"No menu data found for {school_name}")
                # Create sensor with no data state
                entity_id = f"sensor.skolmaten_{school_slug.replace('-', '_')}"
                no_data_attributes = {
                    "icon": "mdi:food-off",
                    "friendly_name": f"Menu - {school_name}",
                    "last_updated": datetime.now().isoformat(),
                    "calendar": {}
                }
                return self.ha_api.create_sensor(entity_id, "No menu data available", no_data_attributes)
            
            # Get today's menu
            current_menu = self._get_current_menu(menu_data)
            
            # Prepare sensor state and attributes
            if current_menu:
                state = ", ".join(current_menu.get('courses', []))[:255]  # Limit state length
            else:
                state = "No menu for today"
            
            # Create sensor entity ID
            entity_id = f"sensor.skolmaten_{school_slug.replace('-', '_')}"
            
            # Create attributes
            attributes = self._create_sensor_attributes(menu_data, current_menu)
            attributes['friendly_name'] = school_name
            attributes['last_updated'] = datetime.now().isoformat()
            
            # Update Home Assistant sensor
            success = self.ha_api.create_sensor(entity_id, state, attributes)
            
            if success:
                logger.info(f"Successfully updated sensor for {school_name}")
            else:
                logger.error(f"Failed to update sensor for {school_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Unexpected error updating {school_name}: {e}")
            return False
    
    def update_all_schools(self):
        """Update sensors for all configured schools"""
        logger.info("Starting update cycle for all schools")
        
        if not self.schools:
            logger.warning("No schools configured")
            return
        
        for school in self.schools:
            try:
                self.update_school_sensor(school)
                # Small delay between schools to be respectful to the website
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error processing school {school}: {e}")
        
        logger.info("Completed update cycle")
    
    def run(self):
        """Main run loop"""
        logger.info("Starting Skolmaten Add-on")
        logger.info(f"Configured schools: {len(self.schools)}")
        logger.info(f"Update interval: {self.update_interval} seconds")
        logger.info(f"Number of weeks to fetch: {self.n_weeks}")
        
        # Initial update
        self.update_all_schools()
        
        # Schedule regular updates
        while True:
            try:
                time.sleep(self.update_interval)
                self.update_all_schools()
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(60)  # Wait a minute before retrying

def main():
    """Main entry point"""
    try:
        addon = SkolmatenAddon()
        addon.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        exit(1)

if __name__ == "__main__":
    main()