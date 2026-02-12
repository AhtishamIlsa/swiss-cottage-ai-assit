# -*- coding: utf-8 -*-
# A string template for the system message.
# This template is used to define the behavior and characteristics of the assistant.
SYSTEM_TEMPLATE = """You are a helpful, respectful and honest assistant.
"""

# A string template for the system message when the assistant can call functions.
# This template is used to define the behavior and characteristics of the assistant
# with the capability to call functions with appropriate input when necessary.
TOOL_SYSTEM_TEMPLATE = """You are a helpful, respectful and honest assistant.
You can call functions with appropriate input when necessary.
"""

# A string template with placeholders for question.
QA_PROMPT_TEMPLATE = """Answer the question below:
{question}
"""

# Common system facts shared across all prompts
COMMON_SYSTEM_FACTS = """- Only cottages: 7, 9, 11
- No other cottages exist
- Location: Swiss Cottages Bhurban, Bhurban, Murree, Pakistan (in Murree Hills, NOT Azad Kashmir, NOT Patriata, NOT PC Bhurban)
- Do not invent entities"""

# Short prompt template for simple queries (reduces context size to prevent 413 errors)
# NOTE: This is a fallback template used only when USE_INTENT_FILTERING=false or intent is not detected
SIMPLE_CTX_PROMPT_TEMPLATE = """Context information is below.
---------------------
{context}
---------------------

Answer the question using ONLY the context above. Be concise.

Question: {question}
Answer:"""

# A string template with placeholders for question, and context.
# NOTE: This is a fallback template used only when USE_INTENT_FILTERING=false or intent is not detected
CTX_PROMPT_TEMPLATE = """Context information is below.
---------------------
{context}
---------------------

CRITICAL RULES:
- Answer using ONLY the context provided above. Do NOT use training data.
- Location: Swiss Cottages Bhurban, Bhurban, Murree, Pakistan (in Murree Hills, NOT Azad Kashmir)
- Only cottages: 7, 9, 11 exist
- DO NOT mention pricing unless question explicitly asks about it
- DO NOT mention other hotels/resorts not in context
- Be concise and conversational

Question: {question}
Answer:"""

# Short refined prompt template for simple queries
# NOTE: This is a fallback template used only when USE_INTENT_FILTERING=false or intent is not detected
SIMPLE_REFINED_CTX_PROMPT_TEMPLATE = """Original query: {question}
Existing answer: {existing_answer}
Additional context:
---------------------
{context}
---------------------

Refine the answer using the additional context above. Keep it concise and conversational.
Answer:"""

# A string template with placeholders for question, existing_answer, and context.
# NOTE: This is a fallback template used only when USE_INTENT_FILTERING=false or intent is not detected
REFINED_CTX_PROMPT_TEMPLATE = """The original query is as follows: {question}
We have provided an existing answer: {existing_answer}
We have the opportunity to refine the existing answer with some more context below.
---------------------
{context}
---------------------

CRITICAL INSTRUCTIONS:
- Use ONLY the context information provided above. DO NOT use prior knowledge.
- Location: Swiss Cottages Bhurban, Bhurban, Murree, Pakistan (in Murree Hills, NOT Azad Kashmir)
- Only cottages: 7, 9, 11 exist
- DO NOT mention pricing unless question explicitly asks about it
- IMPORTANT: The new context may contain ADDITIONAL information that should be ADDED to the existing answer.
- If the new context contains relevant information NOT already in the existing answer, you MUST include it in the refined answer.
- **🚨 ABSOLUTE PROHIBITION ON REASONING TEXT 🚨**
- **NEVER output any of the following phrases or similar reasoning text:**
  * "We have the opportunity to refine..."
  * "Based on the context information provided above..."
  * "Based on the provided context..."
  * "Given the context..."
  * "Since the original query..."
  * "The refined answer is..."
  * "The refined answer remains..."
  * "Refined Answer:" or "Answer:"
  * Any explanation of your process, thinking, or reasoning
- **ONLY output the refined answer text itself, nothing else. No explanations, no reasoning, no process description, no meta-commentary.**
- **Start your response directly with the answer content. Do NOT preface it with any reasoning or explanation.**
- Keep your answer CONCISE: 2-5 lines maximum. Avoid repeating generic information.

Refined Answer:
"""

