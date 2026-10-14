from pathlib import Path

from dotenv import load_dotenv

# The one place .env is loaded: src/.env, whatever the working directory. Values already
# in the environment (Cloud Run secrets, CI) win.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
