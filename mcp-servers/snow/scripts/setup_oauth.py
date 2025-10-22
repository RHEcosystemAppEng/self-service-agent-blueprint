#!/usr/bin/env python
"""
ServiceNow OAuth Token Fetcher

This script programmatically retrieves a bearer token from a ServiceNow
instance using OAuth.
The retrieved token can then be used for Bearer Token Authentication.

Usage:
    python mcp-servers/snow/scripts/setup_oauth.py
"""

import base64
import os
import sys
from getpass import getpass

import requests


def get_oauth_token() -> None:
    """
    Guides the user through fetching a ServiceNow OAuth token and prints it.
    """
    print("--- ServiceNow OAuth Token Fetcher ---")
    print("This script will help you get a bearer token from your ServiceNow instance.")
    print("You first need to create an OAuth API client in ServiceNow.")
    print("\nInstructions:")
    print("1. In ServiceNow, navigate to System OAuth > Application Registry.")
    print("2. Click 'New' -> 'Create an OAuth API endpoint for external clients'.")
    print("3. Give it a name (e.g., 'Token Fetcher').")
    print("4. Note the 'Client ID' and 'Client Secret'.\n")

    # --- Collect required information from the user ---
    instance_url = os.getenv("SERVICENOW_INSTANCE_URL")
    if not instance_url:
        instance_url = input(
            "Enter your ServiceNow instance URL (e.g., https://dev12345.service-now.com): "
        )
    instance_url = instance_url.rstrip("/")
    token_url = f"{instance_url}/oauth_token.do"

    client_id = os.getenv("SERVICENOW_CLIENT_ID")
    if not client_id:
        client_id = input("Enter your Client ID: ")

    client_secret = os.getenv("SERVICENOW_CLIENT_SECRET")
    if not client_secret:
        client_secret = getpass("Enter your Client Secret: ")

    access_token = None
    auth_header_val = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    common_headers = {
        "Authorization": f"Basic {auth_header_val}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    username = input("Enter your ServiceNow username: ")
    password = getpass("Enter your ServiceNow password: ")

    try:
        response = requests.post(
            token_url,
            headers=common_headers,
            data={"grant_type": "password", "username": username, "password": password},
            timeout=30,
        )
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get("access_token")
            print("✅ Success! Token obtained using password grant.")
        else:
            print(f"❌ Failed ({response.status_code}): {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ An error occurred: {e}")

    # --- Final Result ---
    if access_token:
        print("\n" + "=" * 50)
        print("🎉 Bearer Token Retrieved Successfully! 🎉")
        print("=" * 50)
        print("\nYour Bearer Token is:")
        print(f"\n{access_token}\n")
        print("You can now use this token with the 'bearer' authentication method:")
        print('export SERVICENOW_AUTH_TYPE="bearer"')
        print(f'export SERVICENOW_BEARER_TOKEN="{access_token}"')
    else:
        print("\n" + "=" * 50)
        print("❌ Could not retrieve a token.")
        print("=" * 50)
        print("\nPlease check:")
        print("1. Your ServiceNow instance URL is correct.")
        print("2. Your Client ID and Client Secret are correct.")
        print("3. The OAuth Application Registry entry in ServiceNow is active.")
        print("4. For password grant, your username and password are correct.")
        sys.exit(1)


if __name__ == "__main__":
    get_oauth_token()
