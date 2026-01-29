import asyncio
import re
from asyncio import get_event_loop
from typing import Any, TYPE_CHECKING, Union

import streamlit as st
from entities.document import Document
from helpers.log import get_logger

from bot.conversation.chat_history import ChatHistory
from bot.conversation.ctx_strategy import AsyncTreeSummarizationStrategy, BaseSynthesisStrategy

if TYPE_CHECKING:
    from bot.client.lama_cpp_client import LamaCppClient
    from bot.client.groq_client import GroqClient

logger = get_logger(__name__)


def refine_question(llm: Union["LamaCppClient", "GroqClient", Any], question: str, chat_history: ChatHistory, max_new_tokens: int = 128) -> str:
    """
    Refines the given question based on the chat history.

    Args:
        llm (LlmClient): The language model client for conversation-related tasks.
        question (str): The original question.
        chat_history (List[Tuple[str, str]]): A list to store the conversation
        history as tuples of questions and answers.
        max_new_tokens (int, optional): The maximum number of tokens to generate in the answer.
            Defaults to 128.

    Returns:
        str: The refined question.
    """

    if chat_history:
        logger.info("--- Refining the question based on the chat history... ---")

        conversation_awareness_prompt = llm.generate_refined_question_conversation_awareness_prompt(
            question, str(chat_history)
        )

        logger.info(f"--- Prompt:\n {conversation_awareness_prompt} \n---")

        refined_question = llm.generate_answer(conversation_awareness_prompt, max_new_tokens=max_new_tokens)

        if llm.model_settings.reasoning:
            refined_question = extract_content_after_reasoning(refined_question, llm.model_settings.reasoning_stop_tag)
            if refined_question == "":
                refined_question = question

        logger.info(f"--- Refined Question: {refined_question} ---")

        return refined_question
    else:
        return question


def answer(llm: Union["LamaCppClient", "GroqClient", Any], question: str, chat_history: ChatHistory, max_new_tokens: int = 512) -> Any:
    """
    Generates an answer to the given question based on the chat history or a direct prompt.

    Args:
        llm (LlmClient): The language model client for conversation-related tasks.
        question (str): The input question for which an answer is generated.
        chat_history (List[Tuple[str, str]]): A list to store the conversation
        history as tuples of questions and answers.
        max_new_tokens (int, optional): The maximum number of tokens to generate in the answer.
            Defaults to 512.

    Returns:
        A streaming iterator (Any) for progressively generating the answer.

    Notes:
        The method checks if there is existing chat history. If chat history is available,
        it constructs a conversation-awareness prompt using the question and chat history.
        The answer is then generated using the LLM with the conversation-awareness prompt.
        If no chat history is available, a prompt is generated directly from the input question,
        and the answer is generated accordingly.
    """

    if chat_history:
        logger.info("--- Answer the question based on the chat history... ---")

        conversation_awareness_prompt = llm.generate_refined_answer_conversation_awareness_prompt(
            question, str(chat_history)
        )

        logger.debug(f"--- Prompt:\n {conversation_awareness_prompt} \n---")

        streamer = llm.start_answer_iterator_streamer(conversation_awareness_prompt, max_new_tokens=max_new_tokens)

        return streamer
    else:
        prompt = llm.generate_qa_prompt(question=question)
        logger.debug(f"--- Prompt:\n {prompt} \n---")
        streamer = llm.start_answer_iterator_streamer(prompt, max_new_tokens=max_new_tokens)
        return streamer


