"""
Speech-to-Text (STT) component using Groq API Whisper models.
Supports transcription and translation of audio files.
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

# Supported STT models
STT_MODELS = {
    "whisper-large-v3-turbo": "whisper-large-v3-turbo",
    "whisper-large-v3": "whisper-large-v3",
}

# Default model
DEFAULT_STT_MODEL = "whisper-large-v3-turbo"


class GroqSTT:
    """
    Speech-to-Text client using Groq API Whisper models.
    Supports transcription and translation of audio files.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_STT_MODEL,
    ):
        """
        Initialize Groq STT client.

        Args:
            api_key: Groq API key. If None, will try to get from GROQ_API_KEY env var.
            model: Whisper model to use. Options: 'whisper-large-v3-turbo', 'whisper-large-v3'
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
        
        if model not in STT_MODELS:
            raise ValueError(
                f"Invalid model: {model}. Supported models: {list(STT_MODELS.keys())}"
            )
        self.model = STT_MODELS[model]

    def transcribe(
        self,
        audio_file: str | Path,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        response_format: Literal["json", "text", "srt", "verbose_json", "vtt"] = "text",
        temperature: float = 0.0,
    ) -> str:
        """
        Transcribe audio file to text using Groq Whisper API.

        Args:
            audio_file: Path to audio file (supports: mp3, mp4, mpeg, mpga, m4a, wav, webm)
            language: Language code (e.g., 'en', 'es', 'fr'). If None, auto-detects.
            prompt: Optional text prompt to guide the model's style or vocabulary
            response_format: Format of the response. Options: 'json', 'text', 'srt', 'verbose_json', 'vtt'
            temperature: Sampling temperature (0.0 to 1.0). Lower = more deterministic.

        Returns:
            str: Transcribed text (or JSON string if response_format is 'json' or 'verbose_json')
        """
        audio_path = Path(audio_file)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        # Validate file extension
        valid_extensions = {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'}
        if audio_path.suffix.lower() not in valid_extensions:
            logger.warning(
                f"File extension {audio_path.suffix} may not be supported. "
                f"Supported formats: {', '.join(valid_extensions)}"
            )

        try:
            with open(audio_path, "rb") as audio:
                # Groq API audio transcriptions endpoint
                transcription = self.client.audio.transcriptions.create(
                    file=audio,
                    model=self.model,
                    language="en",
                    prompt=prompt,
                    response_format=response_format,
                    temperature=0.0
                )

            if response_format in ["json", "verbose_json"]:
                # For JSON formats, return the full response
                return str(transcription)
            else:
                # For text formats, return the text content
                # Groq returns Transcription object with text attribute
                return transcription.text if hasattr(transcription, 'text') else str(transcription)

        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            raise

    def translate(
        self,
        audio_file: str | Path,
        prompt: Optional[str] = None,
        response_format: Literal["json", "text", "srt", "verbose_json", "vtt"] = "text",
        temperature: float = 0.0,
    ) -> str:
        """
        Translate audio file to English text using Groq Whisper API.

        Args:
            audio_file: Path to audio file (supports: mp3, mp4, mpeg, mpga, m4a, wav, webm)
            prompt: Optional text prompt to guide the model's style or vocabulary
            response_format: Format of the response. Options: 'json', 'text', 'srt', 'verbose_json', 'vtt'
            temperature: Sampling temperature (0.0 to 1.0). Lower = more deterministic.

        Returns:
            str: Translated English text (or JSON string if response_format is 'json' or 'verbose_json')
        """
        audio_path = Path(audio_file)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        try:
            with open(audio_path, "rb") as audio:
                # Groq API audio translations endpoint
                translation = self.client.audio.translations.create(
                    file=audio,
                    model=self.model,
                    prompt=prompt,
                    response_format=response_format,
                    temperature=temperature,
                )

            if response_format in ["json", "verbose_json"]:
                # For JSON formats, return the full response
                return str(translation)
            else:
                # For text formats, return the text content
                # Groq returns Translation object with text attribute
                return translation.text if hasattr(translation, 'text') else str(translation)

        except Exception as e:
            logger.error(f"Error translating audio: {e}")
            raise

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        response_format: Literal["json", "text", "srt", "verbose_json", "vtt"] = "text",
        temperature: float = 0.0,
    ) -> str:
        """
        Transcribe audio from bytes.

        Args:
            audio_bytes: Audio data as bytes
            filename: Filename for the audio (used to determine format)
            language: Language code (e.g., 'en', 'es', 'fr'). If None, auto-detects.
            prompt: Optional text prompt to guide the model's style or vocabulary
            response_format: Format of the response
            temperature: Sampling temperature

        Returns:
            str: Transcribed text
        """
        import io

        try:
            # Create a file-like object from bytes
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename

            transcription = self.client.audio.transcriptions.create(
                file=audio_file,
                model=self.model,
                language=language,
                prompt=prompt,
                response_format=response_format,
                temperature=temperature,
            )

            if response_format in ["json", "verbose_json"]:
                return str(transcription)
            else:
                # Groq returns Transcription object with text attribute
                return transcription.text if hasattr(transcription, 'text') else str(transcription)

        except Exception as e:
            logger.error(f"Error transcribing audio bytes: {e}")
            raise


# -------------------- Example Usage --------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python stt.py <audio_file> [language]")
        print("Example: python stt.py audio.wav en")
        sys.exit(1)

    audio_file = sys.argv[1]
    language = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        stt = GroqSTT()
        transcript = stt.transcribe(audio_file,language="en", temperature=0.0)
        print(f"Transcription: {transcript}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

