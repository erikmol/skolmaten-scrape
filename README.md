# Skolmaten School Menu Home Assistant Add-on

This Home Assistant Add-on fetches school lunch menus from Skolmaten.se and exposes them as sensors in Home Assistant. There are some custom components ([1](https://github.com/Kaptensanders/skolmat), [2](https://github.com/Sha-Darim/skolmaten)) using Skolmaten.se RSS feed, but they lack the functionality of fetching multiple weeks as this is [restricted by the closed API](https://github.com/Kaptensanders/skolmat/issues/26#issuecomment-2819317349). This add-on is instead using selenium/webdriver-manager to scrape the website which is not straightforward in a non-containerized environment such as a custom component. 

Personally, one of the most important features is to plan for the upcoming week, meaning that the menu for next week must exist already on Saturday or Sunday. 

## Features

- Fetches multiple weeks of lunch menus (configurable 1-10 weeks)
- Supports multiple schools
- Creates one sensor per school
- Today's menu as sensor state
- Compatible with [skolmat-card](https://github.com/Kaptensanders/skolmat-card)
- Configurable update interval


## Installation

1. Navigate in your Home Assistant frontend to <kbd>Settings</kbd> -> <kbd>Add-ons</kbd> -> <kbd>Add-on Store (Bottom Right)</kbd>.
2. Click the 3-dots menu at upper right <kbd>...</kbd> > <kbd>Repositories</kbd> and add this repository's URL: [https://github.com/erikmol/skolmaten-scrape](https://github.com/erikmol/skolmaten-scrape)
3. Reload the page, scroll to the bottom to find the new repository, and click the new add-on named "Skolmaten School Menu".

    Note: Home Assistant loads the repository in the background and the new item won't always show up automatically.  You might need to wait a few seconds and then "hard refesh" the page for it to show up.  On most browser the keyboard shortcut for this is CTRL+F5. If it still doesn't show up, clear your browser's cache and it should then.
4. Click <kbd>Install</kbd> and give it a few minutes to finish downloading.
5. Configure your schools in the add-on configuration
6. Start the add-on

## Configuration
- **Schools**:
```yaml
  - name: "Östra Real"
    slug: "ostra-real"
  - name: "Another School"  
    slug: "another-school-slug"
```
- **Update interval**: How often to fetch new data in seconds
- **Number of weeks**: Number of weeks to fetch (1 = current week only, 2 = current + next week, etc.)

## Finding School Slugs

Visit https://skolmaten.se and search for your school. The slug is the last part of the URL.
Example: `https://skolmaten.se/ostra-real` → slug is `ostra-real`

## Sensor Data

Each school creates a sensor with entity ID: `sensor.skolmaten_{school_slug}`

### Sensor State
The current day's menu courses as a comma-separated string.

### Sensor Attributes
- `today_date`: Today's date (YYYY-MM-DD)
- `today_weekday`: Today's weekday name 
- `today_week`: Week number
- `today_courses`: List of today's menu courses
- `courses_count`: Number of courses for today
- `calendar`: Structured menu data organized by week (see below)
- `last_updated`: Timestamp of last update

#### Calendar Structure

The `calendar` attribute contains menu data organized by week number to be compatible with [skolmat-card](https://github.com/Kaptensanders/skolmat-card).

```yaml
calendar:
  "34":
    - weekday: "Monday" 
      date: "2025-08-18"
      week: 34
      courses:
        - "Korv och potatisbullar"
        - "Vegetarisk korv och potatisbullar"
    - weekday: "Tuesday"
      date: "2025-08-19"
      week: 34
      courses:
        - "Köttfärssås och spagetti"
        - "Vegofärssås och spagetti"
  "35":
    - weekday: "Monday"
      date: "2025-08-25"
      week: 35
      courses:
        - "Linsbolognese, spaghetti"
```



## Troubleshooting

Check the add-on logs for detailed information about:
- Chrome browser startup and version
- Page navigation and title detection
- Menu parsing progress for each day/week
- Home Assistant API communication
- Available buttons if "Next week" navigation fails

## Known issues

The add-on is only using English locale which means [skolmat-card](https://github.com/Kaptensanders/skolmat-card) will put English weekdays (Monday) instead of Swedish (Måndag). This is because of how the page renders (and likely because the container is not putting Swedish in its `Accept-Language` header).

Some schools are using bulletins which will be included in the menu. There should be some option to configure one or multiple phrases into a blacklist which is excluded from the menu.

An example of a bulletin is: "Till varje lunch serveras en varierande grönsaksbuffé."