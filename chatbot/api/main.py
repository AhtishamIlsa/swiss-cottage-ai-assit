"""FastAPI application for RAG chatbot API."""

import os
import re
import json
from pathlib import Path
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, Response

import sys
from pathlib import Path

# Add chatbot directory to path
chatbot_dir = Path(__file__).parent.parent
if str(chatbot_dir) not in sys.path:
    sys.path.insert(0, str(chatbot_dir))

from bot.conversation.conversation_handler import answer_with_context, refine_question, extract_content_after_reasoning
from bot.conversation.intent_router import IntentType
from bot.conversation.refinement_handler import get_refinement_handler
from bot.conversation.capacity_handler import get_capacity_handler
from bot.conversation.query_optimizer import optimize_query_for_rag
from bot.conversation.sentiment_analyzer import get_sentiment_analyzer
from bot.conversation.confidence_scorer import get_confidence_scorer
from bot.conversation.recommendation_engine import get_recommendation_engine
from bot.conversation.fallback_handler import get_fallback_handler
from bot.client.prompt import generate_slot_question_prompt
from helpers.log import get_logger
from helpers.prettier import prettify_source

from .models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ClearSessionRequest,
    ClearSessionResponse,
    ImagesResponse,
    SourceInfo,
)
from .session_manager import session_manager
from .dependencies import (
    get_llm_client,
    get_vector_store,
    get_intent_router,
    get_ctx_synthesis_strategy,
    get_root_folder,
    is_query_optimization_enabled,
    clear_vector_store_cache,
)

logger = get_logger(__name__)

# Load Dropbox image configuration
def load_dropbox_config() -> Dict:
    """Load Dropbox image URLs configuration from JSON file and/or environment variables."""
    config = {"cottage_image_urls": {}, "use_dropbox": False}
    
    # First, try to load from JSON file
    config_file = Path(__file__).parent / "dropbox_images.json"
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            logger.warning(f"Failed to load Dropbox config from file: {e}")
    
    # Override with environment variables if set
    use_dropbox_env = os.getenv("USE_DROPBOX", "").lower()
    if use_dropbox_env in ("true", "1", "yes"):
        config["use_dropbox"] = True
    elif use_dropbox_env in ("false", "0", "no"):
        config["use_dropbox"] = False
    
    # Load cottage image URLs from environment variables
    # Format: DROPBOX_COTTAGE_7_URLS="url1,url2,url3"
    for cottage_num in ["7", "9", "11", "1", "2", "3", "4", "5", "6", "8", "10", "12"]:
        env_key = f"DROPBOX_COTTAGE_{cottage_num}_URLS"
        env_value = os.getenv(env_key, "")
        if env_value:
            # Split by comma and strip whitespace
            urls = [url.strip() for url in env_value.split(",") if url.strip()]
            if urls:
                if "cottage_image_urls" not in config:
                    config["cottage_image_urls"] = {}
                config["cottage_image_urls"][cottage_num] = urls
                logger.info(f"Loaded {len(urls)} Dropbox URLs for cottage {cottage_num} from environment")
    
    return config

# Cache Dropbox config
_dropbox_config = None

def get_dropbox_config() -> Dict:
    """Get cached Dropbox configuration."""
    global _dropbox_config
    if _dropbox_config is None:
        _dropbox_config = load_dropbox_config()
    return _dropbox_config

def reload_dropbox_config():
    """Reload Dropbox configuration (useful after .env changes)."""
    global _dropbox_config
    _dropbox_config = None
    return get_dropbox_config()

def get_dropbox_image_urls(cottage_number: str, max_images: int = 6) -> List[str]:
    """
    Get Dropbox image URLs for a specific cottage.
    
    Returns list of direct image URLs, or empty list if not configured.
    
    Note: Dropbox folder sharing links cannot be directly converted to individual
    image URLs without using the Dropbox API. The user should provide direct
    image file URLs in the dropbox_images.json configuration file.
    """
    config = get_dropbox_config()
    
    if not config.get("use_dropbox", False):
        return []
    
    cottage_urls = config.get("cottage_image_urls", {}).get(str(cottage_number), [])
    
    if not cottage_urls:
        return []
    
    # Process URLs - handle both folder links and direct image URLs
    all_urls = []
    for url in cottage_urls:
        # Check if this is a folder sharing link (scl/fo)
        if "www.dropbox.com/scl/fo" in url:
            # This is a folder link - cannot be used directly for images
            logger.warning(f"Dropbox folder link detected for cottage {cottage_number}. "
                         f"Folder links cannot be used to display individual images. "
                         f"Please provide direct image file URLs in dropbox_images.json")
            # Skip folder links - they won't work for displaying images
            continue
        elif "dropbox.com/s/" in url or "dropbox.com/scl/fi" in url or "dl.dropboxusercontent.com" in url:
            # This is a file sharing link or direct download URL
            # Ensure it has dl=1 for direct download
            if "?dl=0" in url:
                direct_url = url.replace("?dl=0", "?dl=1")
            elif "?dl=1" in url:
                direct_url = url
            elif "?" in url:
                # Has other query params, add dl=1
                direct_url = f"{url}&dl=1"
            else:
                # No query params, add dl=1
                direct_url = f"{url}?dl=1"
            
            # Convert www.dropbox.com to dl.dropboxusercontent.com for better reliability
            if "www.dropbox.com" in direct_url and "dl.dropboxusercontent.com" not in direct_url:
                # Keep the original URL format for scl/fi links as they work with dl=1
                pass
            
            all_urls.append(direct_url)
        else:
            # Assume it's already a direct image URL (from another CDN, etc.)
            all_urls.append(url)
    
    if not all_urls:
        logger.warning(f"No valid Dropbox image URLs found for cottage {cottage_number}. "
                      f"Please provide direct image file URLs (not folder links) in dropbox_images.json")
    
    return all_urls[:max_images]

# Load environment variables
def load_env():
    """Load .env file if it exists."""
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

load_env()

# Initialize FastAPI app
app = FastAPI(
    title="RAG Chatbot API",
    description="API for Swiss Cottages RAG Chatbot",
    version="1.0.0",
)

# CORS configuration
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
cors_origins = [origin.strip() for origin in cors_origins]
# Add localhost origins for local development
cors_origins.extend([
    "http://localhost:8501",
    "http://127.0.0.1:8501",
    "http://localhost",
    "http://127.0.0.1"
])
cors_origins = list(set(cors_origins))  # Remove duplicates

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (widget JS/CSS)
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Note: Images will be served via dedicated endpoint below

# Serve test widget HTML page
@app.get("/test")
async def test_widget():
    """Serve test widget HTML page."""
    test_file = Path(__file__).parent.parent.parent / "test_widget.html"
    if test_file.exists():
        return FileResponse(test_file)
    else:
        return {"message": "Test file not found. Please create test_widget.html in project root."}


# Helper functions from rag_chatbot_app.py
def detect_image_request(query: str) -> tuple[bool, List[str]]:
    """Detect if the query is asking for images/photos of cottages."""
    query_lower = query.lower()
    
    image_keywords = [
        "image", "images", "photo", "photos", "picture", "pictures",
        "show me", "see", "view", "gallery", "visual", "look like",
        "what does", "how does", "appearance", "interior", "exterior"
    ]
    
    is_image_request = any(keyword in query_lower for keyword in image_keywords)
    
    cottage_numbers = []
    for num in ["7", "9", "11"]:
        if f"cottage {num}" in query_lower or f"cottage{num}" in query_lower:
            cottage_numbers.append(num)
    
    if is_image_request and not cottage_numbers:
        cottage_numbers = ["7", "9", "11"]
    
    return is_image_request, cottage_numbers


