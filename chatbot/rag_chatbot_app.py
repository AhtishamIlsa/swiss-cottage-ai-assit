import argparse
import sys
import time
import re
from pathlib import Path
import glob
import os

import streamlit as st
from bot.client.groq_client import GroqClient
from bot.conversation.chat_history import ChatHistory
from typing import TYPE_CHECKING, Union, Any

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
from bot.conversation.conversation_handler import answer_with_context, extract_content_after_reasoning, refine_question
from bot.conversation.intent_router import IntentRouter, IntentType
from bot.conversation.capacity_handler import get_capacity_handler
from bot.conversation.refinement_handler import get_refinement_handler
from bot.conversation.ctx_strategy import (
    BaseSynthesisStrategy,
    get_ctx_synthesis_strategies,
    get_ctx_synthesis_strategy,
)
from bot.memory.embedder import Embedder
from bot.memory.vector_database.chroma import Chroma
from bot.model.model_registry import get_model_settings, get_models
from helpers.log import get_logger
from helpers.prettier import prettify_source

logger = get_logger(__name__)

st.set_page_config(page_title="RAG Chatbot", page_icon="💬", initial_sidebar_state="collapsed")


def detect_image_request(query: str) -> tuple[bool, list[str]]:
    """
    Detect if the query is asking for images/photos of cottages.
    
    Args:
        query: User's query string
        
    Returns:
        Tuple of (is_image_request, cottage_numbers)
        - is_image_request: True if query is asking for images
        - cottage_numbers: List of cottage numbers mentioned (e.g., ['7', '9', '11'])
    """
    query_lower = query.lower()
    
    # Keywords that indicate image request
    image_keywords = [
        "image", "images", "photo", "photos", "picture", "pictures",
        "show me", "see", "view", "gallery", "visual", "look like",
        "what does", "how does", "appearance", "interior", "exterior"
    ]
    
    # Check if query contains image-related keywords
    is_image_request = any(keyword in query_lower for keyword in image_keywords)
    
    # Extract cottage numbers
    cottage_numbers = []
    for num in ["7", "9", "11"]:
        if f"cottage {num}" in query_lower or f"cottage{num}" in query_lower:
            cottage_numbers.append(num)
    
    # If no specific cottage mentioned but asking for images, assume all
    if is_image_request and not cottage_numbers:
        cottage_numbers = ["7", "9", "11"]
    
    return is_image_request, cottage_numbers


def get_cottage_images(cottage_number: str, root_folder: Path, max_images: int = 6) -> list[Path]:
    """
    Get image paths for a specific cottage.
    
    Args:
        cottage_number: Cottage number (e.g., "7", "9", "11")
        root_folder: Root folder of the project
        max_images: Maximum number of images to return
        
    Returns:
        List of image file paths
    """
    # Find the image folder for this cottage
    image_patterns = [
        f"Swiss Cottage {cottage_number} Images*",
        f"*Cottage {cottage_number} Images*",
    ]
    
    image_paths = []
    
    for pattern in image_patterns:
        # Search in root folder
        folders = list(root_folder.glob(pattern))
        if folders:
            # Look for images in the folder (handle nested structure)
            for folder in folders:
                if not folder.is_dir():
                    continue
                    
                # Check direct folder for images
                images = list(folder.glob("**/*.jpg")) + list(folder.glob("**/*.jpeg")) + \
                         list(folder.glob("**/*.png")) + list(folder.glob("**/*.webp")) + \
                         list(folder.glob("**/*.JPG")) + list(folder.glob("**/*.JPEG")) + \
                         list(folder.glob("**/*.PNG"))
                image_paths.extend(images)
                
                # Also check subdirectories
                try:
                    for subfolder in folder.iterdir():
                        if subfolder.is_dir():
                            sub_images = list(subfolder.glob("*.jpg")) + list(subfolder.glob("*.jpeg")) + \
                                        list(subfolder.glob("*.png")) + list(subfolder.glob("*.webp")) + \
                                        list(subfolder.glob("*.JPG")) + list(subfolder.glob("*.JPEG")) + \
                                        list(subfolder.glob("*.PNG"))
                            image_paths.extend(sub_images)
                except (NotADirectoryError, PermissionError) as e:
                    logger.debug(f"Skipping {folder}: {e}")
                    continue
    
    # Remove duplicates and limit
    unique_paths = list(set(image_paths))[:max_images]
    return unique_paths


