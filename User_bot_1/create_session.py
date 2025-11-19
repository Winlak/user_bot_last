"""Create a user session file for the forwarder bot."""
import os
from pathlib import Path

from telethon.sync import TelegramClient

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_NAME = os.getenv("SESSION_NAME", "trustat_keyword_forwarder")
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


def main() -> None:
    """Create a session interactively using your Telegram account."""

    if not API_ID or not API_HASH:
        raise SystemExit("API_ID and API_HASH must be set in the environment")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    session_file = DATA_DIR / f"{SESSION_NAME}.session"
    session_path = str(session_file.with_suffix(""))

    print("Creating Telegram session...")
    print(f"API_ID: {API_ID}")
    print(f"API_HASH: {API_HASH}")
    print(f"Session file: {session_file}")

    client = TelegramClient(session_path, API_ID, API_HASH)
    client.start()

    me = client.get_me()
    print(f"\n✅ Successfully logged in as: {me.first_name} (@{me.username})")
    print(f"📁 Session file created: {session_file}")

    client.disconnect()


if __name__ == "__main__":
    main()