# A string template with placeholders for question, and chat_history to refine the question based on the chat history.
REFINED_QUESTION_CONVERSATION_AWARENESS_PROMPT_TEMPLATE = """Chat History:
---------------------
{chat_history}
---------------------
Follow Up Question: {question}
Given the above conversation and a follow up question, rephrase the follow up question to be a standalone question.

CRITICAL PRONOUN EXPANSION: If the follow-up question uses pronouns like "it", "they", "them", "this", "that", "these", "those", you MUST replace them with the specific entity mentioned in the chat history.
- **COTTAGE-SPECIFIC OVERRIDE:** If the follow-up question EXPLICITLY mentions a specific cottage number (e.g., "tell me about cottage 7", "what is cottage 9", "cottage 11 pricing"), you MUST use that cottage in the standalone question. Do NOT use a different cottage from chat history. The explicitly mentioned cottage takes ABSOLUTE PRIORITY.
- **CRITICAL: "THIS COTTAGE" EXPANSION:** If the follow-up question uses "this cottage", "that cottage", "it" (referring to a cottage), you MUST expand it to the specific cottage number from chat history. Priority: Extract cottage numbers (7, 9, 11) from chat history FIRST, before other entities.
- Scan the chat history to identify the most recent and relevant entity that the pronoun refers to ONLY if no specific cottage is explicitly mentioned in the follow-up question
- Priority order for entity extraction (ONLY when no explicit cottage is mentioned):
  1. Specific cottage numbers: "Cottage 7", "Cottage 9", "Cottage 11" (if mentioned in chat history) - HIGHEST PRIORITY for "this cottage", "that cottage", "it" referring to cottages
  2. "Swiss Cottages Bhurban" or "Swiss Cottages" (if mentioned in chat history)
  3. Topics: pricing, safety, capacity, facilities, availability, etc. (if mentioned)
- Example: Chat history mentions "Cottage 11" + Follow-up: "tell me more about this cottage" → Standalone: "tell me more about cottage 11" (NOT "tell me more about swiss cottages")
- Example: Chat history mentions "Cottage 9" + Follow-up: "is it available?" → Standalone: "is cottage 9 available?"
- Example: Chat history mentions "Swiss Cottages Bhurban" + Follow-up: "is it safe?" → Standalone: "is swiss cottages bhurban safe?"
- Example: Chat history mentions "Swiss Cottages Bhurban" + Follow-up: "which cottage is best?" → Standalone: "which cottage is best at swiss cottages bhurban?"
- Example: Chat history mentions "Swiss Cottages" + Follow-up: "tell me more about it" → Standalone: "tell me more about swiss cottages bhurban"
- Example: Chat history mentions "Swiss Cottages Bhurban" + Follow-up: "what about their pricing?" → Standalone: "what is the pricing for swiss cottages bhurban?"
- Example: Chat history mentions "Cottage 9" + Follow-up: "what about this one?" → Standalone: "what about cottage 9?"
- If the pronoun refers to a general topic (e.g., "pricing", "safety", "capacity"), include both the entity and the topic in the standalone question

CRITICAL ENTITY INCLUSION: If the chat history mentions "Swiss Cottages Bhurban" or "Swiss Cottages" and the follow-up question is ambiguous or general, you MUST include "Swiss Cottages Bhurban" in the standalone question.
- Include "Swiss Cottages Bhurban" when:
  * The follow-up uses pronouns ("it", "they", "them", "this", "that")
  * The follow-up is a general question about the property (e.g., "is it safe", "which cottage is best", "tell me more")
  * The follow-up asks about a topic without specifying the entity (e.g., "what about pricing", "how can I book")
  * The follow-up is comparative without context (e.g., "which one is better", "what's the difference")
- Do NOT include "Swiss Cottages Bhurban" if:
  * The follow-up already explicitly mentions a different entity or location
  * The follow-up is about a completely unrelated topic
  * The chat history doesn't mention "Swiss Cottages" or "Swiss Cottages Bhurban"
- Example: Chat history mentions "Swiss Cottages" + Follow-up: "is it safe?" → Standalone: "is swiss cottages bhurban safe?"
- Example: Chat history mentions "Swiss Cottages Bhurban" + Follow-up: "which cottage is best?" → Standalone: "which cottage is best at swiss cottages bhurban?"
- Example: Chat history mentions "Swiss Cottages" + Follow-up: "what about pricing?" → Standalone: "what is the pricing for swiss cottages bhurban?"

CRITICAL: If the follow-up adds a constraint or modifier (e.g., "just weekdays", "for 3 people", "cheaper option", "only weekends"), incorporate it into the standalone question.
- Example: Previous Q: "pricing for 5 days" + Follow-up: "just weekdays" → Standalone: "pricing for 5 days on weekdays only"
- Example: Previous Q: "cottage capacity" + Follow-up: "for 3 people" → Standalone: "cottage capacity for 3 people"
- Example: Previous Q: "Swiss Cottages pricing" + Follow-up: "for weekdays only" → Standalone: "swiss cottages bhurban weekday pricing"
- When adding constraints, preserve the entity context from chat history

CRITICAL CONTEXT MAINTENANCE: If the user asks a follow-up question like "and what on weekends?" or "what about weekdays?" or "and what about...", you MUST include the cottage number or topic from the previous conversation context.
- **COTTAGE SWITCHING DETECTION:** If the follow-up question EXPLICITLY mentions a different cottage number than what was in chat history, you MUST use the NEW cottage mentioned in the follow-up question. Do NOT carry over the old cottage from chat history.
  * Example: Chat history mentions "Cottage 9" + Follow-up: "tell me about cottage 7" → Standalone: "tell me about cottage 7" (NOT "tell me about cottage 9")
  * Example: Chat history mentions "Cottage 9 pricing" + Follow-up: "what is cottage 11" → Standalone: "what is cottage 11" (NOT "what is cottage 9")
  * Example: Chat history mentions "Cottage 9" + Follow-up: "cottage 7 pricing" → Standalone: "cottage 7 pricing" (NOT "cottage 9 pricing")
- If the chat history mentions "Cottage 7", "Cottage 9", or "Cottage 11" AND the follow-up does NOT explicitly mention a different cottage, include the cottage from chat history in the standalone question
- Example: Previous Q: "Cottage 9 pricing" + Follow-up: "and what on weekends?" → Standalone: "Cottage 9 weekend pricing"
- Example: Previous Q: "Cottage 9 pricing" + Follow-up: "what about weekdays?" → Standalone: "Cottage 9 weekday pricing"
- Example: Previous Q: "Swiss Cottages pricing" + Follow-up: "what about weekends?" → Standalone: "swiss cottages bhurban weekend pricing"
- If the follow-up is about pricing/rates and a cottage was mentioned before (AND no new cottage is explicitly mentioned), include that cottage in the standalone question
- Extract cottage numbers (7, 9, 11) from chat history ONLY if the follow-up question is ambiguous and does NOT explicitly mention a cottage
- If chat history mentions "Swiss Cottages Bhurban" and the follow-up is a general question (and does NOT mention a specific cottage), include "Swiss Cottages Bhurban" in the standalone question
- For comparative questions (e.g., "which is better", "which one"), include the entity context from chat history UNLESS a specific cottage is explicitly mentioned in the follow-up

ADDITIONAL GUIDELINES:
- If the follow-up question is completely standalone and doesn't reference previous conversation, return it as-is
- Preserve the original intent and meaning of the follow-up question
- Make the standalone question natural and grammatically correct
- If multiple entities are mentioned in chat history, prioritize the most recent or most relevant one
- For questions about "best", "better", "recommended", include the entity context (e.g., "which cottage is best at swiss cottages bhurban")

Standalone question:
"""

