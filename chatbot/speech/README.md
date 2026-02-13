# Speech Processing Module

This module provides Speech-to-Text (STT) and Text-to-Speech (TTS) functionality using Groq API.

## Components

### 1. STT (Speech-to-Text) - `stt.py`

Converts audio files to text using Groq's Whisper models.

**Supported Models:**
- `whisper-large-v3-turbo` (default) - Fast, multilingual transcription
- `whisper-large-v3` - High accuracy, multilingual transcription

**Features:**
- Transcribe audio files to text
- Translate audio files to English
- Support for multiple audio formats (mp3, mp4, mpeg, mpga, m4a, wav, webm)
- Transcribe from bytes (useful for streaming)

**Example:**
```python
from chatbot.speech import GroqSTT

# Initialize STT client
stt = GroqSTT(model="whisper-large-v3-turbo")

# Transcribe audio file
transcript = stt.transcribe("audio.wav", language="en")
print(transcript)

# Translate to English
translation = stt.translate("spanish_audio.wav")
print(translation)
```

### 2. TTS (Text-to-Speech) - `tts.py`

Converts text to audio using Groq's speech synthesis models.

**Supported Models:**
- `canopylabs/orpheus-v1-english` (user-specified) - Expressive TTS with vocal direction controls
- `playai-tts` (Groq SDK default) - Standard TTS
- `playai-tts-arabic` - Arabic TTS

**Supported Voices:**
- `alloy` (default)
- `echo`
- `fable`
- `onyx`
- `nova`
- `shimmer`

**Supported Formats:**
- `mp3` (default)
- `flac`
- `wav`
- `ogg`
- `mulaw`

**Example:**
```python
from chatbot.speech import GroqTTS

# Initialize TTS client
tts = GroqTTS(
    model="canopylabs/orpheus-v1-english",
    voice="alloy",
    speed=1.0
)

# Synthesize text to speech
audio_data = tts.synthesize("Hello, world!", output_file="output.mp3")

# Or save directly to file
tts.synthesize_to_file("Hello, world!", "output.mp3")
```

### 3. VAD (Voice Activity Detection) - `vad.py`

Detects voice activity in audio streams using Silero VAD.

**Example:**
```python
from chatbot.speech import VoiceActivityDetector
import soundfile as sf

vad = VoiceActivityDetector()
audio, sr = sf.read("audio.wav")
has_voice, confidence = vad.detect_voice(audio, sr)
print(f"Voice detected: {has_voice}, confidence: {confidence}")
```

## Setup

1. **Install dependencies:**
```bash
pip install groq
```

2. **Set API key:**
```bash
export GROQ_API_KEY="your-api-key-here"
```

Or in Python:
```python
import os
os.environ["GROQ_API_KEY"] = "your-api-key-here"
```

## API Endpoints

### STT Endpoints
- **Transcriptions:** `https://api.groq.com/openai/v1/audio/transcriptions`
- **Translations:** `https://api.groq.com/openai/v1/audio/translations`

### TTS Endpoint
- **Speech:** `https://api.groq.com/openai/v1/audio/speech`

## Usage Examples

### Full Voice Assistant Pipeline

```python
from chatbot.speech import GroqSTT, GroqTTS

# 1. Transcribe user's speech
stt = GroqSTT()
user_text = stt.transcribe("user_audio.wav")

# 2. Process with chatbot (your existing chatbot logic)
response_text = chatbot.process(user_text)

# 3. Synthesize response
tts = GroqTTS()
tts.synthesize_to_file(response_text, "response.mp3")
```

### Streaming Audio Transcription

```python
from chatbot.speech import GroqSTT

stt = GroqSTT()

# Read audio as bytes
with open("audio.wav", "rb") as f:
    audio_bytes = f.read()

# Transcribe from bytes
transcript = stt.transcribe_bytes(audio_bytes, filename="audio.wav")
```

### Custom TTS Settings

```python
from chatbot.speech import GroqTTS

tts = GroqTTS(
    model="canopylabs/orpheus-v1-english",
    voice="nova",  # Different voice
    speed=1.2,     # Faster speech
)

audio = tts.synthesize(
    "Hello, this is a test.",
    output_file="output.wav",
    response_format="wav"  # WAV format instead of MP3
)
```

## Error Handling

Both STT and TTS classes will raise exceptions if:
- API key is not set
- Audio file is not found
- Invalid model/voice/format is specified
- API request fails

Always wrap calls in try-except blocks:

```python
try:
    stt = GroqSTT()
    transcript = stt.transcribe("audio.wav")
except ValueError as e:
    print(f"Configuration error: {e}")
except FileNotFoundError as e:
    print(f"File not found: {e}")
except Exception as e:
    print(f"API error: {e}")
```

## Integration with Chatbot

To integrate with your existing chatbot:

1. **Add STT endpoint to FastAPI:**
```python
from chatbot.speech import GroqSTT
from fastapi import UploadFile

@app.post("/api/audio/transcribe")
async def transcribe_audio(file: UploadFile):
    stt = GroqSTT()
    # Save uploaded file temporarily
    # Then transcribe
    transcript = stt.transcribe(temp_file_path)
    return {"transcript": transcript}
```

2. **Add TTS endpoint to FastAPI:**
```python
from chatbot.speech import GroqTTS
from fastapi.responses import StreamingResponse

@app.post("/api/audio/synthesize")
async def synthesize_speech(text: str):
    tts = GroqTTS()
    audio_data = tts.synthesize(text)
    return StreamingResponse(
        io.BytesIO(audio_data),
        media_type="audio/mp3"
    )
```

## Notes

- **Model Compatibility:** The Groq SDK may show different model names than the API documentation. The code supports both naming conventions.
- **Rate Limits:** Be aware of Groq API rate limits. Handle rate limit errors gracefully.
- **File Formats:** Supported audio formats may vary. Check Groq API documentation for the latest supported formats.
- **Language Support:** STT supports multilingual transcription. Specify the `language` parameter for better accuracy.

## See Also

- [Groq API Documentation](https://console.groq.com/docs)
- [Example Usage](example_usage.py)