def get_cottage_images(cottage_number: str, root_folder: Path, max_images: int = 6) -> List[Path]:
    """Get image paths for a specific cottage."""
    image_patterns = [
        f"Swiss Cottage {cottage_number} Images*",
        f"*Cottage {cottage_number} Images*",
    ]
    
    image_paths = []
    
    for pattern in image_patterns:
        folders = list(root_folder.glob(pattern))
        if folders:
            for folder in folders:
                if not folder.is_dir():
                    continue
                    
                images = (
                    list(folder.glob("**/*.jpg")) + list(folder.glob("**/*.jpeg")) +
                    list(folder.glob("**/*.png")) + list(folder.glob("**/*.webp")) +
                    list(folder.glob("**/*.JPG")) + list(folder.glob("**/*.JPEG")) +
                    list(folder.glob("**/*.PNG"))
                )
                image_paths.extend(images)
                
                try:
                    for subfolder in folder.iterdir():
                        if subfolder.is_dir():
                            sub_images = (
                                list(subfolder.glob("*.jpg")) + list(subfolder.glob("*.jpeg")) +
                                list(subfolder.glob("*.png")) + list(subfolder.glob("*.webp")) +
                                list(subfolder.glob("*.JPG")) + list(subfolder.glob("*.JPEG")) +
                                list(subfolder.glob("*.PNG"))
                            )
                            image_paths.extend(sub_images)
                except (NotADirectoryError, PermissionError):
                    continue
    
    unique_paths = list(set(image_paths))[:max_images]
    return unique_paths


def clean_answer_text(answer: str) -> str:
    """
    Remove LLM reasoning and process text from answer.
    Users should only see the final answer, not the LLM's thinking process.
    """
    if not answer:
        return answer
    
    # Remove common reasoning prefixes and process text
    reasoning_patterns = [
        r"^.*?Let me (think|check|analyze|search|find|look|reason|consider).*?\n",
        r"^.*?I (need|should|will|can|must) (think|check|analyze|search|find|look|reason|consider).*?\n",
        r"^.*?Based on.*?context.*?\n",
        r"^.*?According to.*?context.*?\n",
        r"^.*?Looking at.*?context.*?\n",
        r"^.*?From the.*?context.*?\n",
        r"^.*?The context.*?shows.*?\n",
        r"^.*?In the.*?context.*?\n",
        r"^.*?Thinking.*?\n",
        r"^.*?Analyzing.*?\n",
        r"^.*?Reasoning.*?\n",
        r"^.*?Step \d+.*?\n",
        r"^.*?First.*?then.*?\n",
        r"However, there seems to be missing context.*?\.\s*",
        r"Since the original context is now provided.*?\.\s*",
        r"The new context is as follows:.*?---\s*",
        r"Since the question and the answer already match.*?\.\s*",
        r"Therefore, I'll leave the answer as it is\.\s*",
        r"Refined Answer:\s*",
        r"Refined answer:\s*",
        r"Answer:\s*",
        r"Based on the provided context.*?\.\s*",
        r"Given the context.*?\.\s*",
        r"Based on the existing answer and the new context.*?\.\s*",
        r"We have the opportunity to refine.*?\.\s*",
        r"To refine the existing answer.*?\.\s*",
        r"Considering.*?the refined answer.*?\.\s*",
    ]
    
    cleaned = answer
    for pattern in reasoning_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove markdown code blocks that might contain reasoning
    cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL)
    
    # Remove lines that are just reasoning (e.g., "The new context is as follows:")
    lines = cleaned.split('\n')
    filtered_lines = []
    skip_next = False
    
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        # Skip reasoning lines - more comprehensive patterns
        reasoning_indicators = [
            "let me", "i need to", "i should", "i will", "i can", "i must",
            "based on", "according to", "looking at", "from the", "the context",
            "in the context", "thinking", "analyzing", "checking", "searching",
            "finding", "reasoning", "process", "step", "first", "then", "next",
            "to answer", "to find", "to check", "to determine", "to understand",
            "the new context is", "since the original", "however, there seems",
            "to refine the existing", "we have the opportunity", "considering the",
        ]
        
        if any(indicator in line_lower for indicator in reasoning_indicators) and len(line) < 200:
            skip_next = True
            continue
        
        # Skip separator lines after reasoning
        if skip_next and (line.strip() in ["---", "===", "***", "###", ""]):
            continue
        
        skip_next = False
        filtered_lines.append(line)
    
    cleaned = '\n'.join(filtered_lines)
    
    # Remove extra whitespace
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    
    return cleaned


def is_answer_relevant(answer: str, query: str) -> bool:
    """
    Check if answer is relevant to the query.
    Returns False if answer seems completely unrelated.
    """
    if not answer or not query:
        return True  # Don't filter empty answers
    
    query_lower = query.lower()
    answer_lower = answer.lower()
    
    # Extract key terms from query (words 4+ chars)
    query_terms = set(re.findall(r'\b\w{4,}\b', query_lower))
    
    # Check if answer contains any query terms
    answer_terms = set(re.findall(r'\b\w{4,}\b', answer_lower))
    
    # Specific checks for common mismatches
    # If query is about "availability" but answer is about "wifi", they're unrelated
    if "avail" in query_lower and "wifi" in answer_lower and "avail" not in answer_lower:
        logger.warning(f"Answer relevance check failed: query about 'availability' but answer about 'wifi'")
        return False
    
    # If query is about "wifi" but answer is about "availability", they're unrelated
    if "wifi" in query_lower and "avail" in answer_lower and "wifi" not in answer_lower:
        logger.warning(f"Answer relevance check failed: query about 'wifi' but answer about 'availability'")
        return False
    
    # If query has key terms but none appear in answer, might be irrelevant
    if len(query_terms) > 0:
        # Remove common stop words
        stop_words = {"what", "when", "where", "which", "who", "how", "tell", "about", "information", "need", "want"}
        query_terms = query_terms - stop_words
        
        if len(query_terms) > 0 and len(query_terms & answer_terms) == 0:
            logger.warning(f"Answer relevance check failed: no query terms found in answer. Query terms: {query_terms}, Answer terms: {answer_terms}")
            return False
    
    return True


def check_document_relevance(query: str, documents: list) -> tuple[bool, str]:
    """Check if retrieved documents are relevant to the query."""
    query_lower = query.lower()
    documents_text = " ".join([doc.page_content.lower() for doc in documents])
    
    location_keywords = {
        "india": ["pakistan", "bhurban", "murree", "azad kashmir", "pakistani"],
        "pakistan": ["india", "mumbai", "delhi", "bangalore", "indian"],
        "bhurban": ["india", "mumbai", "delhi", "indian"],
        "murree": ["india", "mumbai", "delhi", "indian"],
    }
    
    for location, conflicting in location_keywords.items():
        if location in query_lower:
            for conflict in conflicting:
                if conflict in documents_text and location not in documents_text:
                    return False, f"Your question mentions '{location}', but the retrieved documents are about '{conflict}'. These don't match."
    
    if "swiss cottages bhurban" in documents_text.lower() or "bhurban" in documents_text.lower():
        if "india" in query_lower and "india" not in documents_text:
            return False, "Your question asks about 'India', but the retrieved documents are about 'Swiss Cottages Bhurban' in Pakistan. These don't match."
    
    # Additional check: ensure documents match query topic
    # Extract key topic from query
    query_topics = []
    if "avail" in query_lower:
        query_topics.append("avail")
    if "wifi" in query_lower or "wi-fi" in query_lower:
        query_topics.append("wifi")
    if "price" in query_lower or "pricing" in query_lower:
        query_topics.append("price")
    if "cottage" in query_lower:
        query_topics.append("cottage")
    
    # Check for specific topic mismatches
    # Pets query should not match heating/other topics
    if any(word in query_lower for word in ["pet", "pets", "dog", "cat", "animal"]):
        if not any(word in documents_text for word in ["pet", "pets", "animal", "dog", "cat"]):
            # Check if documents are about completely different topics
            if any(word in documents_text for word in ["heating", "heat", "winter", "cold", "temperature"]):
                return False, "Your question is about pets, but the retrieved documents are about heating/facilities. These don't match."
    
    # Advance payment query should match advance/payment topics
    if any(phrase in query_lower for phrase in ["advance payment", "advance", "partial payment", "booking confirmation"]):
        if not any(word in documents_text for word in ["advance", "partial", "payment", "confirm"]):
            return False, "Your question is about advance payment/booking confirmation, but the retrieved documents don't contain this information."
    
    # Check if documents contain the query topics
    if query_topics:
        # If query is about availability, documents should mention availability
        if "avail" in query_topics:
            if "avail" not in documents_text and len(documents) > 0:
                # Check if all documents are about something else (e.g., wifi)
                if "wifi" in documents_text and "avail" not in documents_text:
                    logger.warning(f"Query about 'availability' but documents are about 'wifi'")
                    return False, "The retrieved documents don't seem to match your question about availability."
    
    return True, ""


