"""
Text-to-Speech (TTS) component using Groq API.
Converts text to audio using Groq's speech synthesis models.
"""

import os
from typing import Optional, Literal
from pathlib import Path
import logging

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logging.warning("groq package not available. Install with: pip install groq")

logger = logging.getLogger(__name__)

# Supported TTS models
# Note: Groq API currently supports playai-tts models, but user mentioned orpheus-v1-english
# We'll support both naming conventions
TTS_MODELS = {
    "orpheus-v1-english": "canopylabs/orpheus-v1-english",  # User-specified model
    "playai-tts": "playai-tts",  # Groq SDK default
    "playai-tts-arabic": "playai-tts-arabic",  # Arabic variant
}

# Default model (try user's model first, fallback to Groq default)
DEFAULT_TTS_MODEL = "orpheus-v1-english"

# Supported voice options for orpheus-v1-english model
VOICE_OPTIONS = {
    "autumn": "autumn",
    "diana": "diana",
    "hannah": "hannah",
    "austin": "austin",
    "daniel": "daniel",
    "troy": "troy",
}

# Default voice
DEFAULT_VOICE = "autumn"

# Supported response formats (based on Groq API)
RESPONSE_FORMATS = {
    "mp3": "mp3",
    "flac": "flac",
    "wav": "wav",
    "ogg": "ogg",
    "mulaw": "mulaw",
}

# Default response format (Groq orpheus-v1-english only supports wav)
DEFAULT_RESPONSE_FORMAT = "wav"


class GroqTTS:
    """
    Text-to-Speech client using Groq API.
    Converts text to audio using expressive TTS models.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_TTS_MODEL,
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
    ):
        """
        Initialize Groq TTS client.

        Args:
            api_key: Groq API key. If None, will try to get from GROQ_API_KEY env var.
            model: TTS model to use. Currently: 'orpheus-v1-english'
            voice: Voice to use. Options: 'alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'
            speed: Speed of the generated speech (0.25 to 4.0). Default: 1.0
        """
        if not GROQ_AVAILABLE:
            raise ImportError(
                "groq package is required. Install with: pip install groq"
            )

        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Groq API key is required. Set GROQ_API_KEY environment variable or pass api_key parameter."
            )

        self.client = Groq(api_key=self.api_key)

        # Allow direct model names or mapped names
        if model in TTS_MODELS:
            self.model = TTS_MODELS[model]
        else:
            # Allow direct model ID (e.g., "canopylabs/orpheus-v1-english")
            self.model = model
            logger.info(f"Using model directly: {model}")

        if voice not in VOICE_OPTIONS:
            logger.warning(
                f"Voice '{voice}' may not be supported. Using default: {DEFAULT_VOICE}"
            )
            voice = DEFAULT_VOICE
        self.voice = VOICE_OPTIONS.get(voice, DEFAULT_VOICE)

        # Validate speed
        if not 0.25 <= speed <= 4.0:
            raise ValueError("Speed must be between 0.25 and 4.0")
        self.speed = speed

    def synthesize(
        self,
        text: str,
        output_file: Optional[str | Path] = None,
        response_format: Literal["mp3", "flac", "wav", "ogg", "mulaw"] = DEFAULT_RESPONSE_FORMAT,
    ) -> bytes:
        """
        Synthesize text to speech audio.

        Args:
            text: Text to convert to speech
            output_file: Optional path to save the audio file. If None, returns bytes only.
            response_format: Audio format. Options: 'mp3', 'opus', 'aac', 'flac'

        Returns:
            bytes: Audio data as bytes
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        if response_format not in RESPONSE_FORMATS:
            raise ValueError(
                f"Invalid response_format: {response_format}. "
                f"Supported formats: {list(RESPONSE_FORMATS.keys())}"
            )

        try:
            # Groq API audio speech endpoint
            response = self.client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text,
                response_format=response_format,
                speed=self.speed,
            )

            # Groq returns BinaryAPIResponse which can be read as bytes
            # Try different methods to extract bytes from the response
            if hasattr(response, 'read'):
                # If it has a read() method, use it
                audio_data = response.read()
                logger.debug(f"Extracted audio data using read() method, size: {len(audio_data)} bytes")
            elif hasattr(response, 'content'):
                # If it has a content attribute, use it
                audio_data = response.content
                logger.debug(f"Extracted audio data using content attribute, size: {len(audio_data)} bytes")
            elif hasattr(response, 'iter_bytes'):
                # If it has iter_bytes, collect all chunks
                audio_data = b''.join(response.iter_bytes())
                logger.debug(f"Extracted audio data using iter_bytes(), size: {len(audio_data)} bytes")
            else:
                # Last resort: try to iterate over the response
                try:
                    audio_data = b''.join(response)
                    logger.debug(f"Extracted audio data by iterating, size: {len(audio_data)} bytes")
                except TypeError:
                    # If all else fails, log the response type for debugging
                    logger.error(f"Cannot extract bytes from response. Type: {type(response)}, Attributes: {dir(response)}")
                    raise ValueError(f"Cannot extract bytes from response type: {type(response)}. Available methods: {[m for m in dir(response) if not m.startswith('_')]}")

            # Save to file if output_file is provided
            if output_file:
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(audio_data)
                logger.info(f"Audio saved to: {output_path}")

            return audio_data

        except Exception as e:
            logger.error(f"Error synthesizing speech: {e}")
            raise

    def synthesize_to_file(
        self,
        text: str,
        output_file: str | Path,
        response_format: Literal["mp3", "flac", "wav", "ogg", "mulaw"] = DEFAULT_RESPONSE_FORMAT,
    ) -> Path:
        """
        Synthesize text to speech and save to file.

        Args:
            text: Text to convert to speech
            output_file: Path to save the audio file
            response_format: Audio format

        Returns:
            Path: Path to the saved audio file
        """
        output_path = Path(output_file)
        self.synthesize(text, output_file=output_path, response_format=response_format)
        return output_path

    def synthesize_stream(
        self,
        text: str,
        chunk_size: int = 1024,
        response_format: Literal["mp3", "flac", "wav", "ogg", "mulaw"] = DEFAULT_RESPONSE_FORMAT,
    ):
        """
        Synthesize text to speech and yield audio chunks (for streaming).

        Args:
            text: Text to convert to speech
            chunk_size: Size of each chunk in bytes
            response_format: Audio format

        Yields:
            bytes: Audio data chunks
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            # Get full audio data
            audio_data = self.synthesize(text, response_format=response_format)

            # Yield in chunks
            for i in range(0, len(audio_data), chunk_size):
                yield audio_data[i:i + chunk_size]

        except Exception as e:
            logger.error(f"Error streaming speech synthesis: {e}")
            raise


# -------------------- Example Usage --------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python tts.py <text> [output_file]")
        print("Example: python tts.py 'Hello, world!' output.mp3")
        sys.exit(1)

    text = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "output.mp3"

    try:
        tts = GroqTTS()
        output_path = tts.synthesize_to_file(text, output_file)
        print(f"Audio saved to: {output_path}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

