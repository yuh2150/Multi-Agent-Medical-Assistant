import os
from pytz import timezone
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from config import Config as RootConfig

class BookingAgentConfig:
    def __init__(self):
        # Base config from root project
        self.root_config = RootConfig()
        
        # Backend API Base URL
        self.backend_url = os.getenv("BACKEND_API_URL", "http://localhost:3000").rstrip("/")
        
        # Timezone settings (Asia/Ho_Chi_Minh)
        self.timezone = timezone(os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh"))
        
        # Initialize LLM for booking agent
        # We check if standard OpenAI API key is present, otherwise fallback to Azure OpenAI from root config
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key and not os.getenv("azure_endpoint"):
            self.llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
                openai_api_key=openai_api_key,
                temperature=0.0  # Keep it deterministic for structured parsing
            )
        else:
            # Fallback to AzureChatOpenAI from root config or initialize custom low-temp AzureChatOpenAI
            self.llm = AzureChatOpenAI(
                deployment_name=os.getenv("deployment_name"),
                model_name=os.getenv("model_name"),
                azure_endpoint=os.getenv("azure_endpoint"),
                openai_api_key=os.getenv("openai_api_key"),
                openai_api_version=os.getenv("openai_api_version"),
                temperature=0.0  # Keep it deterministic for structured parsing
            )
        
        # HTTP client configuration
        self.http_timeout = float(os.getenv("HTTP_TIMEOUT", "10.0"))
        self.http_max_retries = int(os.getenv("HTTP_MAX_RETRIES", "3"))

# Initialize singleton config
booking_config = BookingAgentConfig()