def was_asking_if_want_to_know_more(session_id: str, session_mgr) -> bool:
    """Check if the last assistant message in a session was asking if user wants to know more."""
    chat_history = session_manager.get_or_create_session(session_id)
    if chat_history and len(chat_history) > 0:
        # Get last assistant message from chat history
        for entry in reversed(chat_history):
            if "answer:" in str(entry):
                content = str(entry).split("answer:", 1)[1].strip().lower()
                asking_patterns = [
                    "is there anything else",
                    "anything else you'd like",
                    "anything else you would like",
                    "what else",
                    "anything else",
                ]
                return any(pattern in content for pattern in asking_patterns)
    return False


def is_direct_booking_request(query: str) -> bool:
    """Check if query is a direct request to book (not just asking about booking)."""
    query_lower = query.lower()
    booking_verbs = ["book", "reserve", "reservation"]
    request_indicators = ["for me", "for us", "i want", "i need", "can you", "please"]
    
    # Check if it contains booking verb AND request indicator
    has_booking_verb = any(verb in query_lower for verb in booking_verbs)
    has_request = any(indicator in query_lower for indicator in request_indicators)
    
    # Also check for imperative form (e.g., "book a cottage", "book this")
    is_imperative = (
        query_lower.startswith("book ") or 
        query_lower.startswith("reserve ") or
        "book this" in query_lower or
        "book that" in query_lower or
        "book one" in query_lower
    )
    
    return (has_booking_verb and has_request) or (is_imperative and has_booking_verb)


def prioritize_cottage_documents(query: str, documents: list) -> list:
    """Re-order documents to prioritize those mentioning the specific cottage number asked about."""
    query_lower = query.lower()
    
    cottage_numbers = []
    for num in ["7", "9", "11"]:
        if f"cottage {num}" in query_lower or f"cottage{num}" in query_lower:
            cottage_numbers.append(num)
    
    if not cottage_numbers:
        return documents
    
    prioritized = []
    others = []
    
    for doc in documents:
        doc_text_lower = doc.page_content.lower()
        mentions_specific_cottage = any(
            f"cottage {num}" in doc_text_lower or f"cottage{num}" in doc_text_lower
            for num in cottage_numbers
        )
        
        if mentions_specific_cottage:
            prioritized.append(doc)
        else:
            others.append(doc)
    
    return prioritized + others