def display_cottage_images(cottage_numbers: list[str], root_folder: Path):
    """
    Display images for the specified cottages in Streamlit.
    
    Args:
        cottage_numbers: List of cottage numbers to display images for
        root_folder: Root folder of the project
    """
    if not cottage_numbers:
        return
    
    for cottage_num in cottage_numbers:
        images = get_cottage_images(cottage_num, root_folder, max_images=6)
        
        if images:
            st.markdown(f"### 🏡 Cottage {cottage_num} Images")
            
            # Display images in a grid (2 columns)
            cols = st.columns(2)
            for idx, img_path in enumerate(images):
                col = cols[idx % 2]
                with col:
                    try:
                        st.image(str(img_path), caption=f"Cottage {cottage_num} - Image {idx + 1}", use_container_width=True)
                    except Exception as e:
                        logger.warning(f"Error displaying image {img_path}: {e}")
        else:
            st.info(f"📷 No images found for Cottage {cottage_num}")


@st.cache_resource()
def load_llm_client(model_folder: Path, model_name: str, use_groq: bool = True, groq_api_key: str = None, _cache_key: str = "v2") -> Union["LamaCppClient", GroqClient, Any]:
    """
    Load LLM client - either Groq API (fast) or local model (slower but offline).
    
    Args:
        model_folder: Path to model folder (for local models)
        model_name: Model name
        use_groq: If True, use Groq API. If False, use local model.
        groq_api_key: Groq API key (if None, will try GROQ_API_KEY env var)
    
    Returns:
        LLM client (GroqClient or LamaCppClient)
    """
    if use_groq:
        try:
            model_settings = get_model_settings(model_name)
            llm = GroqClient(api_key=groq_api_key, model_name="llama-3.1-8b-instant", model_settings=model_settings)
            logger.info("✅ Using Groq API (fast mode)")
            return llm
        except Exception as e:
            logger.warning(f"Failed to initialize Groq client: {e}. Falling back to local model.")
            # Fall back to local model
            use_groq = False
    
    if not use_groq:
        # Lazy import to avoid requiring llama_cpp module
        try:
            from bot.client.lama_cpp_client import LamaCppClient
            model_settings = get_model_settings(model_name)
            llm = LamaCppClient(model_folder=model_folder, model_settings=model_settings)
            logger.info("✅ Using local model (llama.cpp)")
            return llm
        except ImportError:
            logger.error("llama_cpp module not installed. Cannot use local model. Please install it or use Groq API.")
            raise RuntimeError(
                "❌ Local model requires 'llama_cpp' module.\n\n"
                "💡 **Solution:** Use Groq API instead (faster and no installation needed):\n"
                "   Set 'use_groq=True' in the sidebar or ensure GROQ_API_KEY is set in .env"
            )


@st.cache_resource()
def init_chat_history(total_length: int = 2) -> ChatHistory:
    chat_history = ChatHistory(total_length=total_length)
    return chat_history


@st.cache_resource()
def load_ctx_synthesis_strategy(ctx_synthesis_strategy_name: str, _llm: Union["LamaCppClient", GroqClient, Any]) -> BaseSynthesisStrategy:
    ctx_synthesis_strategy = get_ctx_synthesis_strategy(ctx_synthesis_strategy_name, llm=_llm)
    return ctx_synthesis_strategy


@st.cache_resource()
def load_index(vector_store_path: Path, _cache_version: str = "v2") -> Chroma:
    """
    Loads a Vector Database index based on the specified vector store path.
    
    The _cache_version parameter is used to bust the cache when the vector store is rebuilt.

    Args:
        vector_store_path (Path): The path to the vector store.
        _cache_version (str): Cache version string to force cache refresh.

    Returns:
        Chroma: An instance of the Vector Database.
    """
    from bot.memory.embedder import Embedder
    
    embedding = Embedder()
    
    try:
        index = Chroma(persist_directory=str(vector_store_path), embedding=embedding)
        # Test that it works by getting the count
        doc_count = index.collection.count()
        logger.info(f"Successfully loaded vector store with {doc_count} documents")
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"Error loading vector store: {e}")
        # If there's a schema error, provide clear instructions
        if "no such column" in error_msg or "topic" in error_msg or "operationalerror" in error_msg:
            logger.error("ChromaDB schema mismatch detected!")
            st.error("❌ Vector store schema error detected.")
            st.info("💡 **Solution:** Please rebuild the vector index:")
            st.code("python3 chatbot/memory_builder.py --chunk-size 512 --chunk-overlap 25", language="bash")
            st.stop()
        raise

    return index


