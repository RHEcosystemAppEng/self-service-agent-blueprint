"""
ServiceNow Personal Developer Instance (PDI) Wake-up Script

This script automates the process of waking up a hibernating ServiceNow
developer instance by logging into the ServiceNow Developer Portal and
triggering the instance wake-up.

"""

import argparse
import logging
import time

from playwright.sync_api import Page, sync_playwright

from .utils import get_env_var


def set_cookies(page: Page) -> None:
    """
    Set cookies to bypass cookie consent modal.

    Args:
        page: Playwright page object
    """
    logging.info("Setting cookies to pre-confirm cookie modal")

    # Create cookie expiration (180 days from now)
    expiration = int(time.time()) + (180 * 24 * 60 * 60)

    cookies = [
        {"name": "notice_preferences", "value": "0"},
        {"name": "notice_gdpr_prefs", "value": "0"},
        {
            "name": "cmapi_gtm_bl",
            "value": "ga-ms-ua-ta-asp-bzi-sp-awct-cts-csm-img-flc-fls-mpm-mpr-m6d-tc-tdc",
        },
        {"name": "cmapi_cookie_privacy", "value": "permit 1 required"},
    ]

    for cookie in cookies:
        page.context.add_cookies(
            [
                {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": "developer.servicenow.com",
                    "path": "/",
                    "expires": expiration,
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ]
        )

    logging.info("Cookies set successfully")


def wake_up_instance(
    username: str, password: str, headless: bool = True, timeout: int = 60
) -> None:
    """
    Wake up ServiceNow PDI by automating the login process.

    Args:
        username: ServiceNow Developer Portal username/email
        password: ServiceNow Developer Portal password
        headless: Run browser in headless mode (default: True)
        timeout: Timeout in seconds (default: 60)

    Raises:
        Exception: If any step in the wake-up process fails
    """
    initial_url = (
        "https://developer.servicenow.com/userlogin.do?"
        "relayState=https%3A%2F%2Fdeveloper.servicenow.com%2F"
        "dev.do%23!%2Fhome%3Fwu%3Dtrue"
    )

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1280},
        )
        page = context.new_page()

        # Set default timeout
        page.set_default_timeout(timeout * 1000)  # Convert to milliseconds

        try:
            # Navigate to the login page
            logging.info(f"Navigating to: {initial_url}")
            page.goto(initial_url)
            logging.info("Successfully navigated to the webpage")

            # Wait for logo to confirm page loaded
            logging.info("Searching for the logo element")
            page.wait_for_selector("#logo", state="visible")
            logging.info("Found logo element")

            # Fill username
            logging.info("Filling out the username field")
            page.fill("#username", username)
            logging.info(f"Filled username field with {username}")

            # Click Next button
            logging.info("Clicking the next button")
            page.click("#identify-submit")
            logging.info("Clicked Next button")

            # Wait for password field
            logging.info("Searching for the password field")
            page.wait_for_selector("#password", state="visible")
            logging.info("Found password field")

            # Fill password
            logging.info("Filling out the password field")
            page.fill("#password", password)
            logging.info("Filled password field with ******")

            # Click Sign In button
            logging.info("Clicking the Sign In button")
            page.click("#challenge-authenticator-submit")
            logging.info("Clicked Sign In button")

            # Wait for navigation to complete after login
            logging.info("Waiting for navigation after login")
            try:
                page.wait_for_url("**/dev.do**", timeout=30000)
                logging.info("Navigation complete - reached developer portal")
            except Exception:
                # Sometimes the URL might be different, just wait a bit
                logging.info("URL didn't match expected pattern, waiting 3 seconds")
                page.wait_for_timeout(3000)

            logging.info("Login successful!")

            # Set cookies to bypass modal
            set_cookies(page)

            logging.info(
                "Instance wakeup initiated successfully, "
                "your instance should be awake pretty soon!"
            )

        except Exception as e:
            logging.error(f"Error during wake-up process: {e}")
            raise

        finally:
            browser.close()


def main() -> None:
    """Main entry point for the wake-up script"""
    parser = argparse.ArgumentParser(
        description="Wake up your ServiceNow developer instance from hibernation"
    )

    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        default=True,
        help="Run browser in visible mode (default: headless)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        help="Timeout in seconds (default: 60)",
        default=60,
    )

    args = parser.parse_args()

    # Set up logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Get credentials from environment variables (required)
    username = get_env_var("SERVICENOW_DEV_PORTAL_USERNAME")
    password = get_env_var("SERVICENOW_DEV_PORTAL_PASSWORD")

    logging.info(
        f"Starting wake-up with debug={args.debug}/"
        f"headless={args.headless}/account={username}"
    )

    try:
        wake_up_instance(
            username=username,
            password=password,
            headless=args.headless,
            timeout=args.timeout,
        )
        logging.info("✅ Wake-up process completed successfully!")
    except Exception as e:
        logging.error(f"❌ Wake-up process failed: {e}")
        raise


if __name__ == "__main__":
    main()
