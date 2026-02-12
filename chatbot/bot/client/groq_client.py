import os
import logging
from typing import Any, Iterator

from groq import Groq

logger = logging.getLogger(__name__)

from bot.client.prompt import (
    CTX_PROMPT_TEMPLATE,
    QA_PROMPT_TEMPLATE,
    REFINED_ANSWER_CONVERSATION_AWARENESS_PROMPT_TEMPLATE,
    REFINED_CTX_PROMPT_TEMPLATE,
    REFINED_QUESTION_CONVERSATION_AWARENESS_PROMPT_TEMPLATE,
    TOOL_SYSTEM_TEMPLATE,
    generate_conversation_awareness_prompt,
    generate_ctx_prompt,
    generate_qa_prompt,
    generate_refined_ctx_prompt,
)
from bot.model.base_model import ModelSettings


class GroqClient:
    """
    Client for Groq API - much faster than local models.
    Compatible with LamaCppClient interface.
    """

    def __init__(self, api_key: str = None, model_name: str = None, model_settings: ModelSettings = None):
        """
        Initialize Groq client.

        Args:
            api_key: Groq API key. If None, will try to get from GROQ_API_KEY env var.
            model_name: Groq model name. If None, will use FAST_MODEL_NAME env var (default: llama-3.1-8b-instant)
            model_settings: ModelSettings object for compatibility (optional)
        """
        # Use env var if model_name not provided
        if model_name is None:
            model_name = os.getenv("FAST_MODEL_NAME", "llama-3.1-8b-instant")
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("Groq API key is required. Set GROQ_API_KEY environment variable or pass api_key parameter.")
        
        self.client = Groq(api_key=self.api_key)
        self.model_name = model_name
        self.model_settings = model_settings or self._create_default_model_settings()
    
    def _create_default_model_settings(self) -> ModelSettings:
        """Create a default ModelSettings object for compatibility."""
        from bot.model.settings.llama import Llama31Settings
        return Llama31Settings()

    def generate_answer(self, prompt: str, max_new_tokens: int = 512) -> str:
        """
        Generates an answer based on the given prompt using Groq API.

        Args:
            prompt (str): The input prompt for generating the answer.
            max_new_tokens (int): The maximum number of new tokens to generate (default is 512).

        Returns:
            str: The generated answer.
        """
        system_content = self.model_settings.system_template if self.model_settings else "You are a helpful assistant."

        # Add stop sequences for early stopping
        stop_sequences = ["\n\n\n", "---", "###", "##"]
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_new_tokens,
            temperature=0.7,
            stop=stop_sequences,
        )

        return response.choices[0].message.content

    async def async_generate_answer(self, prompt: str, max_new_tokens: int = 512) -> str:
        """
        Generates an answer based on the given prompt using Groq API asynchronously.

        Args:
            prompt (str): The input prompt for generating the answer.
            max_new_tokens (int): The maximum number of new tokens to generate (default is 512).

        Returns:
            str: The generated answer.
        """
        return self.generate_answer(prompt, max_new_tokens)

    def stream_answer(self, prompt: str, max_new_tokens: int = 512) -> str:
        """
        Generates an answer by streaming tokens.

        Args:
            prompt (str): The input prompt for generating the answer.
            max_new_tokens (int): The maximum number of new tokens to generate (default is 512).

        Returns:
            str: The generated answer.
        """
        answer = ""
        stream = self.start_answer_iterator_streamer(prompt, max_new_tokens=max_new_tokens)

        for output in stream:
            token = self.parse_token(output)
            answer += token
            print(token, end="", flush=True)

        return answer

    def start_answer_iterator_streamer(
        self, prompt: str, max_new_tokens: int = 512
    ) -> Iterator[dict]:
        """
        Start an answer iterator streamer for a given prompt using Groq API.

        Args:
            prompt (str): The input prompt for generating the answer.
            max_new_tokens (int): The maximum number of new tokens to generate (default is 512).

        Returns:
            Iterator[dict]: Iterator that yields token dictionaries compatible with LamaCppClient format.
        """
        system_content = self.model_settings.system_template if self.model_settings else "You are a helpful assistant."

        # Add stop sequences for early stopping
        stop_sequences = ["\n\n\n", "---", "###", "##"]
        
        try:
            logger.info(f"🔧 Creating Groq stream with max_tokens={max_new_tokens}, model={self.model_name}, prompt_length={len(prompt)}")
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_new_tokens,
                temperature=0.7,
                stream=True,
                stop=stop_sequences,
            )
            logger.info(f"✅ Groq stream created successfully with max_tokens={max_new_tokens}")
            logger.debug(f"Created Groq stream for prompt (length: {len(prompt)} chars)")
            import sys
            print(f"[GROQ_API] Created Groq stream for model: {self.model_name}, prompt length: {len(prompt)}", file=sys.stderr, flush=True)
            logger.error(f"[GROQ_API] Created Groq stream for model: {self.model_name}, prompt length: {len(prompt)}")
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "rate limit" in error_msg or "rate_limit" in error_msg:
                raise RuntimeError(
                    f"Rate limit error: {e}\n\n"
                    "Please wait a few seconds and try again. "
                    "You may need to upgrade your Groq API tier for higher rate limits."
                ) from e
            raise

        def streamer():
            chunk_count = 0
            empty_chunks = 0
            is_gpt_oss = "gpt-oss" in self.model_name.lower() or "openai/gpt" in self.model_name.lower()
            # Force logging to stderr as well to ensure we see it
            import sys
            print(f"[GROQ_STREAMER] Starting to iterate over Groq stream for model: {self.model_name} (is_gpt_oss: {is_gpt_oss})", file=sys.stderr, flush=True)
            logger.error(f"[GROQ_STREAMER] Starting to iterate over Groq stream for model: {self.model_name} (is_gpt_oss: {is_gpt_oss})")
            try:
                for chunk in stream:
                    chunk_count += 1
                    # Log raw chunk structure for first few chunks - ALWAYS log these
                    if chunk_count <= 5:
                        logger.info(f"Raw chunk {chunk_count} type: {type(chunk)}, has choices: {hasattr(chunk, 'choices')}")
                        if hasattr(chunk, 'choices'):
                            logger.info(f"Chunk {chunk_count} choices length: {len(chunk.choices) if chunk.choices else 0}")
                        # Log the entire chunk structure for debugging
                        try:
                            logger.info(f"Chunk {chunk_count} full structure: {chunk}")
                        except:
                            logger.info(f"Chunk {chunk_count} full structure: (could not stringify)")
                        if hasattr(chunk, '__dict__'):
                            logger.info(f"Chunk {chunk_count} attributes: {list(chunk.__dict__.keys())}")
                        else:
                            logger.info(f"Chunk {chunk_count} has no __dict__ attribute")
                    
                    # Check if chunk has choices and content
                    if chunk.choices and len(chunk.choices) > 0:
                        choice = chunk.choices[0]
                        
                        # Check for finish_reason - if present and not None, this might be the last chunk
                        finish_reason = getattr(choice, 'finish_reason', None)
                        if finish_reason:
                            logger.warning(f"⚠️ Chunk {chunk_count} has finish_reason: {finish_reason} - Stream may be ending early!")
                            if finish_reason == "stop" and chunk_count < 100:
                                logger.error(f"🚨 EARLY STOP DETECTED at chunk {chunk_count} with finish_reason='stop' - This may indicate stop sequence was hit or max_tokens limit reached")
                        elif chunk_count <= 3:
                            logger.info(f"Chunk {chunk_count} has finish_reason: {finish_reason}")
                        
                        # Log choice structure for first few chunks
                        if chunk_count <= 3:
                            logger.info(f"Choice {chunk_count} type: {type(choice)}, has delta: {hasattr(choice, 'delta')}, finish_reason: {finish_reason}")
                            if hasattr(choice, '__dict__'):
                                logger.info(f"Choice {chunk_count} attributes: {list(choice.__dict__.keys())}")
                        
                        delta = getattr(choice, 'delta', None)
                        if delta:
                            # Log delta structure for first few chunks - ALWAYS log these with ERROR level
                            if chunk_count <= 5:
                                import sys
                                print(f"[GROQ_STREAMER] Delta {chunk_count} type: {type(delta)}", file=sys.stderr, flush=True)
                                logger.error(f"[GROQ_STREAMER] Delta {chunk_count} type: {type(delta)}")
                                if hasattr(delta, '__dict__'):
                                    attrs = list(delta.__dict__.keys())
                                    print(f"[GROQ_STREAMER] Delta {chunk_count} attributes: {attrs}", file=sys.stderr, flush=True)
                                    logger.error(f"[GROQ_STREAMER] Delta {chunk_count} attributes: {attrs}")
                                else:
                                    print(f"[GROQ_STREAMER] Delta {chunk_count} has no __dict__ attribute", file=sys.stderr, flush=True)
                                    logger.error(f"[GROQ_STREAMER] Delta {chunk_count} has no __dict__ attribute")
                                # Try to get content immediately and log it
                                try:
                                    direct_content = delta.content if hasattr(delta, 'content') else None
                                    print(f"[GROQ_STREAMER] Delta {chunk_count} direct content access: {repr(direct_content)}", file=sys.stderr, flush=True)
                                    logger.error(f"[GROQ_STREAMER] Delta {chunk_count} direct content access: {repr(direct_content)}")
                                except Exception as e:
                                    print(f"[GROQ_STREAMER] Delta {chunk_count} direct content access failed: {e}", file=sys.stderr, flush=True)
                                    logger.error(f"[GROQ_STREAMER] Delta {chunk_count} direct content access failed: {e}")
                            
                            # Try different ways to get content
                            # For GPT-OSS models, the response structure might be different
                            # CRITICAL: Check if delta.content exists but is None vs doesn't exist
                            if chunk_count <= 3:
                                import sys
                                # Try to get all possible attributes using dir()
                                try:
                                    delta_attrs = [attr for attr in dir(delta) if not attr.startswith('_')]
                                    print(f"[GROQ_DEBUG] Delta {chunk_count} dir() attributes (first 20): {delta_attrs[:20]}", file=sys.stderr, flush=True)
                                    logger.error(f"[GROQ_DEBUG] Delta {chunk_count} dir() attributes (first 20): {delta_attrs[:20]}")
                                except:
                                    pass
                                
                                # Try accessing content via different methods and log the actual values
                                for attr in ['content', 'text', 'message', 'role', 'function_call', 'tool_calls']:
                                    if hasattr(delta, attr):
                                        try:
                                            val = getattr(delta, attr)
                                            print(f"[GROQ_DEBUG] Delta {chunk_count}.{attr} = {repr(val)} (type: {type(val)})", file=sys.stderr, flush=True)
                                            logger.error(f"[GROQ_DEBUG] Delta {chunk_count}.{attr} = {repr(val)} (type: {type(val)})")
                                        except Exception as e:
                                            print(f"[GROQ_DEBUG] Delta {chunk_count}.{attr} access failed: {e}", file=sys.stderr, flush=True)
                                            logger.error(f"[GROQ_DEBUG] Delta {chunk_count}.{attr} access failed: {e}")
                            
                            if is_gpt_oss:
                                # GPT-OSS models might use different field names - try all possible locations
                                content = None
                                
                                # First try standard delta.content
                                if hasattr(delta, 'content'):
                                    try:
                                        content = delta.content
                                    except:
                                        pass
                                
                                # Try delta.text
                                if content is None and hasattr(delta, 'text'):
                                    try:
                                        content = delta.text
                                    except:
                                        pass
                                
                                # Try choice.content (some models put it here)
                                if content is None and hasattr(choice, 'content'):
                                    try:
                                        content = choice.content
                                    except:
                                        pass
                                
                                # Try choice.text
                                if content is None and hasattr(choice, 'text'):
                                    try:
                                        content = choice.text
                                    except:
                                        pass
                                
                                # Try as dict
                                if content is None and isinstance(delta, dict):
                                    content = delta.get('content') or delta.get('text')
                                
                                # Try choice as dict
                                if content is None and isinstance(choice, dict):
                                    content = choice.get('content') or choice.get('text')
                                
                                # Try getattr as fallback
                                if content is None:
                                    content = getattr(delta, 'content', None)
                                if content is None:
                                    content = getattr(delta, 'text', None)
                                if content is None:
                                    content = getattr(choice, 'content', None)
                                if content is None:
                                    content = getattr(choice, 'text', None)
                            else:
                                # Standard llama models - use standard approach
                                # First, try the standard delta.content (most common)
                                content = getattr(delta, 'content', None)
                                
                                # If None, try accessing it directly (some API versions)
                                if content is None and hasattr(delta, 'content'):
                                    try:
                                        content = delta.content
                                    except:
                                        pass
                                
                                # Also check if there's a 'text' attribute (some API versions use this)
                                if content is None:
                                    content = getattr(delta, 'text', None)
                                
                                # Also check if content is in the choice itself (some API versions)
                                if content is None:
                                    content = getattr(choice, 'content', None)
                                if content is None:
                                    content = getattr(choice, 'text', None)
                                
                                # Last resort: check if delta is a dict-like object
                                if content is None and hasattr(delta, 'get'):
                                    content = delta.get('content') or delta.get('text')
                                
                                # If still None, try to access as dict
                                if content is None and isinstance(delta, dict):
                                    content = delta.get('content') or delta.get('text')
                            
                            # Check if content is actually an empty string vs None
                            # Groq sometimes sends empty strings for certain chunks (like finish_reason chunks)
                            if content == "":
                                # Empty string - this is normal for some chunks, skip it
                                empty_chunks += 1
                                if chunk_count <= 3:
                                    logger.debug(f"Chunk {chunk_count} has empty string content (normal), continuing...")
                                continue
                            
                            # Log first few chunks to debug
                            if chunk_count <= 5:
                                logger.info(f"Chunk {chunk_count}: delta type={type(delta)}, content={repr(content)}, content type={type(content) if content else None}")
                                if hasattr(delta, '__dict__'):
                                    logger.info(f"Chunk {chunk_count} delta attributes: {list(delta.__dict__.keys())}")
                            
                            # Only yield if content is not None and not empty
                            if content:  # Yield only non-empty content
                                # Format to match LamaCppClient's format
                                yield {
                                    "choices": [{
                                        "delta": {
                                            "content": content
                                        }
                                    }]
                                }
                            else:
                                empty_chunks += 1
                                if chunk_count == 1:
                                    logger.debug(f"First chunk has no content (this is normal for Groq streaming), continuing...")
                                elif empty_chunks <= 3:
                                    logger.debug(f"Chunk {chunk_count} has no content, continuing...")
                        else:
                            empty_chunks += 1
                            if chunk_count <= 3:
                                logger.warning(f"Chunk {chunk_count} has no delta attribute")
                    else:
                        empty_chunks += 1
                        if chunk_count <= 3:
                            logger.debug(f"Chunk {chunk_count} has no choices, continuing...")
                
                if chunk_count > 0 and empty_chunks == chunk_count:
                    logger.error(f"All {chunk_count} chunks had no content - stream is empty or API returned no content. This may indicate an API issue or the response was cut off.")
                    # Log more details about the last few chunks for debugging
                    logger.error(f"Last chunk processed: chunk_count={chunk_count}, empty_chunks={empty_chunks}")
                elif empty_chunks > 0:
                    logger.debug(f"Processed {chunk_count} chunks, {empty_chunks} were empty, {chunk_count - empty_chunks} had content")
            except Exception as e:
                logger.error(f"Error in streamer generator (processed {chunk_count} chunks, {empty_chunks} empty before error): {e}", exc_info=True)
                error_msg = str(e).lower()
                if "429" in error_msg or "rate limit" in error_msg or "rate_limit" in error_msg:
                    raise RuntimeError(
                        f"Rate limit error during streaming: {e}\n\n"
                        "Please wait a few seconds and try again. "
                        "You may need to upgrade your Groq API tier for higher rate limits."
                    ) from e
                raise

        return streamer()

    async def async_start_answer_iterator_streamer(
        self, prompt: str, max_new_tokens: int = 512
    ) -> Iterator[dict]:
        """
        Asynchronously start an answer iterator streamer.

        Args:
            prompt (str): The input prompt for generating the answer.
            max_new_tokens (int): The maximum number of new tokens to generate (default is 512).

        Returns:
            Iterator[dict]: Iterator that yields token dictionaries.
        """
        return self.start_answer_iterator_streamer(prompt, max_new_tokens)

    def retrieve_tools(
        self, prompt: str, max_new_tokens: int = 512, tools: list[dict] = None, tool_choice: str = None
    ) -> list[dict] | None:
        """
        Retrieves tools based on the given prompt using Groq API.

        Args:
            prompt (str): The input prompt for retrieving tools.
            max_new_tokens (int): The maximum number of new tokens to generate (default is 512).
            tools (list[dict], optional): A list of tools that can be used by the language model.
            tool_choice (str, optional): The specific tool to use. If None, the tool choice is set to "auto".

        Returns:
            list[dict] | None: A list of tool calls made by the language model, or None if no tools were called.
        """
        tool_choice_param = {"type": "function", "function": {"name": tool_choice}} if tool_choice else "auto"

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": TOOL_SYSTEM_TEMPLATE},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_new_tokens,
            tools=tools,
            tool_choice=tool_choice_param,
            temperature=0.7,
        )

        tool_calls = response.choices[0].message.tool_calls
        return tool_calls if tool_calls else None

    @staticmethod
    def parse_token(token):
        """Parse token from stream response (compatible with LamaCppClient format)."""
        return token["choices"][0]["delta"].get("content", "")

    @staticmethod
    def generate_qa_prompt(question: str) -> str:
        """
        Generates a question-answering (QA) prompt using predefined templates.

        Args:
            question (str): The question for which the prompt is generated.

        Returns:
            str: The generated QA prompt.
        """
        return generate_qa_prompt(
            template=QA_PROMPT_TEMPLATE,
            question=question,
        )

    def generate_ctx_prompt(self, question: str, context: str, use_simple_prompt: bool = False) -> str:
        """
        Generates a context-based prompt using predefined templates.

        Args:
            question (str): The question for which the prompt is generated.
            context (str): The context information for the prompt.
            use_simple_prompt (bool, optional): If True, use simple prompt template. Defaults to False.

        Returns:
            str: The generated context-based prompt.
        """
        return generate_ctx_prompt(
            template=None,  # Will select based on use_simple_prompt
            question=question,
            context=context,
            use_simple_prompt=use_simple_prompt,
        )

    def generate_refined_ctx_prompt(self, question: str, context: str, existing_answer: str, use_simple_prompt: bool = False) -> str:
        """
        Generates a refined prompt for question-answering with existing answer.

        Args:
            question (str): The question for which the prompt is generated.
            context (str): The context information for the prompt.
            existing_answer (str): The existing answer to be refined.
            use_simple_prompt (bool, optional): If True, use simple prompt template. Defaults to False.

        Returns:
            str: The generated refined prompt.
        """
        return generate_refined_ctx_prompt(
            template=None,  # Will select based on use_simple_prompt
            question=question,
            context=context,
            existing_answer=existing_answer,
            use_simple_prompt=use_simple_prompt,
        )

    @staticmethod
    def generate_refined_question_conversation_awareness_prompt(question: str, chat_history: str) -> str:
        return generate_conversation_awareness_prompt(
            template=REFINED_QUESTION_CONVERSATION_AWARENESS_PROMPT_TEMPLATE,
            question=question,
            chat_history=chat_history,
        )

    @staticmethod
    def generate_refined_answer_conversation_awareness_prompt(question: str, chat_history: str) -> str:
        return generate_conversation_awareness_prompt(
            template=REFINED_ANSWER_CONVERSATION_AWARENESS_PROMPT_TEMPLATE,
            question=question,
            chat_history=chat_history,
        )
