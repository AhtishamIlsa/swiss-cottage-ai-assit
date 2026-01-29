import os
from typing import Any, Iterator

from groq import Groq

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

    def __init__(self, api_key: str = None, model_name: str = "llama-3.1-8b-instant", model_settings: ModelSettings = None):
        """
        Initialize Groq client.

        Args:
            api_key: Groq API key. If None, will try to get from GROQ_API_KEY env var.
            model_name: Groq model name (default: llama-3.1-8b-instant)
            model_settings: ModelSettings object for compatibility (optional)
        """
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

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_new_tokens,
            temperature=0.7,
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

        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_new_tokens,
                temperature=0.7,
                stream=True,
            )
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
            try:
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        # Format to match LamaCppClient's format
                        yield {
                            "choices": [{
                                "delta": {
                                    "content": chunk.choices[0].delta.content
                                }
                            }]
                        }
            except Exception as e:
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

    @staticmethod
    def generate_ctx_prompt(question: str, context: str) -> str:
        """
        Generates a context-based prompt using predefined templates.

        Args:
            question (str): The question for which the prompt is generated.
            context (str): The context information for the prompt.

        Returns:
            str: The generated context-based prompt.
        """
        return generate_ctx_prompt(
            template=CTX_PROMPT_TEMPLATE,
            question=question,
            context=context,
        )

    @staticmethod
    def generate_refined_ctx_prompt(question: str, context: str, existing_answer: str) -> str:
        """
        Generates a refined prompt for question-answering with existing answer.

        Args:
            question (str): The question for which the prompt is generated.
            context (str): The context information for the prompt.
            existing_answer (str): The existing answer to be refined.

        Returns:
            str: The generated refined prompt.
        """
        return generate_refined_ctx_prompt(
            template=REFINED_CTX_PROMPT_TEMPLATE,
            question=question,
            context=context,
            existing_answer=existing_answer,
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
