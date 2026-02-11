"""
Example usage of STT and TTS components.
"""

import os
from pathlib import Path
from stt import GroqSTT, DEFAULT_STT_MODEL
from tts import GroqTTS, DEFAULT_TTS_MODEL

# Example 1: Transcribe audio file
def example_transcribe():
    """Example: Transcribe an audio file to text."""
    print("Example 1: Transcribing audio file...")
    
    # Initialize STT client
    stt = GroqSTT(model=DEFAULT_STT_MODEL)
    
    # Transcribe audio file
    audio_file = "sample_audio.wav"  # Replace with your audio file
    if Path(audio_file).exists():
        transcript = stt.transcribe(audio_file, language="en")
        print(f"Transcription: {transcript}")
    else:
        print(f"Audio file not found: {audio_file}")


# Example 2: Translate audio file to English
def example_translate():
    """Example: Translate an audio file to English."""
    print("\nExample 2: Translating audio file to English...")
    
    # Initialize STT client
    stt = GroqSTT(model=DEFAULT_STT_MODEL)
    
    # Translate audio file
    audio_file = "spanish_audio.wav"  # Replace with your audio file
    if Path(audio_file).exists():
        translation = stt.translate(audio_file)
        print(f"Translation: {translation}")
    else:
        print(f"Audio file not found: {audio_file}")


# Example 3: Synthesize text to speech
def example_synthesize():
    """Example: Convert text to speech."""
    print("\nExample 3: Synthesizing text to speech...")
    
    # Initialize TTS client
    tts = GroqTTS(model=DEFAULT_TTS_MODEL, voice="alloy", speed=1.0)
    
    # Synthesize text
    text = "Hello! This is a test of the text-to-speech system."
    output_file = "output.mp3"
    
    try:
        audio_data = tts.synthesize(text, output_file=output_file)
        print(f"Audio saved to: {output_file}")
        print(f"Audio data size: {len(audio_data)} bytes")
    except Exception as e:
        print(f"Error: {e}")
        print("Note: Make sure GROQ_API_KEY is set in your environment")


# Example 4: Full voice assistant pipeline
def example_voice_assistant():
    """Example: Full voice assistant pipeline (STT -> Process -> TTS)."""
    print("\nExample 4: Voice assistant pipeline...")
    
    # Step 1: Transcribe user's speech
    stt = GroqSTT()
    audio_file = "user_question.wav"
    
    if not Path(audio_file).exists():
        print(f"Audio file not found: {audio_file}")
        return
    
    # Transcribe
    user_text = stt.transcribe(audio_file)
    print(f"User said: {user_text}")
    
    # Step 2: Process the text (e.g., send to chatbot)
    # response_text = chatbot.process(user_text)
    response_text = f"Thank you for saying: {user_text}"
    
    # Step 3: Synthesize response
    tts = GroqTTS()
    response_audio = tts.synthesize_to_file(response_text, "response.mp3")
    print(f"Response audio saved to: {response_audio}")


# Example 5: Transcribe from bytes (for streaming/real-time)
def example_transcribe_bytes():
    """Example: Transcribe audio from bytes (useful for streaming)."""
    print("\nExample 5: Transcribing from bytes...")
    
    stt = GroqSTT()
    
    # Read audio file as bytes
    audio_file = "sample_audio.wav"
    if Path(audio_file).exists():
        with open(audio_file, "rb") as f:
            audio_bytes = f.read()
        
        # Transcribe from bytes
        transcript = stt.transcribe_bytes(audio_bytes, filename=audio_file)
        print(f"Transcription: {transcript}")
    else:
        print(f"Audio file not found: {audio_file}")


if __name__ == "__main__":
    # Check for API key
    if not os.getenv("GROQ_API_KEY"):
        print("Warning: GROQ_API_KEY not set in environment")
        print("Set it with: export GROQ_API_KEY='your-api-key'")
        print()
    
    # Run examples
    example_transcribe()
    example_translate()
    example_synthesize()
    example_transcribe_bytes()
    # example_voice_assistant()  # Uncomment if you have test audio files