# A string template for query optimization for RAG retrieval.
QUERY_OPTIMIZATION_PROMPT_TEMPLATE = """You are a query optimization assistant for a Swiss Cottages FAQ system.

Your task: Rewrite the user's query to be more effective for semantic search in a knowledge base about Swiss Cottages Bhurban.

Knowledge Base Topics:
- Pricing and rates (weekday/weekend/peak season, PKR currency)
- Cottage properties (Cottage 7, 9, 11 - 2-bedroom and 3-bedroom)
- Capacity and accommodation (guests, members, people, base capacity 6, max capacity 9)
- Facilities and amenities (kitchen, terrace, balcony, lounge)
- Booking and payment (Airbnb, direct booking, payment methods)
- Location and nearby attractions (Bhurban, PC Bhurban, Chinar Golf Club)

CRITICAL RULES:
1. If query mentions a number with "people/guests/members", it's GROUP SIZE, NOT a cottage number
   - Example: "4 people" → "4 guests group size accommodation capacity"
   - Do NOT interpret as "cottage 4"
2. Only extract cottage numbers when "cottage" keyword is explicitly mentioned
   - Example: "cottage 7" → "Cottage 7 two-bedroom"
3. Expand abbreviations and add domain terms
   - "price" → "pricing rates weekday weekend peak season"
   - "capacity" → "accommodation capacity guests members"
   - "tell me about cottages" → "Swiss Cottages properties accommodation features amenities bedrooms facilities"
   - "about cottages" → "cottage properties spaces features amenities accommodation"
   - "which cottages are available" → "cottage availability available dates booking vacancies year-round"
   - "tell me about the availability" → "cottage availability available dates booking vacancies year-round"
   - "tell me about cottage X" → "cottage X properties features amenities accommodation details"
   - "tell me the pricing" → "cottage pricing rates per night weekday weekend PKR cost"
   - "if stay X nights" → "pricing total cost X nights calculation weekday weekend rates"
   - "stay X nights" → "pricing total cost X nights calculation weekday weekend rates"
   - "X nights" → "pricing total cost X nights calculation weekday weekend rates"
   - "one day" → "pricing per night one night rate weekday weekend"
   - "one day pricing" → "pricing per night one night rate weekday weekend"
   - "price for one day" → "pricing per night one night rate weekday weekend"
   - "how can I book" → "booking process reservation how to book contact Airbnb website"
   - "advance payment" → "advance payment partial payment booking confirmation required"
   - "is advance payment required" → "advance payment required booking confirmation partial payment"
   - "are pets allowed" → "pets allowed pet-friendly permission approval"
   - "pet" → "pets pet-friendly allowed permission"
   - "is it safe" → "safety security secure gated community security guards guest safety"
   - "safe for us" → "safety security secure gated community security guards guest safety"
   - "is it safe for" → "safety security secure gated community security guards guest safety"
   - "safety" → "safety security secure gated community security guards"
4. For availability queries, emphasize availability-related terms
   - "available" → "availability available dates booking vacancies year-round"
   - "which cottages" → "cottage availability available cottages booking options"
5. For general questions like "tell me about X" or "what is X", expand to include comprehensive information terms
   - Add terms like: features, amenities, properties, spaces, accommodation, experience, details
6. Add relevant synonyms and related terms for better semantic matching
7. Keep the core intent unchanged - don't change what the user is asking
8. Make it more searchable for semantic similarity search
9. Keep it concise (1-2 sentences max)

Original Query: {query}

Optimized Query (rewrite for better RAG retrieval, keep it concise):"""

# A string template with placeholders for question, and chat_history to answer the question based on the chat history.
REFINED_ANSWER_CONVERSATION_AWARENESS_PROMPT_TEMPLATE = """
You are engaging in a conversation with a human participant who is unaware that they might be
interacting with a machine.
Your goal is to respond in a way that convincingly simulates human-like intelligence and behavior.
The conversation should be natural, coherent, and contextually relevant.
Chat History:
---------------------
{chat_history}
---------------------
Follow Up Question: {question}\n
Given the context provided in the Chat History and the follow up question, please answer the follow up question above.
If the follow up question isn't correlated to the context provided in the Chat History, please just answer the follow up
question, ignoring the context provided in the Chat History.
Please also don't reformulate the follow up question, and write just a concise answer.
"""


def generate_qa_prompt(template: str, question: str) -> str:
    """
    Generates a prompt for a question-answer task.

    Args:
        template (str): A string template with placeholders for system, question.
        question (str): The question to be included in the prompt.

    Returns:
        str: The generated prompt.
    """

    prompt = template.format(question=question)
    return prompt


def generate_ctx_prompt(template: str = None, question: str = "", context: str = "", use_simple_prompt: bool = False) -> str:
    """
    Generates a prompt for a context-aware question-answer task.

    Args:
        template (str, optional): A string template with placeholders for question, and context.
            If None, will use SIMPLE_CTX_PROMPT_TEMPLATE or CTX_PROMPT_TEMPLATE based on use_simple_prompt.
        question (str): The question to be included in the prompt.
        context (str, optional): Additional context information. Defaults to "".
        use_simple_prompt (bool, optional): If True, use SIMPLE_CTX_PROMPT_TEMPLATE. Defaults to False.

    Returns:
        str: The generated prompt.
    """
    if template is None:
        if use_simple_prompt:
            template = SIMPLE_CTX_PROMPT_TEMPLATE
        else:
            template = CTX_PROMPT_TEMPLATE

    prompt = template.format(context=context, question=question)
    return prompt


def generate_refined_ctx_prompt(template: str = None, question: str = "", existing_answer: str = "", context: str = "", use_simple_prompt: bool = False) -> str:
    """
    Generates a prompt for a refined context-aware question-answer task.

    Args:
        template (str, optional): A string template with placeholders for question, existing_answer, and context.
            If None, will use SIMPLE_REFINED_CTX_PROMPT_TEMPLATE or REFINED_CTX_PROMPT_TEMPLATE based on use_simple_prompt.
        question (str): The question to be included in the prompt.
        existing_answer (str): The existing answer associated with the question.
        context (str, optional): Additional context information. Defaults to "".
        use_simple_prompt (bool, optional): If True, use SIMPLE_REFINED_CTX_PROMPT_TEMPLATE. Defaults to False.

    Returns:
        str: The generated prompt.
    """
    if template is None:
        if use_simple_prompt:
            template = SIMPLE_REFINED_CTX_PROMPT_TEMPLATE
        else:
            template = REFINED_CTX_PROMPT_TEMPLATE

    prompt = template.format(
        context=context,
        existing_answer=existing_answer,
        question=question,
    )
    return prompt


def generate_conversation_awareness_prompt(template: str, question: str, chat_history: str) -> str:
    """
    Generates a prompt for a conversation-awareness task.

    Args:
        template (str): A string template with placeholders for question, and chat_history.
        question (str): The question to be included in the prompt.
        chat_history (str): The chat history associated with the conversation.

    Returns:
        str: The generated prompt.
    """

    prompt = template.format(
        chat_history=chat_history,
        question=question,
    )
    return prompt


