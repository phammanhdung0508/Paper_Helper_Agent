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

# OpenRouter Config
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")

# Groq Config
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# LLM Routing Config
ENABLE_LLM_FALLBACK = os.getenv("ENABLE_LLM_FALLBACK", "true").lower() in ("true", "1", "yes")
ENABLE_LLM_DEBUG_LOG = os.getenv("ENABLE_LLM_DEBUG_LOG", "false").lower() in ("true", "1", "yes")
ENABLE_OPENROUTER_FALLBACK = os.getenv("ENABLE_OPENROUTER_FALLBACK", "false").lower() in ("true", "1", "yes")
LLM_ROUTER_PROVIDER = os.getenv("LLM_ROUTER_PROVIDER", "local,groq,codex")
LLM_GENERAL_PROVIDER = os.getenv("LLM_GENERAL_PROVIDER", "groq,codex")
LLM_RAG_PROVIDER = os.getenv("LLM_RAG_PROVIDER", "groq,codex")
LLM_KG_PROVIDER = os.getenv("LLM_KG_PROVIDER", "groq,codex")
LLM_VISUAL_PROVIDER = os.getenv("LLM_VISUAL_PROVIDER", "groq,codex")
LLM_EVAL_PROVIDER = os.getenv("LLM_EVAL_PROVIDER", "groq,codex")

ENABLE_CODEX_FALLBACK_FOR_BATCH = os.getenv("ENABLE_CODEX_FALLBACK_FOR_BATCH", "false").lower() in ("true", "1", "yes")
ENABLE_CODEX_FALLBACK_FOR_INTERACTIVE = os.getenv("ENABLE_CODEX_FALLBACK_FOR_INTERACTIVE", "true").lower() in ("true", "1", "yes")


# Workspace Folders
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_DATA_DIR = os.path.join(BASE_DIR, "user-data")
DOCS_DIR = os.path.join(USER_DATA_DIR, "documents")
DB_PATH = os.path.join(USER_DATA_DIR, "app.db")

# Create folders if they do not exist
os.makedirs(USER_DATA_DIR, exist_ok=True)
os.makedirs(DOCS_DIR, exist_ok=True)
