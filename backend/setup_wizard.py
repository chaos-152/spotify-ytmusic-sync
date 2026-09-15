"""
Interactive CLI Setup Wizard for Spotify ⇄ YouTube Music Sync.
Guides new users through configuring Google Cloud OAuth credentials,
initializing the SQLite database, and validating system readiness.

Usage:
    python -m backend.setup_wizard
"""
import os
import sys
import urllib.request
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / "backend" / ".env"
ROOT_ENV_PATH = REPO_ROOT / ".env"

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    print(f"\n{CYAN}{BOLD}" + "=" * 65)
    print("   Spotify ⇄ YT Music Sync: Interactive Setup Wizard   ")
    print("=" * 65 + f"{RESET}\n")
    print("Welcome! This tool will help you set up your environment in under 2 minutes.\n")


def check_python_version():
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 10):
        print(f"{RED}❌ Python 3.10 or higher is required. You are running {major}.{minor}.{RESET}")
        sys.exit(1)
    print(f"{GREEN}✓ Python {major}.{minor} detected.{RESET}")


def prompt_credentials():
    existing_id = os.getenv("YTMUSIC_CLIENT_ID", "")
    existing_secret = os.getenv("YTMUSIC_CLIENT_SECRET", "")

    # Check if already present in backend/.env
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("YTMUSIC_CLIENT_ID=") and not existing_id:
                    existing_id = line.split("=", 1)[1].strip()
                elif line.startswith("YTMUSIC_CLIENT_SECRET=") and not existing_secret:
                    existing_secret = line.split("=", 1)[1].strip()

    if existing_id and existing_secret and not existing_id.startswith("your_"):
        print(f"{GREEN}✓ Existing credentials found:{RESET}")
        print(f"  Client ID: {existing_id[:16]}... ({len(existing_id)} chars)")
        print(f"  Client Secret: {'*' * 8}")
        choice = input(f"\nDo you want to keep existing credentials? [{BOLD}Y{RESET}/n]: ").strip().lower()
        if choice not in ("n", "no"):
            return existing_id, existing_secret

    print(f"\n{BOLD}Step 1: Google Cloud OAuth 2.0 Credentials{RESET}")
    print("To sync with YouTube Music at zero cost, you need free OAuth credentials:")
    print(f"  1. Go to {CYAN}https://console.cloud.google.com/{RESET}")
    print(f"  2. Enable {BOLD}YouTube Data API v3{RESET} under APIs & Services -> Library")
    print(f"  3. Configure OAuth Consent Screen (type: {BOLD}External{RESET}, add your email to {BOLD}Test Users{RESET})")
    print(f"  4. Create Credentials -> OAuth Client ID -> Type: {BOLD}TVs and Limited Input devices{RESET}\n")

    while True:
        client_id = input(f"{BOLD}[?] Enter your Google Client ID{RESET}\n    (e.g., xxx.apps.googleusercontent.com): ").strip()
        if not client_id:
            print(f"{YELLOW}Client ID cannot be empty. Please paste your Client ID.{RESET}")
            continue
        break

    while True:
        client_secret = input(f"\n{BOLD}[?] Enter your Google Client Secret{RESET}\n    (e.g., GOCSPX-xxx): ").strip()
        if not client_secret:
            print(f"{YELLOW}Client Secret cannot be empty. Please paste your Client Secret.{RESET}")
            continue
        break

    return client_id, client_secret


def save_env(client_id: str, client_secret: str):
    updates = {
        "YTMUSIC_CLIENT_ID": client_id,
        "YTMUSIC_CLIENT_SECRET": client_secret,
    }

    for env_path in (ENV_PATH, ROOT_ENV_PATH):
        env_path.parent.mkdir(parents=True, exist_ok=True)
        existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        updated_keys = set(updates.keys())
        new_lines = [line for line in existing_lines if line.split("=", 1)[0].strip() not in updated_keys]
        for key, val in updates.items():
            new_lines.append(f"{key}={val}")
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Export to current process environment
    os.environ["YTMUSIC_CLIENT_ID"] = client_id
    os.environ["YTMUSIC_CLIENT_SECRET"] = client_secret
    print(f"{GREEN}✓ Google credentials saved to {ENV_PATH.name} (existing Spotify credentials preserved){RESET}")


def check_network():
    print(f"\n{BOLD}Step 2: Checking Google OAuth Connectivity{RESET}")
    try:
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/device/code",
            headers={"User-Agent": "Spotify-YTMusic-Sync/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                pass
        except urllib.error.HTTPError as e:
            if e.code in (400, 405):
                print(f"{GREEN}✓ Google OAuth endpoint reachable.{RESET}")
            else:
                print(f"{YELLOW}⚠️ Google OAuth responded with HTTP {e.code} (connection works).{RESET}")
    except Exception as e:
        print(f"{YELLOW}⚠️ Could not verify direct Google reachability: {e}{RESET}")
        print("  (Make sure you have an active internet connection when running sync).")


def init_database():
    print(f"\n{BOLD}Step 3: Initializing Database{RESET}")
    try:
        from backend import db
        db.init_db()
        print(f"{GREEN}✓ Local SQLite database initialized at {db.DB_PATH}{RESET}")
    except Exception as e:
        print(f"{RED}❌ Database initialization failed: {e}{RESET}")
        sys.exit(1)


def main():
    print_banner()
    check_python_version()
    client_id, client_secret = prompt_credentials()
    save_env(client_id, client_secret)
    check_network()
    init_database()

    print(f"\n{GREEN}{BOLD}" + "=" * 65)
    print("   Setup Complete! You're ready to sync playlists.   ")
    print("=" * 65 + f"{RESET}\n")
    print(f"To start the server:\n  {CYAN}./run.sh{RESET} (or {CYAN}uvicorn backend.main:app --port 8000{RESET})\n")
    print(f"Then open {BOLD}http://127.0.0.1:8000{RESET} in your browser.\n")


if __name__ == "__main__":
    main()