# Slot-aware prompt template for generating follow-up questions
SLOT_QUESTION_PROMPT_TEMPLATE = """Generate a friendly, natural follow-up question to collect missing information for a Swiss Cottages booking.

Context:
- Intent: {intent}
- Missing slot: {missing_slot}
- Already collected: {collected_slots}

Generate ONE follow-up question that:
1. Is friendly and conversational (not robotic)
2. Asks for the missing information naturally
3. Doesn't mention "slots" or technical terms
4. Is concise (one sentence)
5. If the intent is booking, pricing, or availability, subtly suggest that once this information is provided, you can help with booking or provide contact details

Examples:
- Missing slot: guests → "How many guests will be staying?"
- Missing slot: dates → "What dates are you planning to visit? Once you share your dates, I can help you with booking and provide contact details."
- Missing slot: cottage_id → "Do you have a preference for which cottage?"
- Missing slot: family → "Will this be for a family or friends group?"

Missing slot: {missing_slot}
Follow-up question:"""


# Recommendation generation prompt template
RECOMMENDATION_PROMPT_TEMPLATE = """Generate a gentle, helpful recommendation for a Swiss Cottages inquiry.

Context:
- Intent: {intent}
- Collected information: {slots}
- User journey: {user_journey}

Generate a recommendation that:
1. Is gentle and helpful (not pushy)
2. Provides useful tips or insights
3. Is relevant to the user's intent and collected information
4. Uses emoji sparingly (💡 for tips)
5. Is concise (2-3 lines max)

Intent: {intent}
Recommendation:"""


# Booking nudge prompt template
BOOKING_NUDGE_PROMPT_TEMPLATE = """Generate a soft booking nudge for a user who has provided enough information.

Context:
- Collected information: {slots}
- User journey: {user_journey}

Generate a booking nudge that:
1. Is soft and non-pushy
2. Acknowledges the information collected
3. Gently suggests next steps
4. Offers to help with booking process
5. Is friendly and conversational

Booking nudge:"""


def generate_slot_question_prompt(intent: str, missing_slot: str, collected_slots: dict) -> str:
    """
    Generate a prompt for creating a slot-filling question.
    
    Args:
        intent: Detected intent
        missing_slot: Name of missing slot
        collected_slots: Dictionary of already collected slots
        
    Returns:
        Formatted prompt string
    """
    collected_str = ", ".join([f"{k}: {v}" for k, v in collected_slots.items() if v is not None])
    if not collected_str:
        collected_str = "None"
    
    return SLOT_QUESTION_PROMPT_TEMPLATE.format(
        intent=intent,
        missing_slot=missing_slot,
        collected_slots=collected_str
    )


def generate_recommendation_prompt(intent: str, slots: dict, user_journey: str = "") -> str:
    """
    Generate a prompt for creating recommendations.
    
    Args:
        intent: Detected intent
        slots: Dictionary of collected slots
        user_journey: Optional user journey description
        
    Returns:
        Formatted prompt string
    """
    slots_str = ", ".join([f"{k}: {v}" for k, v in slots.items() if v is not None])
    if not slots_str:
        slots_str = "None"
    
    return RECOMMENDATION_PROMPT_TEMPLATE.format(
        intent=intent,
        slots=slots_str,
        user_journey=user_journey or "browsing"
    )


def generate_booking_nudge_prompt(slots: dict, user_journey: str = "") -> str:
    """
    Generate a prompt for creating booking nudges.
    
    Args:
        slots: Dictionary of collected slots
        user_journey: Optional user journey description
        
    Returns:
        Formatted prompt string
    """
    slots_str = ", ".join([f"{k}: {v}" for k, v in slots.items() if v is not None])
    if not slots_str:
        slots_str = "None"
    
    return BOOKING_NUDGE_PROMPT_TEMPLATE.format(
        slots=slots_str,
        user_journey=user_journey or "ready_to_book"
    )


# Intent-specific prompt templates (Phase 3: Split Prompts by Intent)

