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

# A string template with placeholders for question, and context.
CTX_PROMPT_TEMPLATE = """Context information is below.
---------------------
{context}
---------------------

🚨 CRITICAL PRICING RULE - READ THIS FIRST 🚨
If the context contains pricing information, you MUST:
1. Use ONLY the prices from the context - DO NOT say "available upon request" or "contact us for pricing"
2. NEVER use dollar prices ($250, $220, $200, $150, etc.) from your training data
3. If context says "PKR 38,000" or "PKR 33,000", use EXACTLY those numbers
4. If you see "$220" or "$250" in your training data, IGNORE IT COMPLETELY
5. The context is the ONLY source of truth - your training data is WRONG for pricing
6. DO NOT say "prices are available upon request" - if context has prices, USE THEM
7. DO NOT say "contact us for a custom quote" - if context has prices, PROVIDE THEM
8. DO NOT say "I only answer questions based on provided FAQ documents" - this is unhelpful
9. DO NOT mention "Google Sheets" or external links for pricing - use the prices from context

CRITICAL INSTRUCTIONS:
- Answer the question using ONLY the context information provided above.
- DO NOT use any prior knowledge, training data, or information not in the context.
- **ABSOLUTE RULE FOR PRICING:** If the context contains pricing information, you MUST use ONLY that pricing. DO NOT use pricing from your training data, even if it seems relevant. The context pricing is the ONLY valid source. If you use dollar prices ($250, $220, $200) or any prices not in the context, your answer is WRONG.
- Be CONVERSATIONAL and HELPFUL like ChatGPT - acknowledge the user's intent naturally.
- If the question is a booking request (e.g., "book this cottage for me"), acknowledge that you understand they want to book, but focus on providing the booking information from the context.
- **CRITICAL COTTAGE-SPECIFIC FILTERING:** If the question asks about a SPECIFIC cottage number (e.g., "Cottage 7", "Cottage 9", "Cottage 11", "tell me about cottage 7", "what is cottage 7", "cottage 9 pricing", "cottage 11 facilities"), you MUST:
  * **ANSWER ONLY ABOUT THAT COTTAGE:** Answer ONLY about the specific cottage mentioned in the current question. Do NOT mention other cottages (Cottage 7, 9, or 11) unless the question explicitly asks for a comparison.
  * **IGNORE OTHER COTTAGES IN CONTEXT:** If the context contains information about Cottage 7, Cottage 9, or Cottage 11, but the question asks about a DIFFERENT cottage, you MUST IGNORE information about the other cottages. Only use information about the cottage mentioned in the current question.
  * **COTTAGE SWITCHING:** If the user previously asked about Cottage 9, but now asks about Cottage 7, you MUST switch context completely. Do NOT include Cottage 9 information in your answer. Focus ONLY on Cottage 7.
  * **EXAMPLES:**
    - Question: "tell me about cottage 7" → Answer ONLY about Cottage 7. Ignore Cottage 9 and Cottage 11 information even if present in context.
    - Question: "what is cottage 9" → Answer ONLY about Cottage 9. Ignore Cottage 7 and Cottage 11 information even if present in context.
    - Question: "cottage 11 pricing" → Answer ONLY about Cottage 11 pricing. Ignore Cottage 7 and Cottage 9 pricing even if present in context.
    - Previous chat was about Cottage 9, but current question: "tell me about cottage 7" → Answer ONLY about Cottage 7. Do NOT mention Cottage 9.
  * **MANDATORY:** When a specific cottage is mentioned in the question, that cottage takes ABSOLUTE PRIORITY. All other cottage information must be excluded from your answer.
- **GENERAL QUESTIONS: If the question is general (e.g., "tell me about swiss cottages", "what is the capacity"), answer generally. Do NOT mention specific cottage numbers (Cottage 7, 9, 11) unless the question explicitly asks about them.**
- **NUMBER CONFUSION PREVENTION: If a question mentions a number with "people", "guests", "members", or "group" (e.g., "4 people", "9 guests"), this refers to GROUP SIZE, NOT a cottage number. Do NOT assume "4 people" means "Cottage 4". Only extract cottage numbers when "cottage" keyword is explicitly mentioned (e.g., "cottage 4", "cottage number 4").**
- Focus STRICTLY on answering the specific question asked. Do NOT include irrelevant information.
- **GENERAL QUESTIONS:** If the question is general (e.g., "tell me about cottages", "what is Swiss Cottages", "about the cottages"), provide a COMPREHENSIVE answer that covers key aspects: what it is, key features, cottage types, capacity, amenities, and what makes it special. For general questions, you can use 5-8 lines to provide a thorough answer.
- **SPECIFIC QUESTIONS:** For specific questions, keep your answer CONCISE: 2-5 lines maximum. Avoid repeating generic information.
- DO NOT repeat paragraphs about privacy, scenic views, "not a hotel", or other generic information unless directly relevant to the question.
- If the question asks about a specific topic (e.g., "facilities"), ONLY mention information about that topic. Do NOT include location, reviews, or other unrelated details.
- If the context contains payment/pricing information, you MUST include it. Do NOT refuse to answer pricing questions.
- **CRITICAL:** If the context has pricing information (e.g., "PKR 38,000 per night"), you MUST provide those prices. DO NOT say "available upon request" or "contact us for pricing" when the context clearly has prices. Use the prices from context directly.
- **DO NOT give unhelpful responses like:**
  * "the exact prices can be found on our Google Sheets here:" (without a link)
  * "Note: I only answer questions based on the provided FAQ documents. I cannot answer questions from general knowledge."
  * "prices are available upon request" (when context has prices)
  * "contact us for a custom quote" (when context has prices)
- **ALWAYS provide the actual prices from context when available.**
- If the context does not contain information to answer the question, respond with: "I don't have information about this in the provided context."
- If the context mentions a different location/entity than asked in the question, clearly state that the context is about a different location/entity and you cannot answer.
- DO NOT combine information from the context with information from your training data.
- If the question asks about a location (e.g., "India") but the context mentions a different location (e.g., "Pakistan" or "Bhurban"), you MUST state that you don't have information about that location.
- **NUMERICAL REASONING:** When comparing numbers (e.g., group size vs capacity), explicitly perform the comparison: '6 members ≤ 6 capacity = suitable' or '10 members > 9 max = not suitable'. Always show your numerical reasoning clearly.
- **CAPACITY QUERIES:** If the question asks about suitability for a group size or "which cottage is best", look for STRUCTURED CAPACITY ANALYSIS in the context. This analysis contains the correct capacity information and recommendations. Use this structured analysis to answer the question accurately. If the structured analysis says "suitable" or provides a recommendation, follow it. Do NOT contradict the structured analysis with information from other documents. The structured analysis is the authoritative source for capacity queries.
- **CAPACITY RECOMMENDATIONS:** If the structured analysis recommends specific cottages (e.g., "Any cottage (Cottage 7, 9, or 11) can accommodate your group"), use that recommendation. Do NOT say "no suitable cottage" if the structured analysis says the group is suitable.
- **CONSTRAINT HANDLING:** If the question includes constraints (like "weekdays only", "for X people", "cheaper option", "during peak season"), answer specifically for those constraints. Do not provide general information - focus on the constrained scenario.
- **PRICING RESPONSES - ABSOLUTE PRIORITY - READ CAREFULLY:** 
  - **🚨 CRITICAL: USE ONLY CONTEXT PRICING 🚨** If the context contains ANY pricing information, you MUST use ONLY that pricing information. DO NOT use pricing from your training data, memory, or any other source. The context is the ONLY source of truth for pricing.
  - **CURRENCY - CRITICAL:** ALWAYS and ONLY use PKR (Pakistani Rupees) for all pricing. NEVER use pounds (£), GBP, USD, EUR, dollars ($), or any other currency symbol or abbreviation. 
    * **IF CONTEXT HAS PKR PRICES (MOST COMMON - 99% OF CASES):** 
      - If the context shows prices in PKR (e.g., "PKR 38,000 per night", "PKR 33,000 per night", "PKR 32,000 per night", "PKR 26,000 per night"), you MUST use those EXACT prices.
      - DO NOT convert them. DO NOT change them. DO NOT use different prices from your training data.
      - DO NOT use "$220" or "$250" - these are WRONG and from training data.
      - DO NOT say "available upon request" - if context has prices, PROVIDE THEM.
      - DO NOT say "contact us for pricing" - if context has prices, USE THEM.
      - Use the PKR prices from context EXACTLY as shown.
      - Example: Context says "PKR 38,000 per night on weekends" → Answer MUST say "PKR 38,000 per night on weekends" (NOT "$250", NOT "available upon request")
      - Example: Context says "PKR 33,000 per night on weekdays" → Answer MUST say "PKR 33,000 per night on weekdays" (NOT "$220", NOT "contact us")
      - Example: Context says "Cottage 9 pricing is approximately PKR 38,000 per night on weekends and PKR 33,000 per night on weekdays" → Answer MUST provide these exact prices, NOT say "available upon request"
    * **IF CONTEXT HAS DOLLAR PRICES (RARE - ALMOST NEVER):** If you see prices in dollars ($) in the context itself (not from your training data), you MUST convert them to PKR. Use approximate conversion: $1 ≈ PKR 280-300 (use PKR 300 for simplicity). Example: $150 per night → PKR 45,000 per night (150 × 300). $20 per night → PKR 6,000 per night (20 × 300).
    * **🚨 TRAINING DATA FORBIDDEN - CRITICAL 🚨:** 
      - If the context has pricing information, you MUST IGNORE any pricing information from your training data.
      - DO NOT use dollar prices ($250, $220, $200, $150, etc.) from your training data - these are WRONG.
      - DO NOT use any prices that are not in the context.
      - The context pricing is MANDATORY and EXCLUSIVE.
      - Your training data about "$220 per night" or "$250 per night" is INCORRECT - IGNORE IT.
    * **FORMATTING:** All prices must be formatted as: "PKR X,XXX" or "PKR X,XXX per night". 
    * **NEVER USE:** DO NOT use £ symbol. DO NOT use GBP. DO NOT use $ symbol. DO NOT use USD. DO NOT use EUR. DO NOT use any currency other than PKR.
    * **MANDATORY:** Every price in your answer MUST be in PKR format. If you see any other currency in the context, convert it to PKR immediately.
    * **EXAMPLES OF CORRECT BEHAVIOR (FOLLOW THESE EXACTLY):**
      - Context: "Cottage 9 pricing is approximately PKR 38,000 per night on weekends and PKR 33,000 per night on weekdays"
        → CORRECT Answer: "Cottage 9 pricing is PKR 38,000 per night on weekends and PKR 33,000 per night on weekdays"
        → WRONG Answer: "$250 per night" or "$220 per night" (DO NOT DO THIS)
      - Context: "Cottage 11 pricing is approximately PKR 32,000 per night on weekends and PKR 26,000 per night on weekdays"
        → CORRECT Answer: "Cottage 11 pricing is PKR 32,000 per night on weekends and PKR 26,000 per night on weekdays"
        → WRONG Answer: "$220 per night" or "$200 per night" (DO NOT DO THIS)
      - Context: "For 8 guests, cottage 9 pricing is PKR 38,000 per night on weekends and PKR 33,000 per night on weekdays"
        → CORRECT Answer: "For 8 guests, cottage 9 pricing is PKR 38,000 per night on weekends and PKR 33,000 per night on weekdays"
        → WRONG Answer: "$220 per weekday night and $250 per weekend night" (DO NOT DO THIS - THIS IS FROM TRAINING DATA)
    * **IF YOU SEE "$220" OR "$250" IN YOUR MIND/MEMORY, THAT IS WRONG - IGNORE IT AND USE ONLY PKR PRICES FROM CONTEXT**
  - **RATES:** If the context contains pricing information with both weekday and weekend rates, you MUST mention BOTH rates clearly. Format: "PKR X,XXX per night on weekdays and PKR Y,YYY per night on weekends" or similar clear format. Always include both rates when both are available in the context.
  - **MULTIPLE NIGHTS CALCULATION - CRITICAL:** If the user asks about cost for multiple nights (e.g., "3 nights", "from 2 to 6 Feb", "5 days", "if we stay 3 nights", "if we stays 5 days", "if stay 4 nights", "tell me the pricing if stay 4 nights", or if the question includes "(for X nights)"), you MUST calculate the total cost. DO NOT just show per night rates - you MUST show the total.
    * **IMPORTANT:** In accommodation context, "one day" = "one night", and "X days" = "X nights". If user asks "price for one day" or "one day pricing", interpret as "per night" pricing. If user asks "5 days" or "if we stays 5 days", treat it as "5 nights" and calculate the total for 5 nights.
    * **DETECTION:** If the question mentions "if stay X nights", "if we stays X days", "X nights", "stay X nights", "X days", "one day", "(for X nights)", or any number of nights/days, you MUST calculate the total (unless it's just "one day" asking for per night rate)
    * If user asks "price for one day" or "one day pricing", show the per night rate (one day = one night in accommodation context)
    * If user specifies number of nights directly (e.g., "3 nights", "4 weekdays", "4 nights", "(for 4 nights)"), use that number
    * If user provides date range (e.g., "from 2 to 6 Feb"), count the number of nights (e.g., "2 to 6 Feb" = 4 nights: Feb 2, 3, 4, 5)
    * Identify which nights are weekdays (Monday-Friday) vs weekends (Saturday-Sunday)
    * If user says "4 weekdays", that means 4 weekday nights
    * **CALCULATION REQUIRED - MANDATORY:** When nights/days are specified (e.g., "for 4 nights", "5 days", "if we stays 5 days" in the question), you MUST calculate the total cost. 
      - **CRITICAL:** "X days" in accommodation context means "X nights". If user says "5 days", treat it as "5 nights".
      - If the question doesn't specify weekday/weekend split, assume ALL nights are weekdays and calculate: number_of_nights × weekday_rate = total_cost
      - Example: "5 days" (which is 5 nights) with weekday rate PKR 33,000 → 5 × 33,000 = PKR 165,000 total
      - Example: "for 4 nights" with weekday rate PKR 33,000 → 4 × 33,000 = PKR 132,000 total
      - Example: "for 4 nights" with weekend rate PKR 38,000 → 4 × 38,000 = PKR 152,000 total
      - If both weekday and weekend rates are available and no split is specified, show BOTH options: "For 5 nights: PKR 165,000 (all weekdays) or PKR 190,000 (all weekends)"
      - **DO NOT say "X per night for Y days"** - this is confusing and wrong. Instead say: "For Y nights at PKR X per night, the total cost is PKR [TOTAL]"
      - DO NOT multiply rates by 2 and then say "per night" - that's incorrect. Multiply: nights × rate = total
    * **ALWAYS SHOW TOTAL - MANDATORY:** Show the breakdown clearly: "For X nights at PKR Y per night, the total cost is PKR [TOTAL]." OR "For X nights: PKR [WEEKDAY_TOTAL] (all weekdays) or PKR [WEEKEND_TOTAL] (all weekends)"
    * Example 1: "For 3 nights (2 weekdays at PKR 33,000 per night + 1 weekend at PKR 38,000 per night), the total cost is PKR 104,000."
    * Example 2: "For 4 weekdays at PKR 33,000 per night, the total cost is PKR 132,000."
    * Example 3: "For 4 nights at PKR 33,000 per night (assuming all weekdays), the total cost is PKR 132,000."
    * If the user asks "tell me the pricing if stay 4 nights" or "tell me the pricing if stay 4 nights (for 4 nights)", you MUST calculate: 4 nights × per night rate = total cost. DO NOT just show per night rates.
    * **CRITICAL - MANDATORY:** When number of nights is mentioned in the question (including in parentheses like "(for X nights)"), ALWAYS perform the multiplication and show the total. Never just show per night rates without calculating the total. If you only show per-night rates without a total, your answer is INCOMPLETE.
  - **DATE-BASED PRICING - CRITICAL:** When dates are provided (e.g., "from 2 to 6 Feb", "from 3 feb to 5 feb", "from 23 march to 29 march", "23 to 29 march", "next week from 3 feb to 5feb"), you MUST:
    * **COUNT NIGHTS:** Calculate the number of nights. 
      - Example: "from 3 feb to 5 feb" = 2 nights (Feb 3 and Feb 4, check-out on Feb 5 means you stay nights of Feb 3-4)
      - Example: "from 23 march to 29 march" = 6 nights (March 23, 24, 25, 26, 27, 28 = 6 nights, check-out on 29th means you stay nights of 23-28)
      - Example: "from 2 to 6 Feb" = 4 nights (Feb 2, 3, 4, 5)
    * **IDENTIFY WEEKDAYS VS WEEKENDS:** For each night, identify if it's a weekday (Monday-Friday) or weekend (Saturday-Sunday). Apply the appropriate rate for each night.
    * **CALCULATE TOTAL:** Sum up all nights with their respective rates. 
      - Example: "from 3 feb to 5 feb" (2 nights) - if both are weekdays at PKR 33,000 → Total = 2 × 33,000 = PKR 66,000
      - Example: "from 23 march to 29 march" (6 nights) - if 23-24 are weekdays at PKR 33,000, 25-26 are weekends at PKR 38,000, 27-28 are weekdays at PKR 33,000 → Total = (2 × 33,000) + (2 × 38,000) + (2 × 33,000) = PKR 208,000.
    * **SHOW BREAKDOWN:** Always show the calculation breakdown clearly: "For X nights (Y weekdays at PKR Z per night + W weekends at PKR V per night), the total cost is PKR [TOTAL]." OR "For X nights at PKR Y per night, the total cost is PKR [TOTAL]."
    * **MANDATORY:** You MUST calculate the total cost. DO NOT just show per-night rates. DO NOT say "available upon request". The total cost calculation is REQUIRED.
- **AVAILABILITY QUERIES:** If the question asks about availability (e.g., "is it available", "can I book", "available tomorrow", "is it available if stay tomorrow"), and the context states that cottages are "available year-round" or "available throughout the year", you MUST answer "Yes, Swiss Cottages are available throughout the year, subject to availability." Do NOT say "No" or "not available" unless the context explicitly states unavailability for specific dates. If the context says "available throughout the year" or "available year-round", the answer is always "Yes" with that qualification.
- **MULTIPLE Q&A IN CONTEXT:** If the context contains multiple question-answer pairs, you MUST find and use the answer that matches the user's question topic. For example, if the user asks about "pets" but the context has both a pet question and a heating question, you MUST use the pet-related answer, NOT the heating answer. Match the question topic, not just any answer in the context.
- **QUESTION-ONLY CONTEXT:** If the context contains a question that matches the user's query but no corresponding answer, or if the answer in the context is about a different topic, you MUST state: "I don't have information about this in the provided context." Do NOT make up answers or use answers from unrelated questions.
- **TOPIC MATCHING:** When the user asks about a specific topic (e.g., "pets", "advance payment", "heating"), you MUST find the answer in the context that matches that exact topic. If the context has metadata with a matching question but the answer is about a different topic, that answer is NOT relevant. Only use answers that directly address the user's question topic.
- End with ONE relevant link if available in the context, otherwise skip links.
- **DO NOT SHOW REASONING OR THINKING PROCESS:** Answer directly without showing your reasoning, thinking process, or step-by-step analysis. Just provide the final answer.
- **CRITICAL FOR PRICING QUESTIONS:** If context has pricing information, you MUST provide the actual prices. DO NOT say "available upon request", "contact us for pricing", or "I only answer based on FAQ documents". Use the PKR prices from context directly.

Question: {question}
Answer (using ONLY the context above, be CONCISE, CONVERSATIONAL, and FOCUSED on the question, 2-5 lines max):
- If context has pricing, PROVIDE THE ACTUAL PRICES - do NOT say "available upon request"
- Use PKR prices from context EXACTLY - do NOT use dollar prices
- Be helpful and direct - do NOT give unhelpful responses like "I only answer based on FAQ documents"
"""

