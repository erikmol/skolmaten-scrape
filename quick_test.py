#!/usr/bin/env python3
"""
Quick test script for Skolmaten API
"""

import json
from skolmaten import get_school_menu


def main():
    school_name = "hovagens-forskola"  # svenstorps-forskola

    try:
        current_menu = get_school_menu(school_name, next_week=True, headless=True)
        print(f"Data: {len(current_menu)} days found")

        # Dump into json:
        with open(f"{school_name}.json", "w", encoding="utf-8") as f:
            json.dump(current_menu, f, ensure_ascii=False, indent=4)

    except Exception as e:
        print(f"Error: {e}")
        return False

    return True


if __name__ == "__main__":
    main()
