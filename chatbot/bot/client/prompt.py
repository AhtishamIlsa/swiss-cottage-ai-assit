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
CRITICAL INSTRUCTIONS:
- Answer the question using ONLY the context information provided above.
- DO NOT use any prior knowledge, training data, or information not in the context.
- Be CONVERSATIONAL and HELPFUL like ChatGPT - acknowledge the user's intent naturally.
- If the question is a booking request (e.g., "book this cottage for me"), acknowledge that you understand they want to book, but focus on providing the booking information from the context.
- **CRITICAL: If the question asks about a SPECIFIC cottage number (e.g., "Cottage 7", "Cottage 9", "Cottage 11"), you MUST answer ONLY about that specific cottage. Do NOT mention other cottages unless the question explicitly asks for a comparison.**
- **If the question asks "tell me about Cottage 7" or "what is Cottage 7", focus ONLY on Cottage 7 information. Ignore information about Cottage 9 or Cottage 11 in the context unless the question asks for comparison.**
- Focus STRICTLY on answering the specific question asked. Do NOT include irrelevant information.
- Keep your answer CONCISE: 2-5 lines maximum. Avoid repeating generic information.
- DO NOT repeat paragraphs about privacy, scenic views, "not a hotel", or other generic information unless directly relevant to the question.
- If the question asks about a specific topic (e.g., "facilities"), ONLY mention information about that topic. Do NOT include location, reviews, or other unrelated details.
- If the context contains payment/pricing information, you MUST include it. Do NOT refuse to answer pricing questions.
- If the context does not contain information to answer the question, respond with: "I don't have information about this in the provided context."
- If the context mentions a different location/entity than asked in the question, clearly state that the context is about a different location/entity and you cannot answer.
- DO NOT combine information from the context with information from your training data.
- If the question asks about a location (e.g., "India") but the context mentions a different location (e.g., "Pakistan" or "Bhurban"), you MUST state that you don't have information about that location.
- End with ONE relevant link if available in the context, otherwise skip links.

Question: {question}
Answer (using ONLY the context above, be CONCISE, CONVERSATIONAL, and FOCUSED on the question, 2-5 lines max):
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
- IMPORTANT: The new context may contain ADDITIONAL information that should be ADDED to the existing answer.
- If the new context contains relevant information NOT already in the existing answer, you MUST include it in the refined answer.
- **CRITICAL: If the question asks about a SPECIFIC cottage number (e.g., "Cottage 7", "Cottage 9", "Cottage 11"), you MUST answer ONLY about that specific cottage. Do NOT add information about other cottages unless the question explicitly asks for a comparison.**
- **If the question asks "tell me about Cottage 7" or "what is Cottage 7", focus ONLY on Cottage 7 information. Ignore information about Cottage 9 or Cottage 11 in the new context unless the question asks for comparison.**
- Focus STRICTLY on answering the specific question asked. Do NOT include irrelevant information.
- Keep your answer CONCISE: 2-5 lines maximum. Avoid repeating generic information.
- DO NOT repeat paragraphs about privacy, scenic views, "not a hotel", or other generic information unless directly relevant to the question.
- If the question asks about a specific topic (e.g., "facilities"), ONLY mention information about that topic. Do NOT include location, reviews, or other unrelated details.
- If the new context mentions a different location/entity than the question, do not use it.
- DO NOT combine information from the context with information from your training data.
- If the question asks about a location (e.g., "India") but the context mentions a different location (e.g., "Pakistan" or "Bhurban"), you MUST state that you don't have information about that location.
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
Standalone question:
"""

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
