"""
vad_component.py
-----------------
Voice Activity Detection component using Silero VAD with optional
speech enhancement and safe fallbacks for CPU/GPU production voice assistants.
"""

from typing import Tuple, List
import numpy as np
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Optional dependencies
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("torch not available. Install with: pip install torch")

try:
    import noisereduce as nr
    NOISE_REDUCE_AVAILABLE = True
except ImportError:
    NOISE_REDUCE_AVAILABLE = False
    logger.warning("noisereduce not available. Install with: pip install noisereduce")

try:
    from scipy import signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("scipy not available")


class VoiceActivityDetector:
    """
    Production-grade Voice Activity Detector component.
    Works with streaming audio and WebSocket-based voice assistants.
    Supports:
    - Silero VAD (GPU/CPU)
    - Energy-based fallback
    - Optional speech enhancement
    """

    def __init__(
        self,
        use_silero_vad: bool = True,
        silero_threshold: float = 0.5,
        energy_threshold: float = 0.015,
        min_speech_duration_ms: int = 300,
        min_silence_duration_ms: int = 150,
        enable_speech_enhancement: bool = True,
        noise_reduction_prop_decrease: float = 0.8,
    ):
        self.use_silero_vad = use_silero_vad and TORCH_AVAILABLE
        self.silero_threshold = silero_threshold
        self.energy_threshold = energy_threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.enable_speech_enhancement = enable_speech_enhancement and NOISE_REDUCE_AVAILABLE
        self.noise_reduction_prop_decrease = noise_reduction_prop_decrease

        self.device = None
        self.model = None
        self.get_speech_timestamps = None

        if self.use_silero_vad:
            self._load_silero()

    # -------------------- Model Loading --------------------
    def _load_silero(self):
        logger.info("Loading Silero VAD model...")
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
            verbose=False,
        )
        (get_speech_timestamps, _, _, _, _) = utils

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = model.to(self.device).eval()
        self.get_speech_timestamps = get_speech_timestamps
        logger.info(f"Silero VAD loaded on {self.device}")

    # -------------------- Speech Enhancement --------------------
    def enhance(self, audio: np.ndarray, sr: int) -> np.ndarray:
        if not self.enable_speech_enhancement:
            return audio

        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 0.01:  # skip near silence
            return audio

        try:
            enhanced = nr.reduce_noise(
                y=audio,
                sr=sr,
                stationary=True,
                prop_decrease=self.noise_reduction_prop_decrease,
            )

            if SCIPY_AVAILABLE:
                # High-pass filter at 80 Hz
                sos = signal.butter(4, 80, "hp", fs=sr, output="sos")
                enhanced = signal.sosfilt(sos, enhanced)

            return enhanced
        except Exception as e:
            logger.warning(f"Speech enhancement failed: {e}")
            return audio

    # -------------------- Public API --------------------
    def detect_voice(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        enhance: bool = True,
    ) -> Tuple[bool, float]:
        """
        Detects if audio contains voice.

        Returns:
            has_voice (bool): True if voice detected
            confidence (float): Confidence level (0.0-1.0)
        """

        if len(audio) == 0:
            return False, 0.0

        # Normalize to float32 [-1, 1]
        if audio.dtype.kind == "i":
            audio = audio.astype(np.float32) / np.iinfo(audio.dtype).max
        else:
            audio = audio.astype(np.float32)

        # Fast energy-based gate
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < self.energy_threshold:
            return False, 0.0

        if enhance:
            audio = self.enhance(audio, sample_rate)

        if self.use_silero_vad:
            try:
                return self._detect_silero(audio, sample_rate)
            except Exception as e:
                logger.warning(f"Silero failed, falling back to energy VAD: {e}")

        return self._detect_energy(audio)

    # -------------------- Silero Detection --------------------
    def _detect_silero(self, audio: np.ndarray, sr: int) -> Tuple[bool, float]:
        if sr != 16000:
            if not SCIPY_AVAILABLE:
                return self._detect_energy(audio)
            audio = signal.resample(audio, int(len(audio) * 16000 / sr))
            # sr is now effectively 16000 after resampling

        tensor = torch.from_numpy(audio).to(self.device)
        timestamps = self.get_speech_timestamps(
            tensor,
            self.model,
            threshold=self.silero_threshold,
            min_speech_duration_ms=self.min_speech_duration_ms,
            min_silence_duration_ms=self.min_silence_duration_ms,
            return_seconds=False,
        )

        has_voice = len(timestamps) > 0
        confidence = min(len(timestamps) / 3.0, 1.0)
        return has_voice, confidence

    # -------------------- Energy-based fallback --------------------
    def _detect_energy(self, audio: np.ndarray) -> Tuple[bool, float]:
        rms = np.sqrt(np.mean(audio ** 2))
        has_voice = rms > self.energy_threshold
        confidence = min(rms / self.energy_threshold, 1.0) if has_voice else 0.0
        return has_voice, confidence

    # -------------------- Post-STT text filtering --------------------
    def is_valid_transcript(self, text: str) -> bool:
        if not text or len(text.strip()) < 2:
            return False

        text = text.lower().strip()
        fillers = {"uh", "um", "ah", "er", "hmm", "mmm"}
        if text in fillers:
            return False

        return True


# -------------------- Example Usage --------------------
if __name__ == "__main__":
    import soundfile as sf

    vad = VoiceActivityDetector()
    audio, sr = sf.read("sample_audio.wav")
    has_voice, confidence = vad.detect_voice(audio, sr)
    print(f"Voice detected: {has_voice}, confidence: {confidence}")
