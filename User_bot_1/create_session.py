
"""Create and print a Telegram StringSession for the bot."""
import os
from pathlib import Path

from telethon.sessions import StringSession
from telethon.sync import TelegramClient

API_ID = int(os.getenv("TELEGRAM_API_ID", os.getenv("API_ID", "0")))
API_HASH = os.getenv("TELEGRAM_API_HASH", os.getenv("API_HASH", ""))

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


def main() -> None:

    """Interactively log in and print the StringSession value."""

    if not API_ID or not API_HASH:
        raise SystemExit(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in the environment"
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Creating Telegram StringSession...")

    print(f"API_ID: {API_ID}")
    print(f"API_HASH: {API_HASH}")
    print(f"Session file: {session_file}")


    with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        client.start()
        me = client.get_me()
        session_string = client.session.save()


    print(f"\n✅ Successfully logged in as: {me.first_name} (@{me.username})")

    print("🔑 TELEGRAM_STRING_SESSION (add to your .env):")
    print(session_string)



if __name__ == "__main__":
    main()
