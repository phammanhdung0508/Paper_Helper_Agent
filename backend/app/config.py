import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Langfuse Config
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

# LLM Routing Config
ENABLE_LLM_FALLBACK = os.getenv("ENABLE_LLM_FALLBACK", "true").lower() in ("true", "1", "yes")
ENABLE_LLM_DEBUG_LOG = os.getenv("ENABLE_LLM_DEBUG_LOG", "false").lower() in ("true", "1", "yes")
LLM_ROUTER_PROVIDER = os.getenv("LLM_ROUTER_PROVIDER", "local,gemini,codex")
LLM_GENERAL_PROVIDER = os.getenv("LLM_GENERAL_PROVIDER", "gemini,codex")
LLM_RAG_PROVIDER = os.getenv("LLM_RAG_PROVIDER", "codex,gemini")
LLM_KG_PROVIDER = os.getenv("LLM_KG_PROVIDER", "gemini,codex")
LLM_VISUAL_PROVIDER = os.getenv("LLM_VISUAL_PROVIDER", "gemini,codex")
LLM_EVAL_PROVIDER = os.getenv("LLM_EVAL_PROVIDER", "gemini,codex")

# Workspace Folders
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_DATA_DIR = os.path.join(BASE_DIR, "user-data")
DOCS_DIR = os.path.join(USER_DATA_DIR, "documents")
DB_PATH = os.path.join(USER_DATA_DIR, "app.db")

# Create folders if they do not exist
os.makedirs(USER_DATA_DIR, exist_ok=True)
os.makedirs(DOCS_DIR, exist_ok=True)
