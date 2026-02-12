"""FastAPI application for RAG chatbot API."""

import os
import re
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from entities.document import Document

from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, Response, StreamingResponse
import asyncio

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
from bot.conversation.pricing_handler import get_pricing_handler
from bot.conversation.date_extractor import get_date_extractor
from bot.conversation.query_optimizer import (
    optimize_query_for_rag,
    optimize_query_for_retrieval,
    extract_entities_for_retrieval,
    get_retrieval_filter,
    is_complex_query,
)
from bot.conversation.sentiment_analyzer import get_sentiment_analyzer
from bot.conversation.confidence_scorer import get_confidence_scorer
from bot.conversation.recommendation_engine import get_recommendation_engine
from bot.conversation.fallback_handler import get_fallback_handler
from bot.conversation.cottage_registry import get_cottage_registry
from bot.conversation.query_complexity import get_complexity_classifier
from bot.client.prompt import generate_slot_question_prompt
from helpers.log import get_logger
from helpers.prettier import prettify_source

# Speech modules
from speech import GroqSTT, GroqTTS, VoiceActivityDetector
from entities.document import Document
import tempfile
import base64
import asyncio

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
    get_fast_llm_client,
    get_reasoning_llm_client,
    get_vector_store,
    get_intent_router,
    get_ctx_synthesis_strategy,
    get_root_folder,
    is_query_optimization_enabled,
    is_intent_filtering_enabled,
    clear_vector_store_cache,
)

logger = get_logger(__name__)