PRICING_PROMPT_TEMPLATE = """Context information is below.
---------------------
{context}
---------------------

SYSTEM FACTS (AUTHORITATIVE):
{common_facts}

ALLOWED FIELDS:
- Pricing (PKR only)
- Weekday/weekend rates
- Total cost calculations
- Number of nights
- Cottage-specific pricing

FORBIDDEN FIELDS:
- Capacity information (unless asked)
- Availability details (unless asked)
- Safety information
- Location details
- Facility descriptions

RESPONSE LENGTH: Provide a complete, helpful answer. Provide direct answer first (manager-style), then brief explanation. Be concise but informative.

CRITICAL: Complete your answer fully - do not stop mid-sentence. Include all necessary pricing information and calculations.

CRITICAL RULES:
- 🚨 ABSOLUTE PROHIBITION: DO NOT INVENT, GENERATE, OR HALLUCINATE PRICES 🚨
- 🚨🚨🚨 COTTAGE PRICES ARE ALREADY PROVIDED IN THE CONTEXT ABOVE 🚨🚨🚨
- **DO NOT search online for prices**
- **DO NOT use dollar prices from your training data**
- **DO NOT convert dollars to PKR**
- **DO NOT look up prices on Airbnb or other websites**
- **The cottage prices are ALREADY in the context above - USE THEM DIRECTLY**
- Use ONLY PKR prices that are EXPLICITLY stated in the context above
- If context does NOT contain specific PKR amounts, DO NOT make up prices
- DO NOT convert to lacs/lakhs
- 🚨🚨🚨 ABSOLUTE PROHIBITION ON DOLLAR PRICES 🚨🚨🚨
- DO NOT use dollar prices ($) - EVER
- DO NOT say "$1,200", "$220", "$250", "$400", or any dollar amounts
- DO NOT convert PKR to dollars
- DO NOT convert dollars to PKR
- ALL prices MUST be in PKR (Pakistani Rupees) ONLY
- If you see "$" in your answer, your answer is WRONG - replace it with PKR
- **IMPORTANT: The context above contains the EXACT cottage prices - check it carefully**
- **If context contains "GENERAL PRICING RATES", "Cottage X: PKR", or any pricing data, USE IT DIRECTLY**
- **If context contains "PKR" followed by numbers (e.g., "PKR 38,000", "PKR 33,000"), this IS pricing information - USE IT**
- **If context has pricing (even if formatted as "Cottage 9: PKR 33,000 per night on weekdays, PKR 38,000 per night on weekends"), provide it directly**
- If context has pricing, provide it directly EXACTLY as stated
- **ONLY if context has NO pricing information at all (no "PKR", no "pricing", no rates), then say "I don't have specific pricing information in my knowledge base. Please contact us for current rates."**
- **CRITICAL: If context contains "STRUCTURED PRICING ANALYSIS" or "TOTAL COST FOR X NIGHTS: PKR", this means pricing has been CALCULATED - you MUST provide this calculated total**
- **🚨🚨🚨 MANDATORY: When user provides dates OR nights in their question, you MUST calculate total cost 🚨🚨🚨**
- **CASE 1: If user provides dates (e.g., "i will stay from 10 march to 19 march"):**
  1. **EXTRACT the dates:**
     - Start: 10 March
     - End: 19 March
  2. **CALCULATE nights:**
     - Check-in: 10 March (stay night of 10th)
     - Check-out: 19 March (leave on 19th)
     - Nights = 19 - 10 = 9 nights (you stay on nights of: 10, 11, 12, 13, 14, 15, 16, 17, 18 = 9 nights)
  3. **CALCULATE total cost:**
     - Get rates from context (e.g., Cottage 9: PKR 33,000 weekday, PKR 38,000 weekend)
     - Count weekday nights (Monday-Friday) and weekend nights (Saturday-Sunday) in the date range
     - Calculate: (weekday nights × PKR 33,000) + (weekend nights × PKR 38,000) = Total PKR
  4. **PROVIDE the answer:**
     - "For your stay from 10 March to 19 March (9 nights) at Cottage 9:"
     - "X weekday nights at PKR 33,000 = PKR XXX"
     - "X weekend nights at PKR 38,000 = PKR XXX"
     - "Total cost: PKR XXX"
- **CASE 2: If user provides only nights (e.g., "i will stay for 5 nights" or "tell me pricing for 5 nights"):**
  1. **EXTRACT the number of nights:**
     - Nights = 5 (from "5 nights")
  2. **CALCULATE total cost using estimated weekday/weekend mix:**
     - Get rates from context (e.g., Cottage 9: PKR 33,000 weekday, PKR 38,000 weekend)
     - If context contains "ESTIMATED TOTAL" or "typical weekday/weekend mix", use that calculation
     - If context shows price range (minimum/maximum), provide the estimated total and mention the range
  3. **PROVIDE the answer:**
     - "For 5 nights at Cottage 9, the estimated total cost is PKR XXX (based on a typical weekday/weekend mix)."
     - "Price range: PKR XXX (all weekdays) to PKR XXX (all weekends)."
     - "The exact price depends on which days are weekdays vs weekends."
- **🚨 CRITICAL: DO NOT ask for dates if dates OR nights are in the question - calculate immediately**
- **🚨 CRITICAL: DO NOT say "I need dates" if nights are provided - calculate using nights**
- **🚨 CRITICAL: DO NOT say "I need check-in dates" if nights are provided - provide estimated pricing**
- **🚨 CRITICAL: DO NOT ask for guest count if already mentioned - use the provided number**
- **🚨 CRITICAL: If dates OR nights are provided, you MUST calculate and provide the total cost - do not defer to Airbnb or website**
- **🚨 CRITICAL: If user says "i will stay for 5 nights", calculate estimated total immediately using typical weekday/weekend mix**
- Calculate totals when nights are specified, but ONLY using prices from context
- DO NOT say "I don't have direct access to real-time pricing" or "I'm a large language model" - if context has pricing data, USE IT
- DO NOT suggest visiting Airbnb or website if context contains calculated pricing - provide the calculated price directly
- DO NOT use prices like "PKR 18,000", "PKR 12,000", "PKR 24,000" unless they appear in the context above

🚨 ABSOLUTE PROHIBITION: DO NOT OUTPUT TEMPLATES OR INSTRUCTIONS 🚨
- If context contains "🚨 CRITICAL PRICING INFORMATION" or "STRUCTURED PRICING ANALYSIS" or "⚠️ MANDATORY INSTRUCTIONS FOR LLM" or "GENERAL PRICING RATES", these contain PRICING DATA that you MUST USE
- **CRITICAL: If context contains "GENERAL PRICING RATES" followed by pricing information (e.g., "Cottage 9: PKR 33,000 per night on weekdays, PKR 38,000 per night on weekends"), this IS the pricing information you must provide to the user**
- **The template markers (🚨, ⚠️) and instruction text are for YOU to understand the data - but the PRICING DATA itself (the rates, amounts, cottage numbers) is what the user needs**
- **DO NOT START YOUR ANSWER WITH "⚠️" OR "🚨" OR "GENERAL" - these are template markers, NOT part of your answer**
- **DO NOT output "⚠️ GENERAL PRICING QUERY DETECTED" or similar template text**
- **START YOUR ANSWER DIRECTLY with the actual pricing information (e.g., "Cottage 9 costs PKR 33,000...")**
- DO NOT copy, repeat, or output ANY part of the template markers or instruction text to the user
- DO NOT include the emoji markers (🚨, ⚠️, 🎯) in your answer
- DO NOT include the instruction numbers (1., 2., 3., etc.) in your answer
- DO NOT include phrases like "CRITICAL PRICING INFORMATION", "MANDATORY INSTRUCTIONS", "STRUCTURED PRICING ANALYSIS", "GENERAL PRICING QUERY DETECTED" in your answer
- **BUT DO extract and provide the actual pricing data (cottage numbers, PKR amounts, weekday/weekend rates) from the template**
- Instead, extract ONLY the pricing information (dates, nights, rates, total cost) and provide a natural, conversational answer
- Example: If template says "Cottage 9: PKR 33,000 per night on weekdays, PKR 38,000 per night on weekends", you should say: "Cottage 9 costs PKR 33,000 per night on weekdays and PKR 38,000 per night on weekends" (extract the pricing data, ignore the template markers)
- Example: If template says "TOTAL COST FOR 1 NIGHTS: PKR 33,000", you should say: "For 1 night at Cottage 9, the total cost is PKR 33,000" (NOT the entire template)
- Your answer should be natural and conversational, NOT a template or instruction list
- START YOUR ANSWER DIRECTLY with the pricing information - do not include any template text, emojis, or warning symbols

Question: {question}
Answer:"""