# API Endpoints
@app.get("/api/health", response_model=HealthResponse)
async def health_check(
    llm=Depends(get_llm_client),
):
    """Health check endpoint - doesn't require vector store."""
    try:
        model_loaded = llm is not None
        
        # Try to get vector store, but don't fail if it doesn't exist
        try:
            vector_store = get_vector_store()
            vector_store_loaded = vector_store is not None
        except Exception as e:
            logger.warning(f"Vector store not available: {e}")
            vector_store_loaded = False
        
        status = "healthy" if (vector_store_loaded and model_loaded) else "degraded"
        
        return HealthResponse(
            status=status,
            vector_store_loaded=vector_store_loaded,
            model_loaded=model_loaded,
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            vector_store_loaded=False,
            model_loaded=False,
        )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    llm=Depends(get_llm_client),
    vector_store=Depends(get_vector_store),
    intent_router=Depends(get_intent_router),
):
    """Main chat endpoint."""
    try:
        # Get or create chat history (same as Streamlit - total_length=2)
        chat_history = session_manager.get_or_create_session(request.session_id, total_length=2)
        
        # Get synthesis strategy
        strategy_name = request.synthesis_strategy or "create-and-refine"
        ctx_synthesis_strategy = get_ctx_synthesis_strategy(strategy_name)
        
        # Classify intent
        intent = intent_router.classify(request.question, chat_history)
        intent_type = intent.value if hasattr(intent, 'value') else str(intent)
        
        # Handle different intents
        if intent == IntentType.GREETING:
            answer = (
                "Hi! 👋 How may I help you today?\n\n"
                "I can help you with information about Swiss Cottages Bhurban, including:\n"
                "- Pricing and availability\n"
                "- Facilities and amenities\n"
                "- Location and nearby attractions\n"
                "- Booking and payment information\n\n"
                "What would you like to know?"
            )
            return ChatResponse(
                answer=answer,
                sources=[],
                intent=intent_type,
                session_id=request.session_id,
            )
        
        elif intent == IntentType.HELP:
            answer = (
                "I can help you with information about Swiss Cottages Bhurban! 🏡\n\n"
                "Here's what I can assist you with:\n"
                "- **Pricing & Availability**: Get information about rates, booking, and availability\n"
                "- **Facilities & Amenities**: Learn about what's available at the cottages\n"
                "- **Location & Nearby**: Find out about the location and nearby attractions\n"
                "- **Booking & Payment**: Get details about how to book and payment methods\n\n"
                "What would you like to know more about?"
            )
            return ChatResponse(
                answer=answer,
                sources=[],
                intent=intent_type,
                session_id=request.session_id,
            )
        
        elif intent == IntentType.AFFIRMATIVE:
            if was_asking_if_want_to_know_more(request.session_id, session_manager):
                answer = (
                    "Great! What would you like to know about Swiss Cottages Bhurban?\n\n"
                    "I can help you with:\n"
                    "- **Pricing & Availability**: Rates, booking, availability\n"
                    "- **Facilities & Amenities**: What's available at the cottages\n"
                    "- **Location & Nearby**: Location details and nearby attractions\n"
                    "- **Booking & Payment**: How to book and payment methods\n\n"
                    "Just ask me any question, and I'll find the information for you!"
                )
            else:
                answer = (
                    "Great! What would you like to know about Swiss Cottages Bhurban?\n\n"
                    "I can help you with:\n"
                    "- Pricing and availability\n"
                    "- Facilities and amenities\n"
                    "- Location and nearby attractions\n"
                    "- Booking and payment information"
                )
            return ChatResponse(
                answer=answer,
                sources=[],
                intent=intent_type,
                session_id=request.session_id,
            )
        
        elif intent == IntentType.NEGATIVE:
            if was_asking_if_want_to_know_more(request.session_id, session_manager):
                answer = "Great! Feel free to reach out if you have any questions about Swiss Cottages Bhurban. Have a wonderful day! 😊"
            else:
                answer = "No problem! If you need any information about Swiss Cottages Bhurban in the future, just ask. Have a great day! 😊"
            return ChatResponse(
                answer=answer,
                sources=[],
                intent=intent_type,
                session_id=request.session_id,
            )
        
        elif intent == IntentType.STATEMENT:
            # Check if statement is actually a follow-up question (e.g., "but we are in group", "but which cottage")
            query_lower = request.question.lower().strip()
            if any(phrase in query_lower for phrase in [
                'but we', 'but i', 'but they', 'but which', 'but what', 'but how', 'but when', 'but where',
                'but can', 'but is', 'but are', 'but do', 'but does', 'but will', 'but would',
                'we are', 'we have', 'we need', 'we want', 'which cottage', 'what cottage'
            ]):
                # This is actually a follow-up question, not a statement - proceed with RAG
                logger.info(f"Statement '{request.question}' detected as follow-up question, proceeding with RAG")
                # Fall through to FAQ_QUESTION handling below
            else:
                answer = "You're welcome! 😊\n\nIs there anything else you'd like to know about Swiss Cottages Bhurban?"
                return ChatResponse(
                    answer=answer,
                    sources=[],
                    intent=intent_type,
                    session_id=request.session_id,
                )
        
        elif intent == IntentType.CLARIFICATION_NEEDED:
            clar_question = intent_router.get_clarification_question(request.question)
            answer = f"To give you the most accurate answer, could you please clarify: **{clar_question}**"
            return ChatResponse(
                answer=answer,
                sources=[],
                intent=intent_type,
                session_id=request.session_id,
            )
        
        elif intent == IntentType.REFINEMENT:
            # Handle refinement request - combine previous question with constraint
            logger.info(f"Processing refinement request: {request.question}")
            refinement_handler = get_refinement_handler(llm)
            refinement_result = refinement_handler.process_refinement(
                request.question, chat_history, llm
            )
            
            # Use combined question for RAG instead of original query
            combined_question = refinement_result["combined_question"]
            logger.info(f"Refined question: '{request.question}' → '{combined_question}'")
            
            # Replace original question with combined question for RAG processing
            original_question = request.question
            request.question = combined_question  # Use combined question for RAG
            
            # Proceed with RAG using combined question (fall through to else block)
        
        # Get slot manager and context tracker for manager-style features
        slot_manager = session_manager.get_or_create_slot_manager(request.session_id, llm)
        context_tracker = session_manager.get_or_create_context_tracker(request.session_id)
        
        # Track intent in context BEFORE checking for slot responses
        context_tracker.add_intent(intent)
        
        # Check if this is a follow-up response to a slot question
        # Look for patterns like "we are X", "X people", "X guests", etc. that indicate answering a question
        query_lower = request.question.lower().strip()
        is_slot_response = False
        last_message = chat_history.get_last_message() if chat_history else None
        
        # Check if last message was asking for slot information
        if last_message and isinstance(last_message, str):
            last_lower = last_message.lower()
            slot_question_indicators = [
                "how many", "what dates", "which cottage", "will this be for",
                "how many guests", "how many people", "joining you", "staying"
            ]
            if any(indicator in last_lower for indicator in slot_question_indicators):
                # Check if current query looks like an answer (not a new question)
                answer_patterns = [
                    r"we\s+are\s+\d+",
                    r"\d+\s+(?:people|guests|members|persons)",
                    r"\d+\s+in\s+which",
                    r"cottage\s+\d+",
                    r"\d+[/-]\d+",  # Date patterns
                ]
                if any(re.search(pattern, query_lower) for pattern in answer_patterns):
                    is_slot_response = True
                    logger.info(f"Detected slot response: '{request.question}' is answering previous slot question")
        
        # Extract slots from query
        extracted_slots = slot_manager.extract_slots(request.question, intent)
        slot_manager.update_slots(extracted_slots)
        
        # If this is a slot response, use the previous intent instead of current classification
        if is_slot_response:
            # Get the intent from before the current one (since we just added current intent)
            if len(context_tracker.intent_history) >= 2:
                last_intent = context_tracker.intent_history[-2]  # Second to last (before current)
                if last_intent != intent:
                    logger.info(f"Using previous intent {last_intent.value} instead of {intent.value} for slot response")
                    # Remove current intent and use previous one
                    context_tracker.intent_history.pop()  # Remove current intent
                    intent = last_intent
                    context_tracker.add_intent(intent)  # Re-add with correct intent
                    # Re-extract slots with correct intent
                    extracted_slots = slot_manager.extract_slots(request.question, intent)
                    slot_manager.update_slots(extracted_slots)
        
        # Analyze sentiment
        sentiment_analyzer = get_sentiment_analyzer(llm)
        sentiment = sentiment_analyzer.analyze(request.question)
        
        # FAQ_QUESTION, UNKNOWN, REFINEMENT, or new manager intents - proceed with RAG
        manager_intents = [IntentType.PRICING, IntentType.ROOMS, IntentType.SAFETY, 
                          IntentType.BOOKING, IntentType.AVAILABILITY, IntentType.FACILITIES, IntentType.LOCATION]
        if intent in [IntentType.FAQ_QUESTION, IntentType.UNKNOWN, IntentType.REFINEMENT] + manager_intents:
            # Check for image requests
            is_image_request, cottage_numbers = detect_image_request(request.question)
            
            # Check if this is a direct booking request
            is_booking_request = is_direct_booking_request(request.question)
            
            # Refine question (same as Streamlit - uses bot code directly)
            max_new_tokens = request.max_new_tokens or 128
            refined_question = refine_question(
                llm, request.question, chat_history=chat_history, max_new_tokens=max_new_tokens
            )
            logger.info(f"Original query: {request.question}")
            logger.info(f"Refined query: {refined_question}")
            
            # Query optimization for better RAG retrieval
            if is_query_optimization_enabled():
                try:
                    optimized_query = optimize_query_for_rag(
                        llm,
                        refined_question,  # Use refined question as input
                        max_new_tokens=max_new_tokens
                    )
                    logger.info(f"Query optimization: '{refined_question}' → '{optimized_query}'")
                    search_query = optimized_query
                except Exception as e:
                    logger.warning(f"Query optimization failed: {e}, using refined query")
                    search_query = refined_question
            else:
                search_query = refined_question
                logger.debug("Query optimization disabled, using refined query")
            
            # Determine effective k (exactly like Streamlit)
            # Streamlit shows 3 sources by default, so use k=3 to match
            effective_k = request.k or 3  # Default k value (matches Streamlit's 3 sources)
            query_lower = request.question.lower()
            
            # Increase k for availability queries
            if any(word in query_lower for word in ["available", "availability", "which cottages", "which cottage", "vacant", "vacancy"]):
                effective_k = max(effective_k, 5)  # Get at least 5 documents for availability queries
                logger.info(f"Increased k to {effective_k} for availability query")
            
            # Increase k for payment/pricing/booking queries (same as Streamlit)
            if any(word in query_lower for word in ["payment", "price", "pricing", "cost", "rate", "methods", "book", "booking", "reserve"]):
                effective_k = max(effective_k, 5)  # Get at least 5 documents for payment/pricing/booking queries
                logger.info(f"Increased k to {effective_k} for payment/pricing/booking query")
            
            # Increase k for cottage-specific queries (same as Streamlit)
            if any(cottage in query_lower for cottage in ["cottage 7", "cottage 9", "cottage 11", "cottage7", "cottage9", "cottage11"]):
                effective_k = max(effective_k, 5)  # Get at least 5 documents for cottage-specific queries
                logger.info(f"Increased k to {effective_k} for cottage-specific query")
            
            # Increase k for facility/amenity queries and general "tell me about" queries to get comprehensive information
            if any(word in query_lower for word in ["cook", "kitchen", "facility", "amenity", "amenities", "facilities", "what", "tell me about", "information about", "about cottages", "about the cottages"]):
                effective_k = max(effective_k, 5)  # Get at least 5 documents for general information queries to ensure comprehensive answers
                logger.info(f"Increased k to {effective_k} for facility/amenity/general query")
            
            # Increase k for group size/capacity queries to ensure we get documents with cottage numbers
            if any(word in query_lower for word in ["member", "members", "people", "person", "persons", "guest", "guests", "group", "suitable", "best for", "accommodate", "capacity"]):
                effective_k = max(effective_k, 5)  # Get at least 5 documents for group size queries
                logger.info(f"Increased k to {effective_k} for group size/capacity query")
            
            # Retrieve documents
            retrieved_contents = []
            sources = []
            
            try:
                # Retrieve more documents than needed to ensure diversity
                retrieved_contents, sources = vector_store.similarity_search_with_threshold(
                    query=search_query, k=min(effective_k * 3, 15), threshold=0.0  # Get 3x more for deduplication
                )
                logger.info(f"Retrieved {len(retrieved_contents)} documents with search query")
                
                # Deduplicate by source to ensure diversity
                seen_sources = set()
                unique_contents = []
                unique_sources = []
                
                for doc, source_info in zip(retrieved_contents, sources):
                    source = source_info.get("document", "unknown")
                    # Use source as key for deduplication
                    if source not in seen_sources:
                        seen_sources.add(source)
                        unique_contents.append(doc)
                        unique_sources.append(source_info)
                        if len(unique_contents) >= effective_k:
                            break
                
                retrieved_contents = unique_contents
                sources = unique_sources
                logger.info(f"After deduplication: {len(retrieved_contents)} unique documents")
            except Exception as e:
                logger.warning(f"Error with threshold search (refined): {e}, trying without threshold")
                try:
                    # Retrieve more for deduplication
                    retrieved_contents = vector_store.similarity_search(query=search_query, k=min(effective_k * 3, 15))
                    # Deduplicate
                    seen_sources = set()
                    unique_contents = []
                    unique_sources = []
                    for doc in retrieved_contents:
                        source = doc.metadata.get("source", "unknown")
                        if source not in seen_sources:
                            seen_sources.add(source)
                            unique_contents.append(doc)
                            unique_sources.append({
                                "score": "N/A",
                                "document": source,
                                "content_preview": f"{doc.page_content[0:256]}..."
                            })
                            if len(unique_contents) >= effective_k:
                                break
                    retrieved_contents = unique_contents
                    sources = unique_sources
                except Exception as e2:
                    logger.error(f"Error with similarity search (refined): {e2}")
            
            # If no results, try original query
            if not retrieved_contents:
                logger.info("No results with optimized query, trying original query")
                try:
                    retrieved_contents, sources = vector_store.similarity_search_with_threshold(
                        query=request.question, k=effective_k, threshold=0.0
                    )
                except Exception as e:
                    try:
                        retrieved_contents = vector_store.similarity_search(query=request.question, k=effective_k)
                        sources = [
                            {
                                "score": "N/A",
                                "document": doc.metadata.get("source", "unknown"),
                                "content_preview": f"{doc.page_content[0:256]}..."
                            }
                            for doc in retrieved_contents
                        ]
                    except Exception as e2:
                        logger.error(f"Error with similarity search (original): {e2}")
                        retrieved_contents = []
                        sources = []
            
                # Prioritize cottage-specific documents and documents mentioning cottage numbers for capacity queries
                if retrieved_contents:
                    query_lower = request.question.lower()
                    # For capacity/group size queries, prioritize documents that mention cottage numbers
                    if any(word in query_lower for word in ["member", "members", "people", "person", "persons", "guest", "guests", "group", "suitable", "best for", "accommodate", "capacity", "which cottage"]):
                        # Prioritize documents that mention cottage numbers
                        cottage_docs = []
                        other_docs = []
                        for doc in retrieved_contents:
                            doc_text_lower = doc.page_content.lower()
                            if any(cottage in doc_text_lower for cottage in ["cottage 7", "cottage 9", "cottage 11", "cottage7", "cottage9", "cottage11"]):
                                cottage_docs.append(doc)
                            else:
                                other_docs.append(doc)
                        if cottage_docs:
                            retrieved_contents = cottage_docs + other_docs
                            logger.info(f"Prioritized {len(cottage_docs)} documents with cottage numbers for capacity query")
                    else:
                        # For other queries, use existing prioritization
                        retrieved_contents = prioritize_cottage_documents(request.question, retrieved_contents)
            
            # Check if this is a capacity query and process it
            capacity_handler = get_capacity_handler()
            if capacity_handler.is_capacity_query(request.question):
                logger.info("Detected capacity query, processing with structured logic")
                capacity_result = capacity_handler.process_capacity_query(
                    request.question, retrieved_contents
                )
                
                # Enhance context with capacity analysis if we have structured info
                # IMPORTANT: Enhance even if has_all_info is False (e.g., group-only queries)
                if capacity_result.get("answer_template"):
                    retrieved_contents = capacity_handler.enhance_context_with_capacity_info(
                        retrieved_contents, capacity_result
                    )
                    logger.info(f"Enhanced context with capacity analysis: suitable={capacity_result.get('suitable')}, has_all_info={capacity_result.get('has_all_info')}")
            
            # Generate answer
            if retrieved_contents:
                # Check relevance with enhanced topic matching
                is_relevant, reason = check_document_relevance(request.question, retrieved_contents)
                
                # Additional check: if low confidence scores or topic mismatch, try to find better matches
                query_lower = request.question.lower()
                low_scores = sources and len(sources) > 0 and all(float(s.get("score", 0)) < 0.5 for s in sources[:3])
                
                if not is_relevant or low_scores:
                    logger.warning(f"Low relevance or low scores detected. Query: '{request.question}', Scores: {[s.get('score') for s in sources[:3]] if sources else 'N/A'}")
                    # Try re-querying with more specific terms for known problematic queries
                    
                    # For specific queries, try exact keyword matching
                    if any(word in query_lower for word in ["pet", "pets", "animal", "dog", "cat"]):
                        # Try searching with pet-specific terms
                        try:
                            pet_query = "pet pets allowed pet-friendly permission approval"
                            pet_results, pet_sources = vector_store.similarity_search_with_threshold(
                                query=pet_query, k=5, threshold=0.0
                            )
                            if pet_results:
                                # Deduplicate
                                seen_sources = set()
                                unique_contents = []
                                unique_sources = []
                                for doc, source_info in zip(pet_results, pet_sources):
                                    source = source_info.get("document", "unknown")
                                    if source not in seen_sources:
                                        seen_sources.add(source)
                                        unique_contents.append(doc)
                                        unique_sources.append(source_info)
                                        if len(unique_contents) >= 3:
                                            break
                                
                                # Check if these are actually about pets
                                pet_docs_text = " ".join([doc.page_content.lower() for doc in unique_contents])
                                if any(word in pet_docs_text for word in ["pet", "pets", "animal", "dog", "cat"]):
                                    logger.info(f"Found better pet-related documents, using those instead")
                                    retrieved_contents = unique_contents
                                    sources = unique_sources
                                    is_relevant = True
                        except Exception as e:
                            logger.warning(f"Error re-querying for pets: {e}")
                    
                    elif any(phrase in query_lower for phrase in ["advance payment", "advance", "partial payment", "booking confirmation"]):
                        # Try searching with advance payment specific terms
                        try:
                            payment_query = "advance payment partial payment booking confirmation required"
                            payment_results, payment_sources = vector_store.similarity_search_with_threshold(
                                query=payment_query, k=5, threshold=0.0
                            )
                            if payment_results:
                                # Deduplicate
                                seen_sources = set()
                                unique_contents = []
                                unique_sources = []
                                for doc, source_info in zip(payment_results, payment_sources):
                                    source = source_info.get("document", "unknown")
                                    if source not in seen_sources:
                                        seen_sources.add(source)
                                        unique_contents.append(doc)
                                        unique_sources.append(source_info)
                                        if len(unique_contents) >= 3:
                                            break
                                
                                # Check if these are actually about advance payment
                                payment_docs_text = " ".join([doc.page_content.lower() for doc in unique_contents])
                                if any(word in payment_docs_text for word in ["advance", "partial", "payment", "confirm"]):
                                    logger.info(f"Found better advance payment documents, using those instead")
                                    retrieved_contents = unique_contents
                                    sources = unique_sources
                                    is_relevant = True
                        except Exception as e:
                            logger.warning(f"Error re-querying for advance payment: {e}")
                    
                    # For pets, also try searching with broader terms to find Services_Rules_faq_056
                    if any(word in query_lower for word in ["pet", "pets", "animal", "dog", "cat"]):
                        # Try searching with pet-friendly specific terms
                        try:
                            pet_friendly_query = "pet-friendly pets allowed permission approval management"
                            pet_friendly_results, pet_friendly_sources = vector_store.similarity_search_with_threshold(
                                query=pet_friendly_query, k=5, threshold=0.0
                            )
                            if pet_friendly_results:
                                # Check if we found Services_Rules_faq_056 or better pet docs
                                for doc, source_info in zip(pet_friendly_results, pet_friendly_sources):
                                    doc_text = doc.page_content.lower()
                                    source = source_info.get("document", "unknown")
                                    # Check if this is the correct pet FAQ (Services_Rules_faq_056)
                                    if "pet" in doc_text and ("permission" in doc_text or "approval" in doc_text or "faq_056" in source.lower()):
                                        logger.info(f"Found correct pet FAQ (Services_Rules_faq_056), using it")
                                        retrieved_contents = [doc]
                                        sources = [source_info]
                                        is_relevant = True
                                        break
                        except Exception as e:
                            logger.warning(f"Error re-querying for pet-friendly: {e}")
                
                if not is_relevant:
                    answer = (
                        f"❌ **I don't have information about that in the knowledge base.**\n\n"
                        f"**Your question:** {request.question}\n\n"
                        f"**Issue:** {reason}\n\n"
                        "💡 **Note:** I only have information about Swiss Cottages Bhurban (in Pakistan). "
                        "I cannot answer questions about Swiss Cottages in other locations.\n\n"
                        "**Try asking about:**\n"
                        "- Swiss Cottages Bhurban\n"
                        "- Properties in Bhurban, Pakistan\n"
                        "- Swiss Cottages (the property in Pakistan)\n"
                    )
                    return ChatResponse(
                        answer=answer,
                        sources=[],
                        intent=intent_type,
                        session_id=request.session_id,
                    )
                
                # Generate answer with context (same as Streamlit)
                max_new_tokens = request.max_new_tokens or 512
                streamer, _ = answer_with_context(
                    llm,
                    ctx_synthesis_strategy,
                    refined_question,
                    chat_history,
                    retrieved_contents,
                    max_new_tokens,
                )
                
                # Collect answer from streamer (same as Streamlit - no modifications)
                answer_text = ""
                for token in streamer:
                    parsed_token = llm.parse_token(token)
                    answer_text += parsed_token
                
                # Handle reasoning models (same as Streamlit)
                if llm.model_settings.reasoning:
                    answer_text = extract_content_after_reasoning(
                        answer_text, llm.model_settings.reasoning_stop_tag
                    )
                    if answer_text == "":
                        answer_text = "I didn't provide the answer; perhaps I can try again."
                
                # Clean answer text to remove LLM reasoning/process text
                answer_text = clean_answer_text(answer_text)
                
                # Score confidence in retrieval and answer
                confidence_scorer = get_confidence_scorer(llm)
                retrieval_confidence = confidence_scorer.score_retrieval(
                    request.question, retrieved_contents
                )
                answer_relevance = confidence_scorer.score_answer_relevance(request.question, answer_text)
                
                # Check if fallback should be used
                fallback_handler = get_fallback_handler(confidence_scorer, llm)
                use_fallback = fallback_handler.should_use_fallback(
                    request.question, retrieved_contents, answer_text
                )
                
                if use_fallback:
                    # Use safe fallback response
                    answer_text = fallback_handler.generate_fallback_response(
                        request.question, intent_type
                    )
                    # Add human support offer if frustrated
                    if sentiment_analyzer.should_escalate(sentiment):
                        answer_text += fallback_handler.offer_human_support()
                
                # Validate answer relevance with enhanced topic matching
                if not is_answer_relevant(answer_text, request.question):
                    logger.warning(f"Answer not relevant to query. Query: '{request.question}', Answer preview: '{answer_text[:100]}'")
                    
                    # Check for specific topic mismatches before retrying
                    query_lower = request.question.lower()
                    answer_lower = answer_text.lower()
                    
                    # Pets query getting wrong answer
                    if any(word in query_lower for word in ["pet", "pets", "animal", "dog", "cat"]) and not any(word in answer_lower for word in ["pet", "pets", "animal", "dog", "cat"]):
                        logger.warning("Query about pets but answer doesn't mention pets - likely wrong document retrieved")
                        answer_text = (
                            "I apologize, but I'm having trouble finding specific information about pets in our knowledge base. "
                            "For questions about pet policies, please contact us directly:\n"
                            "- Contact us: https://swisscottagesbhurban.com/contact-us/\n"
                            "- On-site caretaker (Jaafar): +92 301 5111817"
                        )
                    # Advance payment query getting wrong answer
                    elif any(phrase in query_lower for phrase in ["advance payment", "advance", "partial payment", "booking confirmation"]) and not any(word in answer_lower for word in ["advance", "partial", "payment", "confirm"]):
                        logger.warning("Query about advance payment but answer doesn't mention it - likely wrong document retrieved")
                        answer_text = (
                            "I apologize, but I'm having trouble finding specific information about advance payment requirements. "
                            "For detailed payment and booking information, please contact us:\n"
                            "- Contact us: https://swisscottagesbhurban.com/contact-us/\n"
                            "- On-site caretaker (Jaafar): +92 301 5111817"
                        )
                    else:
                        # Try using only the first (most relevant) document
                        if len(retrieved_contents) > 1:
                            logger.info("Retrying with only the first document")
                            try:
                                first_doc_only = [retrieved_contents[0]]
                                streamer, _ = answer_with_context(
                                    llm,
                                    ctx_synthesis_strategy,
                                    refined_question,
                                    chat_history,
                                    first_doc_only,
                                    max_new_tokens,
                                )
                                answer_text = ""
                                for token in streamer:
                                    parsed_token = llm.parse_token(token)
                                    answer_text += parsed_token
                                
                                if llm.model_settings.reasoning:
                                    answer_text = extract_content_after_reasoning(
                                        answer_text, llm.model_settings.reasoning_stop_tag
                                    )
                                
                                answer_text = clean_answer_text(answer_text)
                                
                                # Check relevance again with enhanced topic matching
                                if not is_answer_relevant(answer_text, request.question):
                                    logger.warning("Answer still not relevant after retry with first document")
                                    
                                    # Try to provide a more helpful fallback based on query topic
                                    query_lower = request.question.lower()
                                    if any(word in query_lower for word in ["pet", "pets", "animal", "dog", "cat"]):
                                        answer_text = (
                                            "I apologize, but I'm having trouble finding specific information about pets in our knowledge base. "
                                            "For questions about pet policies, please contact us directly:\n"
                                            "- Contact us: https://swisscottagesbhurban.com/contact-us/\n"
                                            "- On-site caretaker (Jaafar): +92 301 5111817"
                                        )
                                    elif any(phrase in query_lower for phrase in ["advance payment", "advance", "partial payment", "booking confirmation"]):
                                        answer_text = (
                                            "I apologize, but I'm having trouble finding specific information about advance payment requirements. "
                                            "For detailed payment and booking information, please contact us:\n"
                                            "- Contact us: https://swisscottagesbhurban.com/contact-us/\n"
                                            "- On-site caretaker (Jaafar): +92 301 5111817"
                                        )
                                    else:
                                        answer_text = "I apologize, but I'm having trouble finding the exact information you're looking for. Could you please rephrase your question or ask about a specific aspect?"
                            except Exception as e:
                                logger.error(f"Error retrying with first document: {e}")
                
                # Handle booking requests specially
                if is_booking_request:
                    booking_acknowledgment = (
                        "I understand you'd like to book a cottage! 🏡\n\n"
                        "While I can't process bookings directly, I can help you with all the information you need to make a booking. "
                    )
                    answer_text = booking_acknowledgment + "\n\n**Here's what I found about booking:**\n\n" + answer_text
                    answer_text += "\n\n💡 **To proceed with booking, you can:**\n"
                    answer_text += "- Contact the property directly using the information above\n"
                    answer_text += "- Visit the website for online booking options\n"
                    answer_text += "- Ask me about availability, pricing, or any other details you need\n\n"
                    answer_text += "Is there anything specific about the booking process you'd like to know more about?"
                
                # Manager-style enhancements: Add follow-ups, recommendations, and nudges
                response_parts = [answer_text]
                
                # Check for missing slots AFTER answering
                # Only ask for missing slots if they're actually needed for the current intent
                # Don't ask if user is just asking informational questions
                # IMPORTANT: Don't ask for slots that were just provided in this turn
                # IMPORTANT: Don't ask if user is responding affirmatively to a recommendation
                missing_slot = None
                
                # Check if user is responding affirmatively to a recommendation
                is_affirmative_response = False
                query_lower = request.question.lower().strip()
                affirmative_patterns = [
                    r"^yes\s+(?:recommend|please|go ahead|sure|ok)",
                    r"^yes$",
                    r"^ok(?:ay)?$",
                    r"^sure$",
                    r"^go ahead$",
                    r"^please$",
                    r"^recommend me$",
                    r"^yes recommend",
                ]
                for pattern in affirmative_patterns:
                    if re.match(pattern, query_lower):
                        is_affirmative_response = True
                        logger.info(f"Detected affirmative response to recommendation: '{request.question}'")
                        break
                
                # Check if last bot message was a recommendation
                last_bot_message = None
                if chat_history and len(chat_history) > 0:
                    last_message = chat_history[-1]
                    if isinstance(last_message, str) and "recommend" in last_message.lower():
                        last_bot_message = last_message
                
                # Suppress follow-up if user is responding affirmatively to recommendation
                if is_affirmative_response and last_bot_message:
                    logger.info("User responding affirmatively to recommendation, suppressing follow-up question")
                    missing_slot = None
                elif intent in [IntentType.BOOKING, IntentType.PRICING, IntentType.AVAILABILITY]:
                    # Only ask for slots for booking/pricing/availability intents
                    try:
                        missing_slot = slot_manager.get_most_important_missing_slot(intent)
                        # Check if this slot was just extracted in the current turn
                        if missing_slot and missing_slot in extracted_slots:
                            # Slot was just provided, don't ask for it again
                            logger.info(f"Slot '{missing_slot}' was just extracted, skipping follow-up question")
                            missing_slot = None
                    except Exception as e:
                        logger.warning(f"Error getting missing slot: {e}")
                
                if missing_slot:
                    # Generate follow-up question using LLM or template
                    try:
                        slot_prompt = generate_slot_question_prompt(
                            intent_type, missing_slot, slot_manager.get_slots()
                        )
                        follow_up = llm.generate_answer(slot_prompt, max_new_tokens=64).strip()
                        # Clean up follow-up
                        follow_up = follow_up.strip('"').strip("'").strip()
                        if follow_up and len(follow_up) > 10:  # Basic validation
                            response_parts.append(f"\n\n{follow_up}")
                    except Exception as e:
                        logger.warning(f"Failed to generate slot question: {e}")
                        # Fallback to simple question
                        slot_questions = {
                            "guests": "How many guests will be staying?",
                            "dates": "What dates are you planning to visit?",
                            "room_type": "Do you have a preference for which cottage?",
                            "family": "Will this be for a family or friends group?",
                            "season": "Are you planning to visit on weekdays or weekends?",
                        }
                        if missing_slot in slot_questions:
                            response_parts.append(f"\n\n{slot_questions[missing_slot]}")
                
                # Add gentle recommendations for pricing, rooms, or safety intents
                # Only show recommendations when they add value (not on every response)
                recommendation_engine = get_recommendation_engine()
                # Only show recommendations for specific intents and when user has provided relevant info
                if intent in [IntentType.PRICING, IntentType.ROOMS, IntentType.SAFETY]:
                    slots = slot_manager.get_slots()
                    # Only show recommendation if it's relevant to the current query
                    # For rooms: show if user asked about rooms/cottages
                    # For pricing: show if user asked about pricing
                    # For safety: show if user asked about safety
                    should_show_recommendation = False
                    if intent == IntentType.ROOMS and (slots.get("guests") or slots.get("room_type") or "cottage" in query_lower):
                        should_show_recommendation = True
                    elif intent == IntentType.PRICING and (slots.get("guests") or slots.get("dates") or "price" in query_lower or "pricing" in query_lower or "cost" in query_lower):
                        should_show_recommendation = True
                    elif intent == IntentType.SAFETY:
                        should_show_recommendation = True
                    
                    if should_show_recommendation:
                        recommendation = recommendation_engine.generate_gentle_recommendation(
                            intent, slots, context_tracker
                        )
                        if recommendation:
                            response_parts.append(f"\n\n{recommendation}")
                
                # Add cross-recommendations for facilities/services
                # Show related services after answering facility-related questions
                # Check if query is about facilities/amenities (kitchen, cook, chef, wifi, parking, food, etc.)
                facility_keywords = [
                    "kitchen", "cook", "cooking", "chef", "chief", "wifi", "wi-fi", "internet",
                    "parking", "park", "food", "dining", "meal", "bbq", "barbecue", "facility",
                    "amenity", "amenities", "facilities", "what is available", "what do you have"
                ]
                is_facility_query = (
                    intent == IntentType.FACILITIES or 
                    any(keyword in query_lower for keyword in facility_keywords)
                )
                
                if is_facility_query:
                    cross_rec = recommendation_engine.generate_cross_recommendation(
                        request.question,
                        intent
                    )
                    if cross_rec:
                        response_parts.append(f"\n\n{cross_rec}")
                
                # Add booking nudge if enough info available AND user seems ready
                # Only show when user has asked about booking/availability
                if slot_manager.has_enough_booking_info():
                    nudge = recommendation_engine.generate_booking_nudge(
                        slot_manager.get_slots(), 
                        context_tracker,
                        intent
                    )
                    if nudge:
                        response_parts.append(f"\n\n{nudge}")
                
                # Combine all response parts
                answer_text = "".join(response_parts)
                
                # Adjust tone based on sentiment
                answer_text = sentiment_analyzer.adjust_tone(answer_text, sentiment)
                
                # Update chat history (same as Streamlit - uses refined_question)
                chat_history.append(f"question: {refined_question}, answer: {answer_text}")
                
                # Format sources (show all retrieved sources, up to effective_k)
                source_infos = [
                    SourceInfo.from_dict(src)
                    for src in sources[:effective_k]  # Show all retrieved sources
                ]
                
                # Get cottage images if requested
                cottage_image_urls = None
                if is_image_request and cottage_numbers:
                    # First, try to get Dropbox URLs
                    dropbox_config = get_dropbox_config()
                    use_dropbox = dropbox_config.get("use_dropbox", False)
                    
                    all_images = []
                    
                    if use_dropbox:
                        # Use Dropbox URLs
                        logger.info("Using Dropbox image URLs")
                        for cottage_num in cottage_numbers:
                            dropbox_urls = get_dropbox_image_urls(cottage_num, max_images=6)
                            if dropbox_urls:
                                all_images.extend(dropbox_urls)
                                logger.info(f"Found {len(dropbox_urls)} Dropbox image URLs for cottage {cottage_num}")
                            else:
                                logger.warning(f"No Dropbox URLs found for cottage {cottage_num}, falling back to local files")
                                # Fallback to local files
                                root_folder = get_root_folder()
                                images = get_cottage_images(cottage_num, root_folder, max_images=6)
                                for img_path in images:
                                    rel_path = img_path.relative_to(root_folder)
                                    from urllib.parse import quote
                                    encoded_path = str(rel_path).replace('\\', '/')
                                    url_path = '/'.join(quote(part, safe='') for part in encoded_path.split('/'))
                                    image_url = f"/images/{url_path}"
                                    all_images.append(image_url)
                    else:
                        # Use local file paths
                        root_folder = get_root_folder()
                        logger.info("Using local file paths for images")
                        for cottage_num in cottage_numbers:
                            images = get_cottage_images(cottage_num, root_folder, max_images=6)
                            logger.info(f"Found {len(images)} local images for cottage {cottage_num}")
                            for img_path in images:
                                rel_path = img_path.relative_to(root_folder)
                                from urllib.parse import quote
                                encoded_path = str(rel_path).replace('\\', '/')
                                url_path = '/'.join(quote(part, safe='') for part in encoded_path.split('/'))
                                image_url = f"/images/{url_path}"
                                all_images.append(image_url)
                                logger.info(f"Image URL: {image_url} (from path: {rel_path})")
                    
                    cottage_image_urls = all_images[:6]  # Limit total images
                    logger.info(f"Returning {len(cottage_image_urls)} image URLs")
                
                return ChatResponse(
                    answer=answer_text,
                    sources=source_infos,
                    intent=intent_type,
                    session_id=request.session_id,
                    cottage_images=cottage_image_urls,
                )
            else:
                # No documents found
                answer = (
                    "I couldn't find specific information about that in our knowledge base.\n\n"
                    "💡 **Please try:**\n"
                    "- Rephrasing your question (e.g., 'What is Swiss Cottages Bhurban?')\n"
                    "- Using different keywords\n"
                    "- Being more specific about Swiss Cottages Bhurban\n\n"
                    "**Note:** I only answer questions based on the provided FAQ documents. "
                    "I cannot answer questions from general knowledge.\n"
                )
                return ChatResponse(
                    answer=answer,
                    sources=[],
                    intent=intent_type,
                    session_id=request.session_id,
                )
    
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/api/chat/clear", response_model=ClearSessionResponse)
async def clear_session(request: ClearSessionRequest):
    """Clear chat history for a session."""
    try:
        cleared = session_manager.clear_session(request.session_id)
        if cleared:
            return ClearSessionResponse(
                status="success",
                message=f"Chat history cleared for session {request.session_id}",
            )
        else:
            return ClearSessionResponse(
                status="not_found",
                message=f"Session {request.session_id} not found",
            )
    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing session: {str(e)}")


