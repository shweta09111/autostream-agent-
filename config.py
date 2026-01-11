import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = "anthropic"
LLM_MODEL = "claude-3-haiku-20240307"
LLM_TEMPERATURE = 0.7
MAX_TOKENS = 500

KNOWLEDGE_BASE_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base", "product_info.json")
