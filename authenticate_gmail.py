"""
Standalone script to authenticate with Gmail and save credentials.

This script will:
1. Open a browser for you to log in with Google
2. Save the credentials to a file for later use
3. Test the credentials by listing your emails

Usage:
    python3 authenticate_gmail.py
"""
import json
import os
import sys
from pathlib import Path

# Add py-inbox to path
sys.path.insert(0, str(Path(__file__).parent / "py-inbox"))

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path, override=True)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Gmail API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]

# Credentials file path
CREDENTIALS_FILE = Path(__file__).parent / "gmail_credentials.json"
TOKEN_FILE = Path(__file__).parent / "gmail_token.json"


def authenticate():
    """Authenticate with Google and save credentials."""
    print("=" * 80)
    print("🔐 Gmail Authentication")
    print("=" * 80)

    creds = None

    # Check if we already have valid credentials
    if TOKEN_FILE.exists():
        print("\n📄 Found existing token file...")
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            print("✅ Loaded existing credentials")
        except Exception as e:
            print(f"⚠️  Could not load existing credentials: {e}")

    # If credentials are invalid or don't exist, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("\n🔄 Refreshing expired credentials...")
            try:
                creds.refresh(Request())
                print("✅ Credentials refreshed")
            except Exception as e:
                print(f"❌ Could not refresh credentials: {e}")
                creds = None

        if not creds:
            # Check if credentials file exists
            if not CREDENTIALS_FILE.exists():
                print("\n❌ Error: gmail_credentials.json not found!")
                print("\nPlease follow these steps:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a new project or select existing one")
                print("3. Enable Gmail API and Google Calendar API")
                print("4. Create OAuth 2.0 credentials (Desktop app)")
                print("5. Download the JSON file")
                print(f"6. Save it as: {CREDENTIALS_FILE}")
                print("\nThen run this script again.")
                return False

            print("\n🌐 Opening browser for authentication...")
            print("Please log in with your Google account and grant permissions.")
            
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), SCOPES
                )
                creds = flow.run_local_server(port=0)
                print("✅ Authentication successful!")
            except Exception as e:
                print(f"❌ Authentication failed: {e}")
                return False

        # Save credentials for future use
        print(f"\n💾 Saving credentials to {TOKEN_FILE}...")
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        print("✅ Credentials saved")

    # Test the credentials
    print("\n🧪 Testing credentials...")
    try:
        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=creds)
        results = service.users().messages().list(userId="me", maxResults=5).execute()
        messages = results.get("messages", [])

        print(f"✅ Successfully connected to Gmail!")
        print(f"✅ Found {len(messages)} recent emails")

        if messages:
            print("\n📧 Recent emails:")
            for i, msg in enumerate(messages[:3], 1):
                msg_data = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg["id"], format="metadata")
                    .execute()
                )
                headers = {h["name"]: h["value"] for h in msg_data.get("headers", [])}
                subject = headers.get("Subject", "(No subject)")
                from_addr = headers.get("From", "(Unknown)")
                print(f"  {i}. {subject[:50]}... - {from_addr}")

    except Exception as e:
        print(f"❌ Error testing credentials: {e}")
        return False

    print("\n" + "=" * 80)
    print("✅ Authentication complete!")
    print("=" * 80)
    print(f"\nYour credentials are saved in: {TOKEN_FILE}")
    print("\nYou can now run the agent with real Gmail access.")
    print("To test, run: python3 test_agent_real_gmail.py")

    return True


if __name__ == "__main__":
    success = authenticate()
    sys.exit(0 if success else 1)

