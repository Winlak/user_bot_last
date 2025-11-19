"""Create Telegram session file."""
import os
from telethon.sync import TelegramClient

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = "trustat_keyword_forwarder"


def main():
    """Create session interactively."""
    print("Creating Telegram session...")
    print(f"API_ID: {API_ID}")
    print(f"API_HASH: {API_HASH}")

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    client.start()

    me = client.get_me()
    print(f"\n✅ Successfully logged in as: {me.first_name} (@{me.username})")
    print(f"📁 Session file created: {SESSION_NAME}.session")

    client.disconnect()


if __name__ == "__main__":
    main()