@app.post("/api/vector-store/reload")
async def reload_vector_store():
    """Reload the vector store (useful after rebuilding)."""
    try:
        clear_vector_store_cache()
        # Force reload
        vector_store = get_vector_store(force_reload=True)
        doc_count = vector_store.collection.count()
        return {
            "status": "success",
            "message": f"Vector store reloaded successfully with {doc_count} documents",
        }
    except Exception as e:
        logger.error(f"Error reloading vector store: {e}")
        raise HTTPException(status_code=500, detail=f"Error reloading vector store: {str(e)}")


@app.get("/api/images/{cottage_number}", response_model=ImagesResponse)
async def get_cottage_images_endpoint(cottage_number: str):
    """Get image URLs for a specific cottage."""
    try:
        root_folder = get_root_folder()
        images = get_cottage_images(cottage_number, root_folder, max_images=10)
        
        # Convert to URLs (serve via /images endpoint)
        from urllib.parse import quote
        image_urls = []
        for img_path in images:
            rel_path = img_path.relative_to(root_folder)
            # URL encode the path (especially spaces)
            encoded_path = str(rel_path).replace('\\', '/')  # Normalize path separators
            url_path = '/'.join(quote(part, safe='') for part in encoded_path.split('/'))
            image_urls.append(f"/images/{url_path}")
        
        return ImagesResponse(images=image_urls)
    except Exception as e:
        logger.error(f"Error getting cottage images: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting images: {str(e)}")