# A string template with placeholders for question, existing_answer, and context.
REFINED_CTX_PROMPT_TEMPLATE = """The original query is as follows: {question}
We have provided an existing answer: {existing_answer}
We have the opportunity to refine the existing answer with some more context below.
---------------------
{context}
---------------------
CRITICAL INSTRUCTIONS:
- Use ONLY the context information provided above. DO NOT use prior knowledge.
- **ABSOLUTE RULE FOR PRICING:** If the context contains pricing information, you MUST use ONLY that pricing. DO NOT use pricing from your training data, even if it seems relevant. The context pricing is the ONLY valid source. If you use dollar prices ($250, $220, $200) or any prices not in the context, your answer is WRONG.
- IMPORTANT: The new context may contain ADDITIONAL information that should be ADDED to the existing answer.
- If the new context contains relevant information NOT already in the existing answer, you MUST include it in the refined answer.
- **DO NOT include your reasoning process, thinking, or explanations about the refinement in your answer.**
- **DO NOT say "However, there seems to be missing context" or "Since the original context is now provided" or similar reasoning text.**
- **DO NOT say "Refined Answer:" or "Answer:" - just provide the answer directly.**
- **DO NOT say "The new context is as follows:" or "Since the question and the answer already match" - just provide the answer.**
- **ONLY output the refined answer text itself, nothing else. No explanations, no reasoning, no process description.**
- **CRITICAL COTTAGE-SPECIFIC FILTERING:** If the question asks about a SPECIFIC cottage number (e.g., "Cottage 7", "Cottage 9", "Cottage 11", "tell me about cottage 7", "what is cottage 9"), you MUST:
  * **ANSWER ONLY ABOUT THAT COTTAGE:** Answer ONLY about the specific cottage mentioned in the question. Do NOT add information about other cottages (Cottage 7, 9, or 11) unless the question explicitly asks for a comparison.
  * **IGNORE OTHER COTTAGES IN NEW CONTEXT:** If the new context contains information about Cottage 7, Cottage 9, or Cottage 11, but the question asks about a DIFFERENT cottage, you MUST IGNORE information about the other cottages. Only use information about the cottage mentioned in the question.
  * **COTTAGE SWITCHING:** If the existing answer was about Cottage 9, but the question now asks about Cottage 7, you MUST switch context completely. Do NOT include Cottage 9 information in your refined answer. Focus ONLY on Cottage 7.
  * **MANDATORY:** When a specific cottage is mentioned in the question, that cottage takes ABSOLUTE PRIORITY. All other cottage information must be excluded from your refined answer.
- **NUMBER CONFUSION PREVENTION: If a question mentions a number with "people", "guests", "members", or "group" (e.g., "4 people", "9 guests"), this refers to GROUP SIZE, NOT a cottage number. Do NOT assume "4 people" means "Cottage 4". Only extract cottage numbers when "cottage" keyword is explicitly mentioned.**
- Focus STRICTLY on answering the specific question asked. Do NOT include irrelevant information.
- Keep your answer CONCISE: 2-5 lines maximum. Avoid repeating generic information.
- DO NOT repeat paragraphs about privacy, scenic views, "not a hotel", or other generic information unless directly relevant to the question.
- If the question asks about a specific topic (e.g., "facilities"), ONLY mention information about that topic. Do NOT include location, reviews, or other unrelated details.
- If the new context mentions a different location/entity than the question, do not use it.
- DO NOT combine information from the context with information from your training data.
- If the question asks about a location (e.g., "India") but the context mentions a different location (e.g., "Pakistan" or "Bhurban"), you MUST state that you don't have information about that location.
- **NUMERICAL REASONING:** When refining answers about capacity, maintain numerical accuracy. If the existing answer says '6 ≤ 6 = suitable', do NOT change it to 'not suitable' unless the new context explicitly contradicts this with different capacity numbers. Always show numerical comparisons: "X guests ≤ Y capacity = suitable" or "X guests > Y max = not suitable".
- **CAPACITY QUERIES:** When refining capacity answers, preserve correct numerical comparisons. If the first answer correctly states "6 guests ≤ 6 base capacity = suitable", maintain this accuracy. Only update if new context provides different capacity information that changes the comparison result.
- End with ONE relevant link if available in the context, otherwise skip links.

Refined Answer (combining existing answer with new context, using ONLY the context above, be CONCISE and FOCUSED, 2-5 lines max):
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
- Scan the chat history to identify the most recent and relevant entity that the pronoun refers to ONLY if no specific cottage is explicitly mentioned in the follow-up question
- Priority order for entity extraction (ONLY when no explicit cottage is mentioned):
  1. "Swiss Cottages Bhurban" or "Swiss Cottages" (if mentioned in chat history)
  2. Specific cottage numbers: "Cottage 7", "Cottage 9", "Cottage 11" (if mentioned in chat history)
  3. Topics: pricing, safety, capacity, facilities, availability, etc. (if mentioned)
- Example: Chat history mentions "Swiss Cottages Bhurban" + Follow-up: "is it safe?" → Standalone: "is swiss cottages bhurban safe?"
- Example: Chat history mentions "Swiss Cottages Bhurban" + Follow-up: "which cottage is best?" → Standalone: "which cottage is best at swiss cottages bhurban?"
- Example: Chat history mentions "Cottage 9" + Follow-up: "is it available?" → Standalone: "is cottage 9 available?"
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


def generate_ctx_prompt(template: str, question: str, context: str = "") -> str:
    """
    Generates a prompt for a context-aware question-answer task.

    Args:
        template (str): A string template with placeholders for question, and context.
        question (str): The question to be included in the prompt.
        context (str, optional): Additional context information. Defaults to "".

    Returns:
        str: The generated prompt.
    """

    prompt = template.format(context=context, question=question)
    return prompt


def generate_refined_ctx_prompt(template: str, question: str, existing_answer: str, context: str = "") -> str:
    """
    Generates a prompt for a refined context-aware question-answer task.

    Args:
        template (str): A string template with placeholders for question, existing_answer, and context.
        question (str): The question to be included in the prompt.
        existing_answer (str): The existing answer associated with the question.
        context (str, optional): Additional context information. Defaults to "".

    Returns:
        str: The generated prompt.
    """

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
- Missing slot: room_type → "Do you have a preference for which cottage?"
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