AVAILABILITY_PROMPT_TEMPLATE = """🚨🚨🚨 CRITICAL: READ THIS FIRST 🚨🚨🚨
**ABSOLUTE PROHIBITION ON PRICING - THIS IS MANDATORY**
- DO NOT mention ANY pricing, prices, costs, rates, PKR amounts, or monetary information
- DO NOT say "PKR 32,000", "PKR 38,000", "costs", "pricing", "price", "rate", "per night"
- Even if context contains pricing, DO NOT include it in your answer
- This is an AVAILABILITY query, NOT a pricing query
- If you mention pricing, your answer is WRONG

Context information is below.
---------------------
{context}
---------------------

SYSTEM FACTS (AUTHORITATIVE):
{common_facts}

ALLOWED FIELDS:
- Availability status
- Booking information
- Contact details
- Date-related availability

FORBIDDEN FIELDS:
- Pricing information (ABSOLUTELY FORBIDDEN - do not mention PKR, prices, costs, rates)
- Capacity details (unless asked)
- Safety information
- Location details
- Facility descriptions

RESPONSE LENGTH: Provide a complete, helpful answer. Include all relevant booking information, contact details, and next steps. Do not cut off mid-sentence.

CRITICAL RULES - READ CAREFULLY:
- Swiss Cottages are available year-round, subject to availability

🚨🚨🚨 MANDATORY COTTAGE PRIORITIZATION 🚨🚨🚨:
- **IF the user does NOT specify a cottage number**, you MUST prioritize and mention Cottage 9 and Cottage 11 FIRST
- **DO NOT mention Cottage 7** unless the user specifically asks for "Cottage 7" or "cottage 7"
- **Your response MUST start with Cottage 9 and Cottage 11**, not with "cottages 7, 9, and 11"
- Example CORRECT format: "You can book Cottage 9 or Cottage 11 at Swiss Cottages Bhurban..."
- Example WRONG format: "Our cottages available for booking include 7, 9, and 11-cottages" ❌

🚨🚨🚨 MANDATORY AIRBNB LINKS 🚨🚨🚨:
- **YOU MUST include Airbnb links in your response**
- Cottage 9 Airbnb: https://www.airbnb.com/rooms/651168099240245080
- Cottage 11 Airbnb: https://www.airbnb.com/rooms/886682083069412842
- Format: "Book Cottage 9 on Airbnb: [link]" and "Book Cottage 11 on Airbnb: [link]"
- Only include Cottage 7 Airbnb link if user specifically asks for Cottage 7

🚨🚨🚨 MANDATORY BOOKING INFORMATION 🚨🚨🚨:
- Website: https://swisscottagesbhurban.com (format correctly with proper URL structure)
- Contact Manager: +92 300 1218563 (WhatsApp)
- Include both website and Airbnb links in your response

🚨🚨🚨 RESPONSE FORMAT REQUIREMENTS 🚨🚨🚨:
1. Start by mentioning Cottage 9 and Cottage 11 (NOT Cottage 7)
2. Include Airbnb links for Cottage 9 and Cottage 11
3. Mention the website link (properly formatted)
4. Include contact information
5. DO NOT mention Cottage 7 unless user specifically asks for it
6. Complete your answer fully - do not stop mid-sentence
7. Use all available tokens to provide a complete response

🚨 ABSOLUTE PROHIBITION: DO NOT mention pricing, prices, costs, rates, PKR amounts

Question: {question}
Answer:"""


SAFETY_PROMPT_TEMPLATE = """🚨🚨🚨 CRITICAL: READ THIS FIRST 🚨🚨🚨
**ABSOLUTE PROHIBITION ON PRICING - THIS IS MANDATORY**
- DO NOT mention ANY pricing, prices, costs, rates, PKR amounts, or monetary information
- DO NOT say "PKR 32,000", "PKR 38,000", "costs", "pricing", "price", "rate", "per night"
- Even if context contains pricing, DO NOT include it in your answer
- This is a SAFETY query, NOT a pricing query
- If you mention pricing, your answer is WRONG

Context information is below.
---------------------
{context}
---------------------

SYSTEM FACTS (AUTHORITATIVE):
{common_facts}

ALLOWED FIELDS:
- Security measures
- Safety features
- Guard information
- Gated community details
- Emergency procedures

FORBIDDEN FIELDS:
- Pricing information (ABSOLUTELY FORBIDDEN - do not mention PKR, prices, costs, rates)
- Availability details
- Capacity information
- Location details (unless relevant to safety)
- Facility descriptions

RESPONSE LENGTH: Provide a complete answer with key safety points. Be concise but complete.

CRITICAL: Complete your answer fully - do not stop mid-sentence. Include all relevant safety information.

CRITICAL RULES:
- Focus on safety and security features
- Mention guards, gated community if in context
- 🚨 ABSOLUTE PROHIBITION: DO NOT mention pricing, prices, costs, rates, PKR amounts

🚨🚨🚨 HANDLING GENERAL VS SPECIFIC INFORMATION 🚨🚨🚨:
- **IF user asks about safety "for each cottage", "in each cottage", or "for Cottage X, Y, Z"** BUT context only contains general/overall safety information:
  - **DO NOT say "I don't have enough information" or "I couldn't find specific details"**
  - **DO NOT say "Unfortunately, I don't have information about each cottage"**
  - **INSTEAD: Provide the general safety information from context**
  - **State that these safety measures apply to ALL cottages (Cottage 7, Cottage 9, and Cottage 11)**
  - **Use phrases like "All cottages have...", "The cottages include...", or "Each cottage features..."**
  - **Example: If context mentions "gated community with security guards" and user asks "safety for each cottage", respond: "All cottages at Swiss Cottages Bhurban are located in a secure gated community with security guards. These safety measures apply to Cottage 7, Cottage 9, and Cottage 11."**
- **IF context contains general safety information, ALWAYS provide it - do not say information is unavailable**
- **ONLY say "I don't have information" if context truly has NO safety information at all**

Question: {question}
Answer:"""