@app.get("/images/{file_path:path}")
async def serve_image(file_path: str):
    """Serve cottage images from root directory."""
    try:
        root_folder = get_root_folder()
        # Decode URL-encoded path
        from urllib.parse import unquote
        decoded_path = unquote(file_path)
        
        # Try the path as-is first
        image_path = root_folder / decoded_path
        
        # Security check: ensure path is within root folder
        try:
            image_path.resolve().relative_to(root_folder.resolve())
        except ValueError:
            logger.error(f"Security check failed: {decoded_path}")
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Check if file exists
        if not image_path.exists() or not image_path.is_file():
            # Try alternative path handling (in case of encoding issues)
            logger.warning(f"Image not found at: {image_path}")
            logger.warning(f"Decoded path: {decoded_path}")
            logger.warning(f"Root folder: {root_folder}")
            
            # Try to find the file by searching for similar paths
            # This handles cases where folder names have trailing spaces
            path_parts = decoded_path.split('/')
            if len(path_parts) > 1:
                # Try with trailing space in folder name
                alt_path = root_folder
                for i, part in enumerate(path_parts):
                    if i < len(path_parts) - 1:  # Not the last part (filename)
                        # Try with trailing space
                        alt_path = alt_path / (part + ' ')
                    else:
                        alt_path = alt_path / part
                
                if alt_path.exists() and alt_path.is_file():
                    logger.info(f"Found image at alternative path: {alt_path}")
                    image_path = alt_path
                else:
                    raise HTTPException(status_code=404, detail=f"Image not found: {decoded_path}")
            else:
                raise HTTPException(status_code=404, detail=f"Image not found: {decoded_path}")
        
        # Determine content type
        content_type = "image/jpeg"
        if image_path.suffix.lower() in [".png", ".PNG"]:
            content_type = "image/png"
        elif image_path.suffix.lower() in [".webp", ".WEBP"]:
            content_type = "image/webp"
        
        logger.info(f"Serving image: {image_path} (Content-Type: {content_type})")
        
        # Return with CORS headers (CORS middleware should handle this, but ensure it works)
        response = FileResponse(str(image_path), media_type=content_type)
        response.headers["Cache-Control"] = "public, max-age=3600"  # Cache for 1 hour
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving image: {e}")
        raise HTTPException(status_code=500, detail=f"Error serving image: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "RAG Chatbot API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
