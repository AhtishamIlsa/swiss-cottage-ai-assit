"""
Intent Router Module

This module provides intent classification and routing for the RAG chatbot.
It determines whether a query should:
- Return a fixed response (greeting, help, etc.)
- Go to RAG retrieval (FAQ questions)
- Be handled as a statement/acknowledgment

Design principles:
- Lightweight pattern matching first
- LLM classification as fallback for ambiguous cases
- No hardcoded responses per sentence
- Production-ready and scalable
"""

from enum import Enum
from typing import Optional
from helpers.log import get_logger
from bot.client.lama_cpp_client import LamaCppClient
from bot.conversation.chat_history import ChatHistory

logger = get_logger(__name__)


class IntentType(Enum):
    """Intent types for query classification."""
    GREETING = "greeting"
    HELP = "help"
    FAQ_QUESTION = "faq_question"
    STATEMENT = "statement"
    AFFIRMATIVE = "affirmative"
    NEGATIVE = "negative"
    CLARIFICATION_NEEDED = "clarification_needed"
    UNKNOWN = "unknown"


class IntentRouter:
    """
    Intent router that classifies user queries and routes them appropriately.
    
    Flow:
    1. Pattern matching (fast, lightweight)
    2. LLM classification (fallback for ambiguous cases)
    3. Route to appropriate handler
    """
    
    def __init__(self, llm: Optional[LamaCppClient] = None, use_llm_fallback: bool = True):
        """
        Initialize the intent router.
        
        Args:
            llm: LLM client for classification fallback (optional)
            use_llm_fallback: Whether to use LLM for ambiguous queries
        """
        self.llm = llm
        self.use_llm_fallback = use_llm_fallback
        
        # Pattern-based intent detection (fast path)
        self.greeting_patterns = [
            "hi", "hello", "hey", "greetings", "good morning", "good afternoon", "good evening",
            "hlo", "helo", "hii", "hiii", "heyy", "heyyy",  # Common typos
            "hiya", "howdy", "sup", "yo",
        ]
        
        self.help_patterns = [
            "how can you help", "how you can help", "how can you assist", "how you can assist",
            "what can you help", "what you can help", "what can you assist", "what you can assist",
            "how do you help", "how do you assist",
            "what do you do", "what can you do",
            "how can i", "what help", "can you help", "can you assist",
        ]
        
        self.affirmative_patterns = ["yes", "yeah", "yep", "yup", "sure"]
        
        self.negative_patterns = ["no", "nope", "nah", "not really", "nothing", "nothing else"]
        
        self.statement_patterns = [
            "great", "good", "nice", "awesome", "excellent", "perfect", "wonderful",
            "thanks", "thank you", "thx", "thank", "appreciate",
            "ok", "okay", "alright", "fine", "got it", "understood",
            "that's helpful", "that helps", "helpful", "useful",
            "good to know", "i see", "i understand",
            "cool", "nice one", "well done",
        ]
        
        # Confirmation patterns (statements that confirm understanding)
        self.confirmation_patterns = [
            "so it", "so they", "so that", "so this", "so these",
            "i see", "i understand", "got it", "makes sense",
            "that's clear", "that makes sense",
        ]
        
        # Topic keywords that should go directly to FAQ retrieval
        self.topic_keywords = [
            "pricing", "price", "cost", "rates", "rate",
            "location", "address", "where",
            "facilities", "amenities", "features",
            "booking", "book", "reservation",
            "payment", "pay", "methods",
            "availability", "available",
        ]
        
    
    def classify(self, query: str, chat_history: Optional[ChatHistory] = None) -> IntentType:
        """
        Classify the intent of a user query.
        
        Args:
            query: User query string
            chat_history: Optional chat history for context
            
        Returns:
            IntentType: The classified intent
        """
        query_lower = query.lower().strip()
        words = query_lower.split()
        
        # Fast path: Pattern matching
        intent = self._pattern_match(query_lower, words, original_query=query)
        if intent:
            return intent
        
        # Fallback: LLM classification for ambiguous queries
        if self.use_llm_fallback and self.llm and len(words) <= 8:
            intent = self._llm_classify(query, chat_history)
            if intent:
                logger.debug(f"LLM classified '{query}' as: {intent.value}")
                return intent
            else:
                # LLM classification failed or returned None, default to question (safer)
                logger.debug(f"LLM classification returned None for '{query}', defaulting to FAQ_QUESTION")
        
        # SAFER DEFAULT: Treat as FAQ question when uncertain
        # This prevents misclassifying questions as statements
        # Better to retrieve and potentially find nothing than to miss a real question
        logger.debug(f"Default classification for '{query}': FAQ_QUESTION")
        return IntentType.FAQ_QUESTION
    
    def _pattern_match(self, query_lower: str, words: list, original_query: str = None) -> Optional[IntentType]:
        """
        Fast pattern matching for intent detection.
        
        Args:
            query_lower: Lowercase query string
            words: List of words in the query
            original_query: Original query string (for logging)
        
        Returns:
            IntentType if matched, None otherwise
        """
        # Use original_query for logging if provided, otherwise use query_lower
        log_query = original_query if original_query else query_lower
        # Check for greetings (short queries only OR queries that are ONLY greetings)
        # If query has a greeting BUT ALSO has a question, treat as FAQ question
        has_greeting = False
        greeting_word = None
        
        for greeting in self.greeting_patterns:
            if query_lower.startswith(greeting) or query_lower == greeting:
                has_greeting = True
                greeting_word = greeting
                break
            if f" {greeting} " in f" {query_lower} ":
                has_greeting = True
                greeting_word = greeting
                break
        
        # If query has a greeting, check if it also has a question
        if has_greeting:
            # Remove greeting to check if there's a real question
            query_without_greeting = query_lower.replace(greeting_word, "", 1).strip()
            query_without_greeting = query_without_greeting.lstrip(", ").strip()
            
            # Check if there's content after greeting that looks like a question
            question_words = ["what", "where", "when", "who", "why", "how", "which", 
                            "tell", "show", "explain", "describe", "list", "can", "do", "does", "is", "are"]
            has_question_content = any(qw in query_without_greeting for qw in question_words)
            
            # If query is very short (<= 3 words) and no question content, it's just a greeting
            if len(words) <= 3 and not has_question_content:
                # Don't treat "what is this" as greeting
                if "what" in query_lower and len(words) > 2:
                    pass
                else:
                    return IntentType.GREETING
            # If query has greeting + question content, it's an FAQ question (not just greeting)
            elif has_question_content:
                # Has both greeting and question - treat as FAQ question
                pass  # Continue to FAQ_QUESTION
            # If query is longer but only has greeting, might still be greeting
            elif len(words) <= 4:
                return IntentType.GREETING
        
        # Check for follow-up question indicators BEFORE help/statement checks
        # Queries starting with "and", "but", "if", "what about", "how about" + topic are FAQ questions
        follow_up_starters = ["and ", "but ", "if ", "what about", "how about", "also ", "or "]
        if any(query_lower.startswith(starter) for starter in follow_up_starters):
            # Check if there's meaningful content after the starter (not just "and" or "but")
            query_after_starter = query_lower
            for starter in follow_up_starters:
                if query_lower.startswith(starter):
                    query_after_starter = query_lower[len(starter):].strip()
                    break
            
            # If there's content after the starter, it's likely a follow-up question
            # Even if it doesn't have explicit question words, it's asking for information
            if len(query_after_starter.split()) >= 2:
                # Has meaningful content (e.g., "if are group of 20 people"), treat as FAQ question
                return None  # Let it fall through to FAQ_QUESTION
        
        # CRITICAL: Check for "how to" queries BEFORE help patterns
        # "how to [do something]" = asking for instructions/information, NOT asking how bot can help
        if query_lower.startswith("how to ") or " how to " in query_lower:
            # If it has a topic keyword, it's asking for information about that topic
            if any(keyword in query_lower for keyword in self.topic_keywords):
                return None  # Let it fall through to FAQ_QUESTION
            # Even without topic keyword, "how to" is asking for instructions
                return None  # Let it fall through to FAQ_QUESTION
        
        # Check for help requests
        # IMPORTANT: Only match if query is explicitly asking HOW the bot can help
        # Queries asking FOR information (even without question words) are FAQ questions
        for pattern in self.help_patterns:
            if pattern in query_lower:
                # Make sure it's not asking FOR something (e.g., "what help can you provide" vs "how can you help")
                # If query contains "for" or "about" + topic, it's likely asking for info, not how to help
                if " for " in query_lower or " about " in query_lower:
                    # Check if there's a topic mentioned (not just "how can you help for")
                    words_after_for = query_lower.split(" for ", 1)
                    words_after_about = query_lower.split(" about ", 1)
                    if len(words_after_for) > 1 and len(words_after_for[1].split()) > 1:
                        # Has topic after "for", likely asking for information
                        continue
                    if len(words_after_about) > 1 and len(words_after_about[1].split()) > 1:
                        # Has topic after "about", likely asking for information
                        continue
                
                # CRITICAL: If query contains topic keywords (booking, pricing, etc.), it's asking FOR information, not HOW bot can help
                # Examples: "how can i book" = asking for booking info, NOT asking how bot can help
                #           "how can you help" = asking how bot can help (no topic keyword)
                if any(keyword in query_lower for keyword in self.topic_keywords):
                    # Has topic keyword, so it's asking FOR information about that topic, not asking how bot can help
                    continue
                
                return IntentType.HELP
        
        # Check for negatives (very short only) - check before affirmatives
        if len(words) <= 3:
            for neg in self.negative_patterns:
                if query_lower == neg or query_lower.startswith(neg):
                    return IntentType.NEGATIVE
        
        # Check for affirmatives (very short only)
        if len(words) <= 2:
            for aff in self.affirmative_patterns:
                if query_lower == aff or query_lower.startswith(aff):
                    return IntentType.AFFIRMATIVE
        
        # Check for confirmations (e.g., "so it is in pakistan")
        if any(pattern in query_lower for pattern in self.confirmation_patterns):
            # Make sure it's not a question
            question_words = ["what", "where", "when", "who", "why", "how", "which", 
                            "can", "do", "does", "is", "are", "tell", "show", "explain", 
                            "want", "know", "answer"]
            if not any(qw in query_lower for qw in question_words):
                return IntentType.STATEMENT
        
        # IMPORTANT: Check for topic keywords BEFORE statement check
        # If query contains topic keywords (booking, pricing, etc.), it's asking for information
        # This catches queries like "book one for me", "what is the price", etc.
        if any(keyword in query_lower for keyword in self.topic_keywords):
            # Exclude statements that just mention the topic (e.g., "thanks for booking")
            # Check if it's actually asking for something or requesting an action
            statement_indicators = ["thanks", "thank", "appreciate", "great", "good", "nice"]
            is_just_thanks = any(indicator in query_lower for indicator in statement_indicators) and len(words) <= 4
            
            # If it's not just a thank you statement, treat as FAQ question
            if not is_just_thanks:
                return None  # Let it fall through to FAQ_QUESTION
        
        # Check for statements (short queries)
        if len(words) <= 5:
            # Don't treat queries with "and", "but", "if" at start as statements (likely follow-ups)
            if any(query_lower.startswith(starter) for starter in ["and ", "but ", "if ", "also ", "or "]):
                # Check if there's meaningful content (not just the starter word)
                query_without_starter = query_lower
                for starter in ["and ", "but ", "if ", "also ", "or "]:
                    if query_lower.startswith(starter):
                        query_without_starter = query_lower[len(starter):].strip()
                        break
                
                # If there's content after starter, it's a follow-up question, not a statement
                if len(query_without_starter.split()) > 1:
                    pass  # Continue to FAQ_QUESTION
                else:
                    # Just the starter word, might be a statement
                    pass
            elif " and " in query_lower:
                pass
            # Don't treat topic keywords as statements
            elif len(words) == 1 and query_lower in self.topic_keywords:
                pass
            # Don't treat prepositional phrases as statements (likely follow-ups)
            # Examples: "for family", "with kids", "about pricing"
            elif len(words) <= 3:
                # If it starts with a preposition, it's likely a follow-up, not a statement
                if any(query_lower.startswith(prep + " ") for prep in ["for", "with", "in", "on", "at", "about"]):
                    pass
                # If it's just "and" + prepositional phrase, it's a follow-up
                elif query_lower.startswith("and ") and any(word in query_lower for word in ["for", "with", "in", "on", "at", "about"]):
                    pass
                # Check statement patterns only if it's clearly a statement
                # BE MORE CONSERVATIVE: Only classify as statement if query is very short and matches exactly
                elif any(pattern in query_lower for pattern in self.statement_patterns):
                    # Make sure it's not a question
                    question_words = ["what", "where", "when", "who", "why", "how", "which", 
                                    "can", "do", "does", "is", "are", "tell", "show", "explain", 
                                    "want", "know", "answer"]
                    if not any(qw in query_lower for qw in question_words):
                        # Only return statement if query is very short (1-3 words) and matches statement pattern exactly
                        # This prevents misclassifying questions as statements
                        if len(words) <= 3 and (query_lower in self.statement_patterns or any(query_lower == pattern for pattern in self.statement_patterns)):
                            logger.debug(f"Pattern matched as STATEMENT (conservative): {log_query}")
                        return IntentType.STATEMENT
                        # For longer queries with statement patterns, default to question (safer)
                        logger.debug(f"Query '{log_query}' has statement pattern but is too long, defaulting to FAQ_QUESTION")
            # Check statement patterns for longer queries - BE VERY CONSERVATIVE
            elif len(words) <= 3 and any(pattern in query_lower for pattern in self.statement_patterns):
                # Make sure it's not a question
                question_words = ["what", "where", "when", "who", "why", "how", "which", 
                                "can", "do", "does", "is", "are", "tell", "show", "explain", 
                                "want", "know", "answer"]
                if not any(qw in query_lower for qw in question_words):
                    # Only if it's a very clear statement match (exact match or very short)
                    if query_lower in self.statement_patterns or any(query_lower.startswith(pattern) for pattern in ["thanks", "thank", "ok", "okay"]):
                        logger.debug(f"Pattern matched as STATEMENT (conservative): {log_query}")
                    return IntentType.STATEMENT
                    # Otherwise, default to question
                    logger.debug(f"Query '{log_query}' has statement pattern but not exact match, defaulting to FAQ_QUESTION")
        
        # Check for pronoun/reference queries that need context (e.g., "what is this", "tell me about it")
        # These should go to FAQ_QUESTION so they get refined with context
        # (We check but don't return here, let it fall through to FAQ_QUESTION)
        
        # Check if query is asking FOR information (FAQ question) vs asking HOW bot can help
        # General rule: If query mentions a topic/subject, it's likely asking for information
        if self._is_asking_for_information(query_lower, words):
            # This is an FAQ question, not a help request
            return None  # Let it fall through to FAQ_QUESTION
        
        # Check if clarification is needed (very vague queries)
        if self._needs_clarification(query_lower, words):
            return IntentType.CLARIFICATION_NEEDED
        
        return None
    
    def _is_asking_for_information(self, query_lower: str, words: list) -> bool:
        """
        Check if query is asking FOR information (FAQ question) vs asking HOW bot can help.
        
        General heuristic:
        - Queries with topics/subjects are asking for information
        - Queries asking "how can you help" without a topic are help requests
        - Queries with question words + topic are asking for information
        - Queries with "tell me about", "what is", "where is", etc. are asking for information
        
        Returns:
            True if query appears to be asking for information, False otherwise
        """
        # If query has question words, it's asking for information
        question_words = ["what", "where", "when", "who", "why", "how", "which", 
                         "tell", "show", "explain", "describe", "list"]
        if any(qw in query_lower for qw in question_words):
            # Exception: "how can you help" is a help request, not asking for information
            # BUT: "how can i book" is asking for booking information, not asking how bot can help
            if "how can you" in query_lower or "how you can" in query_lower:
                if "help" in query_lower or "assist" in query_lower:
                    # Check if it also has topic keywords - if so, it's asking for info about that topic
                    if any(keyword in query_lower for keyword in self.topic_keywords):
                        return True  # "how can you help with booking" = asking for booking info
                    return False  # This is a help request
            # Also handle "how can i" + topic keyword (e.g., "how can i book")
            if "how can i" in query_lower or "how i can" in query_lower:
                if any(keyword in query_lower for keyword in self.topic_keywords):
                    return True  # "how can i book" = asking for booking information
            return True  # Has question words, asking for information
        
        # Check for action verbs that indicate requesting information or services
        # These are commands/requests that should go to FAQ retrieval
        action_verbs = ["book", "reserve", "want", "need", "looking", "interested", "get", "find"]
        if any(verb in query_lower for verb in action_verbs):
            # Make sure it's not just "thanks for booking" (statement)
            if not (any(word in query_lower for word in ["thanks", "thank", "appreciate"]) and len(words) <= 4):
                return True  # Has action verb, asking for information/service
        
        # General heuristic: If query has content beyond just help-related words, it's asking for information
        # This works for ANY FAQ topic without hardcoding keywords
        
        # Check if query contains "for" or "about" followed by content (asking FOR information)
        if " for " in query_lower:
            parts = query_lower.split(" for ", 1)
            if len(parts) > 1:
                after_for = parts[1].strip()
                # If there's meaningful content after "for" (not just "help"), it's asking for information
                if len(after_for.split()) > 0 and after_for not in ["help", "assist", "support"]:
                    return True
        
        if " about " in query_lower:
            parts = query_lower.split(" about ", 1)
            if len(parts) > 1:
                after_about = parts[1].strip()
                # If there's meaningful content after "about", it's asking for information
                if len(after_about.split()) > 0:
                    return True
        
        # If query mentions numbers/quantities (e.g., "20 people", "5 members"), it's asking for information
        # This catches queries like "we are 20 people", "group of 20 people", etc.
        if any(char.isdigit() for char in query_lower):
            # Has numbers, likely asking about capacity, pricing, etc.
            # Check if it's not just a help request
            if not any(pattern in query_lower for pattern in ["how can", "what can", "how do", "what do", "can you help"]):
                return True
        
        # If query is longer than 2 words and doesn't match help patterns, likely asking for info
        # Help requests are usually short: "how can you help", "what can you do"
        if len(words) > 2:
            # Check if it's not clearly a help request
            help_patterns_in_query = ["how can you", "how you can", "what can you", "what you can", 
                                     "how do you", "what do you", "can you help", "can you assist"]
            is_help_request = any(pattern in query_lower for pattern in help_patterns_in_query)
            
            if not is_help_request:
                # Longer query without help patterns = likely asking for information about a topic
                return True
        
        # If query is 2-3 words and contains nouns/subjects (not just verbs), likely asking for info
        # This catches queries like "nearby picnic spots", "day-trip locations", etc.
        if 2 <= len(words) <= 3:
            # Exclude queries that are clearly help requests
            if not any(pattern in query_lower for pattern in ["how can", "what can", "how do", "what do", "can you"]):
                # If it's not a help request and has multiple words, likely asking for information
                return True
        
        return False
    
    def _has_pronoun_reference(self, query_lower: str, words: list) -> bool:
        """
        Check if query contains pronouns/references that need conversation context.
        
        Returns:
            True if query has pronouns/references, False otherwise
        """
        # Pronouns and references that need context
        pronouns = ["this", "that", "it", "they", "them", "these", "those"]
        
        # Check if query contains pronouns
        if any(pronoun in query_lower for pronoun in pronouns):
            # Make sure it's not just a standalone pronoun (which might be a statement)
            if len(words) > 1:
                return True
        
        return False
    
    def _needs_clarification(self, query_lower: str, words: list) -> bool:
        """
        Check if query is too vague and needs clarification.
        
        Returns:
            True if clarification is needed, False otherwise
        """
        # Single-word topic keywords should be answered directly
        if len(words) == 1 and query_lower in self.topic_keywords:
            return False
        
        # Pricing questions - only ask for clarification if very vague
        if any(word in query_lower for word in ["price", "pricing", "cost", "how much", "rate", "rates"]):
            has_context = any(word in query_lower for word in ["cottage", "cottages", "swiss", "property", "stay", "booking", "rent"])
            if not has_context and len(words) > 1 and len(words) <= 3:
                return True
        
        # Facilities questions - only ask if truly vague
        if any(word in query_lower for word in ["facilities", "amenities", "what is available", "what do you have"]):
            has_specific = any(word in query_lower for word in ["cottage", "room", "kitchen", "parking", "bbq", "wifi", "available", "what"])
            if not has_specific and len(words) > 1 and len(words) <= 3:
                return True
        
        return False
    
    def _llm_classify(self, query: str, chat_history: Optional[ChatHistory] = None) -> Optional[IntentType]:
        """
        Use LLM to classify ambiguous queries with improved prompt and error handling.
        
        Returns:
            IntentType if classification successful, None otherwise
        """
        if not self.llm:
            return None
        
        # Improved prompt with better structure and clearer instructions
        prompt = f"""You are an intent classifier. Classify the user query into ONE of these categories:
- greeting: Simple greetings like "hi", "hello", "hey"
- help: Asking what the bot can do, like "how can you help", "what can you do"
- question: Asking FOR information about a topic (booking, pricing, facilities, location, etc.)
- statement: Acknowledgments like "thanks", "thank you", "ok", "got it", "understood"

CRITICAL RULES:
1. If the query asks FOR information (about booking, pricing, facilities, location, etc.), it's a QUESTION
2. If the query asks HOW/WHAT the bot can help, it's HELP
3. If the query is just a greeting, it's GREETING
4. If the query is acknowledging/thankful, it's STATEMENT
5. When in doubt, classify as QUESTION (safer default - better to retrieve than to miss)

Examples:
- "hi" → greeting  
- "hello" → greeting
- "hey there" → greeting
- "how can you help" → help
- "what can you do" → help
- "how to book" → question
- "how can i book" → question
- "what is the price" → question
- "book a cottage" → question
- "tell me about facilities" → question
- "where is the location" → question
- "thanks" → statement
- "thank you" → statement
- "ok" → statement
- "got it" → statement
- "understood" → statement

User query: "{query}"

Previous conversation:
{str(chat_history) if chat_history else "None"}

Respond with ONLY the category name (greeting, help, question, or statement):"""
        
        try:
            # Increase tokens for more reliable classification (5 was too short)
            classification = self.llm.generate_answer(prompt, max_new_tokens=10).strip().lower()
            
            # Log the classification for debugging
            logger.debug(f"LLM classification for '{query}': '{classification}'")
            
            # More robust parsing with priority order
            # Check for statement first (most specific), then help, then greeting, default to question
            if any(word in classification for word in ["statement", "thanks", "thank", "ok", "okay", "got it", "understood"]):
                # Only return statement if we're confident (contains explicit statement words)
                if "statement" in classification or classification in ["thanks", "thank", "ok", "okay"]:
                    logger.debug(f"Classified as STATEMENT: {query}")
                return IntentType.STATEMENT
                # If it's ambiguous (e.g., "ok" could be acknowledgment or agreement), default to question
                logger.debug(f"Ambiguous classification '{classification}' for '{query}', defaulting to QUESTION")
                return IntentType.FAQ_QUESTION
            
            elif "greeting" in classification or classification.startswith("greet"):
                logger.debug(f"Classified as GREETING: {query}")
                return IntentType.GREETING
            
            elif "help" in classification and "question" not in classification:
                # Make sure it's not "help with question" or similar
                if "question" not in classification:
                    logger.debug(f"Classified as HELP: {query}")
                    return IntentType.HELP
            
            # Default to question (safest - better to retrieve than to miss)
            logger.debug(f"Classified as FAQ_QUESTION (default): {query}")
            return IntentType.FAQ_QUESTION
            
        except Exception as e:
            logger.warning(f"Error in LLM intent classification for '{query}': {e}")
            # Default to question on error (safer than returning None)
            logger.debug(f"Error in classification, defaulting to FAQ_QUESTION for: {query}")
            return IntentType.FAQ_QUESTION
    
    def get_clarification_question(self, query: str) -> str:
        """
        Get clarification question for vague queries.
        
        Args:
            query: User query
            
        Returns:
            Clarification question string
        """
        query_lower = query.lower().strip()
        
        if any(word in query_lower for word in ["price", "pricing", "cost", "how much", "rate", "rates"]):
            return "Which cottage (9 or 11), which dates (weekday/weekend), and how many guests?"
        elif any(word in query_lower for word in ["facilities", "amenities", "what is available", "what do you have"]):
            return "Which type of facilities are you interested in? (e.g., kitchen, parking, BBQ, WiFi, etc.)"
        
        return "Could you please provide more details?"