ROOMS_PROMPT_TEMPLATE = """🚨🚨🚨 CRITICAL: READ THIS FIRST 🚨🚨🚨
**ABSOLUTE PROHIBITION ON PRICING - THIS IS MANDATORY**
- DO NOT mention ANY pricing, prices, costs, rates, PKR amounts, or monetary information
- DO NOT say "PKR 32,000", "PKR 38,000", "costs", "pricing", "price", "rate", "per night"
- Even if context contains pricing, DO NOT include it in your answer
- This is a COTTAGE/DESCRIPTION query, NOT a pricing query
- If you mention pricing, your answer is WRONG

**LOCATION RULE - MANDATORY**
- Location MUST be "Swiss Cottages Bhurban, Bhurban, Murree" or "Bhurban, Murree, Pakistan" or "Murree Hills, Pakistan"
- NEVER say "Azad Kashmir", "Patriata", or "PC Bhurban" for cottage location
- The cottages are in Murree (Murree Hills), NOT in Azad Kashmir
- If you mention "Azad Kashmir" for cottage location, your answer is WRONG

Context information is below.
---------------------
{context}
---------------------

SYSTEM FACTS (AUTHORITATIVE):
{common_facts}
- Users ask about cottages, not rooms

ALLOWED FIELDS:
- Cottage descriptions (Cottage 7, 9, 11)
- Bedroom count
- Capacity (base and max)
- Cottage features
- Property details

FORBIDDEN FIELDS:
- Pricing information (ABSOLUTELY FORBIDDEN - do not mention PKR, prices, costs, rates)
- Availability details (unless asked)
- Safety information
- Location details (unless relevant - but MUST be "Bhurban, Murree, Pakistan" or "Murree Hills, Pakistan")
- Individual room descriptions within cottages

RESPONSE LENGTH: Provide a complete answer including bedroom count, capacity, and key features. Be concise but complete.

CRITICAL: Complete your answer fully - do not stop mid-sentence. Include all relevant cottage information.

CRITICAL RULES:
- Focus on cottage types/properties (Cottage 7, 9, 11)
- Include capacity: base (up to 6) and max (up to 9 with confirmation)
- 🚨 ABSOLUTE PROHIBITION: DO NOT mention pricing, prices, costs, rates, PKR amounts, or any monetary information
- Location MUST be "Swiss Cottages Bhurban, Bhurban, Murree" or "Bhurban, Murree, Pakistan" - NEVER "Azad Kashmir" or "Patriata"
- Use "cottage_id" terminology, NOT "room_type"
- Answer the question directly - do not add extra information

Question: {question}
Answer:"""


FACILITIES_PROMPT_TEMPLATE = """🚨🚨🚨 CRITICAL: READ THIS FIRST 🚨🚨🚨
**ABSOLUTE PROHIBITION ON PRICING - THIS IS MANDATORY**
- DO NOT mention ANY pricing, prices, costs, rates, PKR amounts, or monetary information
- DO NOT say "PKR 32,000", "PKR 38,000", "costs", "pricing", "price", "rate", "per night"
- Even if context contains pricing, DO NOT include it in your answer
- This is a FACILITIES query, NOT a pricing query
- If you mention pricing, your answer is WRONG

Context information is below.
---------------------
{context}
---------------------

SYSTEM FACTS (AUTHORITATIVE):
{common_facts}

ALLOWED FIELDS:
- Facilities and amenities
- Kitchen details
- Terrace information
- Available services
- Equipment and features

FORBIDDEN FIELDS:
- Pricing information (ABSOLUTELY FORBIDDEN - do not mention PKR, prices, costs, rates)
- Availability details (unless asked)
- Safety information
- Location details
- Cottage descriptions (unless relevant)

RESPONSE LENGTH: Provide a complete answer listing key facilities. Be concise but complete.

CRITICAL: Complete your answer fully - do not stop mid-sentence. Include all relevant facility information.

CRITICAL RULES:
- Focus on facilities and amenities
- 🚨 ABSOLUTE PROHIBITION: DO NOT mention pricing, prices, costs, rates, PKR amounts

🚨🚨🚨 HANDLING GENERAL VS SPECIFIC INFORMATION 🚨🚨🚨:
- **CRITICAL: If user asks about facilities "in each cottage", "for each cottage", or "for Cottage X, Y, Z"**:
  - **FIRST: Check if context contains ANY facilities information (even if general/overall)**
  - **IF context has ANY facilities information (general or specific):**
    - **🚨 ABSOLUTE PROHIBITION: DO NOT say "I couldn't find", "I was unable to find", "I don't have", "unfortunately", "I recommend checking", "please contact", "check the official website", "reach out to", "contact the establishment", or ANY phrase indicating information is unavailable**
    - **🚨 ABSOLUTE PROHIBITION: DO NOT say "I couldn't find any information on" or "I couldn't find specific details"**
    - **🚨 ABSOLUTE PROHIBITION: DO NOT say "I would expect" or "it's likely to include" - if context has information, state it directly**
    - **INSTEAD: IMMEDIATELY provide the facilities information from context (even if it's general)**
    - **State that these facilities apply to ALL cottages (Cottage 7, Cottage 9, and Cottage 11)**
    - **Use phrases like "All cottages have...", "The cottages include...", or "Each cottage features..."**
    - **Example: If context mentions "fully equipped kitchens" or "kitchen" or "microwave, oven, kettle" and user asks "kitchen facilities in each cottage", respond: "All cottages at Swiss Cottages Bhurban have fully equipped kitchens that include: microwave, oven, kettle, refrigerator, cookware, and utensils. These kitchen facilities are available in Cottage 7, Cottage 9, and Cottage 11."**
    - **If context mentions kitchen facilities in general terms, extract and provide them - do not say you couldn't find specific details**
  - **ONLY if context has ABSOLUTELY NO facilities information at all (no mention of kitchen, facilities, amenities, equipment, etc.), then you may say information is unavailable**
- **🚨 CRITICAL RULE: If context contains ANY mention of the topic (kitchen, facilities, amenities, equipment), you MUST provide that information - never say "I couldn't find"**

Question: {question}
Answer:"""


LOCATION_PROMPT_TEMPLATE = """🚨🚨🚨 CRITICAL: READ THIS FIRST 🚨🚨🚨
**ABSOLUTE PROHIBITION ON PRICING - THIS IS MANDATORY**
- DO NOT mention ANY pricing, prices, costs, rates, PKR amounts for cottages OR attractions
- DO NOT say "PKR 32,000", "PKR 38,000", "costs", "pricing", "price", "rate", "per night"
- Even if context contains pricing, DO NOT include it in your answer
- This is a LOCATION query, NOT a pricing query
- If you mention pricing, your answer is WRONG

**LOCATION RULE - MANDATORY**
- Location MUST be "Swiss Cottages Bhurban, Bhurban, Murree" or "Bhurban, Murree, Pakistan" or "Murree Hills, Pakistan"
- NEVER say "Azad Kashmir", "Patriata", or "PC Bhurban" for cottage location
- The cottages are in Murree (Murree Hills), NOT in Azad Kashmir
- PC Bhurban is a viewpoint that overlooks Azad Kashmir, but the cottages themselves are in Murree
- If you mention "Azad Kashmir" for cottage location, your answer is WRONG

Context information is below.
---------------------
{context}
---------------------

SYSTEM FACTS (AUTHORITATIVE):
{common_facts}
- PC Bhurban is a viewpoint that overlooks Azad Kashmir, but the cottages themselves are in Murree (Murree Hills)
- Patriata is a different location, NOT where cottages are

ALLOWED FIELDS:
- Location information (MUST be "Bhurban, Murree, Pakistan" or "Murree Hills, Pakistan")
- Nearby attractions (describe only, NO pricing)
- Directions
- Distance information
- Surrounding areas

FORBIDDEN FIELDS:
- Pricing information (ABSOLUTELY FORBIDDEN - do not mention PKR, prices, costs, rates for cottages OR attractions)
- Availability details (unless asked)
- Safety information
- Capacity information
- Facility descriptions

RESPONSE LENGTH: Provide a complete answer with location and nearby attractions. Be concise but complete.

CRITICAL: Complete your answer fully - do not stop mid-sentence. Include all relevant location information.

CRITICAL RULES:
- Location MUST be "Swiss Cottages Bhurban, Bhurban, Murree" or "Bhurban, Murree, Pakistan" or "Murree Hills, Pakistan"
- 🚨 NEVER say "Azad Kashmir", "Patriata", or "PC Bhurban" for cottage location
- 🚨 ABSOLUTE PROHIBITION: DO NOT mention pricing for cottages OR attractions unless explicitly asked
- DO NOT use cottage prices (PKR 32,000, PKR 38,000) for attractions
- Describe attractions without pricing unless pricing is explicitly in context for that specific attraction

Question: {question}
Answer:"""


