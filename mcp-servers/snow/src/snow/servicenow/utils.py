"""Utility functions for ServiceNow operations."""

from datetime import datetime


def _calculate_laptop_age(purchase_date_str: str) -> str:
    """Calculate the age of a laptop in years and months from purchase date.

    Args:
        purchase_date_str: Purchase date in YYYY-MM-DD format

    Returns:
        A string describing the laptop age in years and months
    """
    try:
        purchase_date = datetime.strptime(purchase_date_str, "%Y-%m-%d")
        current_date = datetime.now()

        # Calculate the difference
        years = current_date.year - purchase_date.year
        months = current_date.month - purchase_date.month

        # Adjust if the current day is before the purchase day in the month
        if current_date.day < purchase_date.day:
            months -= 1

        # Adjust years and months if months is negative
        if months < 0:
            years -= 1
            months += 12

        # Format the output
        if years == 0:
            return f"{months} month{'s' if months != 1 else ''}"
        elif months == 0:
            return f"{years} year{'s' if years != 1 else ''}"
        else:
            return f"{years} year{'s' if years != 1 else ''} and {months} month{'s' if months != 1 else ''}"

    except (ValueError, TypeError):
        return "Unable to calculate age (invalid date format)"