def generate_follow_up_actions(
    intent: IntentType,
    slots: Dict[str, Any],
    query: str,
    context_tracker: Optional["ContextTracker"] = None,
    chat_history: Optional[List[str]] = None,
    llm_client: Optional[Any] = None,
    is_widget_query: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Generate follow-up actions (quick actions and suggestions) based on intent and context.
    Uses 3-tier recommendation system with LLM enhancement.
    
    Args:
        intent: Detected intent type
        slots: Current slot values
        query: User's query
        context_tracker: Optional context tracker for per-session personalization
        chat_history: Optional chat history for topic analysis
        llm_client: Optional LLM client for generating dynamic recommendations
        is_widget_query: Whether this query was triggered from a widget card
        
    Returns:
        Dictionary with quick_actions and suggestions, or None
    """
    from bot.conversation.recommendation_engine import get_recommendation_engine
    from bot.conversation.context_tracker import ContextTracker as CT
    
    quick_actions = []
    suggestions = []
    
    query_lower = query.lower()
    
    # Get recommendation engine
    recommendation_engine = get_recommendation_engine()
    
    # Use default context tracker if not provided
    if context_tracker is None:
        # Create a minimal context tracker for default behavior
        context_tracker = CT(session_id="default")
    
    # Get rule-based contextual suggestions (3-tier system)
    rule_based_suggestions = recommendation_engine.generate_contextual_suggestions(
        query=query,
        intent=intent,
        slots=slots,
        context_tracker=context_tracker,
        chat_history=chat_history
    )
    
    # Get LLM-generated recommendations (1-2 dynamic recommendations)
    llm_suggestions = []
    if llm_client is not None:
        try:
            llm_suggestions = recommendation_engine.generate_llm_recommendations(
                query=query,
                intent=intent,
                chat_history=chat_history or [],
                context_tracker=context_tracker,
                llm_client=llm_client
            )
        except Exception as e:
            logger.warning(f"Failed to generate LLM recommendations: {e}")
    
    # Merge suggestions: LLM first (if any), then rule-based
    # Remove duplicates while preserving order
    seen = set()
    for suggestion in llm_suggestions:
        if suggestion.lower() not in seen:
            suggestions.append(suggestion)
            seen.add(suggestion.lower())
    
    for suggestion in rule_based_suggestions:
        if suggestion.lower() not in seen:
            suggestions.append(suggestion)
            seen.add(suggestion.lower())
    
    # Limit total suggestions to 4-5
    suggestions = suggestions[:5]
    
    # Generate quick actions based on intent
    if intent == IntentType.BOOKING or intent == IntentType.AVAILABILITY:
        quick_actions.append({"text": "Book Now", "action": "booking", "type": "button"})
        quick_actions.append({"text": "Contact Manager", "action": "contact", "type": "button"})
        
    elif intent == IntentType.PRICING:
        quick_actions.append({"text": "Check Availability", "action": "availability", "type": "button"})
        quick_actions.append({"text": "View Pricing", "action": "pricing", "type": "button"})
        
    elif "image" in query_lower or "photo" in query_lower or "picture" in query_lower:
        quick_actions.append({"text": "View More Images", "action": "images", "type": "button"})
        quick_actions.append({"text": "Book Now", "action": "booking", "type": "button"})
        
    elif intent == IntentType.LOCATION:
        quick_actions.append({"text": "Book Visit", "action": "booking", "type": "button"})
        quick_actions.append({"text": "Contact Manager", "action": "contact", "type": "button"})
        
    elif intent == IntentType.ROOMS or intent == IntentType.SAFETY or intent == IntentType.FACILITIES:
        quick_actions.append({"text": "Book Now", "action": "booking", "type": "button"})
        quick_actions.append({"text": "Contact Manager", "action": "contact", "type": "button"})
        
    else:
        # General FAQ
        if is_widget_query:
            quick_actions.append({"text": "Book Now", "action": "booking", "type": "button"})
            quick_actions.append({"text": "Contact Manager", "action": "contact", "type": "button"})
    
    # If we have actions or suggestions, return them
    if quick_actions or suggestions:
        return {
            "quick_actions": quick_actions,
            "suggestions": suggestions
        }
    
    return None


def count_sentences(text: str) -> int:
    """
    Count the number of sentences in a text.
    
    Args:
        text: Text to count sentences in
        
    Returns:
        Number of sentences
    """
    if not text or not text.strip():
        return 0
    
    # Split by sentence-ending punctuation
    sentences = re.split(r'[.!?]+', text)
    # Filter out empty strings
    sentences = [s.strip() for s in sentences if s.strip()]
    return len(sentences)


def get_max_sentences_for_intent(intent: IntentType) -> int:
    """
    Get the maximum number of sentences allowed for a given intent.
    
    Args:
        intent: Intent type
        
    Returns:
        Maximum number of sentences
    """
    max_sentences_map = {
        IntentType.PRICING: 5,
        IntentType.AVAILABILITY: 3,
        IntentType.SAFETY: 4,
        IntentType.ROOMS: 4,
        IntentType.FACILITIES: 4,
        IntentType.LOCATION: 4,
    }
    # Default to 6 for other intents (GENERAL, FAQ_QUESTION, etc.)
    return max_sentences_map.get(intent, 6)


def remove_pricing_template_aggressively(text: str) -> str:
    """
    Aggressively remove structured pricing template and capacity template from text.
    Also removes template markers like "⚠️ GENERAL PRICING QUERY DETECTED" and "MANDATORY RESPONSE" that LLM might output.
    This is a critical function to prevent templates from being shown to users.
    
    Args:
        text: Text that may contain pricing or capacity template
        
    Returns:
        Text with template removed
    """
    if not text:
        return text
    
    # Check if template exists (pricing or capacity)
    # CRITICAL: Check for MANDATORY RESPONSE first (capacity queries)
    if ('MANDATORY RESPONSE' in text.upper() and 
        'YOU MUST USE THIS EXACT ANSWER' in text.upper() and
        'END OF MANDATORY RESPONSE' in text.upper()):
        # This is a capacity query template - handle it immediately
        logger.warning("CRITICAL: Detected MANDATORY RESPONSE template (capacity query)")
        # Extract content from MANDATORY RESPONSE blocks
        mandatory_pattern = r'🚨\s*🚨\s*🚨\s*MANDATORY RESPONSE.*?YOU MUST USE THIS EXACT ANSWER\s*🚨\s*🚨\s*🚨\s*(.*?)\s*🚨\s*🚨\s*🚨\s*END OF MANDATORY RESPONSE\s*🚨\s*🚨\s*🚨'
        match = re.search(mandatory_pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            extracted_content = match.group(1).strip()
            logger.info(f"Extracted content from MANDATORY RESPONSE block: {extracted_content[:50]}...")
            # Use the extracted content directly (it's clean)
            cleaned_text = extracted_content
            # Remove any trailing fragments from extracted content
            cleaned_text = re.sub(r'\s+you have\.?\s*$', '', cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r'\s+have\.?\s*$', '', cleaned_text, flags=re.IGNORECASE)
            cleaned_text = cleaned_text.strip()
            # Remove "To recommend..." lines if they appear after
            cleaned_text = re.sub(r'\n\s*To recommend.*?preferences.*?\.?\s*$', '', cleaned_text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
            cleaned_text = re.sub(r'To recommend.*?preferences.*?\.?\s*$', '', cleaned_text, flags=re.IGNORECASE | re.DOTALL)
            if cleaned_text:
                logger.info("Returning extracted content from MANDATORY RESPONSE block")
                return cleaned_text
    
    # Check for other template types (pricing)
    if ('🚨 CRITICAL PRICING INFORMATION' not in text and 
        'STRUCTURED PRICING ANALYSIS' not in text.upper() and 
        'MANDATORY INSTRUCTIONS FOR LLM' not in text.upper() and
        'CRITICAL INSTRUCTIONS - READ CAREFULLY' not in text.upper()):
        return text
    
    logger.warning("CRITICAL: Detected pricing/capacity template - removing aggressively")
    
    # Method 0: Extract content from MANDATORY RESPONSE blocks (for capacity queries)
    # Pattern: 🚨🚨🚨 MANDATORY RESPONSE - YOU MUST USE THIS EXACT ANSWER 🚨🚨🚨 [CONTENT] 🚨🚨🚨 END OF MANDATORY RESPONSE 🚨🚨🚨
    mandatory_pattern = r'🚨\s*🚨\s*🚨\s*MANDATORY RESPONSE.*?YOU MUST USE THIS EXACT ANSWER\s*🚨\s*🚨\s*🚨\s*(.*?)\s*🚨\s*🚨\s*🚨\s*END OF MANDATORY RESPONSE\s*🚨\s*🚨\s*🚨'
    match = re.search(mandatory_pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        extracted_content = match.group(1).strip()
        logger.info(f"Extracted content from MANDATORY RESPONSE block: {extracted_content[:50]}...")
        # Use the extracted content directly (it's clean)
        cleaned_text = extracted_content
        # Remove any trailing fragments from extracted content
        cleaned_text = re.sub(r'\s+you have\.?\s*$', '', cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r'\s+have\.?\s*$', '', cleaned_text, flags=re.IGNORECASE)
        cleaned_text = cleaned_text.strip()
        # Return early with the clean extracted content
        if cleaned_text:
            logger.info("Returning extracted content from MANDATORY RESPONSE block")
            return cleaned_text
    
    # Method 1: Find where actual answer starts (line-by-line)
    lines = text.split('\n')
    answer_start_idx = None
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        line_upper = line_stripped.upper()
        
        # Skip all template lines
        if any(keyword in line_upper for keyword in [
            '🚨 CRITICAL PRICING', 'MANDATORY INSTRUCTIONS FOR LLM', 'STRUCTURED PRICING ANALYSIS',
            'MANDATORY RESPONSE', 'YOU MUST USE THIS EXACT ANSWER', 'END OF MANDATORY RESPONSE',
            'DO NOT CONVERT TO DOLLARS', 'YOU MUST USE ONLY', 'ALL PRICES ARE IN PKR',
            'DETAILED BREAKDOWN', 'CHECK-IN:', 'CHECK-OUT:', 'GUESTS:', 'TOTAL NIGHTS:',
            'WEEKDAY RATE:', 'WEEKEND RATE:', '🎯 TOTAL COST FOR', '⚠️', 'SEARCHING KNOWLEDGE BASE',
            'CRITICAL INSTRUCTIONS', 'READ CAREFULLY'
        ]) or line_stripped.startswith(('🚨', '⚠️', '🎯')) or re.match(r'^\d+\.\s+(You MUST|DO NOT|THE TOTAL COST)', line_stripped) or line_stripped.startswith('- Guests:') or line_stripped.startswith('- Check-in:') or line_stripped.startswith('- Check-out:') or line_stripped.startswith('- Total Nights:') or line_stripped.startswith('- Weekday Rate:') or line_stripped.startswith('- Weekend Rate:') or 'Weekday Nights' in line_stripped or 'Subtotal:' in line_stripped:
            continue
        
        # Look for actual answer content
        if len(line_stripped) > 10 and (
            ('PKR' in line_stripped and any(word in line_stripped.lower() for word in ['cost', 'total', 'nights', 'night', 'for']))
            or re.search(r'for \d+ nights?', line_stripped, re.IGNORECASE)
            or re.search(r'total cost.*?PKR', line_stripped, re.IGNORECASE)
            or re.search(r'cottage \d+.*?PKR', line_stripped, re.IGNORECASE)
            or (line_stripped[0].isupper() and 'PKR' in line_stripped and not line_stripped.startswith(('🚨', '⚠️', '🎯')))
        ):
            answer_start_idx = i
            break
    
    if answer_start_idx is not None:
        result = '\n'.join(lines[answer_start_idx:]).strip()
        logger.info(f"Removed template, kept answer starting at line {answer_start_idx}")
        return result
    
    # Method 2: Aggressive regex removal (fallback)
    result = text
    # Remove entire template block from start
    result = re.sub(
        r'🚨\s*CRITICAL PRICING INFORMATION.*?Your answer MUST include.*?Total cost.*?PKR.*?(?=\n\n|For |The total|Total cost|Cottage \d+|PKR \d+|$)',
        '',
        result,
        flags=re.IGNORECASE | re.DOTALL
    )
    # Remove all template patterns
    result = re.sub(r'🚨\s*CRITICAL PRICING INFORMATION.*?⚠️\s*MANDATORY INSTRUCTIONS FOR LLM.*?(?=\n\n|For |The total|Total cost|Cottage \d+|PKR \d+|$)', '', result, flags=re.IGNORECASE | re.DOTALL)
    # Remove MANDATORY RESPONSE blocks (for both pricing and capacity)
    # Handle triple emoji format: 🚨🚨🚨 MANDATORY RESPONSE - YOU MUST USE THIS EXACT ANSWER 🚨🚨🚨 ... 🚨🚨🚨 END OF MANDATORY RESPONSE 🚨🚨🚨
    # Pattern 1: Match the full block from first 🚨🚨🚨 to last 🚨🚨🚨 (most aggressive)
    result = re.sub(r'🚨\s*🚨\s*🚨\s*MANDATORY RESPONSE.*?END OF MANDATORY RESPONSE\s*🚨\s*🚨\s*🚨', '', result, flags=re.IGNORECASE | re.DOTALL)
    # Pattern 2: Match with "YOU MUST USE THIS EXACT ANSWER" in the middle
    result = re.sub(r'🚨\s*🚨\s*🚨\s*MANDATORY RESPONSE.*?YOU MUST USE THIS EXACT ANSWER.*?🚨\s*🚨\s*🚨.*?END OF MANDATORY RESPONSE\s*🚨\s*🚨\s*🚨', '', result, flags=re.IGNORECASE | re.DOTALL)
    # Pattern 3: Match without triple emoji at end
    result = re.sub(r'🚨\s*🚨\s*🚨\s*MANDATORY RESPONSE.*?END OF MANDATORY RESPONSE', '', result, flags=re.IGNORECASE | re.DOTALL)
    # Pattern 4: Match single emoji format
    result = re.sub(r'🚨\s*MANDATORY RESPONSE.*?END OF MANDATORY RESPONSE', '', result, flags=re.IGNORECASE | re.DOTALL)
    # Pattern 5: Match just the markers
    result = re.sub(r'MANDATORY RESPONSE.*?YOU MUST USE THIS EXACT ANSWER.*?END OF MANDATORY RESPONSE', '', result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r'STRUCTURED PRICING ANALYSIS.*?⚠️\s*MANDATORY INSTRUCTIONS.*?(?=\n\n|For |The total|Total cost|Cottage \d+|PKR \d+|$)', '', result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r'ALL PRICES ARE IN PKR.*?⚠️\s*MANDATORY INSTRUCTIONS.*?(?=\n\n|For |The total|Total cost|Cottage \d+|PKR \d+|$)', '', result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r'DETAILED BREAKDOWN.*?⚠️\s*MANDATORY INSTRUCTIONS.*?(?=\n\n|For |The total|Total cost|Cottage \d+|PKR \d+|$)', '', result, flags=re.IGNORECASE | re.DOTALL)
    # Remove numbered instructions
    result = re.sub(r'\n\d+\.\s+(You MUST|DO NOT|THE TOTAL COST|Your answer MUST|The dates|The breakdown|Show the breakdown|YOU MUST MENTION|YOUR ENTIRE RESPONSE|DO NOT add|DO NOT list|DO NOT generate|DO NOT ask|DO NOT say).*?(?=\n|$)', '', result, flags=re.IGNORECASE | re.MULTILINE)
    # Remove emoji markers and template prefixes
    result = re.sub(r'^[🚨⚠️🎯]\s*', '', result, flags=re.MULTILINE)
    result = re.sub(r'^⚠️\s*GENERAL.*?\n', '', result, flags=re.IGNORECASE | re.MULTILINE)
    result = re.sub(r'^GENERAL PRICING QUERY DETECTED.*?\n', '', result, flags=re.IGNORECASE | re.MULTILINE)
    # Remove MANDATORY RESPONSE markers (for both pricing and capacity templates)
    # Handle triple emoji format: 🚨🚨🚨 MANDATORY RESPONSE ... 🚨🚨🚨 END OF MANDATORY RESPONSE
    result = re.sub(r'🚨\s*🚨\s*🚨\s*MANDATORY RESPONSE.*?🚨\s*🚨\s*🚨\s*END OF MANDATORY RESPONSE.*?\n', '', result, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE)
    result = re.sub(r'🚨\s*MANDATORY RESPONSE.*?END OF MANDATORY RESPONSE.*?\n', '', result, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE)
    result = re.sub(r'YOU MUST USE THIS EXACT ANSWER.*?END OF MANDATORY RESPONSE.*?\n', '', result, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE)
    result = re.sub(r'MANDATORY RESPONSE.*?YOU MUST USE THIS EXACT ANSWER.*?END OF MANDATORY RESPONSE', '', result, flags=re.IGNORECASE | re.DOTALL)
    # Remove CRITICAL INSTRUCTIONS blocks
    result = re.sub(r'⚠️\s*⚠️\s*⚠️\s*CRITICAL INSTRUCTIONS.*?READ CAREFULLY.*?\n', '', result, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE)
    result = re.sub(r'CRITICAL INSTRUCTIONS.*?READ CAREFULLY.*?\n', '', result, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE)
    # Remove template data lines
    result = re.sub(r'^[-]\s*(Guests:|Check-in:|Check-out:|Total Nights:|Weekday Rate:|Weekend Rate:).*$', '', result, flags=re.MULTILINE)
    result = re.sub(r'^Weekday Nights.*?Subtotal:.*$', '', result, flags=re.MULTILINE | re.DOTALL)
    # Remove "Searching knowledge base..."
    result = re.sub(r'Searching knowledge base\.\.\..*$', '', result, flags=re.IGNORECASE | re.MULTILINE)
    
    # Final pass: Remove any remaining lines that start with template markers
    lines = result.split('\n')
    cleaned_lines = []
    for line in lines:
        line_stripped = line.strip()
        line_upper = line_stripped.upper()
        # Skip lines that are clearly template markers
        if (line_stripped.startswith(('🚨', '⚠️', '🎯')) or
            'MANDATORY RESPONSE' in line_upper or
            'YOU MUST USE THIS EXACT ANSWER' in line_upper or
            'END OF MANDATORY RESPONSE' in line_upper or
            ('CRITICAL INSTRUCTIONS' in line_upper and 'READ CAREFULLY' in line_upper) or
            ('YOUR ENTIRE RESPONSE MUST START WITH' in line_upper) or
            (line_stripped.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')) and 
             any(word in line_upper for word in ['YOU MUST', 'DO NOT', 'YOUR ENTIRE RESPONSE', 'DO NOT ADD', 'DO NOT LIST', 'DO NOT GENERATE', 'DO NOT ASK', 'DO NOT SAY'])) or
            ('DO NOT ADD' in line_upper and 'Swiss Cottages Bhurban offers' in line_upper) or
            ('DO NOT LIST' in line_upper and 'cottages' in line_upper) or
            ('DO NOT GENERATE' in line_upper and 'response' in line_upper) or
            ('DO NOT ASK' in line_upper and ('group size' in line_upper or 'dates' in line_upper)) or
            ('DO NOT SAY' in line_upper and ('share your dates' in line_upper or 'preferences' in line_upper)) or
            ('AFTER THE MANDATORY RESPONSE' in line_upper) or
            ('FOR FAMILIES: THE MANDATORY RESPONSE' in line_upper) or
            ('TO RECOMMEND THE BEST COTTAGE' in line_upper and 'PLEASE SHARE' in line_upper)):
            continue
        cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines).strip()
    
    # Remove any remaining standalone template markers at the start
    result = re.sub(r'^(🚨\s*)+.*?MANDATORY.*?\n', '', result, flags=re.IGNORECASE | re.MULTILINE)
    result = re.sub(r'^(⚠️\s*)+.*?CRITICAL.*?\n', '', result, flags=re.IGNORECASE | re.MULTILINE)
    result = re.sub(r'^(🚨\s*🚨\s*🚨\s*)+.*?MANDATORY.*?END.*?\n', '', result, flags=re.IGNORECASE | re.MULTILINE)
    result = re.sub(r'^(⚠️\s*⚠️\s*⚠️\s*)+.*?CRITICAL.*?\n', '', result, flags=re.IGNORECASE | re.MULTILINE)
    
    # Final aggressive pass: Remove any remaining MANDATORY RESPONSE blocks that might have been missed
    # Match the exact format: 🚨🚨🚨 MANDATORY RESPONSE - YOU MUST USE THIS EXACT ANSWER 🚨🚨🚨 ... 🚨🚨🚨 END OF MANDATORY RESPONSE 🚨🚨🚨
    result = re.sub(r'🚨\s*🚨\s*🚨\s*MANDATORY RESPONSE.*?END OF MANDATORY RESPONSE\s*🚨\s*🚨\s*🚨', '', result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r'🚨\s*🚨\s*🚨\s*MANDATORY RESPONSE.*?YOU MUST USE THIS EXACT ANSWER.*?🚨\s*🚨\s*🚨.*?END OF MANDATORY RESPONSE\s*🚨\s*🚨\s*🚨', '', result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r'🚨\s*🚨\s*🚨\s*MANDATORY RESPONSE.*?END OF MANDATORY RESPONSE.*?', '', result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r'MANDATORY RESPONSE.*?YOU MUST USE THIS EXACT ANSWER.*?END OF MANDATORY RESPONSE', '', result, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove "To recommend the best cottage..." lines that appear after capacity templates
    result = re.sub(r'\n\s*To recommend the best cottage.*?preferences.*?\.?\s*', '', result, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    result = re.sub(r'To recommend the best cottage.*?preferences.*?\.?\s*', '', result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r'To recommend.*?please share.*?dates.*?preferences.*?\.?\s*', '', result, flags=re.IGNORECASE | re.DOTALL)
    
    # Clean up any remaining emoji markers at the start
    result = re.sub(r'^[🚨⚠️🎯\s]+', '', result, flags=re.MULTILINE)
    
    result = result.strip()
    
    # Final cleanup: Remove any trailing fragments like "you have." that might remain
    result = re.sub(r'\s+you have\.?\s*$', '', result, flags=re.IGNORECASE)
    result = re.sub(r'\s+have\.?\s*$', '', result, flags=re.IGNORECASE)
    
    # Remove any remaining "To recommend..." lines that might have been missed
    result = re.sub(r'\n\s*To recommend.*?preferences.*?\.?\s*$', '', result, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    result = re.sub(r'To recommend.*?preferences.*?\.?\s*$', '', result, flags=re.IGNORECASE | re.DOTALL)
    
    result = result.strip()
    logger.info("Removed template using aggressive regex fallback")
    return result


def truncate_to_max_sentences(text: str, max_sentences: int) -> str:
    """
    Truncate text to a maximum number of sentences, keeping only the core answer.
    Removes tips, suggestions, and follow-up questions.
    
    Args:
        text: Text to truncate
        max_sentences: Maximum number of sentences
        
    Returns:
        Truncated text
    """
    if not text or not text.strip():
        return text
    
    current_count = count_sentences(text)
    if current_count <= max_sentences:
        return text
    
    # Split into sentences
    # Use a more sophisticated approach: split by sentence endings but preserve them
    parts = re.split(r'([.!?]+(?:\s|$))', text)
    sentences = []
    current_sentence = ""
    
    for part in parts:
        if re.match(r'^[.!?]+', part):
            # Punctuation - end of sentence
            current_sentence += part
            if current_sentence.strip():
                sentences.append(current_sentence.strip())
                current_sentence = ""
        else:
            current_sentence += part
    
    if current_sentence.strip():
        sentences.append(current_sentence.strip())
    
    # Take only the first max_sentences
    truncated = ' '.join(sentences[:max_sentences])
    
    # Remove common tip/suggestion patterns that might remain
    tip_patterns = [
        r'💡.*',
        r'📷.*',
        r'Would you like.*',
        r'Ready to book.*',
        r'Tip:.*',
    ]
    for pattern in tip_patterns:
        truncated = re.sub(pattern, '', truncated, flags=re.IGNORECASE | re.DOTALL)
    
    return truncated.strip()


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
        logger.debug(f"Dropbox not enabled in config for cottage {cottage_number}")
        return []
    
    cottage_urls = config.get("cottage_image_urls", {}).get(str(cottage_number), [])
    
    if not cottage_urls:
        logger.warning(f"No Dropbox URLs configured for cottage {cottage_number} in dropbox_images.json")
        return []
    
    logger.info(f"Found {len(cottage_urls)} URLs in config for cottage {cottage_number}")
    
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
            logger.debug(f"Processed Dropbox URL for cottage {cottage_number}: {direct_url[:80]}...")
        else:
            # Assume it's already a direct image URL (from another CDN, etc.)
            all_urls.append(url)
            logger.debug(f"Using direct image URL for cottage {cottage_number}: {url[:80]}...")
    
    if not all_urls:
        logger.warning(f"No valid Dropbox image URLs found for cottage {cottage_number}. "
                      f"Please provide direct image file URLs (not folder links) in dropbox_images.json")
    else:
        logger.info(f"Returning {len(all_urls[:max_images])} Dropbox URLs for cottage {cottage_number}")
    
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
     "http://localhost:8002",  # Add this
    "http://127.0.0.1:8002",  # Add this

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
def detect_image_request(query: str, slot_manager=None, context_tracker=None) -> tuple[bool, List[str]]:
    """
    Detect if the query is asking for images/photos of cottages.
    
    Args:
        query: User query string
        slot_manager: Optional SlotManager instance to get current cottage from session
        context_tracker: Optional ContextTracker instance to get current cottage from context
    
    Returns:
        Tuple of (is_image_request, cottage_numbers)
    """
    query_lower = query.lower()
    
    # Exclude non-image contexts that might contain similar keywords
    exclusion_patterns = [
        "availability", "available", "book", "booking", "want to book", "i want to book",
        "reserve", "reservation", "price", "pricing", "cost", "how much",
        "contact", "manager", "location", "nearby", "capacity", "guests"
    ]
    
    # If query is about availability, booking, pricing, etc., it's NOT an image request
    if any(pattern in query_lower for pattern in exclusion_patterns):
        # Only proceed if query explicitly mentions images/photos/pictures
        if not any(keyword in query_lower for keyword in ["image", "images", "photo", "photos", "picture", "pictures", "gallery"]):
            return False, []
    
    # Primary image keywords (high confidence - explicit image requests)
    primary_image_keywords = [
        "image", "images", "photo", "photos", "picture", "pictures",
        "gallery", "visual", "appearance", "interior", "exterior"
    ]
    
    # Secondary keywords that require image context
    secondary_image_keywords = ["show me", "see", "view"]
    image_context_keywords = ["image", "images", "photo", "photos", "picture", "pictures", "gallery"]
    
    # Check for primary image keywords
    is_image_request = any(keyword in query_lower for keyword in primary_image_keywords)
    logger.debug(f"Image request detection - primary keywords check: {is_image_request} for query: {query}")
    
    # For secondary keywords, require image context
    if not is_image_request:
        has_secondary = any(keyword in query_lower for keyword in secondary_image_keywords)
        if has_secondary:
            # Must have image context keyword nearby
            if any(context in query_lower for context in image_context_keywords):
                is_image_request = True
                logger.debug(f"Image request detected via secondary keywords with image context")
    
    # More specific patterns for image requests (not just "what" or "how")
    image_patterns = [
        r"what\s+does\s+(it|the\s+cottage|cottage\s+\d+)\s+look\s+like",
        r"how\s+does\s+(it|the\s+cottage|cottage\s+\d+)\s+look",
        r"what\s+(does|is)\s+(it|the\s+cottage|cottage\s+\d+)\s+(look|appear)",
        r"show\s+(me\s+)?(images|photos|pictures)",
        r"can\s+(you\s+)?(show|see|view)\s+(images|photos|pictures)",
    ]
    
    # Check for specific image patterns (but exclude cooking/kitchen queries)
    if not is_image_request:
        import re
        cooking_keywords = ["cook", "cooking", "kitchen", "chef", "food", "meal", "prepare", "make food"]
        has_cooking_context = any(keyword in query_lower for keyword in cooking_keywords)
        
        if not has_cooking_context:
            for pattern in image_patterns:
                if re.search(pattern, query_lower):
                    is_image_request = True
                    break
    
    cottage_numbers = []
    # First, try to extract from query directly
    for num in ["7", "9", "11"]:
        if f"cottage {num}" in query_lower or f"cottage{num}" in query_lower:
            cottage_numbers.append(num)
    
    # If no cottage in query but image request, check session context
    if is_image_request and not cottage_numbers:
        # Try to get from slot_manager (current cottage from conversation)
        if slot_manager:
            current_cottage = slot_manager.get_current_cottage()
            if current_cottage:
                cottage_numbers.append(current_cottage)
                logger.debug(f"Using current_cottage from slot_manager: {current_cottage}")
        
        # Fallback to context_tracker
        if not cottage_numbers and context_tracker:
            current_cottage = context_tracker.get_current_cottage()
            if current_cottage:
                cottage_numbers.append(current_cottage)
                logger.debug(f"Using current_cottage from context_tracker: {current_cottage}")
        
        # If still no cottage found, default to all cottages
        if not cottage_numbers:
            cottage_numbers = ["7", "9", "11"]
            logger.debug("No cottage specified in query or session context, defaulting to all cottages")
    
    return is_image_request, cottage_numbers


def extract_cottage_from_text(text: str) -> Optional[str]:
    """Extract cottage number from text (answer or query)."""
    text_lower = text.lower()
    for num in ["7", "9", "11"]:
        if f"cottage {num}" in text_lower or f"cottage{num}" in text_lower:
            return num
    return None


def should_offer_images(query: str, answer: str) -> tuple[bool, Optional[str]]:
    """
    Determine if we should offer images based on query and answer.
    
    Returns:
        (should_offer, cottage_number)
    """
    query_lower = query.lower()
    answer_lower = answer.lower()
    
    # Check if user already asked for images
    if any(keyword in query_lower for keyword in ["image", "images", "photo", "photos", "picture", "pictures", "show me", "see", "view"]):
        return False, None
    
    # Exclude booking, availability, pricing, and other non-image contexts
    exclusion_patterns = [
        "book", "booking", "reserve", "reservation", "want to book", "i want to book",
        "available", "availability", "check availability", "price", "pricing", "cost",
        "contact", "manager", "location", "nearby", "capacity", "guests", "how much"
    ]
    
    # If query is about booking, availability, pricing, etc., do NOT offer images
    if any(pattern in query_lower for pattern in exclusion_patterns):
        return False, None
    
    # Check if answer mentions a specific cottage
    cottage_num = extract_cottage_from_text(answer)
    if cottage_num:
        # Check if query was about a specific cottage
        query_cottage = extract_cottage_from_text(query)
        if query_cottage == cottage_num:
            return True, cottage_num
    
    return False, None


def detect_image_type_request(query: str) -> Optional[str]:
    """
    Detect if the query is asking for a specific type of images (kitchen, bathroom, bedroom, etc.).
    
    Args:
        query: User query string
        
    Returns:
        Image type string (e.g., "kitchen", "bathroom", "bedroom") or None
    """
    query_lower = query.lower()
    
    # Map of keywords to image types
    image_type_keywords = {
        "kitchen": ["kitchen", "cooking", "cook"],
        "bathroom": ["bathroom", "bath", "toilet", "washroom", "restroom"],
        "bedroom": ["bedroom", "bed", "sleeping"],
        "living": ["living room", "lounge", "sitting room", "living area"],
        "exterior": ["exterior", "outside", "outside view", "external", "facade"],
        "balcony": ["balcony", "terrace", "patio", "deck"],
        "view": ["view", "scenic", "landscape", "mountain view"],
    }
    
    for image_type, keywords in image_type_keywords.items():
        if any(keyword in query_lower for keyword in keywords):
            return image_type
    
    return None


def get_cottage_images_by_type(cottage_number: str, root_folder: Path, image_type: str = None, max_images: int = 6) -> List[Path]:
    """
    Get image paths for a specific cottage, optionally filtered by image type.
    
    Args:
        cottage_number: Cottage number (e.g., "7", "9", "11")
        root_folder: Root folder of the project
        image_type: Optional image type to filter by (e.g., "kitchen", "bathroom")
        max_images: Maximum number of images to return
        
    Returns:
        List of image file paths
    """
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
                
                # If image_type is specified, try to find matching subfolder or files
                if image_type:
                    # Check subfolders for image type
                    type_folders = []
                    try:
                        for subfolder in folder.iterdir():
                            if subfolder.is_dir():
                                subfolder_lower = subfolder.name.lower()
                                if image_type.lower() in subfolder_lower:
                                    type_folders.append(subfolder)
                    except (NotADirectoryError, PermissionError):
                        pass
                    
                    # If found type-specific folders, search only there
                    if type_folders:
                        for type_folder in type_folders:
                            images = (
                                list(type_folder.glob("*.jpg")) + list(type_folder.glob("*.jpeg")) +
                                list(type_folder.glob("*.png")) + list(type_folder.glob("*.webp")) +
                                list(type_folder.glob("*.JPG")) + list(type_folder.glob("*.JPEG")) +
                                list(type_folder.glob("*.PNG"))
                            )
                            image_paths.extend(images)
                        continue
                    else:
                        # No type-specific folder found, check file names
                        all_images = (
                            list(folder.glob("**/*.jpg")) + list(folder.glob("**/*.jpeg")) +
                            list(folder.glob("**/*.png")) + list(folder.glob("**/*.webp")) +
                            list(folder.glob("**/*.JPG")) + list(folder.glob("**/*.JPEG")) +
                            list(folder.glob("**/*.PNG"))
                        )
                        # Filter by image type in filename
                        filtered_images = [
                            img for img in all_images
                            if image_type.lower() in img.name.lower() or image_type.lower() in str(img.parent).lower()
                        ]
                        if filtered_images:
                            image_paths.extend(filtered_images)
                            continue
                        # If no type-specific images found, return empty (don't fall through to all images)
                        return []
                
                # No image type filter, get all images
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


def get_cottage_images(cottage_number: str, root_folder: Path, max_images: int = 6) -> List[Path]:
    """Get image paths for a specific cottage."""
    return get_cottage_images_by_type(cottage_number, root_folder, image_type=None, max_images=max_images)


def validate_and_fix_currency(answer: str, context: str = "") -> str:
    """
    Validate that answer doesn't contain dollar prices when context has PKR prices.
    Also detect and fix incorrect lac/lakh conversions.
    If dollar prices are found, convert them to PKR or remove them.
    """
    if not answer:
        return answer
    
    converted_answer = answer
    
    # Check if answer contains dollar prices
    dollar_pattern = r'\$(\d+(?:,\d+)?)'
    dollar_matches = re.findall(dollar_pattern, answer)
    
    if dollar_matches:
        logger.error(
            f"⚠️ CRITICAL: Answer contains dollar prices: {dollar_matches}\n"
            f"Answer snippet: {answer[:200]}...\n"
        )
        
        # Convert dollar prices to PKR (approximate conversion: $1 = PKR 300)
        # This is a fallback - ideally the LLM shouldn't generate dollar prices
        for dollar_amount_str in dollar_matches:
            # Remove commas and convert to int
            dollar_amount = int(dollar_amount_str.replace(",", ""))
            # Convert to PKR (using approximate rate)
            pkr_amount = dollar_amount * 300
            # Replace $X with PKR X
            dollar_str = f"${dollar_amount_str}"
            pkr_str = f"PKR {pkr_amount:,}"
            converted_answer = converted_answer.replace(dollar_str, pkr_str)
            logger.warning(f"Converted {dollar_str} to {pkr_str} (approximate conversion)")
        
        # Also check for common dollar price patterns and replace
        # Pattern: "$400 for a weekday" -> "PKR 120,000 for a weekday"
        converted_answer = re.sub(
            r'\$(\d+(?:,\d+)?)\s+(?:for|per)',
            lambda m: f"PKR {int(m.group(1).replace(',', '')) * 300:,} ",
            converted_answer
        )
    
    # Check for lac/lakh conversions (WRONG - should use exact PKR values)
    # Patterns: "8-12 lac PKR", "8 lac PKR", "800,000-1,200,000 PKR", "approximately 8-12 lac"
    lac_patterns = [
        r'(\d+)\s*-\s*(\d+)\s*(?:lac|lakh)\s*PKR',
        r'(\d+)\s*(?:lac|lakh)\s*PKR',
        r'(\d{1,3}(?:,\d{3}){2,})\s*-\s*(\d{1,3}(?:,\d{3}){2,})\s*PKR',  # 800,000-1,200,000 PKR
        r'approximately\s*(\d+)\s*-\s*(\d+)\s*(?:lac|lakh)',
    ]
    
    for pattern in lac_patterns:
        matches = re.finditer(pattern, converted_answer, re.IGNORECASE)
        for match in matches:
            logger.error(
                f"⚠️ CRITICAL: Answer contains lac/lakh conversion: '{match.group(0)}'\n"
                f"This is WRONG - should use exact PKR values from context (e.g., PKR 32,000, PKR 38,000)\n"
                f"Answer snippet: {answer[max(0, match.start()-50):match.end()+50]}...\n"
            )
            # Try to extract context prices if available
            # For now, just log the error - the prompt should prevent this, but this is a safety check
            logger.warning(f"Lac/lakh conversion detected but cannot auto-fix without context prices. Prompt should prevent this.")
    
    return converted_answer


def fix_incorrect_naming(answer: str) -> str:
    """
    Fix incorrect property naming in answers.
    Replaces "Swiss Chalet", "Swiss Chalet cottages", "mountain cottage", "pearl cottage" with "Swiss Cottages Bhurban".
    
    Args:
        answer: The answer text that may contain incorrect naming
        
    Returns:
        Answer text with incorrect naming replaced
    """
    if not answer:
        return answer
    
    answer_lower = answer.lower()
    fixed_answer = answer
    
    # Replace incorrect names with correct name
    incorrect_name_patterns = [
        (r"swiss\s+chalet\s+cottages?", "Swiss Cottages Bhurban"),
        (r"swiss\s+chalet", "Swiss Cottages Bhurban"),
        (r"mountain\s+cottage", "Swiss Cottages Bhurban"),
        (r"pearl\s+cottage", "Swiss Cottages Bhurban"),
    ]
    
    for pattern, replacement in incorrect_name_patterns:
        if re.search(pattern, answer_lower):
            logger.warning(f"Found incorrect naming in answer, replacing: {pattern}")
            fixed_answer = re.sub(pattern, replacement, fixed_answer, flags=re.IGNORECASE)
    
    return fixed_answer


def fix_question_rephrasing(answer: str, question: str = "") -> str:
    """
    Remove question rephrasing from answers.
    Removes phrases like "Considering your stay...", "Regarding your question...", etc.
    
    Args:
        answer: The answer text that may contain question rephrasing
        question: The original question (optional, for better detection)
        
    Returns:
        Answer text with question rephrasing removed
    """
    if not answer:
        return answer
    
    answer_lower = answer.lower()
    fixed_answer = answer
    
    # Patterns that indicate question rephrasing
    rephrasing_patterns = [
        r"^considering\s+(?:your\s+)?(?:stay|question|inquiry)[^.]*[.,]\s*",
        r"^regarding\s+(?:your\s+)?(?:question|inquiry|stay)[^.]*[.,]\s*",
        r"^about\s+(?:your\s+)?(?:question|inquiry)[^.]*[.,]\s*",
        r"^to\s+answer\s+(?:your\s+)?(?:question|inquiry)[^.]*[.,]\s*",
        r"^in\s+response\s+to\s+(?:your\s+)?(?:question|inquiry)[^.]*[.,]\s*",
    ]
    
    # Check if answer starts with a rephrasing pattern
    for pattern in rephrasing_patterns:
        if re.match(pattern, answer_lower):
            logger.warning(f"Found question rephrasing in answer, removing: {pattern}")
            fixed_answer = re.sub(pattern, "", fixed_answer, flags=re.IGNORECASE)
            # Capitalize first letter if needed
            if fixed_answer and fixed_answer[0].islower():
                fixed_answer = fixed_answer[0].upper() + fixed_answer[1:]
            break
    
    # Also check if answer contains the question itself (repeated)
    if question:
        question_lower = question.lower().strip()
        # Remove question marks and normalize
        question_normalized = re.sub(r'[?.,!]', '', question_lower)
        if question_normalized and len(question_normalized) > 10:
            # Check if answer starts with a variation of the question
            answer_start = answer_lower[:len(question_normalized) + 20]  # Check first part
            if question_normalized in answer_start:
                # Find where the actual answer starts (after the question)
                question_pos = answer_lower.find(question_normalized)
                if question_pos < 50:  # Question appears near the start
                    # Extract text after the question
                    after_question = answer[question_pos + len(question):].strip()
                    if after_question and len(after_question) > 20:
                        # Check if it starts with common separators
                        after_question = re.sub(r'^[.,;:\s]+', '', after_question)
                        if after_question:
                            fixed_answer = after_question
                            logger.warning("Removed question repetition from answer start")
    
    return fixed_answer


def detect_and_reject_wrong_location_answer(answer: str, query: str) -> Optional[str]:
    """
    Detect and reject clearly wrong location answers that are from training data.
    Returns None if answer should be rejected, otherwise returns the answer.
    """
    if not answer or not query:
        return answer
    
    answer_lower = answer.lower()
    query_lower = query.lower()
    
    # Only check location queries
    is_location_query = any(word in query_lower for word in ["where", "location", "located", "address"])
    
    if not is_location_query:
        return answer
    
    # CRITICAL: Detect wrong answers that describe Bhurban as a general place
    wrong_patterns = [
        r"^bhurban\s+is\s+a\s+stunning",  # "Bhurban is a stunning hill station..."
        r"^bhurban\s+is\s+a\s+popular",  # "Bhurban is a popular..."
        r"^bhurban\s+is\s+.*?hill\s+station",  # "Bhurban is a hill station..."
        r"bhurban\s+is\s+.*?picnic\s+spot",  # "Bhurban is a picnic spot..."
        r"bhurban\s+is\s+.*?located\s+in.*?azad\s+kashmir",  # "Bhurban is located in Azad Kashmir"
        r"bhurban\s+is\s+.*?near\s+abbottabad",  # "Bhurban is near Abbottabad"
        r"located\s+in\s+the\s+beautiful\s+azad\s+kashmir\s+region",  # "located in the beautiful Azad Kashmir region"
        r"azad\s+kashmir\s+region",  # "Azad Kashmir region"
        r"near\s+abbottabad",  # "near Abbottabad"
        r"abbottabad",  # "Abbottabad"
    ]
    
    for pattern in wrong_patterns:
        if re.search(pattern, answer_lower):
            logger.error(f"REJECTED: Answer contains wrong location pattern: {pattern}")
            logger.error(f"Wrong answer: {answer[:200]}...")
            return None  # Reject this answer
    
    # Check if answer describes Bhurban as a general place (not Swiss Cottages)
    # This catches patterns like "Bhurban is a stunning hill station..." or "Bhurban is a lovely picnic spot..."
    if answer_lower.startswith("bhurban is") or answer_lower.startswith("bhurban is a") or answer_lower.startswith("bhurban is located"):
        logger.error("REJECTED: Answer starts with 'Bhurban is...' - describes Bhurban as place, not Swiss Cottages location")
        return None
    
    # Also check if answer starts with "Bhurban is" anywhere in first 50 chars
    if "bhurban is" in answer_lower[:50] and "swiss cottages" not in answer_lower[:100]:
        logger.error("REJECTED: Answer describes Bhurban as general place, not Swiss Cottages location")
        return None
    
    # Check if answer doesn't mention Swiss Cottages at all (for location queries)
    if "swiss cottages" not in answer_lower and "swiss cottage" not in answer_lower:
        logger.warning("Answer doesn't mention Swiss Cottages - might be wrong")
        # Don't reject, but log warning
    
    return answer


def fix_incorrect_location_mentions(answer: str) -> str:
    """
    Fix incorrect location mentions in answers.
    Replaces "Azad Kashmir" and "Patriata" with correct location information.
    
    Args:
        answer: The answer text that may contain incorrect location mentions
        
    Returns:
        Answer text with incorrect location mentions replaced
    """
    if not answer:
        return answer
    
    answer_lower = answer.lower()
    
    # Check if answer mentions incorrect locations for Swiss Cottages
    incorrect_location_patterns = [
        # Pattern: "Swiss Cottage is located in Bhurban, a popular hill station in Azad Kashmir"
        (r"swiss\s+cottages?\s+(?:is|are)\s+located\s+in\s+bhurban[^.]*azad\s+kashmir", "Swiss Cottages is located adjacent to Pearl Continental (PC) Bhurban in the Murree Hills, within a secure gated community in Bhurban, Pakistan"),
        # Pattern: "Swiss Cottage is located in Azad Kashmir"
        (r"swiss\s+cottages?\s+(?:is|are|located|in)\s+(?:in\s+)?azad\s+kashmir", "Swiss Cottages is located adjacent to Pearl Continental (PC) Bhurban in the Murree Hills, within a secure gated community in Bhurban, Pakistan"),
        # Pattern: "Swiss Cottage is located in Patriata"
        (r"swiss\s+cottages?\s+(?:is|are|located|in)\s+(?:in\s+)?patriata", "Swiss Cottages is located adjacent to Pearl Continental (PC) Bhurban in the Murree Hills, within a secure gated community in Bhurban, Pakistan"),
        # Pattern: "located in Azad Kashmir"
        (r"located\s+in\s+azad\s+kashmir", "located in the Murree Hills, Bhurban, Pakistan"),
        # Pattern: "in Azad Kashmir, Pakistan"
        (r"in\s+azad\s+kashmir,\s+pakistan", "in the Murree Hills, Bhurban, Pakistan"),
        # Pattern: "Azad Kashmir, Pakistan"
        (r"azad\s+kashmir,\s+pakistan", "Murree Hills, Bhurban, Pakistan"),
        # Pattern: "Bhurban, Azad Kashmir"
        (r"bhurban[^,]*,\s*azad\s+kashmir", "Bhurban, Murree, Pakistan"),
        # Pattern: "Bhurban, a popular hill station in Azad Kashmir"
        (r"bhurban[^.]*in\s+azad\s+kashmir", "Bhurban, Murree, Pakistan"),
        # Pattern: "Patriata, Pakistan"
        (r"patriata,\s+pakistan", "Murree Hills, Bhurban, Pakistan"),
    ]
    
    fixed_answer = answer
    for pattern, replacement in incorrect_location_patterns:
        if re.search(pattern, answer_lower):
            logger.warning(f"Found incorrect location mention in answer, replacing: {pattern}")
            fixed_answer = re.sub(pattern, replacement, fixed_answer, flags=re.IGNORECASE)
            # Also ensure Google Maps link is included if it's a location-related answer
            if "location" in answer_lower or "located" in answer_lower or "where" in answer_lower:
                if "goo.gl/maps" not in fixed_answer.lower() and "maps" not in fixed_answer.lower():
                    fixed_answer += "\n\n[MAP] View on Google Maps: https://goo.gl/maps/PQbSR9DsuxwjxUoU6"
    
    # Additional aggressive check: if answer mentions "Azad Kashmir" in any context about Swiss Cottages location, replace it
    # This catches patterns like "Bhurban, Azad Kashmir", "located in Azad Kashmir", "in Azad Kashmir", etc.
    if "azad kashmir" in answer_lower:
        # Check if it's in a location context (not just mentioning viewpoints)
        is_location_context = any(phrase in answer_lower for phrase in [
            "swiss", "cottage", "location", "located", "bhurban", "in azad kashmir",
            "azad kashmir, pakistan", "bhurban, azad kashmir", "gated community in"
        ])
        
        # Check if it's NOT in the correct context (overlooking, viewpoint)
        is_not_viewpoint_context = not any(phrase in answer_lower for phrase in [
            "overlooking azad kashmir",
            "viewpoint",
            "viewpoints overlooking",
            "scenic viewpoints",
            "can see azad kashmir",
            "visible from"
        ])
        
        if is_location_context and is_not_viewpoint_context:
            # Replace "Azad Kashmir" with "Murree Hills, Bhurban, Pakistan" when talking about Swiss Cottages location
            # More aggressive patterns
            replacement_patterns = [
                (r"bhurban[^,.]*,\s*azad\s+kashmir", "Bhurban, Murree, Pakistan"),
                (r"gated\s+community\s+in\s+bhurban[^,.]*,\s*azad\s+kashmir", "gated community in Bhurban, Murree, Pakistan"),
                (r"located\s+within\s+a\s+gated\s+community\s+in\s+bhurban[^,.]*,\s*azad\s+kashmir", "located within a gated community in Bhurban, Murree, Pakistan"),
                (r"in\s+bhurban[^,.]*,\s*azad\s+kashmir", "in Bhurban, Murree, Pakistan"),
                (r"\bazad\s+kashmir\b", "Murree Hills, Bhurban, Pakistan"),  # Catch any remaining instances
            ]
            
            for pattern, replacement in replacement_patterns:
                if re.search(pattern, fixed_answer, flags=re.IGNORECASE):
                    fixed_answer = re.sub(pattern, replacement, fixed_answer, flags=re.IGNORECASE)
                    logger.warning(f"Replaced pattern '{pattern}' with correct location in answer")
        
        # Ensure Google Maps link is included for location answers
        if ("location" in answer_lower or "located" in answer_lower or "where" in answer_lower) and "goo.gl/maps" not in fixed_answer.lower():
            fixed_answer += "\n\n[MAP] View on Google Maps: https://goo.gl/maps/PQbSR9DsuxwjxUoU6"
    
    return fixed_answer


def clean_answer_text(answer: str) -> str:
    """
    Remove LLM reasoning and process text from answer.
    Users should only see the final answer, not the LLM's thinking process.
    """
    if not answer:
        return answer
    
    # First, remove large reasoning blocks that span multiple lines
    # This catches the "We have the opportunity to refine..." pattern with all its content
    large_reasoning_blocks = [
        # Pattern for "We have the opportunity to refine..." through "The refined answer remains..."
        # Matches: "We have the opportunity..." + separator + "answer: ..." + separator + "Since the original query..." + "The refined answer remains..."
        r"We have the opportunity to refine.*?(?:[-=]{3,}.*?)?(?:answer:.*?)?(?:[-=]{3,}.*?)?(?:Since the original query.*?)?(?:The refined answer (?:remains|is).*?\.?)\s*",
        # Pattern for "To refine the existing answer..." through end
        r"To refine the existing answer.*?(?:[-=]{3,}.*?)?(?:answer:.*?)?(?:[-=]{3,}.*?)?(?:Since.*?)?(?:The refined answer.*?\.?)\s*",
        # Pattern for "Based on the existing answer and the new context..." through end
        r"Based on the existing answer and the new context.*?(?:[-=]{3,}.*?)?(?:answer:.*?)?(?:[-=]{3,}.*?)?(?:Since.*?)?(?:The refined answer.*?\.?)\s*",
        # Pattern for "Based on the context information provided above..." through end
        r"Based on the context information provided above.*?(?:[-=]{3,}.*?)?(?:answer:.*?)?(?:[-=]{3,}.*?)?(?:The refined answer (?:remains|is).*?\.?)\s*",
        # Pattern for "Considering..." through end
        r"Considering.*?the refined answer.*?(?:[-=]{3,}.*?)?(?:answer:.*?)?(?:[-=]{3,}.*?)?(?:Since.*?)?(?:The refined answer.*?\.?)\s*",
        # Pattern for "Since the original query is as follows:" through "The refined answer remains..."
        r"Since the original query is as follows:.*?The refined answer (?:remains|is).*?\.?\s*",
        # Pattern for separator lines with "answer:" in between (catches standalone answer blocks)
        r"[-=]{3,}\s*answer:\s*.*?[-=]{3,}\s*",
        # Pattern for "The refined answer remains the same" or similar endings
        r"The refined answer (?:remains the same|is the same|remains unchanged).*?\.?\s*",
        # Pattern for "Thank you for the additional context. I've refined the answer..." through "Here are..."
        r"Thank you for the additional context\.\s*I've refined the answer.*?(?:Here are|Here is|The answer is|The facilities are|The amenities are)",
        # Pattern for "I've refined the answer to provide more accurate information..."
        r"I've refined the answer to provide more accurate information\.\s*(?:Since.*?limited.*?I'll stick to.*?\.\s*)?(?:Here are|Here is|The answer is)",
        # Pattern for "Since specific details about X are limited, I'll stick to..."
        r"Since specific details about.*?are limited.*?I'll stick to.*?\.\s*(?:Here are|Here is)",
    ]
    
    cleaned = answer
    
    # First, try to extract the actual answer from reasoning blocks
    # Pattern: "We have the opportunity... answer: [ACTUAL ANSWER] ... Since the original query..."
    # Extract just the answer part
    answer_extraction_patterns = [
        # Pattern 1: Full block with separators
        r"We have the opportunity to refine.*?[-=]{3,}\s*answer:\s*(.*?)\s*[-=]{3,}.*?Since the original query.*?The refined answer.*?\.?\s*",
        # Pattern 2: Without "Since the original query" part
        r"We have the opportunity to refine.*?[-=]{3,}\s*answer:\s*(.*?)\s*[-=]{3,}.*?The refined answer.*?\.?\s*",
        # Pattern 3: More flexible - any "answer:" in reasoning block
        r"(?:We have the opportunity|To refine|Based on the existing answer).*?answer:\s*(.*?)(?:[-=]{3,}.*?)?(?:Since.*?)?(?:The refined answer.*?\.?)\s*",
    ]
    
    for pattern in answer_extraction_patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE | re.DOTALL)
        if match:
            # Replace the entire reasoning block with just the extracted answer
            actual_answer = match.group(1).strip()
            # Only replace if we found a meaningful answer (not empty, not just reasoning text)
            if actual_answer and len(actual_answer) > 10 and not re.match(r"^(yes|no|the|a|an)\s*$", actual_answer, re.IGNORECASE):
                cleaned = re.sub(pattern, actual_answer + "\n", cleaned, flags=re.IGNORECASE | re.DOTALL)
                break  # Only use the first successful match
    
    # Then remove remaining large reasoning blocks
    for pattern in large_reasoning_blocks:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE)
    
    # Remove common reasoning prefixes and process text (single line patterns)
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
        # Specific patterns from user examples
        r"Based on the context information provided above.*?\.\s*",
        r"Based on the context information provided above.*?:\s*",
        r"We have the opportunity to refine the existing answer with.*?\.\s*",
        r"We have the opportunity to refine the existing answer with.*?:\s*",
        r"The refined answer is:?\s*",
        r"The refined answer remains:?\s*",
        r"Based on the context information provided above, the refined answer is:?\s*",
        r"Based on the context information provided above, the refined answer remains:?\s*",
        # Patterns for "Thank you for the additional context" reasoning
        r"^Thank you for the additional context\.\s*I've refined the answer.*?\.\s*",
        r"^I've refined the answer to provide more accurate information\.\s*",
        r"^Since specific details about.*?are limited.*?I'll stick to.*?\.\s*",
    ]
    
    for pattern in reasoning_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove structured pricing analysis templates (internal instructions that shouldn't be shown to users)
    # This is CRITICAL - the entire template must be removed before showing to users
    
    # Remove template markers that LLM might output at the start
    template_start_patterns = [
        r"^⚠️\s*GENERAL.*?\n",
        r"^⚠️\s*⚠️\s*⚠️.*?\n",
        r"^🚨\s*🚨\s*🚨.*?\n",
        r"^GENERAL PRICING QUERY DETECTED.*?\n",
    ]
    for pattern in template_start_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    
    # Quick check: If answer starts with template markers, find where actual answer begins
    # Enhanced to catch capacity templates too
    if cleaned.strip().startswith('🚨') or cleaned.strip().startswith('⚠️') or '🚨 CRITICAL PRICING INFORMATION' in cleaned or 'CRITICAL CAPACITY INFORMATION' in cleaned:
        # Find the first line that contains actual pricing answer (not template instructions)
        lines = cleaned.split('\n')
        answer_start_idx = None
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            line_upper = line_stripped.upper()
            
            # Skip template lines (enhanced to catch capacity templates too)
            if any(keyword in line_upper for keyword in [
                'CRITICAL PRICING', 'MANDATORY INSTRUCTIONS', 'STRUCTURED PRICING',
                'DO NOT CONVERT', 'YOU MUST USE', 'ALL PRICES ARE IN PKR',
                'DETAILED BREAKDOWN', 'CHECK-IN:', 'CHECK-OUT:', 'GUESTS:',
                'WEEKDAY RATE:', 'WEEKEND RATE:', 'TOTAL NIGHTS:',
                'STRUCTURED CAPACITY ANALYSIS', 'DIRECT ANSWER (USE THIS EXACTLY)',
                'CRITICAL CAPACITY INFORMATION', 'YOU MUST INCLUDE'
            ]) or line_stripped.startswith(('🚨', '⚠️', '🎯')) or re.match(r'^\d+\.\s+(You MUST|DO NOT|THE TOTAL COST)', line_stripped):
                continue
            
            # Look for actual answer content (enhanced to catch capacity answers too)
            if len(line_stripped) > 15 and (
                'PKR' in line_stripped and any(word in line_stripped.lower() for word in ['cost', 'total', 'nights', 'night'])
                or re.search(r'for \d+ nights?', line_stripped, re.IGNORECASE)
                or re.search(r'total cost.*?PKR', line_stripped, re.IGNORECASE)
                or re.search(r'cottage \d+', line_stripped, re.IGNORECASE)
                or re.search(r'up to \d+ guests?', line_stripped, re.IGNORECASE)
                or re.search(r'capacity.*?\d+', line_stripped, re.IGNORECASE)
            ):
                answer_start_idx = i
                break
        
        if answer_start_idx is not None:
            cleaned = '\n'.join(lines[answer_start_idx:]).strip()
        else:
            # Fallback: remove everything up to first meaningful content (enhanced for capacity)
            cleaned = '\n'.join([l for l in lines if l.strip() and not any(
                keyword in l.upper() for keyword in [
                    'CRITICAL PRICING', 'MANDATORY INSTRUCTIONS', 'STRUCTURED PRICING',
                    'DO NOT CONVERT', 'YOU MUST USE', 'ALL PRICES ARE IN PKR',
                    'CRITICAL CAPACITY', 'STRUCTURED CAPACITY', 'DIRECT ANSWER (USE THIS EXACTLY)'
                ]
            ) and not l.strip().startswith(('🚨', '⚠️', '🎯'))]).strip()
    
    # First, try to find where the actual answer starts (after the template)
    # Look for patterns that indicate the template has ended and real answer begins
    answer_start_markers = [
        r"For \d+ nights?",
        r"The total cost",
        r"Total cost",
        r"For cottage",
        r"Cottage \d+",
        r"PKR \d+",
        r"pricing for",
        r"cost is",
    ]
    
    # Split into lines for more precise filtering
    lines = cleaned.split('\n')
    filtered_lines = []
    in_template = False
    template_ended = False
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        line_upper = line_stripped.upper()
        
        # Detect start of template (enhanced to catch capacity templates)
        if not template_ended and (
            line_stripped.startswith('🚨') and ('CRITICAL PRICING' in line_upper or 'CRITICAL CAPACITY' in line_upper)
            or line_stripped.startswith('⚠️') and 'MANDATORY INSTRUCTIONS' in line_upper
            or 'STRUCTURED PRICING ANALYSIS' in line_upper
            or 'STRUCTURED CAPACITY ANALYSIS' in line_upper
            or 'ALL PRICES ARE IN PKR' in line_upper and 'DO NOT USE DOLLAR' in line_upper
            or 'CRITICAL CAPACITY INFORMATION' in line_upper
        ):
            in_template = True
            continue
        
        # Detect template content lines (enhanced to catch capacity templates)
        if in_template and (
            line_stripped.startswith(('🚨', '⚠️', '🎯'))
            or 'CRITICAL PRICING' in line_upper
            or 'CRITICAL CAPACITY' in line_upper
            or 'MANDATORY INSTRUCTIONS FOR LLM' in line_upper
            or 'STRUCTURED PRICING ANALYSIS' in line_upper
            or 'STRUCTURED CAPACITY ANALYSIS' in line_upper
            or 'DO NOT CONVERT TO DOLLARS' in line_upper
            or 'DO NOT USE DOLLAR PRICES' in line_upper
            or 'YOU MUST USE ONLY' in line_upper
            or 'THE TOTAL COST IS PKR' in line_upper and 'YOU MUST INCLUDE' in line_upper
            or 'Your answer MUST include' in line_upper
            or 'YOU MUST include' in line_upper
            or 'DIRECT ANSWER (USE THIS EXACTLY)' in line_upper
            or line_stripped.startswith('- Guests:')
            or line_stripped.startswith('- Check-in:')
            or line_stripped.startswith('- Check-out:')
            or line_stripped.startswith('- Total Nights:')
            or line_stripped.startswith('- Weekday Rate:')
            or line_stripped.startswith('- Weekend Rate:')
            or line_stripped.startswith('- Base capacity:')
            or line_stripped.startswith('- Maximum capacity:')
            or line_stripped.startswith('- Bedrooms:')
            or 'DETAILED BREAKDOWN' in line_upper
            or re.match(r'^\d+\.\s+You MUST', line_stripped)
            or re.match(r'^\d+\.\s+DO NOT', line_stripped)
            or re.match(r'^\d+\.\s+THE TOTAL COST', line_stripped)
        ):
            continue
        
        # Check if we've reached the end of template (empty line or actual answer content)
        if in_template:
            # If we hit an empty line or find answer-like content, template has ended
            if not line_stripped:
                # Check next few lines to see if answer starts
                next_lines = [l.strip() for l in lines[i+1:i+4] if l.strip()]
                if any(re.search(marker, ' '.join(next_lines), re.IGNORECASE) for marker in answer_start_markers):
                    template_ended = True
                    in_template = False
                    # Include this line and continue
                else:
                    continue
            elif any(re.search(marker, line_stripped, re.IGNORECASE) for marker in answer_start_markers):
                # Found actual answer content
                template_ended = True
                in_template = False
                filtered_lines.append(line)
            else:
                # Still in template, skip
                continue
        else:
            # Not in template, include the line
            filtered_lines.append(line)
    
    cleaned = '\n'.join(filtered_lines)
    
    # Also use regex as fallback to catch any remaining template fragments
    # Enhanced to catch ALL internal instruction patterns including capacity templates
    pricing_template_patterns = [
        r"🚨\s*CRITICAL PRICING INFORMATION.*?⚠️\s*MANDATORY INSTRUCTIONS FOR LLM.*?(?=\n\n|\Z)",
        r"STRUCTURED PRICING ANALYSIS FOR COTTAGE.*?⚠️\s*MANDATORY INSTRUCTIONS FOR LLM.*?(?=\n\n|\Z)",
        r"ALL PRICES ARE IN PKR.*?⚠️\s*MANDATORY INSTRUCTIONS FOR LLM.*?(?=\n\n|\Z)",
        r"⚠️\s*MANDATORY INSTRUCTIONS FOR LLM.*?(?=\n\n|\Z)",
        r"You MUST use ONLY these PKR prices.*?(?=\n\n|\Z)",
        r"DO NOT convert to dollars.*?(?=\n\n|\Z)",
        r"Your answer MUST include.*?Total cost.*?(?=\n\n|\Z)",
        r"🎯\s*TOTAL COST FOR.*?🎯\s*",
        # Capacity analysis templates
        r"STRUCTURED CAPACITY ANALYSIS.*?DIRECT ANSWER.*?(?=\n\n|\Z)",
        r"CRITICAL CAPACITY INFORMATION.*?YOU MUST include.*?(?=\n\n|\Z)",
        r"CRITICAL CAPACITY INFORMATION FOR COTTAGE.*?YOU MUST include.*?(?=\n\n|\Z)",
    ]
    
    for pattern in pricing_template_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE)
    
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
            "since the original query", "the refined answer remains", "the refined answer is",
            "refined answer remains", "refined answer is", "answer remains the same",
            "based on the context information provided above", "we have the opportunity to refine",
            "based on the context information", "the context information provided above",
        ]
        
        # Check if line contains reasoning indicators
        is_reasoning_line = any(indicator in line_lower for indicator in reasoning_indicators)
        
        # Also check for lines that are just "answer:" followed by content (reasoning pattern)
        if re.match(r"^\s*answer:\s*", line_lower) and len(line) < 300:
            is_reasoning_line = True
        
        # Skip lines that are clearly reasoning
        if is_reasoning_line and len(line) < 300:
            skip_next = True
            continue
        
        # Skip separator lines after reasoning (dashes, equals, etc.)
        if skip_next and (re.match(r"^[-=*#]{3,}\s*$", line.strip()) or line.strip() == ""):
            continue
        
        skip_next = False
        filtered_lines.append(line)
    
    cleaned = '\n'.join(filtered_lines)
    
    # Remove reasoning text that appears at the start of the answer
    # This catches patterns like "Based on the context information provided above, the refined answer is: [answer]"
    start_reasoning_patterns = [
        r"^(?:We have the opportunity to refine|Based on the context information provided above|Based on the provided context|Given the context|Since the original query).*?:\s*",
        r"^(?:The refined answer is|The refined answer remains|Refined Answer|Answer):\s*",
    ]
    
    for pattern in start_reasoning_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    
    # CRITICAL: Remove example/placeholder URLs that are from training data, not from FAQ documents
    # These are common placeholder URLs that LLMs generate from training data
    placeholder_url_patterns = [
        r"https?://(www\.)?example\.com[^\s\)]*",  # example.com URLs
        r"https?://example\.com[^\s\)]*",  # example.com without www
        r"https?://(www\.)?example\.org[^\s\)]*",  # example.org URLs
        r"https?://(www\.)?placeholder\.com[^\s\)]*",  # placeholder.com URLs
        r"https?://(www\.)?test\.com[^\s\)]*",  # test.com URLs
        r"https?://(www\.)?sample\.com[^\s\)]*",  # sample.com URLs
    ]
    
    for pattern in placeholder_url_patterns:
        # Remove the entire line if it contains a placeholder URL
        lines = cleaned.split('\n')
        filtered_lines = []
        for line in lines:
            if not re.search(pattern, line, flags=re.IGNORECASE):
                filtered_lines.append(line)
            else:
                logger.warning(f"Removed line with placeholder URL: {line[:100]}")
        cleaned = '\n'.join(filtered_lines)
        
        # Also remove the URL itself if it appears in the middle of a line
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    
    # Remove lines that only contain placeholder text like "Take a look at our photo gallery:" without real URLs
    # This catches cases where LLM generates example text from training data
    placeholder_text_patterns = [
        r"^Take a look at our photo gallery:\s*$",
        r"^Visit our photo gallery:\s*$",
        r"^Check out our photo gallery:\s*$",
        r"^See our photo gallery:\s*$",
        r"^View our photo gallery:\s*$",
        r"^Take a look at our photo gallery:\s*https?://example\.com",  # With example.com URL
    ]
    
    lines = cleaned.split('\n')
    filtered_lines = []
    for line in lines:
        is_placeholder = False
        for pattern in placeholder_text_patterns:
            if re.match(pattern, line, flags=re.IGNORECASE):
                is_placeholder = True
                logger.warning(f"Removed placeholder text line: {line}")
                break
        if not is_placeholder:
            filtered_lines.append(line)
    cleaned = '\n'.join(filtered_lines)
    
    # Remove extra whitespace
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    
    return cleaned


def preprocess_context_for_location_clarity(
    retrieved_contents: List["Document"]
) -> List["Document"]:
    """
    Preprocess context documents to clarify location information.
    Adds clarifying notes when "Azad Kashmir" appears in context to prevent LLM misinterpretation.
    
    CRITICAL: When context says "overlooking Azad Kashmir" or "Azad Kashmir View Point",
    the LLM might misinterpret this as "located in Azad Kashmir". This function adds
    clarifying notes to prevent this misinterpretation.
    
    Args:
        retrieved_contents: List of retrieved documents
    
    Returns:
        List of documents with clarifying notes added
    """
    from entities.document import Document
    import re
    
    processed_docs = []
    
    for doc in retrieved_contents:
        content = doc.page_content
        content_lower = content.lower()
        
        # Check if document mentions "Azad Kashmir" in a way that might be misinterpreted
        if "azad kashmir" in content_lower:
            # Check if it's in the correct context (overlooking, viewpoint, etc.)
            has_correct_context = any(phrase in content_lower for phrase in [
                "overlooking azad kashmir",
                "azad kashmir view",
                "azad kashmir view point",
                "viewpoints overlooking",
                "scenic viewpoints",
                "viewpoint near"
            ])
            
            # Check if it might be misinterpreted as location (located in, in azad kashmir, etc.)
            has_wrong_context = any(re.search(pattern, content_lower) for pattern in [
                r"located\s+in\s+azad\s+kashmir",
                r"\bin\s+azad\s+kashmir[^,.]",
                r"azad\s+kashmir,\s+pakistan",
                r"bhurban[^,]*,\s*azad\s+kashmir",
                r"swiss\s+cottages.*azad\s+kashmir"
            ])
            
            # If it has correct context (overlooking), add clarifying note
            if has_correct_context and not has_wrong_context:
                # Add clarifying note at the beginning of the document
                clarification = (
                    "[CLARIFICATION: When this document mentions 'Azad Kashmir' or 'overlooking Azad Kashmir', "
                    "it means you can SEE Azad Kashmir from viewpoints or locations. "
                    "Swiss Cottages is NOT located in Azad Kashmir. "
                    "Swiss Cottages is located in Murree Hills, Bhurban, Pakistan. "
                    "Azad Kashmir is a region that can be SEEN from viewpoints, but the cottages are NOT in Azad Kashmir.]\n\n"
                )
                content = clarification + content
                logger.info("Added location clarification to context document mentioning Azad Kashmir")
        
        # Create new document with processed content
        new_doc = Document(
            page_content=content,
            metadata=doc.metadata.copy() if hasattr(doc, 'metadata') else {}
        )
        processed_docs.append(new_doc)
    
    return processed_docs if processed_docs else retrieved_contents


def inject_essential_info(
    retrieved_contents: List["Document"],
    query: str,
    slots: Dict
) -> List["Document"]:
    """
    Inject essential information based on query type.
    - For cottage description queries: inject capacity information
    - For safety queries: prioritize safety documents (handled separately)
    - For availability queries: use availability handler (handled separately)
    
    Args:
        retrieved_contents: List of retrieved documents
        query: User query
        slots: Extracted slots from query
        
    Returns:
        List of documents with essential info injected
    """
    import re
    from bot.conversation.cottage_capacity import get_capacity_mapper
    from entities.document import Document
    
    query_lower = query.lower()
    enhanced_contents = retrieved_contents.copy()
    
    # For cottage description queries, inject capacity info
    cottage_match = re.search(r'cottage\s*(\d+)', query_lower)
    if cottage_match and any(phrase in query_lower for phrase in [
        'tell me about', 'what is', 'describe', 'about cottage', 'tell me'
    ]):
        cottage_num = cottage_match.group(1)
        try:
            capacity_mapper = get_capacity_mapper()
            capacity_info = capacity_mapper.get_capacity(cottage_num)
            
            if capacity_info:
                capacity_doc = Document(
                    page_content=f"CRITICAL CAPACITY INFORMATION FOR COTTAGE {cottage_num}:\n"
                               f"Base capacity: Up to {capacity_info['base_capacity']} guests\n"
                               f"Maximum capacity: Up to {capacity_info['max_capacity']} guests (with prior confirmation)\n"
                               f"Bedrooms: {capacity_info['bedrooms']}\n\n"
                               f"YOU MUST include this capacity information in your answer about Cottage {cottage_num}.",
                    metadata={"source": "capacity_injection", "cottage": cottage_num}
                )
                enhanced_contents.insert(0, capacity_doc)
                logger.info(f"Injected capacity info for Cottage {cottage_num}")
        except Exception as e:
            logger.warning(f"Failed to inject capacity info for Cottage {cottage_num}: {e}")
    
    return enhanced_contents


def should_filter_pricing(query: str) -> bool:
    """
    Check if pricing should be filtered from context - UNIVERSAL CHECK.
    
    Args:
        query: User query
        
    Returns:
        True if pricing should be filtered (query does NOT ask about pricing)
    """
    query_lower = query.lower()
    pricing_keywords = ["price", "pricing", "cost", "rate", "rates", "how much", "pkr", "per night", "weekday", "weekend", "total cost", "booking cost"]
    
    # If query does NOT ask about pricing, filter pricing from context
    asks_about_pricing = any(kw in query_lower for kw in pricing_keywords)
    
    return not asks_about_pricing  # Filter pricing for ALL non-pricing queries


def filter_pricing_from_context(documents: List["Document"], query: str) -> List["Document"]:
    """
    Filter out or deprioritize pricing-related documents if query doesn't ask about pricing.
    
    Args:
        documents: List of retrieved documents
        query: User query
        
    Returns:
        List of documents with pricing docs deprioritized (non-pricing docs first)
    """
    if not should_filter_pricing(query):
        return documents
    
    # Separate pricing vs non-pricing documents
    pricing_docs = []
    non_pricing_docs = []
    pricing_indicators = ["pricing", "price", "pkr", "cost", "rate", "per night", "weekday", "weekend", "total cost"]
    
    for doc in documents:
        content_lower = doc.page_content.lower()
        # Check if document is primarily about pricing
        # Keep availability handler docs even if they mention pricing
        is_availability_handler = doc.metadata.get("source") == "availability_handler"
        is_capacity_injection = doc.metadata.get("source") == "capacity_injection"
        is_pricing_doc = any(indicator in content_lower for indicator in pricing_indicators) and \
                        ("cottage" in content_lower or "accommodation" in content_lower or "stay" in content_lower) and \
                        not any(kw in content_lower for kw in ["available", "availability", "safety", "security", "guard", "gated"]) and \
                        not is_availability_handler and not is_capacity_injection
        
        if is_pricing_doc:
            pricing_docs.append(doc)  # Keep but deprioritize
        else:
            non_pricing_docs.append(doc)  # Keep with priority
    
    # Return non-pricing docs first, then pricing docs (deprioritized)
    return non_pricing_docs + pricing_docs if non_pricing_docs else documents


def prioritize_safety_documents(documents: List["Document"], query: str) -> List["Document"]:
    """
    Prioritize safety-related documents for safety queries.
    
    Args:
        documents: List of retrieved documents
        query: User query
        
    Returns:
        List of documents with safety docs first
    """
    query_lower = query.lower()
    safety_keywords = ["safe", "safety", "security", "secure", "guard", "guards", "gated", "emergency"]
    
    if not any(kw in query_lower for kw in safety_keywords):
        return documents
    
    safety_docs = []
    other_docs = []
    safety_indicators = ["guard", "guards", "security", "gated community", "secure", "safety", "emergency"]
    
    for doc in documents:
        content_lower = doc.page_content.lower()
        if any(indicator in content_lower for indicator in safety_indicators):
            safety_docs.append(doc)
        else:
            other_docs.append(doc)
    
    return safety_docs + other_docs if safety_docs else documents


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
    
    # CRITICAL: First check if query is about completely unrelated topics (world knowledge, countries, etc.)
    # These should NEVER be answered using Swiss Cottages context
    unrelated_topics = {
        "china": ["china", "chinese", "beijing", "shanghai", "great wall"],
        "usa": ["usa", "united states", "america", "american", "us president", "president of usa", "president of united states"],
        "president": ["president", "presidential", "presidency"],
        "country": ["country", "countries", "nation", "national"],
        "world": ["world", "global", "international"],
    }
    
    # Check if query is about unrelated topics
    query_is_unrelated = False
    unrelated_topic = None
    for topic, keywords in unrelated_topics.items():
        if any(keyword in query_lower for keyword in keywords):
            # Check if documents are NOT about Swiss Cottages
            swiss_cottages_indicators = [
                "swiss cottages", "bhurban", "murree", "cottage 7", "cottage 9", "cottage 11",
                "cottage7", "cottage9", "cottage11", "pakistan", "pakistani"
            ]
            has_swiss_cottages_content = any(indicator in documents_text for indicator in swiss_cottages_indicators)
            
            if not has_swiss_cottages_content:
                query_is_unrelated = True
                unrelated_topic = topic
                break
    
    if query_is_unrelated:
        if unrelated_topic == "china":
            return False, "Your question is about China, but I only have information about Swiss Cottages Bhurban in Pakistan. I cannot answer questions about other countries or general world knowledge."
        elif unrelated_topic in ["usa", "president"]:
            return False, "Your question is about the USA or world leaders, but I only have information about Swiss Cottages Bhurban in Pakistan. I cannot answer questions about other countries, world leaders, or general world knowledge."
        else:
            return False, "Your question is about a topic outside my knowledge base. I only have information about Swiss Cottages Bhurban in Pakistan. I cannot answer questions about other topics or general world knowledge."
    
    # CRITICAL: Ensure documents are actually about Swiss Cottages
    # If documents don't mention Swiss Cottages, Bhurban, or related terms, they're not relevant
    swiss_cottages_indicators = [
        "swiss cottages", "bhurban", "murree", "cottage 7", "cottage 9", "cottage 11",
        "cottage7", "cottage9", "cottage11", "pakistan", "pakistani", "murree hills"
    ]
    has_swiss_cottages_content = any(indicator in documents_text for indicator in swiss_cottages_indicators)
    
    # Exception: For safety/security queries, allow documents with safety keywords even if they don't explicitly mention Swiss Cottages
    # (since they're from the knowledge base, they're implicitly about Swiss Cottages)
    # Safety query detection - include "is it safe" pattern explicitly
    is_safety_query = any(word in query_lower for word in ["safe", "safety", "security", "secure", "guard", "guards", "gated", "emergency"]) or "is it safe" in query_lower
    safety_keywords = ["guard", "guards", "security", "gated community", "secure", "safety", "emergency", "safety measures", "security measures"]
    has_safety_content = any(keyword in documents_text for keyword in safety_keywords)
    
    # Exception: For facilities queries, allow documents with facilities keywords even if they mention Pearl Continental
    # (since they're from the knowledge base, they're implicitly about Swiss Cottages)
    is_facilities_query = any(phrase in query_lower for phrase in [
        "facility", "facilities", "amenity", "amenities", "feature", "features",
        "kitchen", "terrace", "balcony", "socializing", "relaxation", "what is available",
        "what facilities", "facilities available", "facilities are"
    ])
    facilities_keywords = ["kitchen", "facility", "facilities", "amenity", "amenities", "terrace", "balcony", "lounge", "parking", "wifi", "tv", "netflix", "heating", "bbq", "socializing", "relaxation"]
    has_facilities_content = any(keyword in documents_text.lower() for keyword in facilities_keywords)
    
    # CRITICAL: Reject documents that are primarily about Pearl Continental or PC Bhurban
    # BUT be very lenient - only reject if clearly NOT about Swiss Cottages
    # IMPORTANT: If documents are about Swiss Cottages (have Swiss Cottages indicators), allow them
    # even if they mention Pearl Continental (PC Bhurban is nearby, so it's normal to mention it)
    
    # Check for Pearl Continental mentions
    pearl_continental_indicators = ["pearl continental", "pc bhurban", "pearl continental bhurban"]
    pearl_mentions = sum(documents_text.lower().count(indicator) for indicator in pearl_continental_indicators)
    
    # Exception: For date/booking queries, allow documents even if they don't explicitly mention Swiss Cottages
    # (since they're from the knowledge base and user is providing dates, they're implicitly about Swiss Cottages)
    is_date_query = any(word in query_lower for word in [
        "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "january", "february",
        "from", "to", "stay", "staying", "booking", "book", "dates", "check-in", "check-out"
    ]) and any(word in query_lower for word in ["march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "january", "february", "stay", "staying", "nights"])
    
    # CRITICAL: Check for safety/facilities queries FIRST before rejecting documents
    # These queries should be allowed even without explicit Swiss Cottages mentions
    if not has_swiss_cottages_content and len(documents) > 0:
        # If this is a safety query, allow documents even if they don't have explicit safety keywords
        # (since user is asking about safety, any documents retrieved are likely relevant)
        if is_safety_query:
            if has_safety_content:
                logger.info(f"Allowing safety documents with safety keywords for safety query")
            else:
                # Even without explicit safety keywords, if user asks about safety and we have documents, allow them
                # The LLM will handle the response appropriately
                logger.info(f"Allowing documents for safety query even without explicit safety keywords (user asked about safety)")
            # Return True early - safety documents are valid even without explicit Swiss Cottages mentions
            return True, ""
        # If this is a facilities query and documents contain facilities keywords, allow them
        elif is_facilities_query and has_facilities_content:
            logger.info(f"Allowing facilities documents without explicit Swiss Cottages indicators for facilities query")
            # Return True early - facilities documents are valid even without explicit Swiss Cottages mentions
            return True, ""
        # If this is a date/booking query, allow documents (user is providing dates for booking/pricing)
        elif is_date_query:
            logger.info(f"Allowing documents for date/booking query (user provided dates: {query_lower[:100]})")
            # Return True early - date/booking documents are valid
            return True, ""
    
    # ONLY reject if:
    # 1. Documents mention Pearl Continental AND
    # 2. Documents do NOT have Swiss Cottages content (no Swiss Cottages indicators at all)
    # EXCEPTION: If it's a facilities query and documents have facilities content, allow them
    # (documents in knowledge base about facilities are implicitly about Swiss Cottages)
    if pearl_mentions > 0 and not has_swiss_cottages_content:
        # Allow if it's a facilities query with facilities content (implicitly about Swiss Cottages)
        if is_facilities_query and has_facilities_content:
            logger.info(f"Allowing facilities documents with Pearl Continental mention for facilities query (implicitly about Swiss Cottages)")
        else:
            logger.warning(f"Rejecting documents - Pearl Continental mentioned but no Swiss Cottages content (Pearl mentions: {pearl_mentions})")
            return False, "The retrieved documents are about Pearl Continental Bhurban, but I only have information about Swiss Cottages Bhurban. Please ask about Swiss Cottages Bhurban facilities and services."
    
    if not has_swiss_cottages_content and len(documents) > 0:
        # Documents exist but don't mention Swiss Cottages - this is a mismatch
        # (Safety/facilities/date queries already handled above)
        return False, "The retrieved documents don't contain information about Swiss Cottages Bhurban. I only have information about Swiss Cottages Bhurban in Pakistan and cannot answer questions about other topics."
    
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
    """
    Re-order documents to prioritize those mentioning the specific cottage number asked about.
    Also filters out Cottage 7 from general queries (unless specifically asked).
    When a specific cottage is mentioned, FILTER OUT documents about other cottages.
    """
    query_lower = query.lower()
    
    # Check if Cottage 7 is specifically mentioned or if it's a 2-bedroom query
    cottage_7_allowed = (
        "cottage 7" in query_lower or 
        "cottage7" in query_lower or
        "2 bedroom" in query_lower or 
        "two bedroom" in query_lower
    )
    
    # Extract cottage numbers mentioned in query
    cottage_numbers = []
    for num in ["7", "9", "11"]:
        if f"cottage {num}" in query_lower or f"cottage{num}" in query_lower:
            cottage_numbers.append(num)
    
    # If specific cottages mentioned, prioritize those and FILTER OUT others
    if cottage_numbers:
        prioritized = []
        filtered_out = []
        
        for doc in documents:
            doc_text_lower = doc.page_content.lower()
            # Check if document mentions the specific cottage(s) asked about
            mentions_specific_cottage = any(
                f"cottage {num}" in doc_text_lower or f"cottage{num}" in doc_text_lower
                for num in cottage_numbers
            )
            
            # Check if document mentions OTHER cottages (not the one asked about)
            mentions_other_cottage = False
            for num in ["7", "9", "11"]:
                if num not in cottage_numbers:  # This is a different cottage
                    if f"cottage {num}" in doc_text_lower or f"cottage{num}" in doc_text_lower:
                        mentions_other_cottage = True
                        break
            
            if mentions_specific_cottage:
                prioritized.append(doc)
            elif mentions_other_cottage:
                # Filter out documents about other cottages when specific cottage is asked
                filtered_out.append(doc)
                logger.debug(f"Filtered out document mentioning different cottage (query: {cottage_numbers}, doc mentions other cottage)")
            else:
                # Document doesn't mention any specific cottage - keep it (might be general info)
                prioritized.append(doc)
        
        logger.info(f"Prioritized {len(prioritized)} documents for cottage(s) {cottage_numbers}, filtered out {len(filtered_out)} documents about other cottages")
        return prioritized
    
    # For general queries (no specific cottage mentioned):
    # Filter out Cottage 7 documents unless it's a 2-bedroom query
    if not cottage_7_allowed:
        filtered_docs = []
        filtered_count = 0
        for doc in documents:
            doc_text_lower = doc.page_content.lower()
            # Check if document mentions ONLY Cottage 7 (not 9 or 11)
            mentions_cottage_7 = (
                "cottage 7" in doc_text_lower or 
                "cottage7" in doc_text_lower
            )
            mentions_cottage_9_or_11 = (
                "cottage 9" in doc_text_lower or 
                "cottage9" in doc_text_lower or
                "cottage 11" in doc_text_lower or 
                "cottage11" in doc_text_lower
            )
            
            # Include document if:
            # - It doesn't mention Cottage 7, OR
            # - It mentions Cottage 7 BUT also mentions 9 or 11 (general info)
            if not mentions_cottage_7 or mentions_cottage_9_or_11:
                filtered_docs.append(doc)
            else:
                # Document mentions ONLY Cottage 7 - exclude it from general queries
                filtered_count += 1
                logger.info(f"Filtered out Cottage 7-only document from general query: {doc.metadata.get('source', 'unknown')}")
        
        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} Cottage 7-only document(s) from general query. Remaining: {len(filtered_docs)} documents")
        
        return filtered_docs
    
    # Cottage 7 is allowed (2-bedroom query or specifically asked)
    return documents


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
        # Detect if this is a widget-triggered query
        widget_query_patterns = [
            "I want to check availability and book a cottage for my dates",
            "Show me images and photos of the cottages",
            "What are the prices and cottage options? Compare weekday and weekend rates",
            "Tell me about the location and nearby attractions near Swiss Cottages Bhurban"
        ]
        is_widget_query = any(pattern.lower() in request.question.lower() for pattern in widget_query_patterns)
        
        # Get slot manager and context tracker early for image detection
        slot_manager = session_manager.get_or_create_slot_manager(request.session_id, llm)
        context_tracker = session_manager.get_or_create_context_tracker(request.session_id)
        
        # Pre-processing: Check for "yes" responses to image offers
        query_lower = request.question.lower()
        is_yes_response = any(word in query_lower for word in ["yes", "yeah", "yep", "sure", "ok", "okay", "show me", "show images", "show photos"])
        
        # Check if previous message offered images (stored in session)
        if is_yes_response:
            session_data = session_manager.get_session_data(request.session_id)
            if session_data and session_data.get("image_offer_cottage"):
                cottage_num = session_data.get("image_offer_cottage")
                # User said yes to image offer - show images
                is_image_request = True
                cottage_numbers = [cottage_num]
                # Clear the offer from session
                session_data.pop("image_offer_cottage", None)
            else:
                is_image_request, cottage_numbers = detect_image_request(request.question, slot_manager, context_tracker)
        else:
            is_image_request, cottage_numbers = detect_image_request(request.question, slot_manager, context_tracker)
        
        # Pre-processing: Handle explicit image requests early
        if is_image_request and cottage_numbers:
            logger.info(f"Detected explicit image request for cottages: {cottage_numbers}")
            
            # Detect if user is asking for a specific image type
            image_type = detect_image_type_request(request.question)
            logger.info(f"Detected image type request: {image_type}")
            
            # Get images directly without going through full RAG
            root_folder = get_root_folder()
            dropbox_config = get_dropbox_config()
            use_dropbox = dropbox_config.get("use_dropbox", False)
            logger.info(f"Dropbox config - use_dropbox: {use_dropbox}, available cottages: {list(dropbox_config.get('cottage_image_urls', {}).keys())}")
            
            # Group images by cottage
            cottage_images_dict = {}
            no_images_found = []
            
            for cottage_num in cottage_numbers:
                cottage_images = []
                
                if use_dropbox:
                    logger.info(f"Attempting to get Dropbox URLs for cottage {cottage_num}")
                    dropbox_urls = get_dropbox_image_urls(cottage_num, max_images=6)
                    logger.info(f"Got {len(dropbox_urls)} Dropbox URLs for cottage {cottage_num}")
                    if dropbox_urls:
                        # Note: Dropbox URLs don't support type filtering yet
                        cottage_images.extend(dropbox_urls)
                        logger.info(f"Using {len(dropbox_urls)} Dropbox URLs for cottage {cottage_num}")
                    else:
                        logger.warning(f"No Dropbox URLs found for cottage {cottage_num}, falling back to local files")
                        # Fallback to local files with type filtering
                        images = get_cottage_images_by_type(cottage_num, root_folder, image_type=image_type, max_images=6)
                        for img_path in images:
                            rel_path = img_path.relative_to(root_folder)
                            from urllib.parse import quote
                            encoded_path = str(rel_path).replace('\\', '/')
                            url_path = '/'.join(quote(part, safe='') for part in encoded_path.split('/'))
                            image_url = f"/images/{url_path}"
                            cottage_images.append(image_url)
                else:
                    logger.info(f"Dropbox not enabled, using local files for cottage {cottage_num}")
                    images = get_cottage_images_by_type(cottage_num, root_folder, image_type=image_type, max_images=6)
                    for img_path in images:
                        rel_path = img_path.relative_to(root_folder)
                        from urllib.parse import quote
                        encoded_path = str(rel_path).replace('\\', '/')
                        url_path = '/'.join(quote(part, safe='') for part in encoded_path.split('/'))
                        image_url = f"/images/{url_path}"
                        cottage_images.append(image_url)
                
                if cottage_images:
                    cottage_images_dict[cottage_num] = cottage_images
                else:
                    no_images_found.append(cottage_num)
            
            if cottage_images_dict:
                # Generate a brief response
                if len(cottage_numbers) == 1:
                    if image_type:
                        answer = f"Here are {image_type} images of Cottage {cottage_numbers[0]}:"
                    else:
                        answer = f"Here are images of Cottage {cottage_numbers[0]}:"
                else:
                    if image_type:
                        answer = f"Here are {image_type} images of the cottages:"
                    else:
                        answer = f"Here are images of the cottages:"
                
                total_images = sum(len(imgs) for imgs in cottage_images_dict.values())
                logger.info(f"Returning {total_images} image URLs grouped by cottage: {list(cottage_images_dict.keys())}")
                
                # Return as dictionary grouped by cottage
                return ChatResponse(
                    answer=answer,
                    sources=[],
                    intent="images",
                    session_id=request.session_id,
                    cottage_images=cottage_images_dict,  # Now a dict: {"7": [urls], "9": [urls], "11": [urls]}
                )
            else:
                # No images found for the requested type
                if image_type:
                    cottage_text = f"Cottage {', '.join(no_images_found)}" if no_images_found else "the requested cottage"
                    answer = (
                        f"I'm sorry, I don't have {image_type} images available for {cottage_text} at the moment.\n\n"
                        f"You can ask for general images of {cottage_text} to see what's available."
                    )
                else:
                    # No images found at all
                    cottage_text = f"Cottage {', '.join(no_images_found)}" if no_images_found else "the requested cottages"
                    answer = f"I'm sorry, I couldn't find images for {cottage_text}. Please contact us for more information."
                
                return ChatResponse(
                    answer=answer,
                    sources=[],
                    intent="images",
                    session_id=request.session_id,
                )
        
        # Pre-processing: Check for manager contact queries
        manager_contact_patterns = [
            "how can i contact the manager", "contact the manager", "contact manager",
            "manager contact", "manager's contact", "manager contact details",
            "manager phone", "manager number", "cottage manager", "who is the manager",
            "manager information", "reach the manager", "speak to manager"
        ]
        if any(pattern in query_lower for pattern in manager_contact_patterns):
            answer = (
                "**Cottage Manager Contact Information** 📞\n\n"
                "**Abdullah** is the cottage manager at Swiss Cottages Bhurban.\n\n"
                "**Contact Details:**\n"
                "- **Phone:** +92 300 1218563\n"
                "- **Alternate Phone (Urgent):** +92 327 8837088\n"
                "- **Contact Form:** https://swisscottagesbhurban.com/contact-us/\n\n"
                "Abdullah can help you with:\n"
                "- Bookings and availability\n"
                "- Pricing and special requests\n"
                "- General assistance before or during your stay\n\n"
                "Feel free to reach out for personalized assistance! 🏡"
            )
            return ChatResponse(
                answer=answer,
                sources=[],
                intent="contact_manager",
                session_id=request.session_id,
            )
        
        # Pre-processing: Check for single room/person queries
        single_room_patterns = [
            "single room", "one room", "individual room", "separate room",
            "single person", "one person", "individual person", "solo",
            "just me", "only me", "by myself", "alone"
        ]
        if any(pattern in query_lower for pattern in single_room_patterns):
            answer = (
                "Swiss Cottages Bhurban rents **entire cottages**, not individual rooms. 🏡\n\n"
                "Each cottage is a fully private, self-contained unit that includes:\n"
                "- Multiple bedrooms (2-3 bedrooms depending on cottage)\n"
                "- Living areas\n"
                "- Kitchen\n"
                "- Terrace/balcony\n"
                "- Parking\n\n"
                "**Important:** Even if you're traveling alone or as a single person, you would rent the entire cottage. "
                "The base pricing is for up to 6 guests, so a single person would still rent the full cottage.\n\n"
                "Would you like to know more about:\n"
                "- Pricing for a single person stay\n"
                "- Which cottage would be best for you\n"
                "- Availability and booking information"
            )
            return ChatResponse(
                answer=answer,
                sources=[],
                intent="faq_question",
                session_id=request.session_id,
            )
        
        # Pre-processing: Check for cottage listing queries
        # IMPORTANT: This must run BEFORE general "tell me about" handler
        
        # Check for "how many cottages" or "total cottages" queries FIRST
        total_cottages_patterns = [
            "how many cottages", "total cottages", "number of cottages",
            "how many cottages do you have", "total number of cottages"
        ]
        
        if any(pattern in query_lower for pattern in total_cottages_patterns):
            registry = get_cottage_registry()
            answer = registry.format_total_cottages_response()
            return ChatResponse(
                answer=answer,
                sources=[],
                intent="rooms",  # Map cottage_listing to rooms intent
                session_id=request.session_id,
            )
        
        # Check for capacity queries BEFORE cottage listing handler
        # IMPORTANT: Capacity queries should NOT trigger static cottage listing - they need LLM reasoning
        capacity_handler = get_capacity_handler()
        is_capacity_query = capacity_handler.is_capacity_query(request.question)
        
        # Flexible cottage listing detection using keyword combination
        # Check if query contains "cottages" + listing keywords
        # IMPORTANT: Exclude pricing queries, capacity queries, AND facilities queries - they should NOT trigger cottage listing
        is_pricing_query = any(phrase in query_lower for phrase in [
            "pricing", "price", "prices", "cost", "rate", "rates", "how much"
        ])
        
        # Check if this is a facilities query - these should go to RAG, not static listing
        is_facilities_query = any(phrase in query_lower for phrase in [
            "facility", "facilities", "amenity", "amenities", "feature", "features",
            "kitchen", "terrace", "balcony", "socializing", "relaxation", "what is available",
            "chef", "service", "services", "cooking", "food", "meal", "bbq", "grill",
            "wifi", "internet", "tv", "netflix", "parking", "heating", "lounge", "bbq facilities"
        ])
        
        has_cottages_keyword = "cottage" in query_lower or "cottages" in query_lower
        listing_keywords = [
            "you have", "do you have", "available", "offer", "list", 
            "which", "what", "show me", "tell me about the cottages"
        ]
        has_listing_intent = any(keyword in query_lower for keyword in listing_keywords)
        
        # Also check for explicit listing patterns
        explicit_listing_patterns = [
            "which cottages", "what cottages", "list cottages", 
            "cottages do you have", "cottages you have",
            "available cottages", "cottages available",
            "what cottages do you", "which cottages do you"
        ]
        has_explicit_pattern = any(pattern in query_lower for pattern in explicit_listing_patterns)
        
        # If query is about listing cottages (not general info about swiss cottages)
        # AND it's NOT a pricing query AND it's NOT a capacity query AND it's NOT a facilities query
        if has_cottages_keyword and (has_listing_intent or has_explicit_pattern) and not is_pricing_query and not is_capacity_query and not is_facilities_query:
            # Additional check: exclude general "tell me about swiss cottages" queries
            # These should go to RAG for general information
            is_general_info_query = (
                "tell me about swiss cottages" in query_lower or
                "tell me about the swiss cottages" in query_lower or
                ("tell me about" in query_lower and "cottages" in query_lower and 
                 "you have" not in query_lower and "available" not in query_lower and
                 "which" not in query_lower and "what" not in query_lower)
            )
            
            if not is_general_info_query:
                registry = get_cottage_registry()
                # This will automatically filter to show only 9 and 11 (not 7)
                answer = registry.format_cottage_list(query=request.question, show_total=False)
                answer += (
                    "\n\nAll cottages include:\n"
                    "- Fully equipped kitchen\n"
                    "- Living lounge\n"
                    "- Bedrooms and bathrooms\n"
                    "- Outdoor terrace/balcony\n"
                    "- Wi-Fi, smart TV with Netflix\n"
                    "- Heating system\n"
                    "- Secure parking\n\n"
                    "Would you like to know more about:\n"
                    "- Which cottage is best for your group size\n"
                    "- Availability and booking information"
                )
                return ChatResponse(
                    answer=answer,
                    sources=[],
                    intent="rooms",  # Map cottage_listing to rooms intent
                    session_id=request.session_id,
                )
        
        # Handle 2-bedroom queries (will show Cottage 7)
        if "2 bedroom" in query_lower or "two bedroom" in query_lower:
            registry = get_cottage_registry()
            cottages = registry.list_cottages_by_filter(query=request.question)
            if cottages:
                answer = f"🏡 **2-Bedroom Cottages:**\n\n"
                for cottage in cottages:
                    answer += f"**Cottage {cottage.number}** - {cottage.description}\n"
                    answer += f"- Base capacity: Up to {cottage.base_capacity} guests\n"
                    answer += f"- Maximum capacity: {cottage.max_capacity} guests\n\n"
                answer += "Would you like to know about availability or booking?"
                return ChatResponse(
                    answer=answer,
                    sources=[],
                    intent="rooms",  # Map cottage_listing to rooms intent
                    session_id=request.session_id,
                )
        
        # Handle 3-bedroom queries (will show Cottages 9 and 11)
        if "3 bedroom" in query_lower or "three bedroom" in query_lower:
            registry = get_cottage_registry()
            cottages = registry.list_cottages_by_filter(query=request.question)
            if cottages:
                answer = f"🏡 **3-Bedroom Cottages:**\n\n"
                for cottage in cottages:
                    answer += f"**Cottage {cottage.number}** - {cottage.description}\n"
                    answer += f"- Base capacity: Up to {cottage.base_capacity} guests\n"
                    answer += f"- Maximum capacity: {cottage.max_capacity} guests\n\n"
                answer += "Would you like to know about availability or booking?"
                return ChatResponse(
                    answer=answer,
                    sources=[],
                    intent="rooms",  # Map cottage_listing to rooms intent
                    session_id=request.session_id,
                )
        
        # Get or create chat history (same as Streamlit - total_length=2)
        chat_history = session_manager.get_or_create_session(request.session_id, total_length=2)
        
        # Get synthesis strategy
        strategy_name = request.synthesis_strategy or "create-and-refine"
        ctx_synthesis_strategy = get_ctx_synthesis_strategy(strategy_name)
        
        # Classify intent
        intent = intent_router.classify(request.question, chat_history)
        intent_type = intent.value if hasattr(intent, 'value') else str(intent)
        
        # Classify query complexity and select appropriate model
        complexity_classifier = get_complexity_classifier()
        query_complexity = complexity_classifier.classify_complexity(request.question, intent)
        
        # Select model based on complexity
        use_simple_prompt = (query_complexity == "simple")
        if query_complexity == "simple":
            llm = get_fast_llm_client()
            fast_model_name = os.getenv("FAST_MODEL_NAME", "llama-3.1-8b-instant")
            logger.info(f"Using fast model ({fast_model_name}) for simple query")
        else:
            llm = get_reasoning_llm_client()
            reasoning_model_name = os.getenv("REASONING_MODEL_NAME", "llama-3.1-70b-versatile")
            logger.info(f"Using reasoning model ({reasoning_model_name}) for complex query")
        
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
            # Generate follow-up actions for help
            # Convert chat_history to list format for recommendations
            chat_history_list = list(chat_history) if chat_history else []
            follow_up_actions = generate_follow_up_actions(
                intent,
                slot_manager.get_slots(),
                request.question,
                context_tracker=context_tracker,
                chat_history=chat_history_list,
                llm_client=llm,
                is_widget_query=is_widget_query
            )
            return ChatResponse(
                answer=answer,
                sources=[],
                intent=intent_type,
                session_id=request.session_id,
                follow_up_actions=follow_up_actions,
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
        
        # Track intent in context BEFORE checking for slot responses
        # (slot_manager and context_tracker already created above)
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
        
        # Check for cottage availability queries before slot extraction
        query_lower = request.question.lower()
        availability_patterns = [
            r"is\s+cottage\s+(\d+)\s+available",
            r"cottage\s+(\d+)\s+available",
            r"is\s+cottage\s+(\d+)\s+also\s+available",
        ]
        cottage_availability_match = None
        for pattern in availability_patterns:
            match = re.search(pattern, query_lower)
            if match:
                cottage_availability_match = match.group(1)
                logger.info(f"Detected cottage availability query for Cottage {cottage_availability_match}")
                break
        
        # Extract slots from query
        extracted_slots = slot_manager.extract_slots(request.question, intent)
        
        # Improve context retention: Check chat history for previous slot values
        # This helps when user says "tell me the pricing" after "we are a group of 5 can we stay 4 nights"
        if chat_history and len(chat_history) > 0:
            # Look through recent messages for slot information that might not be in current query
            date_extractor = get_date_extractor()
            for message in reversed(list(chat_history)[-3:]):  # Check last 3 messages
                if isinstance(message, str) and "question:" in message:
                    # Extract question from chat history format: "question: ..., answer: ..."
                    parts = message.split("question:", 1)
                    if len(parts) > 1:
                        full_message = parts[1]
                        # Split into question and answer
                        if "answer:" in full_message:
                            prev_query = full_message.split("answer:")[0].strip()
                            prev_answer = full_message.split("answer:")[1].strip() if "answer:" in full_message else ""
                        else:
                            prev_query = full_message.strip()
                            prev_answer = ""
                        
                        if prev_query and prev_query != request.question:
                            # Try to extract slots from previous questions
                            prev_slots = slot_manager.extract_slots(prev_query, intent)
                            # Merge previous slots that aren't in current extraction
                            for key, value in prev_slots.items():
                                if key not in extracted_slots and value is not None:
                                    # Only add if slot is not already set in slot_manager
                                    if key not in slot_manager.slots or slot_manager.slots[key] is None:
                                        extracted_slots[key] = value
                                        logger.info(f"Retrieved {key}={value} from chat history question: '{prev_query[:50]}...'")
                            
                            # CRITICAL: Also extract dates from previous QUESTIONS (not just answers)
                            # This handles cases like "we are planning from 13 feb to 19 feb"
                            if "dates" not in extracted_slots:
                                date_range = date_extractor.extract_date_range(prev_query)
                                if date_range:
                                    extracted_slots["dates"] = date_range
                                    logger.info(f"✅ Extracted dates from chat history question: {date_range.get('start_date')} to {date_range.get('end_date')}, {date_range.get('nights')} nights")
                                    logger.info(f"   Source text: '{prev_query[:100]}...'")
                        
                        # CRITICAL: Also extract dates from previous ANSWERS (bot responses)
                        # This handles cases where bot mentioned dates like "February 11, 2026, to February 15, 2026"
                        if prev_answer and "dates" not in extracted_slots:
                            # Try to extract dates from the answer text
                            date_range = date_extractor.extract_date_range(prev_answer)
                            if date_range:
                                extracted_slots["dates"] = date_range
                                logger.info(f"✅ Extracted dates from chat history answer: {date_range.get('start_date')} to {date_range.get('end_date')}, {date_range.get('nights')} nights")
                                logger.info(f"   Source text: '{prev_answer[:100]}...'")
        
        slot_manager.update_slots(extracted_slots)
        
        # Update context_tracker.current_cottage if a cottage was extracted
        # But only for queries that should use it (prevents contamination for general info queries)
        current_cottage = slot_manager.get_current_cottage()
        if current_cottage:
            # Only set current_cottage if query should use it (prevents contamination)
            if slot_manager.should_use_current_cottage(request.question, intent):
                context_tracker.set_current_cottage(current_cottage)
            else:
                # Clear current_cottage for general info queries
                logger.debug(f"Clearing current_cottage for general info query: {request.question[:50]}...")
                context_tracker.set_current_cottage(None)
                # Also clear cottage_id slot for general info queries
                if intent in [IntentType.LOCATION, IntentType.FACILITIES, IntentType.FAQ_QUESTION]:
                    if "cottage_id" in slot_manager.slots:
                        slot_manager.slots["cottage_id"] = None
                        logger.debug(f"Cleared cottage_id slot for {intent.value} intent (general info query)")
        elif intent in [IntentType.LOCATION, IntentType.FACILITIES, IntentType.FAQ_QUESTION]:
            # For general info queries, ensure cottage_id is cleared
            if "cottage_id" in slot_manager.slots and slot_manager.slots["cottage_id"]:
                logger.debug(f"Clearing cottage_id for {intent.value} intent (general info query)")
                slot_manager.slots["cottage_id"] = None
        
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
        
        # Check if this is a reasoning query that requires structured processing
        # Capacity queries are detected by capacity_handler, not by intent type
        reasoning_intents = [IntentType.PRICING, IntentType.AVAILABILITY, IntentType.BOOKING]
        is_reasoning_query = intent in reasoning_intents
        
        # Also check if it's a capacity query (can be classified as FAQ_QUESTION or ROOMS)
        capacity_handler = get_capacity_handler()
        is_capacity_query = capacity_handler.is_capacity_query(request.question)
        if is_capacity_query:
            is_reasoning_query = True
        
        # For reasoning queries, validate slots before proceeding
        # Note: Capacity queries can work with partial info, so we skip strict validation for them
        # Note: Pricing queries are handled by pricing_handler which can default guests to 6, so skip strict validation
        is_pricing_query_check = intent == IntentType.PRICING and get_pricing_handler().is_pricing_query(request.question)
        
        # Check if this query needs slot extraction (specific calculation vs general info)
        needs_slots = slot_manager.should_extract_slots(intent, request.question)
        
        # For booking/availability queries, provide general booking info first, then ask for details
        # Skip slot checking for general booking queries (user asking "how to book" or "check availability")
        query_lower_booking = request.question.lower()
        is_general_booking_query = (
            intent in [IntentType.BOOKING, IntentType.AVAILABILITY] and
            any(phrase in query_lower_booking for phrase in [
                "i want to check", "i want to book", "check availability", "book a cottage",
                "how to book", "how can i book", "tell me about booking", "tell me about availability",
                "want to check", "want to book", "check availability and book", "availability and book",
                "for my dates"  # This is a general query asking about booking process
            ])
        )
        
        if is_reasoning_query and not is_capacity_query and not is_pricing_query_check and needs_slots and not is_general_booking_query:
            validation_result = slot_manager.validate_slots_for_intent(intent)
            
            if not validation_result["valid"]:
                # Missing required slots - ask user before proceeding
                missing_slots = validation_result["missing_slots"]
                errors = validation_result["errors"]
                
                logger.info(f"Missing required slots for {intent.value}: {missing_slots}")
                
                # Generate follow-up question for missing slots
                missing_slot = slot_manager.get_most_important_missing_slot(intent)
                if missing_slot:
                    try:
                        slot_prompt = generate_slot_question_prompt(
                            intent.value if hasattr(intent, 'value') else str(intent),
                            missing_slot,
                            slot_manager.get_slots()
                        )
                        follow_up = llm.generate_answer(slot_prompt, max_new_tokens=64).strip()
                        follow_up = follow_up.strip('"').strip("'").strip()
                        if follow_up and len(follow_up) > 10:
                            answer_text = follow_up
                        else:
                            # Fallback to simple question
                            slot_questions = {
                                "guests": "How many guests will be staying?",
                                "dates": "What dates are you planning to visit?",
                                "cottage_id": "Do you have a preference for which cottage?",
                                "family": "Will this be for a family or friends group?",
                                "season": "Are you planning to visit on weekdays or weekends?",
                            }
                            answer_text = slot_questions.get(missing_slot, f"Please provide {missing_slot}.")
                    except Exception as e:
                        logger.warning(f"Failed to generate slot question: {e}")
                        slot_questions = {
                            "guests": "How many guests will be staying?",
                            "dates": "What dates are you planning to visit?",
                            "cottage_id": "Do you have a preference for which cottage?",
                            "family": "Will this be for a family or friends group?",
                            "season": "Are you planning to visit on weekdays or weekends?",
                        }
                        answer_text = slot_questions.get(missing_slot, f"Please provide {missing_slot}.")
                    
                    if errors:
                        answer_text += f"\n\nNote: {errors[0]}"
                    
                    # Update chat history
                    chat_history.append(f"question: {request.question}, answer: {answer_text}")
                    
                    return ChatResponse(
                        answer=answer_text,
                        sources=[],
                        intent=intent.value if hasattr(intent, 'value') else str(intent),
                        session_id=request.session_id,
                    )
        
        # FAQ_QUESTION, UNKNOWN, REFINEMENT, or new manager intents - proceed with RAG
        manager_intents = [IntentType.PRICING, IntentType.ROOMS, IntentType.SAFETY, 
                          IntentType.BOOKING, IntentType.AVAILABILITY, IntentType.FACILITIES, IntentType.LOCATION]
        if intent in [IntentType.FAQ_QUESTION, IntentType.UNKNOWN, IntentType.REFINEMENT] + manager_intents:
            # Check for image requests (use session context)
            is_image_request, cottage_numbers = detect_image_request(request.question, slot_manager, context_tracker)
            
            # Check if this is a direct booking request
            is_booking_request = is_direct_booking_request(request.question)
            
            # Refine question (same as Streamlit - uses bot code directly)
            max_new_tokens = request.max_new_tokens or 128
            refined_question = refine_question(
                llm, request.question, chat_history=chat_history, max_new_tokens=max_new_tokens
            )
            logger.info(f"Original query: {request.question}")
            logger.info(f"Refined query: {refined_question}")
            
            # Fallback: If refined question is empty or just whitespace, use original question
            if not refined_question or not refined_question.strip():
                logger.warning(f"Refined question is empty, using original question: {request.question}")
                refined_question = request.question
            
            # Post-process refined question: If it still has pronouns and we have current_cottage, expand them
            current_cottage = None
            if slot_manager:
                current_cottage = slot_manager.get_current_cottage()
            if not current_cottage and context_tracker:
                current_cottage = context_tracker.get_current_cottage()
            
            if current_cottage:
                # Check if refined question still has pronouns that need expansion
                refined_lower = refined_question.lower()
                has_pronouns = any(phrase in refined_lower for phrase in ["this cottage", "that cottage", "the cottage", "it", "this one", "that one"])
                has_cottage_number = any(f"cottage {num}" in refined_lower or f"cottage{num}" in refined_lower for num in ["7", "9", "11"])
                
                if has_pronouns and not has_cottage_number:
                    # Manually expand pronouns to cottage number
                    refined_question = refined_question.replace("this cottage", f"cottage {current_cottage}")
                    refined_question = refined_question.replace("that cottage", f"cottage {current_cottage}")
                    refined_question = refined_question.replace("the cottage", f"cottage {current_cottage}")
                    refined_question = refined_question.replace("this one", f"cottage {current_cottage}")
                    refined_question = refined_question.replace("that one", f"cottage {current_cottage}")
                    # Handle "it" more carefully - only replace if it's clearly about a cottage
                    if "tell me more" in refined_lower or "what is" in refined_lower or "about it" in refined_lower:
                        refined_question = refined_question.replace(" about it", f" about cottage {current_cottage}")
                        refined_question = refined_question.replace(" about it?", f" about cottage {current_cottage}?")
                    logger.info(f"Post-processed refined question with current_cottage {current_cottage}: {refined_question}")
            
            # Intent-based query optimization and entity extraction
            # Extract entities BEFORE retrieval for better filtering
            entities = extract_entities_for_retrieval(refined_question)
            logger.debug(f"Extracted entities: {entities}")
            
            # Optimize query based on intent (rule-based + optional LLM)
            use_llm_optimization = is_query_optimization_enabled() and is_complex_query(refined_question)
            search_query = optimize_query_for_retrieval(
                refined_question,
                intent,
                entities,
                use_llm=use_llm_optimization,
                llm=llm if use_llm_optimization else None,
                max_new_tokens=max_new_tokens
            )
            logger.info(f"Query optimization: '{refined_question}' → '{search_query}' (intent={intent.value}, use_llm={use_llm_optimization})")
            
            # Build metadata filter for intent-based retrieval
            retrieval_filter = get_retrieval_filter(intent, entities)
            logger.info(f"Intent: {intent.value}, Retrieval filter: {retrieval_filter}, Entities: {entities}")
            
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
            
            # Increase k for safety/security queries to get comprehensive information about guards, gated community, etc.
            if any(word in query_lower for word in ["safe", "safety", "security", "secure", "guard", "guards", "gated", "emergency", "secure for", "is it safe"]):
                effective_k = max(effective_k, 5)  # Get at least 5 documents for safety queries
                logger.info(f"Increased k to {effective_k} for safety/security query")
            
            # Increase k for safety/security queries to get comprehensive information about guards, gated community, etc.
            if any(word in query_lower for word in ["safe", "safety", "security", "secure", "guard", "guards", "gated", "emergency", "secure for", "is it safe"]):
                effective_k = max(effective_k, 5)  # Get at least 5 documents for safety queries
                logger.info(f"Increased k to {effective_k} for safety/security query")
            
            # Retrieve documents
            retrieved_contents = []
            sources = []
            
            try:
                # Retrieve more documents than needed to ensure diversity
                try:
                    result = vector_store.similarity_search_with_threshold(
                        query=search_query, 
                        k=min(effective_k * 3, 15), 
                        threshold=0.0,  # Get 3x more for deduplication
                        filter=retrieval_filter if (is_intent_filtering_enabled() and retrieval_filter) else None  # Intent-based filtering (if enabled)
                    )
                except TypeError as te:
                    # Catch the "object of type 'int' has no len()" error
                    logger.error(f"TypeError in similarity_search_with_threshold: {te}")
                    result = None
                except Exception as e:
                    logger.error(f"Exception in similarity_search_with_threshold: {e}")
                    result = None
                
                # Ensure we got a tuple of (list, list)
                if result is not None and isinstance(result, tuple) and len(result) == 2:
                    retrieved_contents, sources = result
                    # Validate immediately after unpacking - BEFORE any len() calls
                    if not isinstance(retrieved_contents, list):
                        logger.error(f"retrieved_contents is not a list after unpacking: {type(retrieved_contents)}, value: {retrieved_contents}")
                        retrieved_contents = []
                    if not isinstance(sources, list):
                        logger.error(f"sources is not a list after unpacking: {type(sources)}")
                        sources = []
                    
                    # Safe to call len() now
                    if isinstance(retrieved_contents, list):
                        logger.info(f"Retrieved {len(retrieved_contents)} documents with search query (intent={intent.value}, filter={retrieval_filter})")
                        # Log document metadata for debugging
                        if retrieved_contents:
                            doc_intents = [doc.metadata.get("intent", "unknown") for doc in retrieved_contents[:3]]
                            logger.debug(f"First 3 documents have intents: {doc_intents}")
                else:
                    logger.error(f"Unexpected result type from similarity_search_with_threshold: {type(result)}")
                    retrieved_contents = []
                    sources = []
                
                # CRITICAL: Fallback logic - if intent filter returns too few documents, retry without filter
                # This prevents empty retrieval when intent classification is uncertain or documents
                # are classified with different intent metadata than expected
                if is_intent_filtering_enabled() and retrieval_filter and len(retrieved_contents) < 2:
                    logger.warning(
                        f"Intent filter returned only {len(retrieved_contents)} documents for intent '{intent.value}'. "
                        f"Retrying without filter to ensure we have relevant documents."
                    )
                    try:
                        # Retry without intent filter (but keep cottage_id filter if available)
                        fallback_filter = None
                        if entities.get("cottage_id"):
                            fallback_filter = {"cottage_id": str(entities["cottage_id"])}
                        
                        fallback_result = vector_store.similarity_search_with_threshold(
                            query=search_query,
                            k=min(effective_k * 3, 15),
                            threshold=0.0,
                            filter=fallback_filter
                        )
                        
                        if fallback_result and isinstance(fallback_result, tuple) and len(fallback_result) == 2:
                            fallback_contents, fallback_sources = fallback_result
                            if isinstance(fallback_contents, list) and len(fallback_contents) > len(retrieved_contents):
                                logger.info(
                                    f"Fallback retrieval (without intent filter) returned {len(fallback_contents)} documents. "
                                    f"Using fallback results."
                                )
                                retrieved_contents = fallback_contents
                                sources = fallback_sources
                    except Exception as e:
                        logger.warning(f"Error in fallback retrieval without filter: {e}")
                
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
                
                # Log retrieved documents for debugging
                logger.info(f"Retrieved {len(retrieved_contents)} unique documents for query: '{search_query}'")
                # Check if query mentions a specific cottage and verify we have documents about it
                query_lower = search_query.lower()
                for num in ["7", "9", "11"]:
                    if f"cottage {num}" in query_lower or f"cottage{num}" in query_lower:
                        cottage_docs_found = sum(1 for doc in retrieved_contents if f"cottage {num}" in doc.page_content.lower() or f"cottage{num}" in doc.page_content.lower())
                        logger.info(f"Query mentions Cottage {num}: Found {cottage_docs_found} documents mentioning Cottage {num} out of {len(retrieved_contents)} total")
                        if cottage_docs_found == 0 and len(retrieved_contents) > 0:
                            logger.warning(f"⚠️ Query asks about Cottage {num} but no documents mention it! This may cause incorrect answers.")
                for i, doc in enumerate(retrieved_contents[:5]):  # Log first 5
                    doc_preview = doc.page_content[:100].replace('\n', ' ')
                    logger.debug(f"  Doc {i+1}: {doc_preview}...")
                logger.info(f"After deduplication: {len(retrieved_contents)} unique documents")
                
                # No truncation - use full documents
            except Exception as e:
                logger.warning(f"Error with threshold search (refined): {e}, trying without threshold")
                retrieved_contents = []
                sources = []
                try:
                    # Retrieve more for deduplication
                    search_result = vector_store.similarity_search(query=search_query, k=min(effective_k * 3, 15))
                    # Validate result is a list
                    if not isinstance(search_result, list):
                        logger.error(f"similarity_search returned non-list: {type(search_result)}")
                        search_result = []
                    retrieved_contents = search_result
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
                    
                    # No truncation - use full documents
                except Exception as e2:
                    logger.error(f"Error with similarity search (refined): {e2}")
                    # Ensure we have valid empty lists
                    if not isinstance(retrieved_contents, list):
                        retrieved_contents = []
                    if not isinstance(sources, list):
                        sources = []
            
            # If no results, try original query
            if not retrieved_contents:
                logger.info("No results with optimized query, trying original query")
                try:
                    result = vector_store.similarity_search_with_threshold(
                        query=request.question, k=effective_k, threshold=0.0
                    )
                    # Validate result
                    if isinstance(result, tuple) and len(result) == 2:
                        retrieved_contents, sources = result
                        if not isinstance(retrieved_contents, list):
                            logger.error(f"retrieved_contents is not a list: {type(retrieved_contents)}")
                            retrieved_contents = []
                            sources = []
                    else:
                        logger.error(f"Unexpected result type: {type(result)}")
                        retrieved_contents = []
                        sources = []
                except Exception as e:
                    try:
                        search_result = vector_store.similarity_search(query=request.question, k=effective_k)
                        if not isinstance(search_result, list):
                            logger.error(f"similarity_search returned non-list: {type(search_result)}")
                            search_result = []
                        retrieved_contents = search_result
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
            
            # Process structured queries (pricing, capacity) BEFORE vector search
            pricing_handler = get_pricing_handler()
            pricing_result = None
            # Check pricing query by handler (not just intent) - some pricing queries might be classified as ROOMS intent
            if pricing_handler.is_pricing_query(request.question):
                logger.info("Detected pricing query, processing with structured logic")
                slots = slot_manager.get_slots()
                # Use refined_question if available (includes cottage number from context), otherwise use original
                question_for_pricing = refined_question if 'refined_question' in locals() and refined_question else request.question
                pricing_result = pricing_handler.process_pricing_query(
                    question_for_pricing, slots, retrieved_contents
                )
                if pricing_result.get("answer_template"):
                    retrieved_contents = pricing_handler.enhance_context_with_pricing_info(
                        retrieved_contents, pricing_result
                    )
            
            # Check if this is a capacity query and process it
            capacity_handler = get_capacity_handler()
            capacity_result = None  # Initialize to track capacity query results
            if capacity_handler.is_capacity_query(request.question):
                logger.info("Detected capacity query, processing with structured logic")
                capacity_result = capacity_handler.process_capacity_query(
                    request.question, retrieved_contents
                )
                if capacity_result.get("answer_template"):
                    retrieved_contents = capacity_handler.enhance_context_with_capacity_info(
                        retrieved_contents, capacity_result
                    )
            
            # Check if this is an availability query and enhance context
            # CRITICAL: Only inject for ACTUAL booking/availability queries, not general facility questions
            query_lower_avail_chat = request.question.lower()
            
            # Check for explicit booking/availability phrases (must be about booking, not just containing "available")
            explicit_booking_phrases_chat = [
                "i want to check availability", "i want to book", "check availability and book",
                "book a cottage", "want to book", "want to check availability", 
                "can i book", "how to book", "how can i book", "book now",
                "check availability", "availability and book", "book", "reserve", "reservation"
            ]
            has_explicit_booking_phrase_chat = any(phrase in query_lower_avail_chat for phrase in explicit_booking_phrases_chat)
            
            # EXCLUDE queries that are clearly NOT about booking (even if they contain "available")
            is_facilities_query_chat = any(phrase in query_lower_avail_chat for phrase in [
                "what facilities", "facilities available", "facilities are", "tell me about facilities",
                "what amenities", "amenities available", "what features", "features available"
            ])
            is_general_info_query_chat = any(phrase in query_lower_avail_chat for phrase in [
                "tell me about", "what is", "what are", "describe", "information about"
            ]) and not has_explicit_booking_phrase_chat
            
            # Check intent - must be explicitly BOOKING or AVAILABILITY
            is_booking_availability_intent_chat = intent in [IntentType.BOOKING, IntentType.AVAILABILITY]
            
            # Only inject if:
            # 1. It's explicitly about booking/availability (has booking phrase AND intent)
            # 2. OR intent is booking/availability AND query explicitly mentions booking (not just "available")
            # 3. AND it's NOT a facilities/general info query
            is_availability_booking_chat = (
                not is_facilities_query_chat and 
                not (is_general_info_query_chat and not has_explicit_booking_phrase_chat) and
                (
                    (is_booking_availability_intent_chat and has_explicit_booking_phrase_chat) or
                    (is_booking_availability_intent_chat and any(word in query_lower_avail_chat for word in ["book", "booking", "reserve", "reservation"])) or
                    has_explicit_booking_phrase_chat
                )
            )
            
            if is_availability_booking_chat:
                logger.info(f"Detected availability query, enhancing context with availability information (intent={intent}, query='{request.question[:80]}')")
                # Extract cottage number if mentioned
                cottage_num = None
                query_lower = request.question.lower()
                for num in ["7", "9", "11"]:
                    if f"cottage {num}" in query_lower or f"cottage{num}" in query_lower:
                        cottage_num = num
                        break
                
                # Create availability information document
                availability_info = f"""
🚨🚨🚨 CRITICAL AVAILABILITY INFORMATION - HIGHEST PRIORITY 🚨🚨🚨

MANDATORY AVAILABILITY RESPONSE:
YES, Swiss Cottages ARE AVAILABLE THROUGHOUT THE YEAR (YEAR-ROUND), subject to existing bookings.

AVAILABILITY STATUS:
✅ Swiss Cottages are available year-round (throughout the year), subject to availability
✅ All cottages (Cottage 7, 9, and 11) are available throughout the year
✅ Availability is subject to existing bookings only

{"COTTAGE-SPECIFIC INFORMATION:" if cottage_num else "GENERAL INFORMATION:"}
{"✅ Cottage " + cottage_num + " is available throughout the year, subject to availability" if cottage_num else "✅ All cottages are available throughout the year, subject to availability"}

BOOKING INFORMATION (MANAGER-STYLE):
To confirm your booking:
1. Provide your exact check-in and check-out dates
2. Provide the number of guests
3. Specify your preferred cottage (if any)
4. Contact us to confirm availability and complete booking

CONTACT INFORMATION:
- Contact us: https://swisscottagesbhurban.com/contact-us/
- Cottage Manager (Abdullah): +92 300 1218563

⚠️⚠️⚠️ CRITICAL INSTRUCTIONS FOR LLM - YOU MUST FOLLOW THESE ⚠️⚠️⚠️:
1. YOU MUST start your answer with: "Yes, Swiss Cottages are available throughout the year, subject to availability"
2. DO NOT say "not available" or "options are not available" - cottages are available year-round
3. DO NOT say "I don't have real-time availability" - say they are available year-round
4. Always confirm availability positively and prominently
5. Provide manager-style booking information with contact details
6. If user provides dates, acknowledge them and guide them to contact for confirmation
7. The cottages are available year-round - emphasize this clearly in your response
"""
                # Add as a document to retrieved contents (at the beginning for priority)
                from entities.document import Document
                availability_doc = Document(
                    page_content=availability_info,
                    metadata={"source": "availability_handler", "document": "availability_info"}
                )
                retrieved_contents.insert(0, availability_doc)
                logger.info(f"Enhanced context with availability information for {'Cottage ' + cottage_num if cottage_num else 'all cottages'}")
            
            # Prioritize cottage-specific documents
            if retrieved_contents:
                query_lower = request.question.lower()
                # For cottage availability queries, prioritize availability-specific FAQs
                if cottage_availability_match:
                    availability_docs = []
                    other_docs = []
                    cottage_num = cottage_availability_match
                    for doc in retrieved_contents:
                        doc_text_lower = doc.page_content.lower()
                        source_lower = doc.metadata.get("source", "").lower()
                        # Prioritize availability FAQs and documents mentioning the specific cottage
                        if ("availability" in source_lower or "available" in doc_text_lower) and f"cottage {cottage_num}" in doc_text_lower:
                            availability_docs.insert(0, doc)  # Highest priority
                        elif f"cottage {cottage_num}" in doc_text_lower or f"cottage{cottage_num}" in doc_text_lower:
                            availability_docs.append(doc)
                        else:
                            other_docs.append(doc)
                    if availability_docs:
                        retrieved_contents = availability_docs + other_docs
                        logger.info(f"Prioritized {len(availability_docs)} availability documents for Cottage {cottage_num}")
                # For capacity/group size queries, prioritize documents that mention cottage numbers
                elif any(word in query_lower for word in ["member", "members", "people", "person", "persons", "guest", "guests", "group", "suitable", "best for", "accommodate", "capacity", "which cottage"]):
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
                    # Use refined_question for prioritization (includes cottage number from context)
                    prioritization_query = refined_question if 'refined_question' in locals() else request.question
                    retrieved_contents = prioritize_cottage_documents(prioritization_query, retrieved_contents)
            
            # Process structured queries BEFORE vector search (for reasoning queries)
            # For reasoning queries, we do structured calculation first, then enhance with vector search
            # For FAQ queries, we do vector search first (existing flow)
            
            # Check if this is a pricing query and process it with structured logic
            # Process pricing queries BEFORE validation - pricing_handler can handle missing slots gracefully
            # Check pricing query by handler (not just intent) - some pricing queries might be classified as ROOMS intent
            # Also check if query contains dates - if previous query was about pricing and current query has dates, treat as pricing
            pricing_handler = get_pricing_handler()
            pricing_result = None
            
            # Check if this is a pricing query OR a date query following a pricing query
            is_pricing_query = pricing_handler.is_pricing_query(request.question)
            
            # Also check if query has dates/cottage and previous intent was pricing (follow-up with info)
            slots = slot_manager.get_slots()
            has_dates = slots.get("dates") is not None
            has_cottage = slots.get("cottage_id") is not None
            has_nights = slots.get("nights") is not None
            previous_intent_was_pricing = (len(context_tracker.intent_history) > 1 and 
                                          context_tracker.intent_history[-2] == IntentType.PRICING)
            
            # If query has dates/cottage/nights and previous intent was pricing, treat as pricing query
            # This handles cases like "in cottage 9" or "tell me the total cost" after providing dates
            if not is_pricing_query and previous_intent_was_pricing and (has_dates or has_cottage or has_nights):
                logger.info(f"Detected follow-up query with slots (dates={has_dates}, cottage={has_cottage}, nights={has_nights}) following pricing query - treating as pricing query")
                is_pricing_query = True
            
            # Also check if query is asking for total cost and we have slots from previous messages
            if not is_pricing_query and any(phrase in request.question.lower() for phrase in ["tell me the total cost", "tell me total cost", "what is the total cost", "what's the total cost", "total cost"]):
                if has_dates or has_nights:
                    logger.info(f"Detected 'total cost' query with slots (dates={has_dates}, nights={has_nights}) - treating as pricing query")
                    is_pricing_query = True
            
            if is_pricing_query:
                logger.info("Detected pricing query, processing with structured logic")
                # Use refined_question if available (includes cottage number from context), otherwise use original
                question_for_pricing = refined_question if 'refined_question' in locals() and refined_question else request.question
                
                # For pricing queries, ensure we have pricing documents in retrieved_contents
                # If no pricing documents found, the handler will fallback to loading from FAQ files
                pricing_result = pricing_handler.process_pricing_query(
                    question_for_pricing, slots, retrieved_contents
                )
                
                # Enhance context with pricing analysis (even if missing info, to provide helpful context)
                if pricing_result.get("answer_template"):
                    retrieved_contents = pricing_handler.enhance_context_with_pricing_info(
                        retrieved_contents, pricing_result
                    )
                    if pricing_result.get("has_all_info"):
                        logger.info(f"Enhanced context with pricing analysis: total_price={pricing_result.get('total_price')}")
                    else:
                        logger.info(f"Enhanced context with pricing info request: missing_slots={pricing_result.get('missing_slots')}")
            
            # Check if this is a capacity query and process it
            capacity_handler = get_capacity_handler()
            capacity_result = None  # Initialize to track capacity query results
            if capacity_handler.is_capacity_query(request.question):
                logger.info("Detected capacity query, processing with structured logic")
                capacity_result = capacity_handler.process_capacity_query(
                    request.question, retrieved_contents
                )
                
                # Enhance context with capacity analysis (don't return early - let LLM generate natural answer)
                # IMPORTANT: Enhance even if has_all_info is False (e.g., group-only queries)
                if capacity_result:
                    retrieved_contents = capacity_handler.enhance_context_with_capacity_info(
                        retrieved_contents, capacity_result
                    )
                    logger.info(f"Enhanced context with capacity analysis: suitable={capacity_result.get('suitable')}, has_all_info={capacity_result.get('has_all_info')}")
            
            # CRITICAL: Enforce "No Context = No Answer" rule
            # After all retrieval attempts and handler processing, if we still have no content,
            # DO NOT generate answer from training data - return helpful error message instead
            if not retrieved_contents:
                logger.warning(f"No documents retrieved after all attempts for query: '{request.question}'")
                answer = (
                    "I don't have information about that in my knowledge base.\n\n"
                    "💡 **Please try:**\n"
                    "- Rephrasing your question (e.g., 'Where is Swiss Cottages Bhurban located?')\n"
                    "- Using different keywords\n"
                    "- Being more specific about Swiss Cottages Bhurban\n\n"
                    "**Note:** I only answer questions based on the provided FAQ documents about Swiss Cottages Bhurban. "
                    "I cannot answer questions from general knowledge or about other locations.\n"
                )
                return ChatResponse(
                    answer=answer,
                    sources=[],
                    intent=intent_type,
                    session_id=request.session_id,
                )
            
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
                # Optimize max_new_tokens based on query complexity
                base_max_tokens = request.max_new_tokens or 1024  # Increased default to prevent cut-off responses
                query_lower_for_tokens = request.question.lower()
                
                # Reduce tokens ONLY for very simple greetings/acknowledgments
                if any(word in query_lower_for_tokens for word in ["yes", "no", "hi", "hello", "thanks", "thank you", "ok", "okay"]) and len(request.question.split()) <= 3:
                    max_new_tokens = min(base_max_tokens, 128)  # Short for very simple greetings only
                # Availability/booking queries need more tokens for complete responses
                elif any(word in query_lower_for_tokens for word in ["pricing", "price", "cost", "booking", "availability", "book a cottage", "check availability", "i want to check", "i want to book", "book", "available", "reserve", "reservation"]):
                    max_new_tokens = max(base_max_tokens, 1024)  # Ensure enough tokens for complete booking/availability responses
                # "Tell me more" follow-ups - need more tokens to complete properly
                elif any(phrase in query_lower_for_tokens for phrase in ["tell me more", "tell me more about", "more about", "more details", "more information"]):
                    max_new_tokens = max(base_max_tokens, 1024)  # Ensure enough tokens for follow-ups
                # Very short questions (1-2 words) can use fewer tokens
                elif len(request.question.split()) <= 2:
                    max_new_tokens = min(base_max_tokens, 512)  # Short for very brief questions only
                else:
                    # Default: Use full base_max_tokens to ensure complete responses
                    max_new_tokens = base_max_tokens  # Use full amount to prevent cut-off responses
                
                logger.debug(f"Query complexity adjustment: base={base_max_tokens}, adjusted={max_new_tokens}")
                
                # Enhance question with slot information for pricing/booking queries
                enhanced_question = refined_question
                if intent in [IntentType.PRICING, IntentType.BOOKING] and slot_manager.get_slots():
                    slots = slot_manager.get_slots()
                    slot_info_parts = []
                    if slots.get("nights"):
                        slot_info_parts.append(f"for {slots['nights']} nights")
                    if slots.get("guests"):
                        slot_info_parts.append(f"for {slots['guests']} guests")
                    if slots.get("cottage_id"):
                        slot_info_parts.append(f"in {slots['cottage_id']}")
                    if slot_info_parts:
                        # Append slot info to question to make it explicit for LLM
                        enhanced_question = f"{refined_question} ({', '.join(slot_info_parts)})"
                
                # Apply essential information injection, pricing filtering, and safety prioritization
                if retrieved_contents:
                    # Inject essential info (capacity for cottage descriptions)
                    slots_dict = slot_manager.get_slots() if slot_manager else {}
                    # CRITICAL: Preprocess context to clarify "Azad Kashmir" usage before sending to LLM
                    retrieved_contents = preprocess_context_for_location_clarity(retrieved_contents)
                    retrieved_contents = inject_essential_info(retrieved_contents, request.question, slots_dict)
                    
                    # Filter pricing from context for non-pricing queries
                    retrieved_contents = filter_pricing_from_context(retrieved_contents, request.question)
                    if should_filter_pricing(request.question):
                        logger.info(f"Filtered pricing from context for non-pricing query: {request.question}")
                    
                    # Prioritize safety documents for safety queries
                    retrieved_contents = prioritize_safety_documents(retrieved_contents, request.question)
                    safety_keywords = ["safe", "safety", "security", "secure", "guard", "guards", "gated", "emergency"]
                    if any(kw in request.question.lower() for kw in safety_keywords):
                        safety_docs_count = sum(1 for doc in retrieved_contents if any(
                            indicator in doc.page_content.lower() for indicator in 
                            ["guard", "guards", "security", "gated community", "secure", "safety", "emergency"]
                        ))
                        logger.info(f"Prioritized {safety_docs_count} safety documents for safety query")
                
                try:
                    streamer, _ = answer_with_context(
                        llm,
                        ctx_synthesis_strategy,
                        enhanced_question,  # Use enhanced question with slot info
                        chat_history,
                        retrieved_contents,
                        max_new_tokens,
                        use_simple_prompt=use_simple_prompt,
                        intent=intent_type if is_intent_filtering_enabled() else None,  # Pass intent for intent-specific prompts (if enabled)
                    )
                except Exception as e:
                    error_msg = str(e)
                    # Fallback: if fast model fails with 413 error, retry with reasoning model
                    if "413" in error_msg or "Request too large" in error_msg or "too large" in error_msg.lower():
                        llm_model_name = getattr(llm, 'model_name', None)
                        fast_model_name = os.getenv("FAST_MODEL_NAME", "llama-3.1-8b-instant")
                        if query_complexity == "simple" and llm_model_name == fast_model_name:
                            logger.warning("Fast model returned 413 error, falling back to reasoning model")
                            llm = get_reasoning_llm_client()
                            use_simple_prompt = False  # Use full prompt with reasoning model
                            logger.info("Retrying with reasoning model and full prompt")
                            streamer, _ = answer_with_context(
                                llm,
                                ctx_synthesis_strategy,
                                enhanced_question,
                                chat_history,
                                retrieved_contents,
                                max_new_tokens,
                                use_simple_prompt=False,
                                intent=intent_type if is_intent_filtering_enabled() else None,  # Pass intent for intent-specific prompts (if enabled)
                            )
                            logger.info("Fallback to reasoning model succeeded")
                        else:
                            raise  # Re-raise if not a 413 error or not using fast model
                    else:
                        raise  # Re-raise if not a 413 error
                
                # Collect answer from streamer (filtering reasoning tags)
                answer_text = ""
                answer_buffer = ""
                inside_reasoning = False
                reasoning_start_tag = llm.model_settings.reasoning_start_tag if llm.model_settings.reasoning else None
                reasoning_stop_tag = llm.model_settings.reasoning_stop_tag if llm.model_settings.reasoning else None
                
                for token in streamer:
                    parsed_token = llm.parse_token(token)
                    if not parsed_token:
                        continue
                    
                    answer_text += parsed_token  # Keep full text for fallback
                    
                    # Filter reasoning tags during collection
                    if llm.model_settings.reasoning:
                        stripped_token = parsed_token.strip()
                        
                        if reasoning_start_tag and reasoning_start_tag in stripped_token:
                            inside_reasoning = True
                            continue
                        
                        if reasoning_stop_tag and reasoning_stop_tag in stripped_token:
                            inside_reasoning = False
                            continue
                        
                        if inside_reasoning:
                            continue
                    
                    # This is actual answer content
                    answer_buffer += parsed_token
                
                # Use answer_buffer (without reasoning) if available, otherwise extract from full text
                if answer_buffer:
                    answer_text = answer_buffer
                elif llm.model_settings.reasoning:
                    # Fallback: extract reasoning if buffer is empty
                    answer_text = extract_content_after_reasoning(
                        answer_text, reasoning_stop_tag
                    )
                    if answer_text == "":
                        answer_text = "I didn't provide the answer; perhaps I can try again."
                
                # CRITICAL: Remove structured pricing template IMMEDIATELY after LLM response
                # This must happen BEFORE clean_answer_text to catch it early
                answer_text = remove_pricing_template_aggressively(answer_text)
                
                # Clean answer text to remove LLM reasoning/process text
                answer_text = clean_answer_text(answer_text)
                
                # Fix incorrect naming (Swiss Chalet, etc.)
                answer_text = fix_incorrect_naming(answer_text)
                
                # Fix question rephrasing
                answer_text = fix_question_rephrasing(answer_text, request.question)
                
                # CRITICAL: Detect and reject clearly wrong location answers BEFORE fixing
                rejected = detect_and_reject_wrong_location_answer(answer_text, request.question)
                if rejected is None:
                    # Answer was rejected - return error message
                    logger.error("Rejected wrong location answer, returning error message")
                    answer_text = (
                        "I don't have accurate location information in my knowledge base for that query.\n\n"
                        "Swiss Cottages Bhurban is located in Bhurban, Murree, Pakistan. "
                        "For more details, please contact us directly.\n\n"
                        "[MAP] View on Google Maps: https://goo.gl/maps/PQbSR9DsuxwjxUoU6"
                    )
                else:
                    answer_text = rejected
                
                # Fix incorrect location mentions (Azad Kashmir, Patriata)
                answer_text = fix_incorrect_location_mentions(answer_text)
                
                # Check for incomplete responses (cut off mid-sentence)
                if answer_text and not answer_text.strip().endswith(('.', '!', '?', ':', ';')):
                    # Check if it ends mid-word or mid-sentence
                    last_char = answer_text.strip()[-1] if answer_text.strip() else ''
                    if last_char and last_char.isalnum():
                        logger.warning(f"Response appears incomplete - ends with: '{answer_text[-50:]}' (last char: '{last_char}')")
                        # Try to add a period if it's clearly incomplete
                        if len(answer_text.strip()) > 20:  # Only if we have substantial content
                            answer_text = answer_text.strip() + "."
                            logger.info("Added period to incomplete response")
                
                # CRITICAL: Additional check to remove structured pricing template if it still exists
                # This is a fallback in case the cleaning function didn't catch it
                if answer_text and ('🚨 CRITICAL PRICING INFORMATION' in answer_text or 'STRUCTURED PRICING ANALYSIS' in answer_text.upper()):
                    # Find where the actual answer starts (look for pricing information in natural language)
                    answer_start_patterns = [
                        r'(For \d+ nights?.*?total cost is PKR \d+)',
                        r'(The total cost.*?PKR \d+)',
                        r'(Total cost.*?PKR \d+)',
                        r'(Cottage \d+.*?PKR \d+)',
                        r'(For \d+ nights?.*?PKR \d+)',
                    ]
                    
                    extracted_answer = None
                    for pattern in answer_start_patterns:
                        match = re.search(pattern, answer_text, re.IGNORECASE | re.DOTALL)
                        if match:
                            extracted_answer = match.group(1).strip()
                            break
                    
                    if extracted_answer:
                        answer_text = extracted_answer
                    else:
                        # If no pattern match, find first line that looks like an answer
                        lines = answer_text.split('\n')
                        for line in lines:
                            line_stripped = line.strip()
                            # Skip template lines
                            if any(keyword in line_stripped.upper() for keyword in [
                                'CRITICAL PRICING', 'MANDATORY INSTRUCTIONS', 'STRUCTURED PRICING',
                                'DO NOT CONVERT', 'YOU MUST USE', 'ALL PRICES ARE IN PKR',
                                '🚨', '⚠️'
                            ]):
                                continue
                            # Look for actual answer content
                            if len(line_stripped) > 20 and ('PKR' in line_stripped or 'cost' in line_stripped.lower() or 'nights' in line_stripped.lower()):
                                # Find this line's index and take everything from here
                                idx = lines.index(line)
                                answer_text = '\n'.join(lines[idx:]).strip()
                                break
                
                # Validate currency - check if answer has dollar prices when context has PKR
                context_text = "\n".join([doc.page_content for doc in retrieved_contents[:3]])  # Get context from top 3 docs
                answer_text = validate_and_fix_currency(answer_text, context_text)
                
                # Filter out generic requests for group size when it's already known from capacity query
                if capacity_result and capacity_result.get("group_size") is not None:
                    group_size = capacity_result.get("group_size")
                    # Remove phrases that ask for group size/guests when it's already known
                    phrases_to_remove = [
                        r"share your dates,?\s*(?:number of\s*)?guests(?:,?\s*and preferences)?",
                        r"number of\s*guests(?:,?\s*and preferences)?",
                        r"how many\s*guests",
                        r"how many\s*people",
                        r"number of\s*people",
                        r"guests?\s*(?:and\s*)?preferences",
                        r"dates,?\s*(?:number of\s*)?guests(?:,?\s*and preferences)?",
                    ]
                    for phrase in phrases_to_remove:
                        # Replace with just asking for dates and preferences (not guests)
                        answer_text = re.sub(
                            phrase,
                            "dates and preferences",
                            answer_text,
                            flags=re.IGNORECASE
                        )
                    # Also replace specific patterns that include "guests" in the request
                    answer_text = re.sub(
                        r"share your\s+(?:dates,?\s*)?(?:number of\s*)?guests(?:,?\s*and preferences)?",
                        "share your dates and preferences",
                        answer_text,
                        flags=re.IGNORECASE
                    )
                    answer_text = re.sub(
                        r"yes!?\s*share your\s+(?:dates,?\s*)?(?:number of\s*)?guests(?:,?\s*and preferences)?",
                        "Yes! To recommend the best cottage for your stay, please share your dates and preferences",
                        answer_text,
                        flags=re.IGNORECASE
                    )
                    logger.info(f"Filtered out group size requests from answer (group_size={group_size} already known)")
                
                # Filter out "not available" responses for availability queries
                if intent == IntentType.AVAILABILITY or any(word in request.question.lower() for word in ["available", "availability", "can i book", "can we stay", "we want to stay", "we were stay"]):
                    # Replace negative availability responses with positive ones
                    negative_patterns = [
                        r"(?:options?|cottages?|cottage \d+)\s+(?:for|are)\s+(?:staying|staying at|booking)\s+(?:are\s+)?not\s+available",
                        r"not\s+available\s+(?:for|to stay|for staying)",
                        r"(?:options?|cottages?)\s+are\s+not\s+available",
                    ]
                    for pattern in negative_patterns:
                        if re.search(pattern, answer_text, flags=re.IGNORECASE):
                            # Replace with positive availability message
                            answer_text = re.sub(
                                pattern,
                                "are available throughout the year, subject to availability. To confirm your booking",
                                answer_text,
                                flags=re.IGNORECASE
                            )
                            logger.info("Replaced negative availability response with positive availability confirmation")
                    
                    # Also check for phrases like "For [dates], the options... are not available"
                    if re.search(r"for\s+.*?the\s+options?.*?are\s+not\s+available", answer_text, flags=re.IGNORECASE):
                        # Extract dates if mentioned
                        date_match = re.search(r"for\s+([^,]+?)(?:,|\.|$)", answer_text, flags=re.IGNORECASE)
                        if date_match:
                            dates = date_match.group(1).strip()
                            answer_text = re.sub(
                                r"for\s+.*?the\s+options?.*?are\s+not\s+available",
                                f"for {dates}, Swiss Cottages are available throughout the year, subject to availability. To confirm your booking",
                                answer_text,
                                flags=re.IGNORECASE
                            )
                            logger.info(f"Replaced negative availability response with positive confirmation for dates: {dates}")
                
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
                            "- Cottage Manager (Abdullah): +92 300 1218563"
                        )
                    # Advance payment query getting wrong answer
                    elif any(phrase in query_lower for phrase in ["advance payment", "advance", "partial payment", "booking confirmation"]) and not any(word in answer_lower for word in ["advance", "partial", "payment", "confirm"]):
                        logger.warning("Query about advance payment but answer doesn't mention it - likely wrong document retrieved")
                        answer_text = (
                            "I apologize, but I'm having trouble finding specific information about advance payment requirements. "
                            "For detailed payment and booking information, please contact us:\n"
                            "- Contact us: https://swisscottagesbhurban.com/contact-us/\n"
                            "- Cottage Manager (Abdullah): +92 300 1218563"
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
                                    use_simple_prompt=use_simple_prompt,
                                    intent=intent_type if is_intent_filtering_enabled() else None,  # Pass intent for intent-specific prompts (if enabled)
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
                                
                                # Fix incorrect location mentions (Azad Kashmir, Patriata)
                                answer_text = fix_incorrect_location_mentions(answer_text)
                                
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
                                            "- Cottage Manager (Abdullah): +92 300 1218563"
                                        )
                                    elif any(phrase in query_lower for phrase in ["advance payment", "advance", "partial payment", "booking confirmation"]):
                                        answer_text = (
                                            "I apologize, but I'm having trouble finding specific information about advance payment requirements. "
                                            "For detailed payment and booking information, please contact us:\n"
                                            "- Contact us: https://swisscottagesbhurban.com/contact-us/\n"
                                            "- Cottage Manager (Abdullah): +92 300 1218563"
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
                    # Only ask for slots if query needs them (specific calculation vs general info)
                    needs_slots = slot_manager.should_extract_slots(intent, request.question)
                    if not needs_slots:
                        logger.info(f"Query is general info, skipping slot extraction for {intent.value}")
                        missing_slot = None
                    else:
                        # Only ask for slots for booking/pricing/availability intents that need calculation
                        try:
                            missing_slot = slot_manager.get_most_important_missing_slot(intent)
                            # Check if this slot was just extracted in the current turn
                            if missing_slot and missing_slot in extracted_slots:
                                # Slot was just provided, don't ask for it again
                                logger.info(f"Slot '{missing_slot}' was just extracted, skipping follow-up question")
                                missing_slot = None
                            # Special check: Don't ask about cottage_id if cottage is mentioned in query or chat history
                            elif missing_slot == "cottage_id":
                                # Check if cottage was mentioned in the current query
                                from bot.conversation.number_extractor import ExtractCottageNumber
                                cottage_extractor = ExtractCottageNumber()
                                cottage_mentioned = cottage_extractor.extract_cottage_number(request.question)
                                
                                # Also check chat history for cottage mentions
                                if not cottage_mentioned and chat_history:
                                    for message in reversed(list(chat_history)[-3:]):  # Check last 3 messages
                                        if isinstance(message, str):
                                            # Extract question from chat history format
                                            if "question:" in message:
                                                prev_query = message.split("question:")[1].split("answer:")[0].strip()
                                                if prev_query:
                                                    cottage_mentioned = cottage_extractor.extract_cottage_number(prev_query)
                                                    if cottage_mentioned:
                                                        logger.info(f"Cottage {cottage_mentioned} mentioned in chat history, skipping cottage_id question")
                                                        break
                                
                                if cottage_mentioned:
                                    logger.info(f"Cottage {cottage_mentioned} mentioned in query or history, skipping cottage_id question")
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
                            "cottage_id": "Do you have a preference for which cottage?",
                            "family": "Will this be for a family or friends group?",
                            "season": "Are you planning to visit on weekdays or weekends?",
                        }
                        if missing_slot in slot_questions:
                            response_parts.append(f"\n\n{slot_questions[missing_slot]}")
                
                # Get max sentences for this intent
                max_sentences = get_max_sentences_for_intent(intent)
                current_sentence_count = count_sentences(answer_text)
                
                # Add gentle recommendations for pricing, rooms, or safety intents
                # Only show recommendations when they add value AND within length limits
                recommendation_engine = get_recommendation_engine()
                # Only show recommendations for specific intents and when user has provided relevant info
                if intent in [IntentType.PRICING, IntentType.ROOMS, IntentType.SAFETY]:
                    slots = slot_manager.get_slots()
                    # Only show recommendation if it's relevant to the current query
                    # For rooms: show if user asked about rooms/cottages
                    # For pricing: show if user asked about pricing
                    # For safety: show if user asked about safety
                    should_show_recommendation = False
                    if intent == IntentType.ROOMS and (slots.get("guests") or slots.get("cottage_id") or "cottage" in query_lower):
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
                            # Check if adding recommendation would exceed length limit
                            rec_sentence_count = count_sentences(recommendation)
                            if current_sentence_count + rec_sentence_count <= max_sentences:
                                response_parts.append(f"\n\n{recommendation}")
                                current_sentence_count += rec_sentence_count
                            else:
                                logger.debug(f"Skipping recommendation - would exceed max {max_sentences} sentences (current: {current_sentence_count}, recommendation: {rec_sentence_count})")
                
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
                        # Check if adding cross recommendation would exceed length limit
                        rec_sentence_count = count_sentences(cross_rec)
                        if current_sentence_count + rec_sentence_count <= max_sentences:
                            response_parts.append(f"\n\n{cross_rec}")
                            current_sentence_count += rec_sentence_count
                        else:
                            logger.debug(f"Skipping cross recommendation - would exceed max {max_sentences} sentences")
                
                # Add proactive image offer for cottage-specific queries (only if within length limits)
                should_offer, cottage_num = should_offer_images(request.question, answer_text)
                if should_offer and cottage_num and not is_image_request:
                    image_offer = f"\n\n📷 **Would you like to see images of Cottage {cottage_num}?** Just say 'yes' or 'show images'."
                    offer_sentence_count = count_sentences(image_offer)
                    if current_sentence_count + offer_sentence_count <= max_sentences:
                        response_parts.append(image_offer)
                        current_sentence_count += offer_sentence_count
                        # Store in session for "yes" handling
                        session_manager.set_session_data(request.session_id, "image_offer_cottage", cottage_num)
                        logger.info(f"Added image offer for Cottage {cottage_num}")
                    else:
                        logger.debug(f"Skipping image offer - would exceed max {max_sentences} sentences")
                
                # Add image recommendation when cottage is mentioned (but not if user already asked for images)
                if not is_image_request and not should_offer:  # Only suggest if user hasn't already asked for images
                    image_rec = recommendation_engine.generate_image_recommendation(
                        request.question,
                        slot_manager.get_slots(),
                        intent
                    )
                    if image_rec:
                        rec_sentence_count = count_sentences(image_rec)
                        if current_sentence_count + rec_sentence_count <= max_sentences:
                            response_parts.append(f"\n\n{image_rec}")
                            current_sentence_count += rec_sentence_count
                        else:
                            logger.debug(f"Skipping image recommendation - would exceed max {max_sentences} sentences")
                
                # Add booking nudge ONLY for booking/availability intents AND if enough info available AND within length limits
                if intent in [IntentType.BOOKING, IntentType.AVAILABILITY] and slot_manager.has_enough_booking_info():
                    nudge = recommendation_engine.generate_booking_nudge(
                        slot_manager.get_slots(), 
                        context_tracker,
                        intent
                    )
                    if nudge:
                        nudge_sentence_count = count_sentences(nudge)
                        if current_sentence_count + nudge_sentence_count <= max_sentences:
                            response_parts.append(f"\n\n{nudge}")
                            current_sentence_count += nudge_sentence_count
                        else:
                            logger.debug(f"Skipping booking nudge - would exceed max {max_sentences} sentences")
                
                # Combine all response parts
                answer_text = "".join(response_parts)
                
                # CRITICAL: Remove structured pricing template if LLM output it directly
                # This must happen BEFORE any other processing
                answer_text = remove_pricing_template_aggressively(answer_text)
                
                # Clean answer text (removes reasoning, templates, etc.)
                answer_text = clean_answer_text(answer_text)
                
                # CRITICAL: Validate URLs in answer - only allow URLs that appear in context
                # Extract all URLs from context
                context_text = "\n".join([doc.page_content for doc in retrieved_contents[:5]])
                context_urls = set(re.findall(r'https?://[^\s\)]+', context_text, re.IGNORECASE))
                
                # Extract URLs from answer
                answer_urls = re.findall(r'https?://[^\s\)]+', answer_text, re.IGNORECASE)
                
                # Remove URLs from answer that don't appear in context (likely from training data)
                for url in answer_urls:
                    url_lower = url.lower()
                    # Check if this URL (or similar) appears in context
                    url_in_context = any(
                        url_lower in ctx_url.lower() or ctx_url.lower() in url_lower
                        for ctx_url in context_urls
                    )
                    
                    # Also check for known valid domains
                    valid_domains = [
                        'swisscottagesbhurban.com',
                        'airbnb.com',
                        'instagram.com',
                        'facebook.com',
                        'goo.gl/maps',
                        'maps.google.com'
                    ]
                    is_valid_domain = any(domain in url_lower for domain in valid_domains)
                    
                    if not url_in_context and not is_valid_domain:
                        # Remove this URL from answer
                        answer_text = answer_text.replace(url, "")
                        logger.warning(f"Removed URL from answer that's not in context: {url[:50]}")
                
                # Fix incorrect naming (Swiss Chalet, etc.)
                answer_text = fix_incorrect_naming(answer_text)
                
                # Fix question rephrasing
                answer_text = fix_question_rephrasing(answer_text, request.question)
                
                # CRITICAL: Detect and reject clearly wrong location answers BEFORE fixing
                rejected = detect_and_reject_wrong_location_answer(answer_text, request.question)
                if rejected is None:
                    # Answer was rejected - return error message
                    logger.error("Rejected wrong location answer, returning error message")
                    answer_text = (
                        "I don't have accurate location information in my knowledge base for that query.\n\n"
                        "Swiss Cottages Bhurban is located in Bhurban, Murree, Pakistan. "
                        "For more details, please contact us directly.\n\n"
                        "[MAP] View on Google Maps: https://goo.gl/maps/PQbSR9DsuxwjxUoU6"
                    )
                else:
                    answer_text = rejected
                
                # Fix incorrect location mentions (Azad Kashmir, Patriata)
                answer_text = fix_incorrect_location_mentions(answer_text)
                
                # Final length enforcement - truncate if still exceeds limit
                final_sentence_count = count_sentences(answer_text)
                if final_sentence_count > max_sentences:
                    logger.warning(f"Response exceeds max {max_sentences} sentences ({final_sentence_count}). Truncating.")
                    answer_text = truncate_to_max_sentences(answer_text, max_sentences)
                
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
                    # Detect if user is asking for a specific image type
                    image_type = detect_image_type_request(request.question)
                    logger.info(f"Detected image type request in stream: {image_type}")
                    
                    # First, try to get Dropbox URLs
                    dropbox_config = get_dropbox_config()
                    use_dropbox = dropbox_config.get("use_dropbox", False)
                    
                    all_images = []
                    
                    if use_dropbox:
                        # Use Dropbox URLs (Note: Dropbox URLs don't support type filtering yet)
                        logger.info("Using Dropbox image URLs")
                        for cottage_num in cottage_numbers:
                            dropbox_urls = get_dropbox_image_urls(cottage_num, max_images=6)
                            if dropbox_urls:
                                all_images.extend(dropbox_urls)
                                logger.info(f"Found {len(dropbox_urls)} Dropbox image URLs for cottage {cottage_num}")
                            else:
                                logger.warning(f"No Dropbox URLs found for cottage {cottage_num}, falling back to local files")
                                # Fallback to local files with type filtering
                                root_folder = get_root_folder()
                                images = get_cottage_images_by_type(cottage_num, root_folder, image_type=image_type, max_images=6)
                                for img_path in images:
                                    rel_path = img_path.relative_to(root_folder)
                                    from urllib.parse import quote
                                    encoded_path = str(rel_path).replace('\\', '/')
                                    url_path = '/'.join(quote(part, safe='') for part in encoded_path.split('/'))
                                    image_url = f"/images/{url_path}"
                                    all_images.append(image_url)
                    else:
                        # Use local file paths with type filtering
                        root_folder = get_root_folder()
                        logger.info("Using local file paths for images")
                        for cottage_num in cottage_numbers:
                            images = get_cottage_images_by_type(cottage_num, root_folder, image_type=image_type, max_images=6)
                            logger.info(f"Found {len(images)} local images for cottage {cottage_num} (type: {image_type})")
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
                    
                    # If no images found for specific type, modify answer
                    if not cottage_image_urls and image_type:
                        answer_text = (
                            f"I'm sorry, I don't have {image_type} images available for the requested cottage at the moment.\n\n"
                            f"You can ask for general images to see what's available."
                        )
                
                # Generate follow-up actions
                # Convert chat_history to list format for recommendations
                chat_history_list = list(chat_history) if chat_history else []
                follow_up_actions = generate_follow_up_actions(
                    intent,
                    slot_manager.get_slots(),
                    request.question,
                    context_tracker=context_tracker,
                    chat_history=chat_history_list,
                    llm_client=llm,
                    is_widget_query=is_widget_query
                )
                
                return ChatResponse(
                    answer=answer_text,
                    sources=source_infos,
                    intent=intent_type,
                    session_id=request.session_id,
                    cottage_images=cottage_image_urls,
                    follow_up_actions=follow_up_actions,
                )
            else:
                # No documents found - but check if we have pricing/capacity results
                # Pricing and capacity handlers can work without retrieved documents
                if pricing_result and pricing_result.get("answer_template"):
                    # Pricing handler has generated content, use it
                    logger.info("No documents retrieved but pricing_result exists - will use pricing template")
                    # Continue to answer generation (pricing template is in retrieved_contents via enhance_context_with_pricing_info)
                    retrieved_contents = pricing_handler.enhance_context_with_pricing_info(
                        retrieved_contents if retrieved_contents else [], pricing_result
                    )
                elif capacity_result and capacity_result.get("answer_template"):
                    # Capacity handler has generated content, use it
                    logger.info("No documents retrieved but capacity_result exists - will use capacity template")
                    retrieved_contents = capacity_handler.enhance_context_with_capacity_info(
                        retrieved_contents if retrieved_contents else [], capacity_result
                    )
                
                # CRITICAL: Enforce "No Context = No Answer" rule
                # After all retrieval attempts and handler processing, if we still have no content,
                # DO NOT generate answer from training data - return helpful error message instead
                if not retrieved_contents:
                    logger.warning(f"No documents retrieved after all attempts for query: '{request.question}'")
                    answer = (
                        "I don't have information about that in my knowledge base.\n\n"
                        "💡 **Please try:**\n"
                        "- Rephrasing your question (e.g., 'Where is Swiss Cottages Bhurban located?')\n"
                        "- Using different keywords\n"
                        "- Being more specific about Swiss Cottages Bhurban\n\n"
                        "**Note:** I only answer questions based on the provided FAQ documents about Swiss Cottages Bhurban. "
                        "I cannot answer questions from general knowledge or about other locations.\n"
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


@app.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    llm=Depends(get_llm_client),
    vector_store=Depends(get_vector_store),
    intent_router=Depends(get_intent_router),
):
    """Streaming chat endpoint using Server-Sent Events."""
    async def generate():
        try:
            # Use initial llm from dependency for slot_manager (before complexity-based selection)
            initial_llm = llm
            # Get slot manager and context tracker early for image detection
            slot_manager = session_manager.get_or_create_slot_manager(request.session_id, initial_llm)
            context_tracker = session_manager.get_or_create_context_tracker(request.session_id)
            
            # Pre-processing: Check for "yes" responses to image offers
            # Detect if this is a widget-triggered query
            widget_query_patterns = [
                "I want to check availability and book a cottage for my dates",
                "Show me images and photos of the cottages",
                "What are the prices and cottage options? Compare weekday and weekend rates",
                "Tell me about the location and nearby attractions near Swiss Cottages Bhurban"
            ]
            is_widget_query = any(pattern.lower() in request.question.lower() for pattern in widget_query_patterns)
            
            query_lower = request.question.lower()
            is_yes_response = any(word in query_lower for word in ["yes", "yeah", "yep", "sure", "ok", "okay", "show me", "show images", "show photos"])
            
            # Check if previous message offered images (stored in session)
            if is_yes_response:
                session_data = session_manager.get_session_data(request.session_id)
                if session_data and session_data.get("image_offer_cottage"):
                    cottage_num = session_data.get("image_offer_cottage")
                    # User said yes to image offer - show images
                    is_image_request = True
                    cottage_numbers = [cottage_num]
                    # Clear the offer from session
                    session_manager.set_session_data(request.session_id, "image_offer_cottage", None)
                else:
                    is_image_request, cottage_numbers = detect_image_request(request.question, slot_manager, context_tracker)
            else:
                is_image_request, cottage_numbers = detect_image_request(request.question, slot_manager, context_tracker)
            
            # Pre-processing: Handle explicit image requests early
            if is_image_request and cottage_numbers:
                logger.info(f"Detected explicit image request for cottages: {cottage_numbers} in stream")
                # Get images directly without going through full RAG
                root_folder = get_root_folder()
                dropbox_config = get_dropbox_config()
                use_dropbox = dropbox_config.get("use_dropbox", False)
                logger.info(f"Dropbox config - use_dropbox: {use_dropbox}, available cottages: {list(dropbox_config.get('cottage_image_urls', {}).keys())}")
                
                # Group images by cottage
                cottage_images_dict = {}
                
                for cottage_num in cottage_numbers:
                    cottage_images = []
                    
                    if use_dropbox:
                        logger.info(f"Attempting to get Dropbox URLs for cottage {cottage_num} in stream")
                        dropbox_urls = get_dropbox_image_urls(cottage_num, max_images=6)
                        logger.info(f"Got {len(dropbox_urls)} Dropbox URLs for cottage {cottage_num} in stream")
                        if dropbox_urls:
                            cottage_images.extend(dropbox_urls)
                            logger.info(f"Using {len(dropbox_urls)} Dropbox URLs for cottage {cottage_num} in stream")
                        else:
                            logger.warning(f"No Dropbox URLs found for cottage {cottage_num}, falling back to local files in stream")
                            # Fallback to local files
                            images = get_cottage_images(cottage_num, root_folder, max_images=6)
                            for img_path in images:
                                rel_path = img_path.relative_to(root_folder)
                                from urllib.parse import quote
                                encoded_path = str(rel_path).replace('\\', '/')
                                url_path = '/'.join(quote(part, safe='') for part in encoded_path.split('/'))
                                image_url = f"/images/{url_path}"
                                cottage_images.append(image_url)
                    else:
                        logger.info(f"Dropbox not enabled, using local files for cottage {cottage_num} in stream")
                        images = get_cottage_images(cottage_num, root_folder, max_images=6)
                        for img_path in images:
                            rel_path = img_path.relative_to(root_folder)
                            from urllib.parse import quote
                            encoded_path = str(rel_path).replace('\\', '/')
                            url_path = '/'.join(quote(part, safe='') for part in encoded_path.split('/'))
                            image_url = f"/images/{url_path}"
                            cottage_images.append(image_url)
                    
                    if cottage_images:
                        cottage_images_dict[cottage_num] = cottage_images
                
                if cottage_images_dict:
                    # Generate a brief response
                    if len(cottage_numbers) == 1:
                        answer = f"Here are images of Cottage {cottage_numbers[0]}:"
                    else:
                        answer = f"Here are images of the cottages:"
                    
                    total_images = sum(len(imgs) for imgs in cottage_images_dict.values())
                    logger.info(f"Returning {total_images} image URLs grouped by cottage: {list(cottage_images_dict.keys())} in stream")
                    
                    yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'sources': [], 'cottage_images': cottage_images_dict})}\n\n"
                    return
                else:
                    # No images found, provide helpful message
                    answer = "I'm sorry, I couldn't find images for the requested cottages. Please contact us for more information."
                    yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                    return
            
            # Pre-processing: Check for manager contact queries
            manager_contact_patterns = [
                "how can i contact the manager", "contact the manager", "contact manager",
                "manager contact", "manager's contact", "manager contact details",
                "manager phone", "manager number", "cottage manager", "who is the manager",
                "manager information", "reach the manager", "speak to manager"
            ]
            if any(pattern in query_lower for pattern in manager_contact_patterns):
                answer = (
                    "**Cottage Manager Contact Information** 📞\n\n"
                    "**Abdullah** is the cottage manager at Swiss Cottages Bhurban.\n\n"
                    "**Contact Details:**\n"
                    "- **Phone:** +92 300 1218563\n"
                    "- **Alternate Phone (Urgent):** +92 327 8837088\n"
                    "- **Contact Form:** https://swisscottagesbhurban.com/contact-us/\n\n"
                    "Abdullah can help you with:\n"
                    "- Bookings and availability\n"
                    "- Pricing and special requests\n"
                    "- General assistance before or during your stay\n\n"
                    "Feel free to reach out for personalized assistance! 🏡"
                )
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                return
            
            # Pre-processing: Check for single room/person queries
            single_room_patterns = [
                "single room", "one room", "individual room", "separate room",
                "single person", "one person", "individual person", "solo",
                "just me", "only me", "by myself", "alone"
            ]
            if any(pattern in query_lower for pattern in single_room_patterns):
                answer = (
                    "Swiss Cottages Bhurban rents **entire cottages**, not individual rooms. 🏡\n\n"
                    "Each cottage is a fully private, self-contained unit that includes:\n"
                    "- Multiple bedrooms (2-3 bedrooms depending on cottage)\n"
                    "- Living areas\n"
                    "- Kitchen\n"
                    "- Terrace/balcony\n"
                    "- Parking\n\n"
                    "**Important:** Even if you're traveling alone or as a single person, you would rent the entire cottage. "
                    "The base pricing is for up to 6 guests, so a single person would still rent the full cottage.\n\n"
                    "Would you like to know more about:\n"
                    "- Pricing for a single person stay\n"
                    "- Which cottage would be best for you\n"
                    "- Availability and booking information"
                )
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                return
            
            # Pre-processing: Check for cottage listing queries
            # IMPORTANT: This must run BEFORE general "tell me about" handler
            
            # Check for "how many cottages" or "total cottages" queries FIRST
            total_cottages_patterns = [
                "how many cottages", "total cottages", "number of cottages",
                "how many cottages do you have", "total number of cottages"
            ]
            
            if any(pattern in query_lower for pattern in total_cottages_patterns):
                registry = get_cottage_registry()
                answer = registry.format_total_cottages_response()
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                return
            
            # Check for capacity queries BEFORE cottage listing handler
            # IMPORTANT: Capacity queries should NOT trigger static cottage listing - they need LLM reasoning
            capacity_handler = get_capacity_handler()
            is_capacity_query = capacity_handler.is_capacity_query(request.question)
            
            # Flexible cottage listing detection using keyword combination
            # Check if query contains "cottages" + listing keywords
            # IMPORTANT: Exclude pricing queries, capacity queries, AND facilities queries - they should NOT trigger cottage listing
            is_pricing_query = any(phrase in query_lower for phrase in [
                "pricing", "price", "prices", "cost", "rate", "rates", "how much"
            ])
            
            # Check if this is a facilities query - these should go to RAG, not static listing
            is_facilities_query = any(phrase in query_lower for phrase in [
                "facility", "facilities", "amenity", "amenities", "feature", "features",
                "kitchen", "terrace", "balcony", "socializing", "relaxation", "what is available",
                "chef", "service", "services", "cooking", "food", "meal", "bbq", "grill",
                "wifi", "internet", "tv", "netflix", "parking", "heating", "lounge", "bbq facilities"
            ])
            
            has_cottages_keyword = "cottage" in query_lower or "cottages" in query_lower
            listing_keywords = [
                "you have", "do you have", "available", "offer", "list", 
                "which", "what", "show me", "tell me about the cottages"
            ]
            has_listing_intent = any(keyword in query_lower for keyword in listing_keywords)
            
            # Also check for explicit listing patterns
            explicit_listing_patterns = [
                "which cottages", "what cottages", "list cottages", 
                "cottages do you have", "cottages you have",
                "available cottages", "cottages available",
                "what cottages do you", "which cottages do you"
            ]
            has_explicit_pattern = any(pattern in query_lower for pattern in explicit_listing_patterns)
            
            # If query is about listing cottages (not general info about swiss cottages)
            # AND it's NOT a pricing query AND it's NOT a capacity query AND it's NOT a facilities query
            if has_cottages_keyword and (has_listing_intent or has_explicit_pattern) and not is_pricing_query and not is_capacity_query and not is_facilities_query:
                # Additional check: exclude general "tell me about swiss cottages" or "tell me about the cottages" queries
                # These should go to RAG for general information
                is_general_info_query = (
                    "tell me about swiss cottages" in query_lower or
                    "tell me about the swiss cottages" in query_lower or
                    "tell me about the cottages" in query_lower or
                    ("tell me about" in query_lower and "cottages" in query_lower and 
                     "you have" not in query_lower and "available" not in query_lower and
                     "which" not in query_lower and "what" not in query_lower and
                     "list" not in query_lower)
                )
                
                if not is_general_info_query:
                    registry = get_cottage_registry()
                    # This will automatically filter to show only 9 and 11 (not 7)
                    answer = registry.format_cottage_list(query=request.question, show_total=False)
                    answer += (
                        "\n\nAll cottages include:\n"
                        "- Fully equipped kitchen\n"
                        "- Living lounge\n"
                        "- Bedrooms and bathrooms\n"
                        "- Outdoor terrace/balcony\n"
                        "- Wi-Fi, smart TV with Netflix\n"
                        "- Heating system\n"
                        "- Secure parking\n\n"
                        "Would you like to know more about:\n"
                        "- Pricing for a specific cottage\n"
                        "- Which cottage is best for your group size\n"
                        "- Availability and booking information"
                    )
                    yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                    return
            
            # Handle 2-bedroom queries (will show Cottage 7)
            if "2 bedroom" in query_lower or "two bedroom" in query_lower:
                registry = get_cottage_registry()
                cottages = registry.list_cottages_by_filter(query=request.question)
                if cottages:
                    answer = f"🏡 **2-Bedroom Cottages:**\n\n"
                    for cottage in cottages:
                        answer += f"**Cottage {cottage.number}** - {cottage.description}\n"
                        answer += f"- Base capacity: Up to {cottage.base_capacity} guests\n"
                        answer += f"- Maximum capacity: {cottage.max_capacity} guests\n\n"
                    answer += "Would you like to know about pricing or availability?"
                    yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                    return
            
            # Handle 3-bedroom queries (will show Cottages 9 and 11)
            if "3 bedroom" in query_lower or "three bedroom" in query_lower:
                registry = get_cottage_registry()
                cottages = registry.list_cottages_by_filter(query=request.question)
                if cottages:
                    answer = f"🏡 **3-Bedroom Cottages:**\n\n"
                    for cottage in cottages:
                        answer += f"**Cottage {cottage.number}** - {cottage.description}\n"
                        answer += f"- Base capacity: Up to {cottage.base_capacity} guests\n"
                        answer += f"- Maximum capacity: {cottage.max_capacity} guests\n\n"
                    answer += "Would you like to know about pricing or availability?"
                    yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                    return
            
            # Get or create chat history
            chat_history = session_manager.get_or_create_session(request.session_id, total_length=2)
            
            # Get synthesis strategy
            strategy_name = request.synthesis_strategy or "create-and-refine"
            ctx_synthesis_strategy = get_ctx_synthesis_strategy(strategy_name)
            
            # Classify intent
            intent = intent_router.classify(request.question, chat_history)
            intent_type = intent.value if hasattr(intent, 'value') else str(intent)
            
            # Classify query complexity and select appropriate model
            complexity_classifier = get_complexity_classifier()
            query_complexity = complexity_classifier.classify_complexity(request.question, intent)
            
            # Select model based on complexity
            use_simple_prompt = (query_complexity == "simple")
            if query_complexity == "simple":
                selected_llm = get_fast_llm_client()
                fast_model_name = os.getenv("FAST_MODEL_NAME", "llama-3.1-8b-instant")
                logger.info(f"Using fast model ({fast_model_name}) for simple query")
            else:
                selected_llm = get_reasoning_llm_client()
                reasoning_model_name = os.getenv("REASONING_MODEL_NAME", "llama-3.1-70b-versatile")
                logger.info(f"Using reasoning model ({reasoning_model_name}) for complex query")
            
            # Handle simple intents
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
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                return
            
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
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                return
            
            elif intent == IntentType.AFFIRMATIVE:
                answer = (
                    "Great! What would you like to know about Swiss Cottages Bhurban?\n\n"
                    "I can help you with:\n"
                    "- **Pricing & Availability**: Rates, booking, availability\n"
                    "- **Facilities & Amenities**: What's available at the cottages\n"
                    "- **Location & Nearby**: Location details and nearby attractions\n"
                    "- **Booking & Payment**: How to book and payment methods\n\n"
                    "Just ask me any question, and I'll find the information for you!"
                )
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                return
            
            elif intent == IntentType.NEGATIVE:
                answer = "Great! Feel free to reach out if you have any questions about Swiss Cottages Bhurban. Have a wonderful day! 😊"
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                return
            
            elif intent == IntentType.STATEMENT:
                query_lower = request.question.lower().strip()
                if not any(phrase in query_lower for phrase in [
                    'but we', 'but i', 'but they', 'but which', 'but what', 'but how', 'but when', 'but where',
                    'but can', 'but is', 'but are', 'but do', 'but does', 'but will', 'but would',
                    'we are', 'we have', 'we need', 'we want', 'which cottage', 'what cottage'
                ]):
                    answer = "You're welcome! 😊\n\nIs there anything else you'd like to know about Swiss Cottages Bhurban?"
                    yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                    return
            
            elif intent == IntentType.CLARIFICATION_NEEDED:
                clar_question = intent_router.get_clarification_question(request.question)
                answer = f"To give you the most accurate answer, could you please clarify: **{clar_question}**"
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                return
            
            # Track intent in context (slot_manager and context_tracker already created above)
            context_tracker.add_intent(intent)
            
            # Check for cottage availability queries
            query_lower_stream = request.question.lower()
            availability_patterns = [
                r"is\s+cottage\s+(\d+)\s+available",
                r"cottage\s+(\d+)\s+available",
                r"is\s+cottage\s+(\d+)\s+also\s+available",
            ]
            cottage_availability_match_stream = None
            for pattern in availability_patterns:
                match = re.search(pattern, query_lower_stream)
                if match:
                    cottage_availability_match_stream = match.group(1)
                    logger.info(f"Detected cottage availability query for Cottage {cottage_availability_match_stream}")
                    break
            
            # Extract slots
            extracted_slots = slot_manager.extract_slots(request.question, intent)
            
            # Improve context retention: Check chat history for previous slot values
            if chat_history and len(chat_history) > 0:
                date_extractor = get_date_extractor()
                for message in reversed(list(chat_history)[-3:]):  # Check last 3 messages
                    if isinstance(message, str) and "question:" in message:
                        parts = message.split("question:", 1)
                        if len(parts) > 1:
                            full_message = parts[1]
                            # Split into question and answer
                            if "answer:" in full_message:
                                prev_query = full_message.split("answer:")[0].strip()
                                prev_answer = full_message.split("answer:")[1].strip() if "answer:" in full_message else ""
                            else:
                                prev_query = full_message.strip()
                                prev_answer = ""
                            
                            if prev_query and prev_query != request.question:
                                prev_slots = slot_manager.extract_slots(prev_query, intent)
                                for key, value in prev_slots.items():
                                    if key not in extracted_slots and value is not None:
                                        if key not in slot_manager.slots or slot_manager.slots[key] is None:
                                            extracted_slots[key] = value
                                            logger.info(f"Retrieved {key}={value} from chat history in stream endpoint")
                            
                            # CRITICAL: Also extract dates from previous ANSWERS (bot responses)
                            # This handles cases where bot mentioned dates like "February 11, 2026, to February 15, 2026"
                            if prev_answer and "dates" not in extracted_slots:
                                # Try to extract dates from the answer text
                                date_range = date_extractor.extract_date_range(prev_answer)
                                if date_range:
                                    extracted_slots["dates"] = date_range
                                    logger.info(f"✅ Extracted dates from chat history answer in stream: {date_range.get('start_date')} to {date_range.get('end_date')}, {date_range.get('nights')} nights")
                                    logger.info(f"   Source text: '{prev_answer[:100]}...'")
            
            slot_manager.update_slots(extracted_slots)
            
            # Update context_tracker.current_cottage if a cottage was extracted
            current_cottage = slot_manager.get_current_cottage()
            if current_cottage:
                context_tracker.set_current_cottage(current_cottage)
            
            # Check if this intent should proceed with RAG
            manager_intents = [IntentType.PRICING, IntentType.ROOMS, IntentType.SAFETY, 
                            IntentType.BOOKING, IntentType.AVAILABILITY, IntentType.FACILITIES, IntentType.LOCATION]
            if intent not in [IntentType.FAQ_QUESTION, IntentType.UNKNOWN, IntentType.REFINEMENT] + manager_intents:
                # This intent doesn't need RAG, return early
                answer = "I'm not sure how to help with that. Could you please ask about Swiss Cottages Bhurban?"
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                return
            
            # Analyze sentiment
            sentiment_analyzer = get_sentiment_analyzer(selected_llm)
            sentiment = sentiment_analyzer.analyze(request.question)
            
            # Check for image requests (already detected in pre-processing, don't overwrite)
            # is_image_request and cottage_numbers are already set in pre-processing section
            is_booking_request = is_direct_booking_request(request.question)
            
            # Refine question
            max_new_tokens = request.max_new_tokens or 128
            refined_question = refine_question(
                selected_llm, request.question, chat_history=chat_history, max_new_tokens=max_new_tokens
            )
            logger.info(f"Original query: {request.question}")
            logger.info(f"Refined query: {refined_question}")
            
            # Fallback: If refined question is empty or just whitespace, use original question
            if not refined_question or not refined_question.strip():
                logger.warning(f"Refined question is empty, using original question: {request.question}")
                refined_question = request.question
            
            # Post-process refined question: If it still has pronouns and we have current_cottage, expand them
            current_cottage = None
            if slot_manager:
                current_cottage = slot_manager.get_current_cottage()
            if not current_cottage and context_tracker:
                current_cottage = context_tracker.get_current_cottage()
            
            if current_cottage:
                # Check if refined question still has pronouns that need expansion
                refined_lower = refined_question.lower()
                has_pronouns = any(phrase in refined_lower for phrase in ["this cottage", "that cottage", "the cottage", "it", "this one", "that one"])
                has_cottage_number = any(f"cottage {num}" in refined_lower or f"cottage{num}" in refined_lower for num in ["7", "9", "11"])
                
                if has_pronouns and not has_cottage_number:
                    # Manually expand pronouns to cottage number
                    refined_question = refined_question.replace("this cottage", f"cottage {current_cottage}")
                    refined_question = refined_question.replace("that cottage", f"cottage {current_cottage}")
                    refined_question = refined_question.replace("the cottage", f"cottage {current_cottage}")
                    refined_question = refined_question.replace("this one", f"cottage {current_cottage}")
                    refined_question = refined_question.replace("that one", f"cottage {current_cottage}")
                    # Handle "it" more carefully - only replace if it's clearly about a cottage
                    if "tell me more" in refined_lower or "what is" in refined_lower or "about it" in refined_lower:
                        refined_question = refined_question.replace(" about it", f" about cottage {current_cottage}")
                        refined_question = refined_question.replace(" about it?", f" about cottage {current_cottage}?")
                    logger.info(f"Post-processed refined question with current_cottage {current_cottage}: {refined_question}")
            
            # Intent-based query optimization and entity extraction (if enabled)
            if is_intent_filtering_enabled():
                # Extract entities BEFORE retrieval for better filtering
                entities = extract_entities_for_retrieval(refined_question)
                logger.debug(f"Extracted entities: {entities}")
                
                # Optimize query based on intent (rule-based + optional LLM)
                use_llm_optimization = is_query_optimization_enabled() and is_complex_query(refined_question)
                search_query = optimize_query_for_retrieval(
                    refined_question,
                    intent,
                    entities,
                    use_llm=use_llm_optimization,
                    llm=selected_llm if use_llm_optimization else None,
                    max_new_tokens=max_new_tokens
                )
                logger.info(f"Query optimization: '{refined_question}' → '{search_query}' (intent={intent.value}, use_llm={use_llm_optimization})")
                
                # Build metadata filter for intent-based retrieval
                retrieval_filter = get_retrieval_filter(intent, entities)
                logger.info(f"Intent: {intent.value}, Retrieval filter: {retrieval_filter}, Entities: {entities}")
            else:
                # Fallback to old behavior (no intent-based filtering)
                entities = {}
                search_query = refined_question
                retrieval_filter = None
                logger.debug("Intent-based filtering disabled, using original query")
            
            # Determine effective k
            effective_k = request.k or 3
            query_lower = request.question.lower()
            
            if any(word in query_lower for word in ["available", "availability", "which cottages", "which cottage", "vacant", "vacancy"]):
                effective_k = max(effective_k, 5)
            
            if any(word in query_lower for word in ["payment", "price", "pricing", "cost", "rate", "methods", "book", "booking", "reserve"]):
                effective_k = max(effective_k, 5)
            
            if any(cottage in query_lower for cottage in ["cottage 7", "cottage 9", "cottage 11", "cottage7", "cottage9", "cottage11"]):
                effective_k = max(effective_k, 5)
            
            if any(word in query_lower for word in ["cook", "kitchen", "facility", "amenity", "amenities", "facilities", "what", "tell me about", "information about", "about cottages", "about the cottages"]):
                effective_k = max(effective_k, 5)
            
            if any(word in query_lower for word in ["member", "members", "people", "person", "persons", "guest", "guests", "group", "suitable", "best for", "accommodate", "capacity"]):
                effective_k = max(effective_k, 5)
            
            # Initialize pricing handler (will process AFTER retrieval)
            pricing_handler = get_pricing_handler()
            pricing_result = None
            # Check pricing query by handler (not just intent) - some pricing queries might not be classified as PRICING intent
            # Also check if query contains dates - if previous query was about pricing and current query has dates, treat as pricing
            is_pricing_query = pricing_handler.is_pricing_query(request.question)
            
            # Also check if query has dates and previous intent was pricing (follow-up with dates)
            slots = slot_manager.get_slots()
            has_dates = slots.get("dates") is not None
            previous_intent_was_pricing = (len(context_tracker.intent_history) > 1 and 
                                          context_tracker.intent_history[-2] == IntentType.PRICING)
            
            # If query has dates and previous intent was pricing, treat as pricing query
            if not is_pricing_query and has_dates and previous_intent_was_pricing:
                logger.info(f"Detected date query following pricing query in stream - treating as pricing query")
                is_pricing_query = True
            
            # capacity_handler and is_capacity_query are already initialized earlier (for cottage listing check)
            # Reuse them here - get_capacity_handler() returns singleton, so safe to call again
            capacity_handler = get_capacity_handler()  # Reuse singleton instance
            capacity_result = None
            # is_capacity_query is already set earlier, no need to check again
            
            # Send searching status (only if we're going to search)
            yield f"data: {json.dumps({'type': 'searching', 'message': 'Searching knowledge base...'})}\n\n"
            await asyncio.sleep(0.05)
            
            # Retrieve documents
            retrieved_contents = []
            sources = []
            
            try:
                # For general queries, increase k to get more comprehensive information
                if any(phrase in request.question.lower() for phrase in [
                    "tell me about", "what is", "about swiss cottages", "about the cottages",
                    "information about", "describe"
                ]):
                    effective_k = max(effective_k, 8)  # Get more documents for general queries
                    logger.info(f"Increased k to {effective_k} for general query")
                
                result = vector_store.similarity_search_with_threshold(
                    query=search_query, 
                    k=min(effective_k * 3, 20), 
                    threshold=0.0,
                    filter=retrieval_filter if (is_intent_filtering_enabled() and retrieval_filter) else None  # Intent-based filtering (if enabled)
                )
                
                # Validate result
                if isinstance(result, tuple) and len(result) == 2:
                    retrieved_contents, sources = result
                    if not isinstance(retrieved_contents, list) or not isinstance(sources, list):
                        logger.error(f"Invalid result types: retrieved_contents={type(retrieved_contents)}, sources={type(sources)}")
                        retrieved_contents = []
                        sources = []
                    else:
                        logger.info(f"Retrieved {len(retrieved_contents)} documents with search query (intent={intent.value}, filter={retrieval_filter})")
                        # Log document metadata for debugging
                        if retrieved_contents:
                            doc_intents = [doc.metadata.get("intent", "unknown") for doc in retrieved_contents[:3]]
                            logger.debug(f"First 3 documents have intents: {doc_intents}")
                else:
                    logger.error(f"Unexpected result type from similarity_search_with_threshold: {type(result)}")
                    retrieved_contents = []
                    sources = []
                
                # CRITICAL: Fallback logic - if intent filter returns too few documents, retry without filter
                # This prevents empty retrieval when intent classification is uncertain or documents
                # are classified with different intent metadata than expected
                if is_intent_filtering_enabled() and retrieval_filter and len(retrieved_contents) < 2:
                    logger.warning(
                        f"Intent filter returned only {len(retrieved_contents)} documents for intent '{intent.value}'. "
                        f"Retrying without filter to ensure we have relevant documents."
                    )
                    try:
                        # Retry without intent filter (but keep cottage_id filter if available)
                        fallback_filter = None
                        if entities.get("cottage_id"):
                            fallback_filter = {"cottage_id": str(entities["cottage_id"])}
                        
                        fallback_result = vector_store.similarity_search_with_threshold(
                            query=search_query,
                            k=min(effective_k * 3, 20),
                            threshold=0.0,
                            filter=fallback_filter
                        )
                        
                        if fallback_result and isinstance(fallback_result, tuple) and len(fallback_result) == 2:
                            fallback_contents, fallback_sources = fallback_result
                            if isinstance(fallback_contents, list) and len(fallback_contents) > len(retrieved_contents):
                                logger.info(
                                    f"Fallback retrieval (without intent filter) returned {len(fallback_contents)} documents. "
                                    f"Using fallback results."
                                )
                                retrieved_contents = fallback_contents
                                sources = fallback_sources
                    except Exception as e:
                        logger.warning(f"Error in fallback retrieval without filter: {e}")
                
                # Deduplicate
                seen_sources = set()
                unique_contents = []
                unique_sources = []
                
                for doc, source_info in zip(retrieved_contents, sources):
                    source = source_info.get("document", "unknown")
                    if source not in seen_sources:
                        seen_sources.add(source)
                        unique_contents.append(doc)
                        unique_sources.append(source_info)
                        if len(unique_contents) >= effective_k:
                            break
                
                retrieved_contents = unique_contents
                sources = unique_sources
                
                # No truncation - use full documents
                
                # Process pricing query AFTER retrieval (needs documents)
                if is_pricing_query:
                    logger.info("Processing pricing query with retrieved documents")
                    slots = slot_manager.get_slots()
                    # Use refined_question if available (includes cottage number from context), otherwise use original
                    question_for_pricing = refined_question if 'refined_question' in locals() and refined_question else request.question
                    pricing_result = pricing_handler.process_pricing_query(
                        question_for_pricing, slots, retrieved_contents
                    )
                    if pricing_result and pricing_result.get("answer_template"):
                        # CRITICAL: DO NOT return template directly - it must go through LLM to convert to natural language
                        # Enhance context with pricing info (template goes to LLM as context, not as direct answer)
                        retrieved_contents = pricing_handler.enhance_context_with_pricing_info(
                            retrieved_contents, pricing_result
                        )
                        # Keep only the first document (pricing doc) for focused context
                        retrieved_contents = retrieved_contents[:1]
                        logger.info("Enhanced context with pricing template - LLM will convert to natural language")
                
                # Process capacity query AFTER retrieval (needs documents)
                if is_capacity_query:
                    logger.info("Processing capacity query with retrieved documents")
                    capacity_result = capacity_handler.process_capacity_query(
                        request.question, retrieved_contents
                    )
                    # Enhance context with capacity info (don't return early - let LLM generate natural answer)
                    if capacity_result:
                        retrieved_contents = capacity_handler.enhance_context_with_capacity_info(
                            retrieved_contents, capacity_result
                        )
                        logger.info(f"Enhanced context with capacity analysis: suitable={capacity_result.get('suitable')}, has_all_info={capacity_result.get('has_all_info')}")
                
                # Check if this is an availability/booking query and enhance context
                # CRITICAL: Only inject for ACTUAL booking/availability queries, not general facility questions
                query_lower_avail = request.question.lower()
                
                # Check for explicit booking/availability phrases (must be about booking, not just containing "available")
                # These phrases explicitly indicate the user wants to book or check availability for booking
                explicit_booking_phrases = [
                    "i want to check availability", "i want to book", "check availability and book",
                    "book a cottage", "want to book", "want to check availability", 
                    "can i book", "how to book", "how can i book", "book now",
                    "check availability", "availability and book", "book", "reserve", "reservation"
                ]
                has_explicit_booking_phrase = any(phrase in query_lower_avail for phrase in explicit_booking_phrases)
                
                # EXCLUDE queries that are clearly NOT about booking (even if they contain "available")
                is_facilities_query = any(phrase in query_lower_avail for phrase in [
                    "what facilities", "facilities available", "facilities are", "tell me about facilities",
                    "what amenities", "amenities available", "what features", "features available"
                ])
                is_general_info_query = any(phrase in query_lower_avail for phrase in [
                    "tell me about", "what is", "what are", "describe", "information about"
                ]) and not has_explicit_booking_phrase
                
                # Check intent - must be explicitly BOOKING or AVAILABILITY
                is_booking_availability_intent = intent in [IntentType.BOOKING, IntentType.AVAILABILITY]
                
                # Only inject if:
                # 1. It's explicitly about booking/availability (has booking phrase AND intent)
                # 2. OR intent is booking/availability AND query explicitly mentions booking (not just "available")
                # 3. AND it's NOT a facilities/general info query
                is_availability_booking = (
                    not is_facilities_query and 
                    not (is_general_info_query and not has_explicit_booking_phrase) and
                    (
                        (is_booking_availability_intent and has_explicit_booking_phrase) or
                        (is_booking_availability_intent and any(word in query_lower_avail for word in ["book", "booking", "reserve", "reservation"])) or
                        has_explicit_booking_phrase
                    )
                )
                
                logger.info(f"🔍 Availability injection check: intent={intent}, has_phrase={has_explicit_booking_phrase}, is_facilities={is_facilities_query}, is_general={is_general_info_query}, is_booking_intent={is_booking_availability_intent}, will_inject={is_availability_booking}, query='{request.question[:80]}'")
                
                if is_availability_booking:
                    logger.info("Detected availability/booking query in stream, enhancing context with availability information")
                    # Extract cottage number if mentioned
                    cottage_num = None
                    query_lower_stream = request.question.lower()
                    for num in ["7", "9", "11"]:
                        if f"cottage {num}" in query_lower_stream or f"cottage{num}" in query_lower_stream:
                            cottage_num = num
                            break
                    
                    # Create availability information document with Cottage 9 and 11 prioritization
                    if cottage_num == "7":
                        # User specifically asked for Cottage 7
                        cottage_info = "✅ Cottage 7 is available throughout the year, subject to availability"
                        booking_cottages = "Cottage 7"
                        airbnb_links = "- Book Cottage 7: Contact manager for booking link"
                        prioritization_rules = "- User specifically asked for Cottage 7 - provide information for this cottage only"
                    elif cottage_num:
                        # User specifically asked for a cottage (9 or 11)
                        cottage_info = f"✅ Cottage {cottage_num} is available throughout the year, subject to availability"
                        booking_cottages = f"Cottage {cottage_num}"
                        if cottage_num == "9":
                            airbnb_links = "- Book Cottage 9 on Airbnb: https://www.airbnb.com/rooms/651168099240245080"
                        elif cottage_num == "11":
                            airbnb_links = "- Book Cottage 11 on Airbnb: https://www.airbnb.com/rooms/886682083069412842"
                        else:
                            airbnb_links = "- Contact manager for booking link"
                        prioritization_rules = f"- User specifically asked for Cottage {cottage_num} - provide information for this cottage only"
                    else:
                        # General query - prioritize Cottage 9 and 11
                        cottage_info = "✅ Cottage 9 and Cottage 11 are available throughout the year, subject to availability. These are our recommended 3-bedroom cottages ideal for families."
                        booking_cottages = "Cottage 9 or Cottage 11"
                        airbnb_links = """- Book Cottage 9 on Airbnb: https://www.airbnb.com/rooms/651168099240245080
- Book Cottage 11 on Airbnb: https://www.airbnb.com/rooms/886682083069412842"""
                        prioritization_rules = """- **CRITICAL**: User did NOT specify a cottage - YOU MUST prioritize and mention Cottage 9 and Cottage 11 FIRST
- **ABSOLUTE RULE**: DO NOT mention Cottage 7 in your response unless user specifically asks for "Cottage 7" or "cottage 7"
- **YOUR RESPONSE MUST START WITH**: "You can book Cottage 9 or Cottage 11..." NOT "cottages 7, 9, and 11"
- **IGNORE any context documents that mention Cottage 7** - they are for reference only
- **YOU MUST prioritize Cottage 9 and Cottage 11** - mention them first, include their Airbnb links
- **DO NOT say "Cottage 7, 9, and 11"** - say "Cottage 9 and Cottage 11" only"""
                    
                    availability_info = f"""
🚨🚨🚨 CRITICAL AVAILABILITY INFORMATION - HIGHEST PRIORITY 🚨🚨🚨

MANDATORY AVAILABILITY RESPONSE:
YES, Swiss Cottages ARE AVAILABLE THROUGHOUT THE YEAR (YEAR-ROUND), subject to existing bookings.

AVAILABILITY STATUS:
✅ Swiss Cottages are available year-round (throughout the year), subject to availability
{cottage_info}
✅ Availability is subject to existing bookings only

🚨🚨🚨 MANDATORY COTTAGE PRIORITIZATION - HIGHEST PRIORITY 🚨🚨🚨:
{prioritization_rules}

BOOKING INFORMATION (MANAGER-STYLE):
To book {booking_cottages}:
1. Visit our website: https://swisscottagesbhurban.com
2. Use the "Book Now" button or contact us directly
3. Book via Airbnb:
{airbnb_links}
4. Contact Manager (Abdullah): +92 300 1218563 (WhatsApp)

⚠️⚠️⚠️ CRITICAL INSTRUCTIONS FOR LLM - YOU MUST FOLLOW THESE ⚠️⚠️⚠️:
1. YOU MUST start your answer with: "Yes, Swiss Cottages are available throughout the year, subject to availability"
{"2. YOU MUST prioritize Cottage 9 and Cottage 11 - mention them FIRST, include their Airbnb links" if not cottage_num else "2. Provide information for Cottage " + cottage_num + " as requested"}
{"3. DO NOT mention Cottage 7 unless user specifically asks for it" if not cottage_num else ""}
4. Include Airbnb links for Cottage 9 and Cottage 11 (or Cottage 7 if specifically requested)
5. Format website URL correctly: https://swisscottagesbhurban.com (not httpsswisscottagesbhurbancom)
6. DO NOT say "not available" or "options are not available" - cottages are available year-round
7. Always confirm availability positively and prominently
8. Provide complete booking information with all links
"""
                    # Add as a document to retrieved contents (at the beginning for priority)
                    from entities.document import Document
                    availability_doc = Document(
                        page_content=availability_info,
                        metadata={"source": "availability_handler", "document": "availability_info"}
                    )
                    retrieved_contents.insert(0, availability_doc)
                    logger.info(f"Enhanced context with availability information in stream for {'Cottage ' + cottage_num if cottage_num else 'all cottages'}")
                
                # Prioritize cottage-specific documents for availability queries
                if retrieved_contents:
                    query_lower_stream = request.question.lower()
                    # For cottage availability queries, prioritize availability-specific FAQs
                    if cottage_availability_match_stream:
                        availability_docs = []
                        other_docs = []
                        cottage_num = cottage_availability_match_stream
                        for doc in retrieved_contents:
                            doc_text_lower = doc.page_content.lower()
                            source_lower = doc.metadata.get("source", "").lower()
                            # Prioritize availability FAQs and documents mentioning the specific cottage
                            if ("availability" in source_lower or "available" in doc_text_lower) and f"cottage {cottage_num}" in doc_text_lower:
                                availability_docs.insert(0, doc)  # Highest priority
                            elif f"cottage {cottage_num}" in doc_text_lower or f"cottage{cottage_num}" in doc_text_lower:
                                availability_docs.append(doc)
                            else:
                                other_docs.append(doc)
                        if availability_docs:
                            retrieved_contents = availability_docs + other_docs
                            logger.info(f"Prioritized {len(availability_docs)} availability documents for Cottage {cottage_num} in stream")
                    else:
                        # For other queries, use existing prioritization
                        # Use refined_question for prioritization (includes cottage number from context)
                        prioritization_query = refined_question if 'refined_question' in locals() else request.question
                        retrieved_contents = prioritize_cottage_documents(prioritization_query, retrieved_contents)
                
            except Exception as e:
                logger.warning(f"Error with threshold search: {e}")
                retrieved_contents = []
                sources = []
            
            # Send sources found status
            if sources and len(sources) > 0:
                yield f"data: {json.dumps({'type': 'sources_found', 'sources': sources[:effective_k]})}\n\n"
                await asyncio.sleep(0.05)
            
            # Check if we have pricing/capacity results even if no documents retrieved
            if not retrieved_contents:
                # Pricing and capacity handlers can work without retrieved documents
                if pricing_result and pricing_result.get("answer_template"):
                    # Pricing handler has generated content, use it
                    logger.info("No documents retrieved but pricing_result exists - will use pricing template")
                    retrieved_contents = pricing_handler.enhance_context_with_pricing_info(
                        retrieved_contents if retrieved_contents else [], pricing_result
                    )
                elif capacity_result and capacity_result.get("answer_template"):
                    # Capacity handler has generated content, use it
                    logger.info("No documents retrieved but capacity_result exists - will use capacity template")
                    retrieved_contents = capacity_handler.enhance_context_with_capacity_info(
                        retrieved_contents if retrieved_contents else [], capacity_result
                    )
            
            # CRITICAL: Enforce "No Context = No Answer" rule
            # After all retrieval attempts and handler processing, if we still have no content,
            # DO NOT generate answer from training data - return helpful error message instead
            if not retrieved_contents:
                logger.warning(f"No documents retrieved after all attempts for query: '{request.question}'")
                # Hide searching message before showing fallback
                yield f"data: {json.dumps({'type': 'hide_searching'})}\n\n"
                await asyncio.sleep(0.05)
                
                answer = (
                    "I don't have information about that in my knowledge base.\n\n"
                    "💡 **Please try:**\n"
                    "- Rephrasing your question (e.g., 'Where is Swiss Cottages Bhurban located?')\n"
                    "- Using different keywords\n"
                    "- Being more specific about Swiss Cottages Bhurban\n\n"
                    "**Note:** I only answer questions based on the provided FAQ documents about Swiss Cottages Bhurban. "
                    "I cannot answer questions from general knowledge or about other locations.\n"
                )
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                return
            
            # Check relevance
            is_relevant, reason = check_document_relevance(request.question, retrieved_contents)
            
            if not is_relevant:
                answer = (
                    f"❌ **I don't have information about that in the knowledge base.**\n\n"
                    f"**Your question:** {request.question}\n\n"
                    f"**Issue:** {reason}\n\n"
                    "💡 **Note:** I only have information about Swiss Cottages Bhurban (in Pakistan).\n"
                )
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': []})}\n\n"
                return
            
            # Send typing indicator
            yield f"data: {json.dumps({'type': 'typing', 'message': 'Bot is typing...'})}\n\n"
            await asyncio.sleep(0.05)
            
            # Generate answer with streaming
            # Optimize max_new_tokens based on query complexity
            base_max_tokens = request.max_new_tokens or 1024  # Increased default to prevent cut-off responses
            query_lower_for_tokens = request.question.lower()
            
            # CRITICAL: Check for booking/availability queries FIRST (before other checks)
            # Availability/booking queries need more tokens for complete responses
            # Check phrases first (multi-word patterns)
            booking_phrases = [
                "i want to check", "i want to book", "check availability and book", 
                "book a cottage", "check availability", "want to check", "want to book"
            ]
            has_booking_phrase = any(phrase in query_lower_for_tokens for phrase in booking_phrases)
            
            # Check single words
            booking_words = ["pricing", "price", "cost", "booking", "availability", "book", "available", "reserve", "reservation"]
            has_booking_word = any(word in query_lower_for_tokens for word in booking_words)
            
            is_booking_availability_query = (
                has_booking_phrase or 
                has_booking_word or
                intent in [IntentType.BOOKING, IntentType.AVAILABILITY]
            )
            
            logger.info(f"🔍 Booking query check: phrase={has_booking_phrase}, word={has_booking_word}, intent={intent}, result={is_booking_availability_query}, query='{request.question[:100]}'")
            
            # CRITICAL: Check booking/availability queries FIRST before any other checks
            # Availability/booking queries need more tokens for complete responses
            if is_booking_availability_query:
                max_new_tokens = max(base_max_tokens, 1024)  # Ensure enough tokens for complete booking/availability responses
                logger.info(f"✅ BOOKING/AVAILABILITY QUERY DETECTED - Setting max_new_tokens to {max_new_tokens} for query: '{request.question[:100]}', intent: {intent}")
            # Reduce tokens ONLY for very simple greetings/acknowledgments
            elif any(word in query_lower_for_tokens for word in ["yes", "no", "hi", "hello", "thanks", "thank you", "ok", "okay"]) and len(request.question.split()) <= 3:
                max_new_tokens = min(base_max_tokens, 128)  # Short for very simple greetings only
            # "Tell me more" follow-ups - need more tokens to complete properly
            elif any(phrase in query_lower_for_tokens for phrase in ["tell me more", "tell me more about", "more about", "more details", "more information"]):
                max_new_tokens = max(base_max_tokens, 1024)  # Ensure enough tokens for follow-ups
            # Very short questions (1-2 words) can use fewer tokens
            elif len(request.question.split()) <= 2:
                max_new_tokens = min(base_max_tokens, 512)  # Short for very brief questions only
            else:
                # Default: Use full base_max_tokens to ensure complete responses
                max_new_tokens = base_max_tokens  # Use full amount to prevent cut-off responses
            
            logger.info(f"Query complexity adjustment: base={base_max_tokens}, adjusted={max_new_tokens}, query='{request.question[:100]}'")
            
            enhanced_question = refined_question
            
            if intent in [IntentType.PRICING, IntentType.BOOKING] and slot_manager.get_slots():
                slots = slot_manager.get_slots()
                slot_info_parts = []
                if slots.get("nights"):
                    slot_info_parts.append(f"for {slots['nights']} nights")
                if slots.get("guests"):
                    slot_info_parts.append(f"for {slots['guests']} guests")
                if slots.get("cottage_id"):
                    slot_info_parts.append(f"in {slots['cottage_id']}")
                if slot_info_parts:
                    enhanced_question = f"{refined_question} ({', '.join(slot_info_parts)})"
            
            # Apply essential information injection, pricing filtering, and safety prioritization
            if retrieved_contents:
                # Inject essential info (capacity for cottage descriptions)
                slots_dict = slot_manager.get_slots() if slot_manager else {}
                retrieved_contents = inject_essential_info(retrieved_contents, request.question, slots_dict)
                
                # For general booking/availability queries (no specific cottage), deprioritize documents mentioning Cottage 7
                query_lower_deprio = request.question.lower()
                if is_booking_availability_query and not any(f"cottage {num}" in query_lower_deprio or f"cottage{num}" in query_lower_deprio for num in ["7", "9", "11"]):
                    # General booking query - prioritize documents that mention Cottage 9/11, deprioritize those mentioning Cottage 7
                    cottage_9_11_docs = []
                    cottage_7_docs = []
                    other_docs = []
                    for doc in retrieved_contents:
                        doc_lower = doc.page_content.lower()
                        mentions_7 = "cottage 7" in doc_lower or "cottage7" in doc_lower
                        mentions_9_11 = ("cottage 9" in doc_lower or "cottage9" in doc_lower or 
                                         "cottage 11" in doc_lower or "cottage11" in doc_lower)
                        if mentions_9_11 and not mentions_7:
                            cottage_9_11_docs.append(doc)
                        elif mentions_7:
                            cottage_7_docs.append(doc)
                        else:
                            other_docs.append(doc)
                    # Reorder: Cottage 9/11 docs first, then others, then Cottage 7 docs last
                    retrieved_contents = cottage_9_11_docs + other_docs + cottage_7_docs
                    if cottage_7_docs:
                        logger.info(f"Deprioritized {len(cottage_7_docs)} document(s) mentioning Cottage 7 for general booking query")
                
                # Filter pricing from context for non-pricing queries
                retrieved_contents = filter_pricing_from_context(retrieved_contents, request.question)
                if should_filter_pricing(request.question):
                    logger.info(f"Filtered pricing from context for non-pricing query: {request.question}")
                
                # Prioritize safety documents for safety queries
                retrieved_contents = prioritize_safety_documents(retrieved_contents, request.question)
                safety_keywords = ["safe", "safety", "security", "secure", "guard", "guards", "gated", "emergency"]
                if any(kw in request.question.lower() for kw in safety_keywords):
                    safety_docs_count = sum(1 for doc in retrieved_contents if any(
                        indicator in doc.page_content.lower() for indicator in 
                        ["guard", "guards", "security", "gated community", "secure", "safety", "emergency"]
                    ))
                    logger.info(f"Prioritized {safety_docs_count} safety documents for safety query")
            
            # Validate inputs before calling answer_with_context
            # But first check if we have pricing/capacity results (they can work without retrieved documents)
            if not retrieved_contents:
                # Check if pricing handler has generated content
                if pricing_result and pricing_result.get("answer_template"):
                    logger.info("No documents retrieved but pricing_result exists - enhancing context with pricing template")
                    retrieved_contents = pricing_handler.enhance_context_with_pricing_info(
                        [], pricing_result
                    )
                elif capacity_result and capacity_result.get("answer_template"):
                    logger.info("No documents retrieved but capacity_result exists - enhancing context with capacity template")
                    retrieved_contents = capacity_handler.enhance_context_with_capacity_info(
                        [], capacity_result
                    )
            
            # CRITICAL: Enforce "No Context = No Answer" rule
            # After all retrieval attempts and handler processing, if we still have no content,
            # DO NOT generate answer from training data - return helpful error message instead
            if not retrieved_contents:
                logger.warning(f"No documents retrieved after all attempts for query: '{request.question}'")
                answer = (
                    "I don't have information about that in my knowledge base.\n\n"
                    "💡 **Please try:**\n"
                    "- Rephrasing your question (e.g., 'Where is Swiss Cottages Bhurban located?')\n"
                    "- Using different keywords\n"
                    "- Being more specific about Swiss Cottages Bhurban\n\n"
                    "**Note:** I only answer questions based on the provided FAQ documents about Swiss Cottages Bhurban. "
                    "I cannot answer questions from general knowledge or about other locations.\n"
                )
                error_sources = []
                if sources:
                    for src in sources[:effective_k]:
                        if isinstance(src, dict):
                            error_sources.append(src)
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': error_sources})}\n\n"
                return
            
            if not ctx_synthesis_strategy:
                logger.error("ctx_synthesis_strategy is None")
                answer = "I encountered an error while processing your question. Please try again."
                error_sources = []
                if sources:
                    for src in sources[:effective_k]:
                        if isinstance(src, dict):
                            error_sources.append(src)
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': error_sources})}\n\n"
                return
            
            try:
                # Log before calling to help debug
                logger.info(f"Calling answer_with_context with {len(retrieved_contents)} documents, strategy: {type(ctx_synthesis_strategy).__name__}, use_simple_prompt: {use_simple_prompt}, max_new_tokens={max_new_tokens}")
                # Get intent type for intent-specific prompts
                intent_type_str = intent.value if hasattr(intent, 'value') else str(intent)
                streamer, _ = answer_with_context(
                    selected_llm,
                    ctx_synthesis_strategy,
                    enhanced_question,
                    chat_history,
                    retrieved_contents,
                    max_new_tokens,
                    use_simple_prompt=use_simple_prompt,
                    intent=intent_type_str,  # Pass intent for intent-specific prompts
                )
                logger.info(f"answer_with_context returned successfully, streamer type: {type(streamer)}")
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                logger.error(f"Error calling answer_with_context: {error_type}: {error_msg}", exc_info=True)
                logger.error(f"retrieved_contents count: {len(retrieved_contents) if retrieved_contents else 0}")
                
                # Fallback: if 413 error (Request too large), retry with simple prompt
                if "413" in error_msg or "Request too large" in error_msg or "too large" in error_msg.lower():
                    if not use_simple_prompt:
                        logger.warning("Request too large (413 error), retrying with simple prompt to reduce size")
                        try:
                            intent_type_str = intent.value if hasattr(intent, 'value') else str(intent)
                            streamer, _ = answer_with_context(
                                selected_llm,
                                ctx_synthesis_strategy,
                                enhanced_question,
                                chat_history,
                                retrieved_contents,
                                max_new_tokens,
                                use_simple_prompt=True,  # Use simple prompt to reduce size
                                intent=intent_type_str if is_intent_filtering_enabled() else None,  # Pass intent for intent-specific prompts (if enabled)
                            )
                            logger.info("Retry with simple prompt succeeded")
                        except Exception as retry_e:
                            logger.error(f"Retry with simple prompt also failed: {retry_e}")
                            raise  # Re-raise the original error if retry also fails
                    else:
                        raise  # Re-raise if already using simple prompt
                else:
                    raise  # Re-raise if not a 413 error
                logger.error(f"retrieved_contents types: {[type(doc).__name__ for doc in retrieved_contents[:3]] if retrieved_contents else 'empty'}")
                logger.error(f"ctx_synthesis_strategy: {type(ctx_synthesis_strategy).__name__}")
                logger.error(f"selected_llm: {type(selected_llm).__name__ if 'selected_llm' in locals() else 'not assigned'}")
                logger.error(f"enhanced_question: {enhanced_question[:100]}")
                logger.error(f"max_new_tokens: {max_new_tokens}")
                
                # Fallback: if 413 error (Request too large), retry with simple prompt first
                if "413" in error_msg or "Request too large" in error_msg or "too large" in error_msg.lower():
                    if not use_simple_prompt:
                        logger.warning("Request too large (413 error), retrying with simple prompt to reduce size")
                        try:
                            intent_type_str = intent.value if hasattr(intent, 'value') else str(intent)
                            streamer, _ = answer_with_context(
                                selected_llm,
                                ctx_synthesis_strategy,
                                enhanced_question,
                                chat_history,
                                retrieved_contents,
                                max_new_tokens,
                                use_simple_prompt=True,  # Use simple prompt to reduce size
                                intent=intent_type_str if is_intent_filtering_enabled() else None,  # Pass intent for intent-specific prompts (if enabled)
                            )
                            logger.info("Retry with simple prompt succeeded")
                            # Continue with streaming instead of returning error
                        except Exception as retry_error:
                            logger.error(f"Retry with simple prompt also failed: {retry_error}")
                            # If simple prompt also fails, try reasoning model (if not already using it)
                            llm_model_name = getattr(selected_llm, 'model_name', None)
                            reasoning_model_name = os.getenv("REASONING_MODEL_NAME", "llama-3.1-70b-versatile")
                            if llm_model_name != reasoning_model_name:
                                logger.warning("Simple prompt also failed, trying reasoning model")
                                try:
                                    selected_llm = get_reasoning_llm_client()
                                    logger.info("Retrying with reasoning model and simple prompt")
                                    intent_type_str = intent.value if hasattr(intent, 'value') else str(intent)
                                    streamer, _ = answer_with_context(
                                        selected_llm,
                                        ctx_synthesis_strategy,
                                        enhanced_question,
                                        chat_history,
                                        retrieved_contents,
                                        max_new_tokens,
                                        use_simple_prompt=True,  # Still use simple prompt
                                        intent=intent_type_str if is_intent_filtering_enabled() else None,  # Pass intent for intent-specific prompts (if enabled)
                                    )
                                    logger.info("Fallback to reasoning model with simple prompt succeeded")
                                    # Continue with streaming instead of returning error
                                except Exception as fallback_error:
                                    logger.error(f"Fallback to reasoning model also failed: {fallback_error}")
                                    answer = f"I encountered an error ({error_type}: {error_msg[:100]}). Please try again or rephrase your question."
                                    error_sources = []
                                    if sources:
                                        for src in sources[:effective_k]:
                                            if isinstance(src, dict):
                                                error_sources.append(src)
                                    yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                                    yield f"data: {json.dumps({'type': 'done', 'sources': error_sources})}\n\n"
                                    return
                            else:
                                # Already using reasoning model, give up
                                answer = f"I encountered an error ({error_type}: {error_msg[:100]}). Please try again or rephrase your question."
                                error_sources = []
                                if sources:
                                    for src in sources[:effective_k]:
                                        if isinstance(src, dict):
                                            error_sources.append(src)
                                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                                yield f"data: {json.dumps({'type': 'done', 'sources': error_sources})}\n\n"
                                return
                    else:
                        # Already using simple prompt, try reasoning model if not already using it
                        llm_model_name = getattr(selected_llm, 'model_name', None)
                        reasoning_model_name = os.getenv("REASONING_MODEL_NAME", "llama-3.1-70b-versatile")
                        if llm_model_name != reasoning_model_name:
                            logger.warning("Simple prompt failed with 413, trying reasoning model")
                            try:
                                selected_llm = get_reasoning_llm_client()
                                logger.info("Retrying with reasoning model and simple prompt")
                                intent_type_str = intent.value if hasattr(intent, 'value') else str(intent)
                                streamer, _ = answer_with_context(
                                    selected_llm,
                                    ctx_synthesis_strategy,
                                    enhanced_question,
                                    chat_history,
                                    retrieved_contents,
                                    max_new_tokens,
                                    use_simple_prompt=True,
                                    intent=intent_type_str if is_intent_filtering_enabled() else None,  # Pass intent for intent-specific prompts (if enabled)
                                )
                                logger.info("Fallback to reasoning model succeeded")
                                # Continue with streaming instead of returning error
                            except Exception as fallback_error:
                                logger.error(f"Fallback to reasoning model also failed: {fallback_error}")
                                answer = f"I encountered an error ({error_type}: {error_msg[:100]}). Please try again or rephrase your question."
                                error_sources = []
                                if sources:
                                    for src in sources[:effective_k]:
                                        if isinstance(src, dict):
                                            error_sources.append(src)
                                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                                yield f"data: {json.dumps({'type': 'done', 'sources': error_sources})}\n\n"
                                return
                        else:
                            # Already using reasoning model with simple prompt, give up
                            answer = f"I encountered an error ({error_type}: {error_msg[:100]}). Please try again or rephrase your question."
                            error_sources = []
                            if sources:
                                for src in sources[:effective_k]:
                                    if isinstance(src, dict):
                                        error_sources.append(src)
                        yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                        yield f"data: {json.dumps({'type': 'done', 'sources': error_sources})}\n\n"
                        return
                else:
                    # For debugging, include error type in response
                    answer = f"I encountered an error ({error_type}: {error_msg[:100]}). Please try again or rephrase your question."
                    error_sources = []
                    if sources:
                        for src in sources[:effective_k]:
                            if isinstance(src, dict):
                                error_sources.append(src)
                    yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'sources': error_sources})}\n\n"
                    return
            
            if not streamer:
                logger.error("Streamer is None or empty")
                answer = "I couldn't generate a response. Please try again."
                # Format sources for error response
                error_sources = []
                if sources:
                    for src in sources[:effective_k]:
                        if isinstance(src, dict):
                            error_sources.append(src)
                yield f"data: {json.dumps({'type': 'token', 'chunk': answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': error_sources})}\n\n"
                return
            
            # Stream tokens
            full_answer = ""
            token_count = 0
            total_estimated_tokens = max_new_tokens  # Estimate for progress
            inside_reasoning = False
            reasoning_start_tag = selected_llm.model_settings.reasoning_start_tag if selected_llm.model_settings.reasoning else None
            reasoning_stop_tag = selected_llm.model_settings.reasoning_stop_tag if selected_llm.model_settings.reasoning else None
            answer_buffer = ""  # Buffer for answer content (excluding reasoning)
            
            try:
                logger.info(f"Starting to iterate over streamer, type: {type(streamer)}")
                token_iter_count = 0
                for token in streamer:
                    token_iter_count += 1
                    if token_iter_count == 1:
                        logger.info(f"First token received: {type(token)}, value: {str(token)[:100] if token else 'None'}")
                    if token is None:
                        logger.debug(f"Token {token_iter_count} is None, skipping")
                        continue
                    parsed_token = selected_llm.parse_token(token)
                    if not parsed_token:
                        logger.debug(f"Token {token_iter_count} parsed to empty, skipping")
                        continue
                    
                    # Check for reasoning tags
                    if selected_llm.model_settings.reasoning:
                        stripped_token = parsed_token.strip()
                        
                        # Check if we're entering reasoning mode
                        if reasoning_start_tag and reasoning_start_tag in stripped_token:
                            inside_reasoning = True
                            # Don't send reasoning start tag to client
                            continue
                        
                        # Check if we're exiting reasoning mode
                        if reasoning_stop_tag and reasoning_stop_tag in stripped_token:
                            inside_reasoning = False
                            # Don't send reasoning stop tag to client
                            continue
                        
                        # Skip tokens that are part of reasoning
                        if inside_reasoning:
                            # Still accumulate for full_answer but don't stream
                            full_answer += parsed_token
                            continue
                    
                    # This is actual answer content
                    full_answer += parsed_token
                    answer_buffer += parsed_token
                    token_count += 1
                    
                    # Send token to client
                    yield f"data: {json.dumps({'type': 'token', 'chunk': parsed_token})}\n\n"
                    
                    # Send progress update every 10 tokens
                    if token_count % 10 == 0:
                        progress = min(100, int((token_count / total_estimated_tokens) * 100))
                        yield f"data: {json.dumps({'type': 'progress', 'progress': progress, 'tokens': token_count})}\n\n"
                    
                    await asyncio.sleep(0.01)  # Small delay for smooth streaming
                
                logger.info(f"Finished iterating over streamer: {token_iter_count if 'token_iter_count' in locals() else 'unknown'} tokens iterated, {token_count} tokens accumulated")
                if 'token_iter_count' in locals() and token_iter_count == 0:
                    logger.error("CRITICAL: Streamer yielded no tokens at all! The generator is empty or not working.")
                elif 'token_iter_count' in locals() and token_count == 0 and token_iter_count > 0:
                    logger.warning(f"Streamer yielded {token_iter_count} tokens but none were accumulated (all filtered out or empty)")
                
                # Check for incomplete responses (cut off mid-sentence) in streaming
                if full_answer and not full_answer.strip().endswith(('.', '!', '?', ':', ';')):
                    last_char = full_answer.strip()[-1] if full_answer.strip() else ''
                    if last_char and last_char.isalnum():
                        logger.warning(f"Streaming response appears incomplete - ends with: '{full_answer[-50:]}' (last char: '{last_char}', tokens: {token_count})")
                        # Add period if substantial content exists
                        if len(full_answer.strip()) > 20:
                            full_answer = full_answer.strip() + "."
                            answer_buffer = answer_buffer.strip() + "."
                            logger.info("Added period to incomplete streaming response")
                    
            except Exception as stream_error:
                logger.error(f"Error during token streaming: {stream_error}", exc_info=True)
                logger.error(f"Token iteration count before error: {token_iter_count if 'token_iter_count' in locals() else 'not initialized'}")
                # If streaming fails, try to send what we have
                if not answer_buffer and not full_answer:
                    full_answer = "I encountered an error while generating the response. Please try again."
                else:
                    # Use answer_buffer if available (without reasoning), otherwise full_answer
                    full_answer = answer_buffer if answer_buffer else full_answer
            
            # Final reasoning extraction as fallback (in case tags weren't detected during streaming)
            if selected_llm.model_settings.reasoning and not answer_buffer:
                try:
                    full_answer = extract_content_after_reasoning(
                        full_answer, reasoning_stop_tag
                    )
                    if full_answer == "":
                        full_answer = "I didn't provide the answer; perhaps I can try again."
                except Exception as e:
                    logger.warning(f"Error extracting reasoning content: {e}")
            elif answer_buffer:
                # Use the answer buffer (which excludes reasoning)
                full_answer = answer_buffer
            
            # Clean answer
            try:
                cleaned = clean_answer_text(full_answer)
                if cleaned:  # Only use cleaned version if it's not empty
                    full_answer = cleaned
                else:
                    logger.warning(f"clean_answer_text returned empty, keeping original full_answer")
                
                # CRITICAL: Validate URLs in answer - only allow URLs that appear in context
                # Extract all URLs from context
                if retrieved_contents:
                    context_text = "\n".join([doc.page_content for doc in retrieved_contents[:5] if hasattr(doc, 'page_content')])
                    context_urls = set(re.findall(r'https?://[^\s\)]+', context_text, re.IGNORECASE))
                    
                    # Extract URLs from answer
                    answer_urls = re.findall(r'https?://[^\s\)]+', full_answer, re.IGNORECASE)
                    
                    # Remove URLs from answer that don't appear in context (likely from training data)
                    for url in answer_urls:
                        url_lower = url.lower()
                        # Check if this URL (or similar) appears in context
                        url_in_context = any(
                            url_lower in ctx_url.lower() or ctx_url.lower() in url_lower
                            for ctx_url in context_urls
                        )
                        
                        # Also check for known valid domains
                        valid_domains = [
                            'swisscottagesbhurban.com',
                            'airbnb.com',
                            'instagram.com',
                            'facebook.com',
                            'goo.gl/maps',
                            'maps.google.com'
                        ]
                        is_valid_domain = any(domain in url_lower for domain in valid_domains)
                        
                        if not url_in_context and not is_valid_domain:
                            # Remove this URL from answer
                            full_answer = full_answer.replace(url, "")
                            logger.warning(f"Removed URL from answer that's not in context: {url[:50]}")
                
                # Fix incorrect naming (Swiss Chalet, etc.)
                full_answer = fix_incorrect_naming(full_answer)
                
                # Fix question rephrasing
                full_answer = fix_question_rephrasing(full_answer, request.question)
                
                # CRITICAL: Detect and reject clearly wrong location answers BEFORE fixing
                rejected = detect_and_reject_wrong_location_answer(full_answer, request.question)
                if rejected is None:
                    # Answer was rejected - return error message
                    logger.error("Rejected wrong location answer in stream, returning error message")
                    full_answer = (
                        "I don't have accurate location information in my knowledge base for that query.\n\n"
                        "Swiss Cottages Bhurban is located in Bhurban, Murree, Pakistan. "
                        "For more details, please contact us directly.\n\n"
                        "[MAP] View on Google Maps: https://goo.gl/maps/PQbSR9DsuxwjxUoU6"
                    )
                else:
                    full_answer = rejected
                
                # Fix incorrect location mentions (Azad Kashmir, Patriata)
                full_answer = fix_incorrect_location_mentions(full_answer)
                
                # Final check for incomplete responses after cleaning
                if full_answer and not full_answer.strip().endswith(('.', '!', '?', ':', ';')):
                    last_char = full_answer.strip()[-1] if full_answer.strip() else ''
                    if last_char and last_char.isalnum() and len(full_answer.strip()) > 20:
                        logger.warning(f"Final answer appears incomplete after cleaning - ends with: '{full_answer[-50:]}'")
                        full_answer = full_answer.strip() + "."
                        logger.info("Added period to incomplete final answer")
                
                # CRITICAL: Additional aggressive check to remove structured pricing template if it still exists
                full_answer = remove_pricing_template_aggressively(full_answer)
            except Exception as e:
                logger.warning(f"Error cleaning answer text: {e}")
            
            # Validate currency
            try:
                context_text = "\n".join([doc.page_content for doc in retrieved_contents[:3]])
                validated = validate_and_fix_currency(full_answer, context_text)
                if validated:  # Only use validated version if it's not empty
                    full_answer = validated
                else:
                    logger.warning(f"validate_and_fix_currency returned empty, keeping original full_answer")
            except Exception as e:
                logger.warning(f"Error validating currency: {e}")
            
            # Final safeguard: ensure full_answer is not empty
            if not full_answer or not full_answer.strip():
                logger.error(f"full_answer is empty after processing! answer_buffer={answer_buffer[:100] if answer_buffer else 'empty'}, token_count={token_count}")
                # Try to use answer_buffer if available
                if answer_buffer and answer_buffer.strip():
                    full_answer = answer_buffer
                    logger.info(f"Using answer_buffer as fallback: {answer_buffer[:100]}")
                else:
                    full_answer = "I'm sorry, I encountered an issue generating the response. Please try asking your question again."
                    logger.warning("Both full_answer and answer_buffer are empty, using fallback message")
            
            # Filter out generic requests for group size when it's already known from capacity query
            try:
                if capacity_result and capacity_result.get("group_size") is not None:
                    group_size = capacity_result.get("group_size")
                    # Remove phrases that ask for group size/guests when it's already known
                    phrases_to_remove = [
                        r"share your dates,?\s*(?:number of\s*)?guests(?:,?\s*and preferences)?",
                        r"number of\s*guests(?:,?\s*and preferences)?",
                        r"how many\s*guests",
                        r"how many\s*people",
                        r"number of\s*people",
                        r"guests?\s*(?:and\s*)?preferences",
                        r"dates,?\s*(?:number of\s*)?guests(?:,?\s*and preferences)?",
                    ]
                    for phrase in phrases_to_remove:
                        # Replace with just asking for dates and preferences (not guests)
                        full_answer = re.sub(
                            phrase,
                            "dates and preferences",
                            full_answer,
                            flags=re.IGNORECASE
                        )
                    # Also replace specific patterns that include "guests" in the request
                    full_answer = re.sub(
                        r"share your\s+(?:dates,?\s*)?(?:number of\s*)?guests(?:,?\s*and preferences)?",
                        "share your dates and preferences",
                        full_answer,
                        flags=re.IGNORECASE
                    )
                    full_answer = re.sub(
                        r"yes!?\s*share your\s+(?:dates,?\s*)?(?:number of\s*)?guests(?:,?\s*and preferences)?",
                        "Yes! To recommend the best cottage for your stay, please share your dates and preferences",
                        full_answer,
                        flags=re.IGNORECASE
                    )
                    logger.info(f"Filtered out group size requests from streaming answer (group_size={group_size} already known)")
                
                # Filter out "not available" responses for availability queries
                if intent == IntentType.AVAILABILITY or any(word in request.question.lower() for word in ["available", "availability", "can i book", "can we stay", "we want to stay", "we were stay"]):
                    # Replace negative availability responses with positive ones
                    negative_patterns = [
                        r"(?:options?|cottages?|cottage \d+)\s+(?:for|are)\s+(?:staying|staying at|booking)\s+(?:are\s+)?not\s+available",
                        r"not\s+available\s+(?:for|to stay|for staying)",
                        r"(?:options?|cottages?)\s+are\s+not\s+available",
                    ]
                    for pattern in negative_patterns:
                        if re.search(pattern, full_answer, flags=re.IGNORECASE):
                            # Replace with positive availability message
                            full_answer = re.sub(
                                pattern,
                                "are available throughout the year, subject to availability. To confirm your booking",
                                full_answer,
                                flags=re.IGNORECASE
                            )
                            logger.info("Replaced negative availability response with positive availability confirmation in stream")
                    
                    # Also check for phrases like "For [dates], the options... are not available"
                    if re.search(r"for\s+.*?the\s+options?.*?are\s+not\s+available", full_answer, flags=re.IGNORECASE):
                        # Extract dates if mentioned
                        date_match = re.search(r"for\s+([^,]+?)(?:,|\.|$)", full_answer, flags=re.IGNORECASE)
                        if date_match:
                            dates = date_match.group(1).strip()
                            full_answer = re.sub(
                                r"for\s+.*?the\s+options?.*?are\s+not\s+available",
                                f"for {dates}, Swiss Cottages are available throughout the year, subject to availability. To confirm your booking",
                                full_answer,
                                flags=re.IGNORECASE
                            )
                            logger.info(f"Replaced negative availability response with positive confirmation for dates in stream: {dates}")
            except Exception as e:
                logger.warning(f"Error filtering group size requests: {e}")
            
            # Get cottage images if requested
            cottage_image_urls = None
            if is_image_request and cottage_numbers:
                dropbox_config = get_dropbox_config()
                use_dropbox = dropbox_config.get("use_dropbox", False)
                all_images = []
                
                if use_dropbox:
                    for cottage_num in cottage_numbers:
                        dropbox_urls = get_dropbox_image_urls(cottage_num, max_images=6)
                        if dropbox_urls:
                            all_images.extend(dropbox_urls)
                else:
                    root_folder = get_root_folder()
                    for cottage_num in cottage_numbers:
                        images = get_cottage_images(cottage_num, root_folder, max_images=6)
                        for img_path in images:
                            rel_path = img_path.relative_to(root_folder)
                            from urllib.parse import quote
                            encoded_path = str(rel_path).replace('\\', '/')
                            url_path = '/'.join(quote(part, safe='') for part in encoded_path.split('/'))
                            image_url = f"/images/{url_path}"
                            all_images.append(image_url)
                
                cottage_image_urls = all_images[:6]
            
            # Format sources for JSON serialization
            sources_list = []
            for src in sources[:effective_k]:
                if isinstance(src, dict):
                    sources_list.append(src)
                else:
                    # Convert SourceInfo to dict
                    sources_list.append({
                        'document': src.document if hasattr(src, 'document') else str(src.get('document', 'unknown')),
                        'score': str(src.score) if hasattr(src, 'score') and src.score else src.get('score', 'N/A'),
                        'content_preview': src.content_preview if hasattr(src, 'content_preview') else src.get('content_preview', '')
                    })
            
            # Add proactive image offer for cottage-specific queries (streaming)
            should_offer, cottage_num = should_offer_images(request.question, full_answer)
            if should_offer and cottage_num and not is_image_request:
                image_offer = f"\n\n📷 **Would you like to see images of Cottage {cottage_num}?** Just say 'yes' or 'show images'."
                full_answer += image_offer
                # Store in session for "yes" handling
                session_manager.set_session_data(request.session_id, "image_offer_cottage", cottage_num)
                logger.info(f"Added image offer for Cottage {cottage_num} in stream")
            
            # Add booking nudge if enough info available (streaming)
            if slot_manager.has_enough_booking_info():
                recommendation_engine = get_recommendation_engine()
                nudge = recommendation_engine.generate_booking_nudge(
                    slot_manager.get_slots(), 
                    context_tracker,
                    intent
                )
                if nudge:
                    full_answer += f"\n\n{nudge}"
            
            # Update chat history
            chat_history.append(f"question: {refined_question}, answer: {full_answer}")
            
            # Generate follow-up actions
            # Convert chat_history to list format for recommendations
            chat_history_list = list(chat_history) if chat_history else []
            follow_up_actions = generate_follow_up_actions(
                intent,
                slot_manager.get_slots(),
                request.question,
                context_tracker=context_tracker,
                chat_history=chat_history_list,
                llm_client=selected_llm,
                is_widget_query=is_widget_query
            )
            
            # Send completion
            completion_data = {
                'type': 'done',
                'answer': full_answer,
                'sources': sources_list,
                'cottage_images': cottage_image_urls,
                'follow_up_actions': follow_up_actions
            }
            yield f"data: {json.dumps(completion_data)}\n\n"
            
        except Exception as e:
            logger.error(f"Error in streaming endpoint: {e}", exc_info=True)
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Full traceback: {error_details}")
            yield f"data: {json.dumps({'type': 'error', 'message': f'An error occurred: {str(e)}'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


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