GENERAL_PROMPT_TEMPLATE = """🚨🚨🚨 CRITICAL: READ THIS FIRST 🚨🚨🚨
**ABSOLUTE PROHIBITION ON PRICING - THIS IS MANDATORY**
- DO NOT mention ANY pricing, prices, costs, rates, PKR amounts UNLESS the question explicitly asks about pricing
- Check the question: Does it contain "price", "pricing", "cost", "rate", "how much", "pkr"?
- If NO → DO NOT mention pricing at all
- If YES → You can mention pricing
- Even if context contains pricing, DO NOT include it unless the question asks about it
- If you mention pricing when the question doesn't ask about it, your answer is WRONG

**LOCATION RULE - MANDATORY**
- Location MUST be "Swiss Cottages Bhurban, Bhurban, Murree" or "Bhurban, Murree, Pakistan" or "Murree Hills, Pakistan"
- NEVER say "Azad Kashmir", "Patriata", or "PC Bhurban" for cottage location
- The cottages are in Murree (Murree Hills), NOT in Azad Kashmir
- If you mention "Azad Kashmir" for cottage location, your answer is WRONG

Context information is below.
---------------------
{context}
---------------------

SYSTEM FACTS (AUTHORITATIVE):
{common_facts}

ALLOWED FIELDS:
- General information about Swiss Cottages
- Any relevant information from context
- Multiple topics if relevant

FORBIDDEN FIELDS:
- Pricing information (ABSOLUTELY FORBIDDEN unless question explicitly asks about pricing)
- Information not in context

RESPONSE LENGTH: Provide a complete answer with direct answer first, then brief context. Be concise but complete.

CRITICAL: Complete your answer fully - do not stop mid-sentence. Include all necessary information to fully answer the question.

CRITICAL RULES:
- Answer using ONLY context information
- 🚨 ABSOLUTE PROHIBITION: DO NOT mention pricing, prices, costs, rates, PKR amounts unless question contains: "price", "pricing", "cost", "rate", "how much", "pkr"
- Location MUST be "Swiss Cottages Bhurban, Bhurban, Murree" or "Bhurban, Murree, Pakistan" or "Murree Hills, Pakistan" - NEVER "Azad Kashmir"
- Be helpful and conversational but concise

🚨🚨🚨 HANDLING GENERAL VS SPECIFIC INFORMATION 🚨🚨🚨:
- **CRITICAL: If user asks about specific details "for each cottage", "in each cottage", or "for Cottage X, Y, Z"**:
  - **FIRST: Check if context contains ANY information about the topic (even if general/overall)**
  - **IF context has ANY information about the topic (general or specific):**
    - **🚨 ABSOLUTE PROHIBITION: DO NOT say "I couldn't find", "I was unable to find", "I don't have", "unfortunately", "I recommend checking", "please contact", "check the official website", "reach out to", "contact the establishment", or ANY phrase indicating information is unavailable**
    - **🚨 ABSOLUTE PROHIBITION: DO NOT say "I don't have enough information to give a definitive answer"**
    - **🚨 ABSOLUTE PROHIBITION: DO NOT say "I would expect" or "it's likely to include" - if context has information, state it directly**
    - **INSTEAD: IMMEDIATELY provide the information from context (even if it's general)**
    - **State that this information applies to ALL cottages (Cottage 7, Cottage 9, and Cottage 11) when relevant**
    - **Use phrases like "All cottages have...", "The cottages include...", or "Each cottage features..."**
    - **Example: If context has general kitchen info and user asks "kitchen facilities in each cottage", respond with the general kitchen information and state it applies to all cottages**
    - **If context mentions the topic in general terms, extract and provide that information - do not say you couldn't find specific details**
  - **ONLY if context has ABSOLUTELY NO information about the topic at all, then you may say information is unavailable**
- **🚨 CRITICAL RULE: If context contains ANY mention of the topic, you MUST provide that information - never say "I couldn't find"**

Question: {question}
Answer:"""


def get_intent_prompt_template(intent: str) -> str:
    """
    Get the appropriate prompt template based on intent.
    
    Args:
        intent: Intent string (e.g., "pricing", "availability", "rooms", "faq_question")
        
    Returns:
        Prompt template string
    """
    intent_lower = intent.lower() if intent else ""
    
    intent_to_template = {
        "pricing": PRICING_PROMPT_TEMPLATE,
        "availability": AVAILABILITY_PROMPT_TEMPLATE,
        "safety": SAFETY_PROMPT_TEMPLATE,
        "rooms": ROOMS_PROMPT_TEMPLATE,
        "facilities": FACILITIES_PROMPT_TEMPLATE,
        "location": LOCATION_PROMPT_TEMPLATE,
        "booking": AVAILABILITY_PROMPT_TEMPLATE,  # Booking uses availability template
        "faq_question": GENERAL_PROMPT_TEMPLATE,  # General questions use general template
    }
    
    return intent_to_template.get(intent_lower, GENERAL_PROMPT_TEMPLATE)


def generate_intent_ctx_prompt(intent: str, question: str = "", context: str = "") -> str:
    """
    Generate a context-aware prompt using intent-specific template.
    
    Args:
        intent: Intent string
        question: The question to be included in the prompt
        context: Additional context information
        
    Returns:
        The generated prompt
    """
    template = get_intent_prompt_template(intent)
    prompt = template.format(context=context, question=question, common_facts=COMMON_SYSTEM_FACTS)
    return prompt
