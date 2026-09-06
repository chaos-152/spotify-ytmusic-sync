"""
Utility script to verify environment configuration, SQLite storage,
and YouTube Music connectivity.
Usage:
    python -m backend.verify_setup
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()
load_dotenv("backend/.env")

from . import db, ytmusic_auth


def verify():
    print("=== YouTube Music Sync Verification ===")
    
    # 1. Credentials Check
    client_id = os.getenv("YTMUSIC_CLIENT_ID")
    client_secret = os.getenv("YTMUSIC_CLIENT_SECRET")

    print("\n1. Environment Credentials:")
    if not client_id or not client_secret:
        print("  ❌ Missing YTMUSIC_CLIENT_ID or YTMUSIC_CLIENT_SECRET.")
        print("     Please create a `backend/.env` file with:")
        print("     YTMUSIC_CLIENT_ID=your_client_id.apps.googleusercontent.com")
        print("     YTMUSIC_CLIENT_SECRET=your_client_secret")
        return False
    else:
        print(f"  ✅ YTMUSIC_CLIENT_ID: {client_id[:12]}...")
        print(f"  ✅ YTMUSIC_CLIENT_SECRET: {'*' * 8}")

    # 2. Database Check
    print("\n2. SQLite Database:")
    try:
        db.init_db()
        print(f"  ✅ SQLite database initialized at: {db.DB_PATH}")
    except Exception as e:
        print(f"  ❌ Failed to initialize database: {e}")
        return False

    # 3. Token & Connection Check
    print("\n3. YouTube Music Token:")
    token = db.get_token("me", "ytmusic")
    if not token:
        print("  ⚠️ No YouTube Music OAuth token stored in database yet.")
        print("     Run the app (`uvicorn backend.main:app --port 8000`) and click 'Connect YT Music',")
        print("     or start the device-code flow via API.")
        return True

    print("  ✅ OAuth token found in database.")
    print("\n4. Testing YouTube Music Client:")
    try:
        yt = ytmusic_auth.get_client("me")
        print("  ✅ Successfully instantiated YTMusic client with stored token.")
    except Exception as e:
        print(f"  ❌ Failed to connect to YouTube Music with stored token: {e}")
        return False

    print("\n🎉 Setup verified successfully!")
    return True


if __name__ == "__main__":
    success = verify()
    sys.exit(0 if success else 1)
