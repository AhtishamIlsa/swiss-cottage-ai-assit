"""
Speech processing module for STT, TTS, and VAD.
"""

from .stt import GroqSTT, STT_MODELS, DEFAULT_STT_MODEL
from .tts import GroqTTS, TTS_MODELS, DEFAULT_TTS_MODEL, VOICE_OPTIONS, DEFAULT_VOICE
from .vad import VoiceActivityDetector

__all__ = [
    # STT
    "GroqSTT",
    "STT_MODELS",
    "DEFAULT_STT_MODEL",
    # TTS
    "GroqTTS",
    "TTS_MODELS",
    "DEFAULT_TTS_MODEL",
    "VOICE_OPTIONS",
    "DEFAULT_VOICE",
    # VAD
    "VoiceActivityDetector",
]