def init_page(root_folder: Path) -> None:
    """
    Initializes the page configuration for the application.
    """
    left_column, central_column, right_column = st.columns([2, 1, 2])

    with left_column:
        st.write(" ")

    with central_column:
        # Handle different Streamlit versions - use width parameter for newer versions
        image_path = str(root_folder / "images/bot.png")
        try:
            # Try with width='stretch' (Streamlit >= 1.38, replaces use_container_width)
            st.image(image_path, width='stretch')
        except (TypeError, ValueError):
            try:
                # Fallback: use_container_width (Streamlit 1.37-1.38)
                st.image(image_path, use_container_width=True)
            except (TypeError, ValueError):
                try:
                    # Fallback: use_column_width (Streamlit < 1.37)
                    st.image(image_path, use_column_width=True)
                except (TypeError, ValueError):
                    # Final fallback: no width parameter
                    st.image(image_path)
        st.markdown("""<h4 style='text-align: center; color: grey;'></h4>""", unsafe_allow_html=True)

    with right_column:
        st.write(" ")

    st.sidebar.title("Options")


@st.cache_resource
def init_welcome_message() -> None:
    """
    Initializes a welcome message for the chat interface.
    """
    with st.chat_message("assistant"):
        st.write("How can I help you today?")


def reset_chat_history(chat_history: ChatHistory) -> None:
    """
    Initializes the chat history, allowing users to clear the conversation.
    """
    clear_button = st.sidebar.button("🗑️ Clear Conversation", key="clear")
    if clear_button or "messages" not in st.session_state:
        st.session_state.messages = []
        chat_history.clear()


