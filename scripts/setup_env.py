"""Create local configuration with unique random secrets without overwriting existing .env."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print(".env already exists; preserved")
else:
    contents = (root / ".env.example").read_text()
    for placeholder in ["replace_with_random_mysql_password", "replace_with_another_random_password", "replace_with_at_least_32_random_characters"]:
        contents = contents.replace(placeholder, secrets.token_urlsafe(36))
    target.touch(mode=0o600, exist_ok=False)
    target.write_text(contents)
    print("Created .env with random secrets. Add your Telegram bot token and username to enable the bot.")
