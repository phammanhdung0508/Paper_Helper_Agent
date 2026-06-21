import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Langfuse Config
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

# Workspace Folders
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_DATA_DIR = os.path.join(BASE_DIR, "user-data")
DOCS_DIR = os.path.join(USER_DATA_DIR, "documents")
DB_PATH = os.path.join(USER_DATA_DIR, "app.db")

# Create folders if they do not exist
os.makedirs(USER_DATA_DIR, exist_ok=True)
os.makedirs(DOCS_DIR, exist_ok=True)