def display_messages_from_history():
    """
    Displays chat messages from the history on app rerun.
    """
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def main(parameters) -> None:
    """
    Main function to run the RAG Chatbot application.

    Args:
        parameters: Parameters for the application.
    """
    root_folder = Path(__file__).resolve().parent.parent
    model_folder = root_folder / "models"
    # Use FAQ vector store (built by pdf_faq_extractor)
    # Check if FAQ index exists at root, otherwise use docs_index
    faq_vector_store = root_folder / "vector_store"
    docs_index_vector_store = root_folder / "vector_store" / "docs_index"
    
    if (faq_vector_store / "chroma.sqlite3").exists():
        vector_store_path = faq_vector_store
        logger.info(f"Using FAQ vector store at: {vector_store_path}")
    elif (docs_index_vector_store / "chroma.sqlite3").exists():
        vector_store_path = docs_index_vector_store
        logger.info(f"Using docs_index vector store at: {vector_store_path}")
    else:
        st.error(f"❌ Vector store not found!")
        st.info("💡 Please build the vector index first:")
        st.info("   python chatbot/pdf_faq_extractor.py --pdf 'Swiss Cottages FAQS - Google Sheets.pdf' --output docs/faq")
        st.stop()
    
    Path(model_folder).parent.mkdir(parents=True, exist_ok=True)

    model_name = parameters.model
    synthesis_strategy_name = parameters.synthesis_strategy
    max_new_tokens = parameters.max_new_tokens

    init_page(root_folder)
    # Use Groq API by default (much faster). Set use_groq=False to use local model
    import os
    groq_api_key = getattr(parameters, 'groq_api_key', None) or os.getenv('GROQ_API_KEY')
    llm = load_llm_client(model_folder, model_name, use_groq=True, groq_api_key=groq_api_key)
    chat_history = init_chat_history(2)
    ctx_synthesis_strategy = load_ctx_synthesis_strategy(synthesis_strategy_name, _llm=llm)
    # Use cache version based on vector store modification time to bust cache on rebuild
    cache_version = str(int(os.path.getmtime(str(vector_store_path / "chroma.sqlite3")))) if (vector_store_path / "chroma.sqlite3").exists() else "v1"
    index = load_index(vector_store_path, _cache_version=cache_version)
    
    # Initialize intent router
    intent_router = IntentRouter(llm=llm, use_llm_fallback=True)
    
    reset_chat_history(chat_history)
    init_welcome_message()
    display_messages_from_history()

    # Supervise user input
    if user_input := st.chat_input("Input your question!"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": user_input})
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(user_input)

        # Display retrieved documents with content previews, and updates the chat interface with the assistant's
        # responses.
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            
            # ============================================
            # INTENT ROUTING LAYER (BEFORE RAG)
            # ============================================
            # Classify intent using the router
            intent = intent_router.classify(user_input, chat_history)
            
            # Helper function to check if last message was asking if user wants to know more
            def was_asking_if_want_to_know_more() -> bool:
                """Check if the last assistant message was asking if user wants to know more."""
                if "messages" in st.session_state and len(st.session_state.messages) > 0:
                    # Get last assistant message
                    for msg in reversed(st.session_state.messages):
                        if msg.get("role") == "assistant":
                            content = msg.get("content", "").lower()
                            # Check if it contains phrases asking if they want to know more
                            asking_patterns = [
                                "is there anything else",
                                "anything else you'd like",
                                "anything else you would like",
                                "what else",
                                "anything else",
                            ]
                            return any(pattern in content for pattern in asking_patterns)
                return False
            
            # ============================================
            # ROUTE BASED ON INTENT
            # ============================================
            
            # GREETING → Fixed response (NO RAG)
            if intent == IntentType.GREETING:
                full_response = "Hi! 👋 How may I help you today?\n\n"
                full_response += "I can help you with information about Swiss Cottages Bhurban, including:\n"
                full_response += "- Pricing and availability\n"
                full_response += "- Facilities and amenities\n"
                full_response += "- Location and nearby attractions\n"
                full_response += "- Booking and payment information\n\n"
                full_response += "What would you like to know?"
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            
            # HELP → Fixed response (NO RAG)
            elif intent == IntentType.HELP:
                full_response = "I can help you with information about Swiss Cottages Bhurban! 🏡\n\n"
                full_response += "Here's what I can assist you with:\n"
                full_response += "- **Pricing & Availability**: Get information about rates, booking, and availability\n"
                full_response += "- **Facilities & Amenities**: Learn about what's available at the cottages\n"
                full_response += "- **Location & Nearby**: Find out about the location and nearby attractions\n"
                full_response += "- **Booking & Payment**: Get details about how to book and payment methods\n\n"
                full_response += "What would you like to know more about?"
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            
            # AFFIRMATIVE → Context-aware response (NO RAG)
            elif intent == IntentType.AFFIRMATIVE:
                if was_asking_if_want_to_know_more():
                    full_response = "Great! What would you like to know about Swiss Cottages Bhurban?\n\n"
                    full_response += "I can help you with:\n"
                    full_response += "- **Pricing & Availability**: Rates, booking, availability\n"
                    full_response += "- **Facilities & Amenities**: What's available at the cottages\n"
                    full_response += "- **Location & Nearby**: Location details and nearby attractions\n"
                    full_response += "- **Booking & Payment**: How to book and payment methods\n\n"
                    full_response += "Just ask me any question, and I'll find the information for you!"
                else:
                    full_response = "Great! What would you like to know about Swiss Cottages Bhurban?\n\n"
                    full_response += "I can help you with:\n"
                    full_response += "- Pricing and availability\n"
                    full_response += "- Facilities and amenities\n"
                    full_response += "- Location and nearby attractions\n"
                    full_response += "- Booking and payment information"
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            
            # NEGATIVE → Graceful closing (NO RAG)
            elif intent == IntentType.NEGATIVE:
                # Check if last message was asking if they want to know more
                if was_asking_if_want_to_know_more():
                    full_response = "Great! Feel free to reach out if you have any questions about Swiss Cottages Bhurban. Have a wonderful day! 😊"
                else:
                    # Generic negative response
                    full_response = "No problem! If you need any information about Swiss Cottages Bhurban in the future, just ask. Have a great day! 😊"
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            
            # STATEMENT → Acknowledgment (NO RAG)
            elif intent == IntentType.STATEMENT:
                full_response = "You're welcome! 😊\n\n"
                full_response += "Is there anything else you'd like to know about Swiss Cottages Bhurban?"
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            
            # CLARIFICATION_NEEDED → Ask for clarification (NO RAG)
            elif intent == IntentType.CLARIFICATION_NEEDED:
                clar_question = intent_router.get_clarification_question(user_input)
                full_response = f"To give you the most accurate answer, could you please clarify: **{clar_question}**"
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            
            # REFINEMENT → Combine with previous question and proceed with RAG
            elif intent == IntentType.REFINEMENT:
                # Handle refinement request - combine previous question with constraint
                logger.info(f"Processing refinement request: {user_input}")
                refinement_handler = get_refinement_handler(llm)
                refinement_result = refinement_handler.process_refinement(
                    user_input, chat_history, llm
                )
                
                # Use combined question for RAG instead of original query
                combined_question = refinement_result["combined_question"]
                logger.info(f"Refined question: '{user_input}' → '{combined_question}'")
                
                # Replace original user_input with combined question for RAG processing
                original_user_input = user_input
                user_input = combined_question  # Use combined question for RAG
                
                # Proceed with RAG using combined question (fall through to else block)
            
            # FAQ_QUESTION, UNKNOWN, or REFINEMENT (after processing) → RAG RETRIEVAL AND ANSWER
            if intent in [IntentType.FAQ_QUESTION, IntentType.UNKNOWN, IntentType.REFINEMENT]:
                # Check if user is asking for images
                is_image_request, cottage_numbers = detect_image_request(user_input)
                
                # Check if this is a direct booking request (like "book this cottage for me")
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
                
                is_booking_request = is_direct_booking_request(user_input)
                
                # Proceed with normal retrieval and answer generation
                with st.spinner(
                    text="Refining the question and Retrieving the docs – hang tight! This should take seconds."
                ):
                    refined_user_input = refine_question(
                        llm, user_input, chat_history=chat_history, max_new_tokens=max_new_tokens
                    )
                    logger.info(f"Original query: {user_input}")
                    logger.info(f"Refined query: {refined_user_input}")
                    
                    # Query optimization for better RAG retrieval
                    import os
                    from bot.conversation.query_optimizer import optimize_query_for_rag
                    
                    if os.getenv("ENABLE_QUERY_OPTIMIZATION", "true").lower() == "true":
                        try:
                            optimized_query = optimize_query_for_rag(
                                llm,
                                refined_user_input,
                                max_new_tokens=max_new_tokens
                            )
                            logger.info(f"Query optimization: '{refined_user_input}' → '{optimized_query}'")
                            search_query = optimized_query
                        except Exception as e:
                            logger.warning(f"Query optimization failed: {e}, using refined query")
                            search_query = refined_user_input
                    else:
                        search_query = refined_user_input
                        logger.debug("Query optimization disabled, using refined query")
                    
                    # Try retrieval with both original and refined queries to maximize chances
                    retrieved_contents = []
                    sources = []
                    
                    # Increase k for payment/pricing/booking/cottage-specific queries to get better coverage
                    effective_k = parameters.k
                    query_lower = user_input.lower()
                    if any(word in query_lower for word in ["payment", "price", "pricing", "cost", "rate", "methods", "book", "booking", "reserve"]):
                        effective_k = max(parameters.k, 5)  # Get at least 5 documents for payment/pricing/booking queries
                        logger.info(f"Increased k to {effective_k} for payment/pricing/booking query")
                    
                    # Increase k for cottage-specific queries to ensure we get documents about the specific cottage
                    if any(cottage in query_lower for cottage in ["cottage 7", "cottage 9", "cottage 11", "cottage7", "cottage9", "cottage11"]):
                        effective_k = max(parameters.k, 5)  # Get at least 5 documents for cottage-specific queries
                        logger.info(f"Increased k to {effective_k} for cottage-specific query")
                    
                    # First try with optimized/refined query
                    try:
                        retrieved_contents, sources = index.similarity_search_with_threshold(
                            query=search_query, k=effective_k, threshold=0.0
                        )
                        logger.info(f"Retrieved {len(retrieved_contents)} documents with search query")
                    except Exception as e:
                        logger.warning(f"Error with threshold search (optimized): {e}, trying without threshold")
                        try:
                            retrieved_contents = index.similarity_search(query=search_query, k=effective_k)
                            sources = [{"score": "N/A", "document": doc.metadata.get("source", "unknown"), 
                                       "content_preview": f"{doc.page_content[0:256]}..."} for doc in retrieved_contents]
                            logger.info(f"Retrieved {len(retrieved_contents)} documents without threshold (optimized)")
                        except Exception as e2:
                            logger.error(f"Error with similarity search (optimized): {e2}")
                    
                    # If no results with optimized query, try original query
                    if not retrieved_contents or len(retrieved_contents) == 0:
                        logger.info("No results with optimized query, trying original query")
                        try:
                            retrieved_contents, sources = index.similarity_search_with_threshold(
                                query=user_input, k=effective_k, threshold=0.0
                            )
                            logger.info(f"Retrieved {len(retrieved_contents)} documents with original query")
                        except Exception as e:
                            logger.warning(f"Error with threshold search (original): {e}, trying without threshold")
                            try:
                                retrieved_contents = index.similarity_search(query=user_input, k=effective_k)
                                sources = [{"score": "N/A", "document": doc.metadata.get("source", "unknown"), 
                                           "content_preview": f"{doc.page_content[0:256]}..."} for doc in retrieved_contents]
                                logger.info(f"Retrieved {len(retrieved_contents)} documents without threshold (original)")
                            except Exception as e2:
                                logger.error(f"Error with similarity search (original): {e2}")
                                retrieved_contents = []
                                sources = []
                    
                    # Validate relevance of retrieved documents before generating answer
                    def check_document_relevance(query: str, documents: list) -> tuple[bool, str]:
                        """
                        Check if retrieved documents are relevant to the query.
                        Returns (is_relevant, reason) tuple.
                        """
                        query_lower = query.lower()
                        documents_text = " ".join([doc.page_content.lower() for doc in documents])
                        
                        # Check for location mismatches
                        location_keywords = {
                            "india": ["pakistan", "bhurban", "murree", "azad kashmir", "pakistani"],
                            "pakistan": ["india", "mumbai", "delhi", "bangalore", "indian"],
                            "bhurban": ["india", "mumbai", "delhi", "indian"],
                            "murree": ["india", "mumbai", "delhi", "indian"],
                        }
                        
                        # If query mentions a location, check if documents mention conflicting locations
                        for location, conflicting in location_keywords.items():
                            if location in query_lower:
                                # Check if documents mention conflicting locations
                                for conflict in conflicting:
                                    if conflict in documents_text and location not in documents_text:
                                        logger.warning(f"Location mismatch: Query mentions '{location}' but documents mention '{conflict}'")
                                        return False, f"Your question mentions '{location}', but the retrieved documents are about '{conflict}'. These don't match."
                        
                        # Check if documents mention "Swiss Cottages Bhurban" but query asks about something else
                        if "swiss cottages bhurban" in documents_text.lower() or "bhurban" in documents_text.lower():
                            # If query asks about a different location (like India), it's not relevant
                            if "india" in query_lower and "india" not in documents_text:
                                logger.warning("Query asks about India but documents are about Bhurban, Pakistan")
                                return False, "Your question asks about 'India', but the retrieved documents are about 'Swiss Cottages Bhurban' in Pakistan. These don't match."
                        
                        # Check topic relevance - ensure documents contain information about the question topic
                        topic_keywords = {
                            "facilities": ["facilities", "amenities", "kitchen", "parking", "bbq", "wifi", "available", "equipment"],
                            "price": ["price", "pricing", "cost", "rate", "rates", "payment", "advance", "booking"],
                            "payment": ["payment", "bank transfer", "cash", "method", "accept", "paid"],
                            "location": ["location", "address", "nearby", "surroundings", "area", "bhurban", "murree"],
                        }
                        
                        # Check if query is about a specific topic and documents don't contain relevant keywords
                        for topic, keywords in topic_keywords.items():
                            if any(kw in query_lower for kw in [topic] + keywords[:2]):  # Check main topic word and first 2 keywords
                                # Check if documents contain at least one relevant keyword
                                if not any(kw in documents_text for kw in keywords):
                                    logger.warning(f"Topic mismatch: Query asks about '{topic}' but documents don't contain relevant keywords")
                                    # Don't reject, but log for debugging - sometimes documents might still be relevant
                        
                        return True, ""
                    
                    # Prioritize documents that mention the specific cottage number if query asks about a specific cottage
                    def prioritize_cottage_documents(query: str, documents: list) -> list:
                        """Re-order documents to prioritize those mentioning the specific cottage number asked about."""
                        query_lower = query.lower()
                        
                        # Extract cottage number from query
                        cottage_numbers = []
                        for num in ["7", "9", "11"]:
                            if f"cottage {num}" in query_lower or f"cottage{num}" in query_lower:
                                cottage_numbers.append(num)
                        
                        if not cottage_numbers:
                            return documents  # No specific cottage mentioned, return as-is
                        
                        # Separate documents into: those mentioning the specific cottage(s) vs others
                        prioritized = []
                        others = []
                        
                        for doc in documents:
                            doc_text_lower = doc.page_content.lower()
                            # Check if document mentions the specific cottage number(s)
                            mentions_specific_cottage = any(
                                f"cottage {num}" in doc_text_lower or f"cottage{num}" in doc_text_lower
                                for num in cottage_numbers
                            )
                            
                            if mentions_specific_cottage:
                                prioritized.append(doc)
                            else:
                                others.append(doc)
                        
                        # Return prioritized documents first, then others
                        return prioritized + others
                    
                    # Re-order documents to prioritize cottage-specific matches
                    if retrieved_contents:
                        retrieved_contents = prioritize_cottage_documents(user_input, retrieved_contents)
                        logger.info(f"Re-ordered {len(retrieved_contents)} documents to prioritize cottage-specific matches")
                    
                    # Check if this is a capacity query and process it
                    capacity_handler = get_capacity_handler()
                    if capacity_handler.is_capacity_query(user_input):
                        logger.info("Detected capacity query, processing with structured logic")
                        capacity_result = capacity_handler.process_capacity_query(
                            user_input, retrieved_contents
                        )
                        
                        # Enhance context with capacity analysis if we have structured info
                        if capacity_result.get("has_all_info") and capacity_result.get("answer_template"):
                            retrieved_contents = capacity_handler.enhance_context_with_capacity_info(
                                retrieved_contents, capacity_result
                            )
                            logger.info(f"Enhanced context with capacity analysis: {capacity_result.get('suitable')}")
                    
                    # Generate answer from retrieved documents
                    if retrieved_contents and len(retrieved_contents) > 0:
                        # Check relevance before generating answer
                        is_relevant, reason = check_document_relevance(user_input, retrieved_contents)
                        
                        if not is_relevant:
                            # Documents don't match the query intent
                            full_response = "❌ **I don't have information about that in the knowledge base.**\n\n"
                            full_response += f"**Your question:** {user_input}\n\n"
                            full_response += f"**Issue:** {reason}\n\n"
                            full_response += "💡 **Note:** I only have information about Swiss Cottages Bhurban (in Pakistan). "
                            full_response += "I cannot answer questions about Swiss Cottages in other locations.\n\n"
                            full_response += "**Try asking about:**\n"
                            full_response += "- Swiss Cottages Bhurban\n"
                            full_response += "- Properties in Bhurban, Pakistan\n"
                            full_response += "- Swiss Cottages (the property in Pakistan)\n"
                            message_placeholder.markdown(full_response)
                            st.session_state.messages.append({"role": "assistant", "content": full_response})
                        else:
                            # Documents are relevant - proceed with answer generation
                            # Show retrieved sources first
                            sources_preview = "**Retrieved sources:**\n\n"
                            for i, source in enumerate(sources[:3], 1):  # Show top 3 sources
                                sources_preview += f"{i}. {prettify_source(source)}\n\n"
                            message_placeholder.markdown(sources_preview)
                            
                            # Generate answer from retrieved documents
                            # Note: create-and-refine is fastest (30-60s), async-tree-summarization is slowest (5-10+ min)
                            strategy_name = ctx_synthesis_strategy.__class__.__name__
                            with st.spinner(text=f"Generating answer from {len(retrieved_contents)} documents using {strategy_name} (this may take 30-120 seconds)..."):
                                try:
                                    streamer, _ = answer_with_context(
                                        llm, ctx_synthesis_strategy, refined_user_input, chat_history, retrieved_contents, max_new_tokens
                                    )
                                    answer_text = ""
                                    token_count = 0
                                    timeout_count = 0
                                    for token in streamer:
                                        parsed_token = llm.parse_token(token)
                                        answer_text += parsed_token
                                        token_count += 1
                                        timeout_count = 0  # Reset timeout counter on successful token
                                        # Update UI every 3 tokens to show progress (but not too frequently)
                                        if token_count % 3 == 0:
                                            message_placeholder.markdown(sources_preview + "\n\n**Answer:**\n\n" + answer_text + "▌")
                                    
                                    # Clean answer text to remove LLM reasoning/process text
                                    def clean_answer_text(answer: str) -> str:
                                        """Remove LLM reasoning and process text from answer."""
                                        if not answer:
                                            return answer
                                        reasoning_patterns = [
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
                                        cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL)
                                        lines = cleaned.split('\n')
                                        filtered_lines = []
                                        skip_next = False
                                        for line in lines:
                                            line_lower = line.lower().strip()
                                            if any(phrase in line_lower for phrase in [
                                                "the new context is",
                                                "since the original",
                                                "however, there seems",
                                                "to refine the existing",
                                                "we have the opportunity",
                                                "considering the",
                                            ]):
                                                skip_next = True
                                                continue
                                            if skip_next and (line.strip() == "---" or line.strip() == ""):
                                                continue
                                            skip_next = False
                                            filtered_lines.append(line)
                                        cleaned = '\n'.join(filtered_lines)
                                        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
                                        return cleaned.strip()
                                    
                                    answer_text = clean_answer_text(answer_text)
                                    
                                    # Final update - handle booking requests specially
                                    if is_booking_request:
                                        # For booking requests, add a helpful acknowledgment
                                        booking_acknowledgment = (
                                            "I understand you'd like to book a cottage! 🏡\n\n"
                                            "While I can't process bookings directly, I can help you with all the information you need to make a booking. "
                                        )
                                        full_response = booking_acknowledgment + "\n\n" + sources_preview + "\n\n**Here's what I found about booking:**\n\n" + answer_text
                                        
                                        # Add helpful follow-up
                                        full_response += "\n\n💡 **To proceed with booking, you can:**\n"
                                        full_response += "- Contact the property directly using the information above\n"
                                        full_response += "- Visit the website for online booking options\n"
                                        full_response += "- Ask me about availability, pricing, or any other details you need\n\n"
                                        full_response += "Is there anything specific about the booking process you'd like to know more about?"
                                    else:
                                        full_response = sources_preview + "\n\n**Answer:**\n\n" + answer_text
                                    
                                    message_placeholder.markdown(full_response)
                                    
                                    # Display images if user asked for them
                                    if is_image_request and cottage_numbers:
                                        st.markdown("---")
                                        display_cottage_images(cottage_numbers, root_folder)

                                    # Update chat history
                                    chat_history.append(f"question: {refined_user_input}, answer: {answer_text}")
                                except Exception as e:
                                    logger.error(f"Error generating answer: {e}", exc_info=True)
                                    error_msg = str(e).lower()
                                    full_response = sources_preview + "\n\n**Error:** Could not generate answer from retrieved documents.\n\n"
                                    
                                    # Check for rate limit errors
                                    if "429" in error_msg or "rate limit" in error_msg or "rate_limit" in error_msg:
                                        full_response += "⚠️ **Rate Limit Error:** The Groq API is currently rate-limited.\n\n"
                                        full_response += "**What you can do:**\n"
                                        full_response += "- Wait 5-10 seconds and try again\n"
                                        full_response += "- Try a simpler/shorter question\n"
                                        full_response += "- Check your Groq API quota at https://console.groq.com\n"
                                        full_response += "- Consider upgrading to a higher tier for more tokens per minute\n\n"
                                        full_response += f"**Error details:** {str(e)[:200]}"
                                    else:
                                        full_response += f"**Details:** {str(e)}\n\n"
                                        full_response += "💡 **Tip:** Try using a faster strategy: `create-and-refine` instead of `async-tree-summarization`"
                                    
                                    message_placeholder.markdown(full_response)
                                    st.error("❌ Error generating response. See message above for details.")

                            st.session_state.messages.append({"role": "assistant", "content": full_response})
                    elif not retrieved_contents or len(retrieved_contents) == 0:
                        # No documents found - handle booking requests specially
                        if is_booking_request:
                            full_response = (
                                "I understand you'd like to book a cottage! 🏡\n\n"
                                "While I can't process bookings directly, I'd be happy to help you with booking information. "
                                "However, I couldn't find specific booking details in my knowledge base right now.\n\n"
                                "💡 **Here's what I can help you with:**\n"
                                "- Booking procedures and requirements\n"
                                "- Pricing and availability information\n"
                                "- Payment methods and policies\n"
                                "- Cottage details and amenities\n\n"
                                "Could you try asking about:\n"
                                "- 'How do I book a cottage?'\n"
                                "- 'What is the booking process?'\n"
                                "- 'What are the booking requirements?'\n"
                                "- 'How much does it cost to book?'\n\n"
                                "Or feel free to ask me anything else about Swiss Cottages Bhurban!"
                            )
                        elif is_image_request and cottage_numbers:
                            # User is asking for images - show them even if no documents found
                            full_response = "Here are the images for the cottages you asked about:\n\n"
                            message_placeholder.markdown(full_response)
                            display_cottage_images(cottage_numbers, root_folder)
                            full_response += "\n\nIs there anything else you'd like to know about these cottages?"
                            message_placeholder.markdown(full_response)
                        else:
                            # No documents found - do NOT generate answer from LLM training data
                            full_response = "I couldn't find specific information about that in our knowledge base.\n\n"
                            full_response += "💡 **Please try:**\n"
                            full_response += "- Rephrasing your question (e.g., 'What is Swiss Cottages Bhurban?')\n"
                            full_response += "- Using different keywords\n"
                            full_response += "- Being more specific about Swiss Cottages Bhurban\n\n"
                            full_response += "**Note:** I only answer questions based on the provided FAQ documents. I cannot answer questions from general knowledge.\n"
                            message_placeholder.markdown(full_response)
                        st.session_state.messages.append({"role": "assistant", "content": full_response})


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG Chatbot")

    model_list = get_models()
    default_model = model_list[0]

    synthesis_strategy_list = get_ctx_synthesis_strategies()
    default_synthesis_strategy = synthesis_strategy_list[0]

    parser.add_argument(
        "--groq-api-key",
        type=str,
        default=None,
        help="Groq API key (or set GROQ_API_KEY env var). If provided, uses Groq API instead of local model (much faster).",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=model_list,
        help=f"Model to be used. Defaults to {default_model}.",
        required=False,
        const=default_model,
        nargs="?",
        default=default_model,
    )

    parser.add_argument(
        "--synthesis-strategy",
        type=str,
        choices=synthesis_strategy_list,
        help=f"Model to be used. Defaults to {default_synthesis_strategy}.",
        required=False,
        const=default_synthesis_strategy,
        nargs="?",
        default=default_synthesis_strategy,
    )

    parser.add_argument(
        "--k",
        type=int,
        help="Number of chunks to return from the similarity search. Defaults to 2.",
        required=False,
        default=2,
    )

    parser.add_argument(
        "--max-new-tokens",
        type=int,
        help="The maximum number of tokens to generate in the answer. Defaults to 512.",
        required=False,
        default=512,
    )

    return parser.parse_args()


# streamlit run rag_chatbot_app.py
if __name__ == "__main__":
    try:
        args = get_args()
        main(args)
    except Exception as error:
        logger.error(f"An error occurred: {str(error)}", exc_info=True, stack_info=True)
        sys.exit(1)