def answer_with_context(
    llm: Union["LamaCppClient", "GroqClient", Any],
    ctx_synthesis_strategy: BaseSynthesisStrategy,
    question: str,
    chat_history: ChatHistory,
    retrieved_contents: list[Document],
    max_new_tokens: int = 512,
):
    """
    Generates an answer to the given question using a context synthesis strategy and retrieved contents.
    If the content is not provided generates an answer based on the chat history or a direct prompt.

    Args:
        llm (LlmClient): The language model client for conversation-related tasks.
        ctx_synthesis_strategy (BaseSynthesisStrategy): The strategy to use for context synthesis.
        question (str): The input question for which an answer is generated.
        chat_history (List[Tuple[str, str]]): A list to store the conversation
        history as tuples of questions and answers.
        retrieved_contents (list[Document]): A list of documents retrieved for context.
        max_new_tokens (int, optional): The maximum number of tokens to generate in the answer. Defaults to 512.

    Returns:
        tuple: A tuple containing the answer streamer and formatted prompts.
    """
    if not retrieved_contents:
        # Do NOT generate answer from LLM training data when no documents are found
        # Return empty streamer to prevent hallucination
        logger.warning("No retrieved contents - refusing to generate answer from training data")
        def empty_streamer():
            yield ""
        return empty_streamer(), []

    if isinstance(ctx_synthesis_strategy, AsyncTreeSummarizationStrategy):
        # Handle async strategy - try to use existing loop or create new one
        logger.warning("Using async-tree-summarization strategy - this is very slow! Consider using 'create-and-refine' instead.")
        try:
            # Try to get running loop first
            try:
                loop = asyncio.get_running_loop()
                # If we have a running loop, we need to use nest_asyncio
                from bot.conversation.ctx_strategy import _ensure_nest_asyncio
                _ensure_nest_asyncio()
                result = loop.run_until_complete(
                    ctx_synthesis_strategy.generate_response(retrieved_contents, question, max_new_tokens=max_new_tokens)
                )
            except RuntimeError:
                # No running loop, create a new one
                loop = get_event_loop()
                result = loop.run_until_complete(
                    ctx_synthesis_strategy.generate_response(retrieved_contents, question, max_new_tokens=max_new_tokens)
                )
            
            # Ensure result is a tuple - check if it's still a coroutine (shouldn't happen)
            if hasattr(result, '__await__'):
                # This is still a coroutine - something went wrong with async handling
                logger.error("Result is still a coroutine - async handling failed")
                raise RuntimeError(
                    "❌ Async strategy error: coroutine was not properly awaited.\n\n"
                    "💡 **Solution:** Use the faster 'create-and-refine' strategy instead:\n"
                    "   ./run_rag_chatbot.sh llama-3.1 5 create-and-refine 512\n\n"
                    "If Streamlit is caching the old strategy, clear cache first:\n"
                    "   rm -rf ~/.streamlit/cache"
                )
            elif isinstance(result, tuple) and len(result) >= 2:
                streamer, fmt_prompts = result[0], result[1]
            elif isinstance(result, tuple) and len(result) == 1:
                streamer = result[0]
                fmt_prompts = []
            else:
                # If it's just a streamer, wrap it
                streamer = result
                fmt_prompts = []
        except RuntimeError as e:
            # Re-raise RuntimeError with our message
            raise
        except Exception as e:
            logger.error(f"Error with async strategy: {e}", exc_info=True)
            raise RuntimeError(
                f"❌ Async strategy failed: {e}\n\n"
                "💡 **Solution:** Use the faster 'create-and-refine' strategy instead:\n"
                "   ./run_rag_chatbot.sh llama-3.1 5 create-and-refine 512\n\n"
                "If Streamlit is caching the old strategy, clear cache first:\n"
                "   rm -rf ~/.streamlit/cache"
            ) from e
    else:
        # Non-async strategies (create-and-refine, tree-summarization)
        try:
            result = ctx_synthesis_strategy.generate_response(
            retrieved_contents, question, max_new_tokens=max_new_tokens
        )
            # Ensure result is a tuple
            if isinstance(result, tuple):
                streamer, fmt_prompts = result
            else:
                # If it's just a streamer, wrap it
                streamer = result
                fmt_prompts = []
        except Exception as e:
            logger.error(f"Error with synthesis strategy: {e}", exc_info=True)
            raise RuntimeError(f"Strategy failed: {e}") from e
    
    return streamer, fmt_prompts


def extract_content_after_reasoning(text: str, reasoning_stop_tag: str) -> str:
    """
    Extracts and strips the text that follows the `reasoning_stop_tag` tag.

    Args:
        text: The input string containing the tag.
        reasoning_stop_tag: The tag after which the text should be extracted.

    Returns:
        The text after the `reasoning_stop_tag` tag, stripped of whitespace, or an empty string
        if the tag is not found.
    """
    try:
        _, content = re.split(reasoning_stop_tag, text, maxsplit=1, flags=re.IGNORECASE)

        if content == "":
            logger.warning(f"Reasoning stop tag '{reasoning_stop_tag}' found but no content after it.")
        else:
            logger.info(f"Extracted content after reasoning stop tag '{reasoning_stop_tag}': {content}")

        return content.strip()
    except ValueError:
        logger.warning(f"Reasoning stop tag '{reasoning_stop_tag}' not found in the text. Returning empty content.")
        return ""


# TODO: Use it later
def stream_response_with_reasoning(
    llm: Union["LamaCppClient", "GroqClient", Any], user_input: str, chat_history: ChatHistory, max_new_tokens: int
) -> tuple[str, str]:
    """
    Streams a response from the language model (LLM) to the user input, including reasoning, and
    updates the UI in real-time.

    Args:
        llm (LamaCppClient): The language model client used to generate responses.
        user_input (str): The input provided by the user.
        chat_history (ChatHistory): The conversation history to provide context for the response.
        max_new_tokens (int): The maximum number of tokens to generate in the response.

    Returns:
        tuple[str, str]: A tuple containing:
            - full_response (str): The full response generated by the LLM.
            - reasoning_response (str): The reasoning portion of the response.

    Notes:
        - The function uses a placeholder to display the response progressively in the UI.
        - The reasoning portion is identified and displayed separately using start and stop tags.
        - The response is updated token by token, with a cursor ("▌") indicating ongoing generation.
    """
    message_placeholder = st.empty()
    full_response = ""
    reasoning_response = ""
    inside_think = False
    for token in answer(llm=llm, question=user_input, chat_history=chat_history, max_new_tokens=max_new_tokens):
        parsed_token = llm.parse_token(token)
        stripped_token = parsed_token.strip()

        if stripped_token == llm.model_settings.reasoning_start_tag:
            inside_think = True
            reasoning_response += parsed_token
            continue

        if stripped_token == llm.model_settings.reasoning_stop_tag:
            inside_think = False
            reasoning_response += parsed_token
            continue

        if inside_think:
            reasoning_response += parsed_token
        else:
            full_response += llm.parse_token(token)

        message_placeholder.markdown(reasoning_response + full_response + "▌")

    message_placeholder.markdown(reasoning_response + full_response)

    return full_response, reasoning_response
