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
    get_root_folder,
    clear_vector_store_cache,
)
from bot.conversation.tools import get_tools_config, get_tools_map
from bot.conversation.conversation_handler import refine_question

logger = get_logger(__name__)


def is_greeting_or_small_talk(query: str) -> bool:
    """
    Simple greeting/small talk detection (replaces Intent Router).
    
    Args:
        query: User query string
        
    Returns:
        True if query is greeting or small talk
    """
    query_lower = query.lower().strip()
    greetings = ["hi", "hello", "hey", "greetings", "good morning", "good afternoon", "good evening"]
    small_talk = ["thanks", "thank you", "ok", "okay", "yes", "no", "bye", "goodbye"]
    return query_lower in greetings or query_lower in small_talk or len(query_lower.split()) <= 2


async def simplified_chat_handler(
    question: str,
    session_id: str,
    vector_store,
    fast_llm,
    reasoning_llm,
    tools_config: list,
    tools_map: dict,
    enable_dual_model: bool = True
) -> Dict[str, Any]:
    """
    Simplified chat handler following the new architecture flowchart.
    
    Args:
        question: User question
        session_id: Session ID for chat history
        vector_store: Vector store instance
        fast_llm: Fast LLM client
        reasoning_llm: Reasoning LLM client
        tools_config: Tools configuration for LLM
        tools_map: Tools function map
        enable_dual_model: Whether to use dual model strategy
        
    Returns:
        Dictionary with answer, sources, and metadata
    """
    # Step 1: Check for greeting/small talk
    if is_greeting_or_small_talk(question):
        greeting_responses = {
            "hi": "Hi! 👋 How may I help you today?",
            "hello": "Hello! 👋 How can I assist you with Swiss Cottages Bhurban?",
            "hey": "Hey there! 👋 What would you like to know?",
            "thanks": "You're welcome! Is there anything else I can help with?",
            "thank you": "You're welcome! Feel free to ask if you need anything else.",
        }
        query_lower = question.lower().strip()
        for key, response in greeting_responses.items():
            if key in query_lower:
                return {
                    "answer": response,
                    "sources": [],
                    "intent": "greeting"
                }
        return {
            "answer": "Hi! 👋 How may I help you today?",
            "sources": [],
            "intent": "greeting"
        }
    
    # Step 2: Enhance query using chat history
    chat_history = session_manager.get_or_create_session(session_id, total_length=2)
    enhanced_query = refine_question(fast_llm, question, chat_history, max_new_tokens=128)
    logger.info(f"Enhanced query: {enhanced_query}")
    
    # Step 3: RAG Retrieval - Top 3 FAQs
    try:
        retrieved_docs = vector_store.similarity_search(
            query=enhanced_query,
            k=3
        )
        logger.info(f"Retrieved {len(retrieved_docs)} documents")
    except Exception as e:
        logger.error(f"Error in vector search: {e}")
        retrieved_docs = []
    
    # Step 4: Prepare context block
    context_parts = []
    sources = []
    for doc in retrieved_docs:
        faq_id = doc.metadata.get("id", "unknown")
        category = doc.metadata.get("category", "")
        context_parts.append(
            f"FAQ #{faq_id} - {category}\n{doc.page_content}"
        )
        sources.append({
            "id": faq_id,
            "category": category,
            "question": doc.metadata.get("question", ""),
            "content": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
        })
    
    context = "\n\n".join(context_parts) if context_parts else "No relevant information found."
    
    # Step 5: Send to LLM with tools enabled
    # Model selection based on ENABLE_DUAL_MODEL
    if enable_dual_model:
        initial_llm = fast_llm
    else:
        initial_llm = reasoning_llm
    
    # Build prompt with context
    prompt = f"""You are a helpful assistant for Swiss Cottages Bhurban.

Context from FAQs:
{context}

User Question: {enhanced_query}

Answer the question based on the context above. If you need to calculate pricing or check capacity, use the available tools."""
    
    # Send to LLM with tools enabled
    try:
        response = initial_llm.client.chat.completions.create(
            model=initial_llm.model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Use tools when needed."},
                {"role": "user", "content": prompt}
            ],
            tools=tools_config,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=512
        )
        
        message = response.choices[0].message
        tool_calls = message.tool_calls
        
        # Step 6: Tool execution & final answer generation
        if tool_calls:
            # LLM called a tool - execute it
            tool_results = []
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                tool_func = tools_map.get(function_name)
                
                if tool_func:
                    try:
                        tool_result = tool_func(**function_args)
                        tool_results.append({
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "result": tool_result
                        })
                    except Exception as e:
                        logger.error(f"Error executing tool {function_name}: {e}")
                        tool_results.append({
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "result": json.dumps({"error": str(e)})
                        })
                else:
                    logger.warning(f"Tool function not found: {function_name}")
            
            # Determine which model to use for final answer
            if enable_dual_model:
                final_llm = reasoning_llm  # Switch to reasoning model after tool execution
            else:
                final_llm = initial_llm
            
            # Send tool results back to LLM for final answer
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
                message,  # Original message with tool calls
            ]
            
            # Add tool results
            for tool_call, tool_result in zip(tool_calls, tool_results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_result["tool_call_id"],
                    "content": tool_result["result"]
                })
            
            # Get final answer from LLM
            final_response = final_llm.client.chat.completions.create(
                model=final_llm.model_name,
                messages=messages,
                tools=tools_config,
                temperature=0.7,
                max_tokens=512
            )
            answer = final_response.choices[0].message.content
        else:
            # No tool needed - use direct response
            answer = message.content if message.content else "I apologize, but I couldn't generate a response."
        
        # Update chat history
        chat_history.append(f"User: {question}\nAssistant: {answer}")
        
        return {
            "answer": answer,
            "sources": sources,
            "intent": "faq_question"
        }
        
    except Exception as e:
        logger.error(f"Error in LLM call: {e}", exc_info=True)
        
        # Check if it's a tool calling error - if so, try without tools
        error_str = str(e).lower()
        if "tool" in error_str or "function" in error_str:
            logger.warning("Tool calling failed, retrying without tools...")
            try:
                # Retry without tools - just use context directly
                response = initial_llm.client.chat.completions.create(
                    model=initial_llm.model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant for Swiss Cottages Bhurban."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=512
                )
                answer = response.choices[0].message.content
                if answer:
                    chat_history.append(f"User: {question}\nAssistant: {answer}")
                    return {
                        "answer": answer,
                        "sources": sources,
                        "intent": "faq_question"
                    }
            except Exception as retry_error:
                logger.error(f"Error in retry without tools: {retry_error}")
        
        return {
            "answer": "I apologize, but I encountered an error processing your question. Please try again.",
            "sources": sources,
            "intent": "error"
        }


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
    vector_store=Depends(get_vector_store),
    fast_llm=Depends(get_fast_llm_client),
    reasoning_llm=Depends(get_reasoning_llm_client),
):
    """Simplified chat endpoint following new architecture."""
    try:
        # Get tools configuration
        tools_config = get_tools_config()
        tools_map = get_tools_map()
        
        # Check if dual model is enabled
        enable_dual_model = os.getenv("ENABLE_DUAL_MODEL", "false").lower() == "true"
        
        # Call simplified chat handler
        result = await simplified_chat_handler(
            question=request.question,
            session_id=request.session_id,
            vector_store=vector_store,
            fast_llm=fast_llm,
            reasoning_llm=reasoning_llm,
            tools_config=tools_config,
            tools_map=tools_map,
            enable_dual_model=enable_dual_model
        )
        
        # Format sources
        source_infos = []
        for source in result.get("sources", []):
            source_infos.append(SourceInfo(
                id=source.get("id", ""),
                category=source.get("category", ""),
                question=source.get("question", ""),
                content=source.get("content", "")
            ))
        
        return ChatResponse(
            answer=result.get("answer", ""),
            sources=source_infos,
            intent=result.get("intent", "faq_question"),
            session_id=request.session_id
        )
    
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    llm=Depends(get_llm_client),
    vector_store=Depends(get_vector_store),
):
    """Streaming chat endpoint using Server-Sent Events."""
    async def generate():
        try:
            # Use simplified_chat_handler for the new simplified flow
            from api.dependencies import get_tools_config, get_tools_map
            tools_config = get_tools_config()
            tools_map = get_tools_map()
            enable_dual_model = os.getenv("ENABLE_DUAL_MODEL", "true").lower() == "true"
            
            result = await simplified_chat_handler(
                question=request.question,
                session_id=request.session_id,
                vector_store=vector_store,
                fast_llm=get_fast_llm_client(),
                reasoning_llm=get_reasoning_llm_client(),
                tools_config=tools_config,
                tools_map=tools_map,
                enable_dual_model=enable_dual_model
            )
            
            # Stream the response
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            
            # Format sources
            source_infos = []
            for source in sources:
                if isinstance(source, dict):
                    source_infos.append(source)
                else:
                    source_infos.append({"content": str(source)})
            
            # Stream the answer
            for chunk in answer.split():
                yield f"data: {json.dumps({'type': 'token', 'content': chunk + ' '})}\n\n"
            
            # Send completion
            yield f"data: {json.dumps({'type': 'done', 'sources': source_infos})}\n\n"
        
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
        logger.error(f"Error clearing session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


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
            "message": f"Vector store reloaded successfully. {doc_count} documents loaded.",
            "document_count": doc_count
        }
    except Exception as e:
        logger.error(f"Error reloading vector store: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error reloading vector store: {str(e)}")


@app.websocket("/ws/voice")
async def websocket_voice_conversation(websocket: WebSocket):
    """WebSocket endpoint for voice conversation."""
    await websocket.accept()
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
