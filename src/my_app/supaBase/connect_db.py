import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
# Go up to the project root (nba_fan_yahoo directory)
project_root = os.path.join(script_dir, "..", "..", "..")
# Load .env from the project root
env_path = os.path.join(project_root, ".env")
print(f"Looking for .env file at: {env_path}")
load_dotenv(env_path)

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_ANON_KEY")
print(f"SUPABASE_URL: {url}")
print(f"SUPABASE_ANON_KEY: {key[:10] if key else 'None'}...")

if not url or not key:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")

supabase= create_client(url, key)


# insert
#update
#delete