@app.post("/api/voice")
async def voice_chat(
    audio: bytes = None,
    session_id: str = None,
):
    """HTTP fallback endpoint for voice conversation."""
    from fastapi import UploadFile, File, Form
    
    try:
        # This is a placeholder - actual implementation would use Form data
        # For now, return error suggesting WebSocket
        return JSONResponse(
            status_code=501,
            content={"error": "HTTP voice endpoint not fully implemented. Please use WebSocket /ws/voice"}
        )
    except Exception as e:
        logger.error(f"Error in voice endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/favicon.ico")
async def favicon():
    """Handle favicon requests to prevent 404 errors."""
    return Response(status_code=204)  # No Content


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "RAG Chatbot API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.websocket("/ws/voice")
async def websocket_voice_conversation(websocket: WebSocket):
    """WebSocket endpoint for voice conversation."""
    await websocket.accept()
    
    try:
        # Send connected message immediately
        await websocket.send_json({"type": "connected", "message": "WebSocket connected"})
        
        # Initialize speech modules and LLM dependencies asynchronously
        logger.info("Initializing speech modules...")
        await websocket.send_json({"type": "status", "message": "Initializing speech modules..."})
        
        # Initialize STT, TTS, and VAD
        stt = GroqSTT()
        tts = GroqTTS()
        vad = VoiceActivityDetector()
        
        await websocket.send_json({"type": "status", "message": "Speech modules initialized"})
        
        # Initialize LLM and vector store
        logger.info("Initializing LLM and vector store...")
        await websocket.send_json({"type": "status", "message": "Initializing LLM and vector store..."})
        
        llm = get_llm_client()
        vector_store = get_vector_store()
        intent_router = get_intent_router()
        ctx_synthesis_strategy = get_ctx_synthesis_strategy("create-and-refine")
        
        await websocket.send_json({"type": "ready", "message": "All dependencies initialized"})
        logger.info("All dependencies initialized, ready for voice conversation")
        
        # Wait for init message from client
        init_data = await websocket.receive_json()
        if init_data.get("type") != "init":
            await websocket.send_json({"type": "error", "message": "Expected init message"})
            return
        
        session_id = init_data.get("session_id", "default_session")
        chat_history = session_manager.get_or_create_session(session_id, total_length=2)
        # Initialize slot manager for voice endpoint (same as text endpoint)
        slot_manager = session_manager.get_or_create_slot_manager(session_id, llm)
        
        # Main conversation loop
        while True:
            try:
                # Receive audio data
                data = await websocket.receive()
                
                if "bytes" in data:
                    # Audio data received
                    audio_bytes = data["bytes"]
                    
                    try:
                        # Save WAV audio to temp file (Web Audio API sends WAV directly)
                        tmp_audio_path = None
                        try:
                            # Validate audio bytes before processing
                            if not audio_bytes or len(audio_bytes) < 100:
                                await websocket.send_json({
                                    "type": "error",
                                    "message": "Invalid audio data - please try speaking again"
                                })
                                continue
                            
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_audio:
                                tmp_audio.write(audio_bytes)
                                tmp_audio_path = tmp_audio.name
                            
                            # Verify file was written correctly
                            if not os.path.exists(tmp_audio_path) or os.path.getsize(tmp_audio_path) == 0:
                                await websocket.send_json({
                                    "type": "error",
                                    "message": "Failed to process audio - please try speaking again"
                                })
                                continue
                            
                            logger.info(f"📁 Saved WAV file: {tmp_audio_path}, size: {os.path.getsize(tmp_audio_path)} bytes")
                            
                            # Transcribe the WAV file
                            transcribed_text = stt.transcribe(tmp_audio_path, language="en", temperature=0.0)
                            print(f"🎤 STT Transcribed text: {transcribed_text}")
                            
                        except Exception as file_error:
                            # Catch any file-related errors
                            logger.error(f"Error processing audio file: {file_error}")
                            await websocket.send_json({
                                "type": "error",
                                "message": "Error processing audio - please try speaking again"
                            })
                            continue
                        finally:
                            # Clean up temporary file
                            if tmp_audio_path and os.path.exists(tmp_audio_path):
                                try:
                                    os.unlink(tmp_audio_path)
                                except Exception:
                                    pass
                        
                        # Validate transcription - reject very short or common false positives
                        transcribed_text_clean = transcribed_text.strip().lower() if transcribed_text else ""
                        
                        # Reject common false positives from silence/noise
                        false_positives = ["thank you", "thanks", "ok", "okay", "yes", "no", "uh", "um", "ah", "hmm"]
                        
                        if not transcribed_text or len(transcribed_text.strip()) < 3:
                            await websocket.send_json({
                                "type": "error",
                                "message": "No speech detected in audio"
                            })
                            continue
                        
                        # Reject if transcription is just a false positive (likely noise/silence)
                        if transcribed_text_clean in false_positives:
                            await websocket.send_json({
                                "type": "error",
                                "message": "No meaningful speech detected (likely background noise)"
                            })
                            continue
                        
                        # Refine question (same as text endpoint - with max_new_tokens)
                        max_new_tokens = 128  # Default for refinement (same as text endpoint)
                        refined_question = refine_question(
                            llm, transcribed_text, chat_history=chat_history, max_new_tokens=max_new_tokens
                        )
                        print(f"🔍 Refined question: {refined_question}")
                        logger.info(f"Original query: {transcribed_text}")
                        logger.info(f"Refined query: {refined_question}")
                        
                        # Classify intent
                        intent = intent_router.classify(refined_question, chat_history)
                        intent_type = intent.value if hasattr(intent, 'value') else str(intent)
                        print(f"🎯 Intent: {intent_type}")
                        
                        # Extract slots (same as text endpoint)
                        extracted_slots = slot_manager.extract_slots(transcribed_text, intent)
                        slot_manager.update_slots(extracted_slots)
                        
                        # Handle different intents (same as text endpoint)
                        if intent == IntentType.GREETING:
                            answer = (
                                "Hi! 👋 How may I help you today? I can help you with information about Swiss Cottages Bhurban, including:\n"
                                "- Pricing and availability\n"
                                "- Facilities and amenities\n"
                                "- Location and nearby attractions\n"
                                "- Booking and payment information\n\n"
                                "What would you like to know?"
                            )
                            await websocket.send_json({
                                "type": "answer",
                                "text": answer,
                                "intent": intent_type
                            })
                            chat_history.append(f"question: {refined_question}, answer: {answer}")
                            continue
                        
                        elif intent == IntentType.HELP:
                            answer = (
                                "I can help you with information about Swiss Cottages Bhurban! Here's what I can assist with:\n\n"
                                "🏡 **Property Information:**\n"
                                "- Cottage details and amenities\n"
                                "- Pricing and availability\n"
                                "- Location and nearby attractions\n\n"
                                "📞 **Contact Information:**\n"
                                "- Booking inquiries\n"
                                "- Payment information\n"
                                "- Special requests\n\n"
                                "💡 **Tips:**\n"
                                "- Ask specific questions for better answers\n"
                                "- I can help with booking information\n"
                                "- Feel free to ask about facilities, pricing, or location\n\n"
                                "What would you like to know?"
                            )
                            await websocket.send_json({
                                "type": "answer",
                                "text": answer,
                                "intent": intent_type
                            })
                            chat_history.append(f"question: {refined_question}, answer: {answer}")
                            continue
                        
                        # Query optimization for better RAG retrieval (same as text endpoint)
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
                        
                        print(f"🔎 Vector search query: {search_query}")
                        
                        # Determine effective k (same as text endpoint)
                        effective_k = 3  # Default k value (matches text endpoint)
                        query_lower = transcribed_text.lower()
                        
                        # Increase k for availability queries
                        if any(word in query_lower for word in ["available", "availability", "which cottages", "which cottage", "vacant", "vacancy"]):
                            effective_k = max(effective_k, 5)
                            logger.info(f"Increased k to {effective_k} for availability query")
                        
                        # Increase k for payment/pricing/booking queries
                        if any(word in query_lower for word in ["payment", "price", "pricing", "cost", "rate", "methods", "book", "booking", "reserve"]):
                            effective_k = max(effective_k, 5)
                            logger.info(f"Increased k to {effective_k} for payment/pricing/booking query")
                        
                        # Increase k for cottage-specific queries
                        if any(cottage in query_lower for cottage in ["cottage 7", "cottage 9", "cottage 11", "cottage7", "cottage9", "cottage11"]):
                            effective_k = max(effective_k, 5)
                            logger.info(f"Increased k to {effective_k} for cottage-specific query")
                        
                        # Increase k for facility/amenity queries and general "tell me about" queries
                        if any(word in query_lower for word in ["cook", "kitchen", "facility", "amenity", "amenities", "facilities", "what", "tell me about", "information about", "about cottages", "about the cottages"]):
                            effective_k = max(effective_k, 5)
                            logger.info(f"Increased k to {effective_k} for facility/amenity/general query")
                        
                        # Increase k for group size/capacity queries
                        if any(word in query_lower for word in ["member", "members", "people", "person", "persons", "guest", "guests", "group", "suitable", "best for", "accommodate", "capacity"]):
                            effective_k = max(effective_k, 5)
                            logger.info(f"Increased k to {effective_k} for group size/capacity query")
                        
                        # Retrieve documents (same logic as text endpoint with deduplication)
                        retrieved_contents = []
                        sources = []
                        
                        try:
                            # Retrieve more documents than needed to ensure diversity (same as text endpoint)
                            retrieved_contents, sources = vector_store.similarity_search_with_threshold(
                                query=search_query, k=min(effective_k * 3, 15), threshold=0.0  # Get 3x more for deduplication
                            )
                            logger.info(f"Retrieved {len(retrieved_contents)} documents with search query")
                            
                            # Deduplicate by source to ensure diversity (same as text endpoint)
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
                                retrieved_docs = vector_store.similarity_search(query=search_query, k=min(effective_k * 3, 15))
                                # Deduplicate
                                seen_sources = set()
                                unique_contents = []
                                unique_sources = []
                                for doc in retrieved_docs:
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
                        
                        # If no results, try original query (same as text endpoint)
                        if not retrieved_contents:
                            logger.info("No results with optimized query, trying original query")
                            try:
                                retrieved_contents, sources = vector_store.similarity_search_with_threshold(
                                    query=transcribed_text, k=effective_k, threshold=0.0
                                )
                            except Exception as e:
                                try:
                                    retrieved_contents = vector_store.similarity_search(query=transcribed_text, k=effective_k)
                                    sources = [
                                        {
                                            "score": "N/A",
                                            "document": doc.metadata.get("source", "unknown"),
                                            "content_preview": f"{doc.page_content[0:256]}..."
                                        }
                                        for doc in retrieved_contents
                                    ]
                                except Exception as e2:
                                    logger.error(f"Error with fallback search: {e2}")
                                    retrieved_contents = []
                                    sources = []
                        
                        print(f"📚 Retrieved {len(retrieved_contents)} documents")
                        
                        if not retrieved_contents:
                            answer = (
                                "I couldn't find specific information about that in our knowledge base.\n\n"
                                "💡 **Please try:**\n"
                                "- Rephrasing your question\n"
                                "- Using different keywords\n"
                                "- Being more specific about Swiss Cottages Bhurban\n"
                            )
                            await websocket.send_json({
                                "type": "answer",
                                "text": answer,
                                "intent": intent_type
                            })
                            chat_history.append(f"question: {refined_question}, answer: {answer}")
                            continue
                        
                        # Convert documents to Document objects if needed (already done above)
                        # Ensure all are Document objects
                        final_contents = []
                        for doc in retrieved_contents:
                            if hasattr(doc, 'page_content'):
                                # Already a Document object
                                final_contents.append(doc)
                            else:
                                # Convert from dict
                                final_contents.append(Document(
                                    page_content=doc.get('page_content', '') if isinstance(doc, dict) else str(doc),
                                    metadata=doc.get('metadata', {}) if isinstance(doc, dict) else {}
                                ))
                        
                        # Generate answer with context (same as text endpoint)
                        max_new_tokens = 512  # Same as text endpoint default
                        
                        # Enhance question with slot information for pricing/booking queries (same as text endpoint)
                        enhanced_question = refined_question
                        if intent in [IntentType.PRICING, IntentType.BOOKING] and slot_manager.get_slots():
                            slots = slot_manager.get_slots()
                            slot_info_parts = []
                            if slots.get("nights"):
                                slot_info_parts.append(f"for {slots['nights']} nights")
                            if slots.get("guests"):
                                slot_info_parts.append(f"for {slots['guests']} guests")
                            if slots.get("room_type"):
                                slot_info_parts.append(f"in {slots['room_type']}")
                            if slot_info_parts:
                                # Append slot info to question to make it explicit for LLM
                                enhanced_question = f"{refined_question} ({', '.join(slot_info_parts)})"
                        
                        streamer, _ = answer_with_context(
                            llm,
                            ctx_synthesis_strategy,
                            enhanced_question,  # Use enhanced question with slot info
                            chat_history,
                            final_contents,
                            max_new_tokens,
                        )
                        
                        # Collect answer from streamer
                        answer = ""
                        print(f"🤖 LLM generating response...")
                        for token in streamer:
                            parsed_token = llm.parse_token(token)
                            answer += parsed_token
                        
                        # Handle reasoning models
                        if llm.model_settings.reasoning:
                            answer = extract_content_after_reasoning(
                                answer, llm.model_settings.reasoning_stop_tag
                            )
                        
                        # Clean answer text
                        answer = clean_answer_text(answer)
                        
                        # Validate currency
                        context_text = "\n".join([doc.page_content for doc in retrieved_contents[:3]])
                        answer = validate_and_fix_currency(answer, context_text)
                        
                        print(f"✅ LLM Response: {answer[:200]}...")
                        
                        # Update chat history
                        chat_history.append(f"question: {refined_question}, answer: {answer}")
                        
                        # Validate answer before TTS
                        answer_lower = answer.lower().strip()
                        if not answer or len(answer) < 10:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Answer too short, skipping TTS"
                            })
                            continue
                        
                        # Check for "no information" indicators
                        no_info_phrases = [
                            "i don't know",
                            "i cannot",
                            "i'm not able",
                            "i don't have",
                            "no information",
                            "couldn't find"
                        ]
                        if any(phrase in answer_lower for phrase in no_info_phrases) and len(answer) < 50:
                            await websocket.send_json({
                                "type": "answer",
                                "text": answer,
                                "question": transcribed_text,  # Include the user's question
                                "intent": intent_type
                            })
                            continue
                        
                        # Generate TTS audio
                        print(f"🔊 Generating TTS audio for answer...")
                        tts_audio_bytes = tts.synthesize(answer)
                        
                        # Send answer text and audio, including the user's question
                        audio_base64 = base64.b64encode(tts_audio_bytes).decode('utf-8')
                        await websocket.send_json({
                            "type": "answer",
                            "text": answer,
                            "audio": audio_base64,
                            "question": transcribed_text,  # Include the user's question
                            "intent": intent_type
                        })
                        
                    except Exception as e:
                        logger.error(f"Error processing voice input: {e}", exc_info=True)
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Error processing audio: {str(e)}"
                        })
                    finally:
                        # Clean up temporary files if they were created
                        cleanup_paths = []
                        if 'tmp_audio_path' in locals() and tmp_audio_path:
                            cleanup_paths.append(tmp_audio_path)
                        
                        for path in cleanup_paths:
                            try:
                                if path and os.path.exists(path):
                                    os.unlink(path)
                            except Exception:
                                pass
                
                elif "text" in data:
                    # Text message (for control messages)
                    message = json.loads(data["text"])
                    if message.get("type") == "cancel":
                        # Client requested cancellation
                        await websocket.send_json({"type": "cancelled"})
                
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "message": f"Internal error: {str(e)}"
                })
    
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during initialization")
    except Exception as e:
        logger.error(f"Error in WebSocket endpoint: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Initialization error: {str(e)}"
            })
        except:
            pass
