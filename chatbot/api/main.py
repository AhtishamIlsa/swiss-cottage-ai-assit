"""FastAPI application for RAG chatbot API."""

import os
from pathlib import Path
from typing import List, Optional

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
)

logger = get_logger(__name__)

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
    vector_store=Depends(get_vector_store),
):
    """Health check endpoint."""
    try:
        vector_store_loaded = vector_store is not None
        model_loaded = llm is not None
        
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
        
        # FAQ_QUESTION or UNKNOWN - proceed with RAG
        else:
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
            
            # Determine effective k (exactly like Streamlit)
            # Streamlit shows 3 sources by default, so use k=3 to match
            effective_k = request.k or 3  # Default k value (matches Streamlit's 3 sources)
            query_lower = request.question.lower()
            
            # Increase k for payment/pricing/booking queries (same as Streamlit)
            if any(word in query_lower for word in ["payment", "price", "pricing", "cost", "rate", "methods", "book", "booking", "reserve"]):
                effective_k = max(effective_k, 5)  # Get at least 5 documents for payment/pricing/booking queries
                logger.info(f"Increased k to {effective_k} for payment/pricing/booking query")
            
            # Increase k for cottage-specific queries (same as Streamlit)
            if any(cottage in query_lower for cottage in ["cottage 7", "cottage 9", "cottage 11", "cottage7", "cottage9", "cottage11"]):
                effective_k = max(effective_k, 5)  # Get at least 5 documents for cottage-specific queries
                logger.info(f"Increased k to {effective_k} for cottage-specific query")
            
            # Increase k for facility/amenity queries to get comprehensive information
            if any(word in query_lower for word in ["cook", "kitchen", "facility", "amenity", "amenities", "facilities", "what", "tell me about", "information about"]):
                effective_k = max(effective_k, 3)  # Get at least 3 documents for general information queries
                logger.info(f"Increased k to {effective_k} for facility/amenity/general query")
            
            # Increase k for group size/capacity queries to ensure we get documents with cottage numbers
            if any(word in query_lower for word in ["member", "members", "people", "person", "persons", "guest", "guests", "group", "suitable", "best for", "accommodate", "capacity"]):
                effective_k = max(effective_k, 5)  # Get at least 5 documents for group size queries
                logger.info(f"Increased k to {effective_k} for group size/capacity query")
            
            # Retrieve documents
            retrieved_contents = []
            sources = []
            
            try:
                retrieved_contents, sources = vector_store.similarity_search_with_threshold(
                    query=refined_question, k=effective_k, threshold=0.0
                )
                logger.info(f"Retrieved {len(retrieved_contents)} documents with refined query")
            except Exception as e:
                logger.warning(f"Error with threshold search (refined): {e}, trying without threshold")
                try:
                    retrieved_contents = vector_store.similarity_search(query=refined_question, k=effective_k)
                    sources = [
                        {
                            "score": "N/A",
                            "document": doc.metadata.get("source", "unknown"),
                            "content_preview": f"{doc.page_content[0:256]}..."
                        }
                        for doc in retrieved_contents
                    ]
                except Exception as e2:
                    logger.error(f"Error with similarity search (refined): {e2}")
            
            # If no results, try original query
            if not retrieved_contents:
                logger.info("No results with refined query, trying original query")
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
            
            # Generate answer
            if retrieved_contents:
                # Check relevance
                is_relevant, reason = check_document_relevance(request.question, retrieved_contents)
                
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
                    root_folder = get_root_folder()
                    all_images = []
                    for cottage_num in cottage_numbers:
                        images = get_cottage_images(cottage_num, root_folder, max_images=6)
                        # Convert to URLs (serve via /images endpoint)
                        for img_path in images:
                            # Make path relative to root and URL encode spaces
                            rel_path = img_path.relative_to(root_folder)
                            # URL encode the path (especially spaces)
                            from urllib.parse import quote
                            encoded_path = str(rel_path).replace('\\', '/')  # Normalize path separators
                            url_path = '/'.join(quote(part, safe='') for part in encoded_path.split('/'))
                            all_images.append(f"/images/{url_path}")
                    cottage_image_urls = all_images[:6]  # Limit total images
                
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
        image_path = root_folder / decoded_path
        
        # Security check: ensure path is within root folder
        try:
            image_path.resolve().relative_to(root_folder.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not image_path.exists() or not image_path.is_file():
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Determine content type
        content_type = "image/jpeg"
        if image_path.suffix.lower() in [".png", ".PNG"]:
            content_type = "image/png"
        elif image_path.suffix.lower() in [".webp", ".WEBP"]:
            content_type = "image/webp"
        
        return FileResponse(str(image_path), media_type=content_type)
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
