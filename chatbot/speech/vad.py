

"""
vad_multi_human.py
------------------
Multi-human Voice Activity Detection using Silero VAD
with speech enhancement, RMS-based loudest speaker detection
for chatbot voice agents.
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
    Voice Activity Detector for multiple humans.
    Features:
    - Silero VAD + energy fallback
    - Speech enhancement
    - Detect multiple speakers, pick loudest/closest human
    """

    def __init__(
        self,
        use_silero_vad: bool = True,
        silero_threshold: float = 0.5,
        energy_threshold: float = 0.03,  # Matches frontend validation (0.05) but slightly lower for backend processing
        min_speech_duration_ms: int = 300,
        min_silence_duration_ms: int = 150,
        enable_speech_enhancement: bool = True,
        noise_reduction_prop_decrease: float = 0.8,
        rms_history_size: int = 20,
        rms_variance_threshold: float = 0.1,  # Lowered to be more reasonable for voice detection
        # Frequency filtering parameters
        enable_frequency_filter: bool = True,
        voice_freq_low: float = 300,   # Lower bound for human voice (Hz)
        voice_freq_high: float = 3400, # Upper bound for human voice (Hz)
    ):
        self.use_silero_vad = use_silero_vad and TORCH_AVAILABLE
        self.silero_threshold = silero_threshold
        self.energy_threshold = energy_threshold  # Now 0.03 for stronger vocals
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.enable_speech_enhancement = enable_speech_enhancement and NOISE_REDUCE_AVAILABLE
        self.noise_reduction_prop_decrease = noise_reduction_prop_decrease

        # Frequency filtering
        self.enable_frequency_filter = enable_frequency_filter and SCIPY_AVAILABLE
        self.voice_freq_low = voice_freq_low
        self.voice_freq_high = voice_freq_high

        self.rms_history_size = rms_history_size
        self.rms_variance_threshold = rms_variance_threshold
        self.rms_history: List[float] = []

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

    # -------------------- Frequency Filtering --------------------
    def filter_voice_frequencies(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Apply bandpass filter to focus on human voice frequencies.
        Human speech typically ranges from 300-3400 Hz.
        """
        if not self.enable_frequency_filter:
            return audio
        
        try:
            # Design bandpass filter for voice frequencies
            # Using Butterworth filter for smooth frequency response
            nyquist = sr / 2.0
            
            # Ensure frequencies are within valid range
            low = max(self.voice_freq_low / nyquist, 0.01)
            high = min(self.voice_freq_high / nyquist, 0.99)
            
            if low >= high:
                logger.warning(f"Invalid frequency range: {self.voice_freq_low}-{self.voice_freq_high} Hz")
                return audio
            
            # 4th order Butterworth bandpass filter
            sos = signal.butter(4, [low, high], btype='band', fs=sr, output='sos')
            filtered_audio = signal.sosfilt(sos, audio)
            
            return filtered_audio
        except Exception as e:
            logger.warning(f"Frequency filtering failed: {e}")
            return audio

    # -------------------- Speech Enhancement --------------------
    def enhance(self, audio: np.ndarray, sr: int) -> np.ndarray:
        if not self.enable_speech_enhancement:
            # Still apply frequency filter even if enhancement is disabled
            if self.enable_frequency_filter:
                return self.filter_voice_frequencies(audio, sr)
            return audio
        
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 0.01:  # skip near silence
            return audio
        
        try:
            # First apply frequency filtering to focus on voice
            if self.enable_frequency_filter:
                audio = self.filter_voice_frequencies(audio, sr)
            
            enhanced = nr.reduce_noise(
                y=audio,
                sr=sr,
                stationary=True,
                prop_decrease=self.noise_reduction_prop_decrease,
            )
            
            if SCIPY_AVAILABLE:
                # High-pass filter at 80 Hz (keep existing)
                sos = signal.butter(4, 80, "hp", fs=sr, output="sos")
                enhanced = signal.sosfilt(sos, enhanced)
            
            return enhanced
        except Exception as e:
            logger.warning(f"Speech enhancement failed: {e}")
            return audio

    # -------------------- Detect Voice --------------------
    def detect_voice(
        self, audio: np.ndarray, sample_rate: int = 16000, enhance: bool = True
    ) -> Tuple[bool, float, bool]:
        """
        Detect voice and identify primary speaker.
        Returns:
            has_voice (bool): True if any voice detected
            confidence (float): Confidence of voice detection
            primary_speaker (bool): True if RMS variance indicates closest/loudest human
        """
        if len(audio) == 0:
            return False, 0.0, False

        # Normalize
        if audio.dtype.kind == "i":
            audio = audio.astype(np.float32) / np.iinfo(audio.dtype).max
        else:
            audio = audio.astype(np.float32)

        # Check RMS BEFORE filtering (frequency filter can reduce RMS significantly)
        # This matches frontend validation which checks RMS on raw audio
        rms_before_filter = np.sqrt(np.mean(audio ** 2))
        
        # Quick energy gate - check RMS before filtering to match frontend behavior
        # Frontend validates with RMS >= 0.05, so backend should accept similar values
        if rms_before_filter < self.energy_threshold:
            logger.warning(f"VAD rejected - RMS before filter {rms_before_filter:.4f} < threshold {self.energy_threshold:.4f}")
            return False, 0.0, False
        
        # Apply frequency filtering AFTER initial RMS check
        if self.enable_frequency_filter:
            audio = self.filter_voice_frequencies(audio, sample_rate)

        # Calculate RMS after filtering for reference
        rms_after_filter = np.sqrt(np.mean(audio ** 2))
        logger.info(f"VAD RMS - Before filter: {rms_before_filter:.4f}, After filter: {rms_after_filter:.4f}, Threshold: {self.energy_threshold:.4f}")

        if enhance:
            audio = self.enhance(audio, sample_rate)

        if self.use_silero_vad:
            try:
                has_voice, confidence = self._detect_silero(audio, sample_rate)
            except Exception as e:
                logger.warning(f"Silero failed, fallback to energy: {e}")
                # Use rms_before_filter for energy fallback since filtered audio has lower RMS
                # We already passed the RMS check, so trust that there's voice
                has_voice, confidence = self._detect_energy(audio, rms_before_filter=rms_before_filter)
        else:
            has_voice, confidence = self._detect_energy(audio, rms_before_filter=rms_before_filter)

        # -------------------- Track RMS for closest speaker --------------------
        # Use RMS before filter for tracking (matches frontend behavior)
        self.rms_history.append(rms_before_filter)
        if len(self.rms_history) > self.rms_history_size:
            self.rms_history.pop(0)

        rms_variance = max(self.rms_history) - min(self.rms_history)
        primary_speaker = rms_variance > self.rms_variance_threshold

        return has_voice, confidence, primary_speaker

    # -------------------- Silero Detection --------------------
    def _detect_silero(self, audio: np.ndarray, sr: int) -> Tuple[bool, float]:
        if sr != 16000:
            if not SCIPY_AVAILABLE:
                return self._detect_energy(audio)
            audio = signal.resample(audio, int(len(audio) * 16000 / sr))
            sr = 16000

        # Ensure audio is float32 (Silero expects Float, not Double)
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        
        tensor = torch.from_numpy(audio).to(self.device)
        # Ensure tensor is float32
        if tensor.dtype != torch.float32:
            tensor = tensor.float()
        
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

    # -------------------- Energy Fallback --------------------
    def _detect_energy(self, audio: np.ndarray, rms_before_filter: float = None) -> Tuple[bool, float]:
        """
        Energy-based voice detection fallback.
        If rms_before_filter is provided, use it for threshold check (since filtered audio has lower RMS).
        """
        rms = np.sqrt(np.mean(audio ** 2))
        
        # If we have rms_before_filter, use it for threshold check (filtered audio has lower RMS)
        # We already passed the initial RMS check, so trust that there's voice
        if rms_before_filter is not None:
            has_voice = rms_before_filter > self.energy_threshold
            # Use rms_before_filter for confidence calculation (more accurate)
            confidence = min(rms_before_filter / self.energy_threshold, 1.0) if has_voice else 0.0
            logger.info(f"Energy VAD - Using pre-filter RMS: {rms_before_filter:.4f} (filtered RMS: {rms:.4f}), Threshold: {self.energy_threshold:.4f}, Has voice: {has_voice}, Confidence: {confidence:.2f}")
        else:
            # Fallback to using filtered audio RMS (for backward compatibility)
            has_voice = rms > self.energy_threshold
            confidence = min(rms / self.energy_threshold, 1.0) if has_voice else 0.0
            logger.info(f"Energy VAD - Using filtered RMS: {rms:.4f}, Threshold: {self.energy_threshold:.4f}, Has voice: {has_voice}, Confidence: {confidence:.2f}")
        
        return has_voice, confidence

    # -------------------- Post-STT text filtering --------------------
    def is_valid_transcript(self, text: str) -> bool:
        if not text or len(text.strip()) < 2:
            return False
        fillers = {"uh", "um", "ah", "er", "hmm", "mmm"}
        return text.lower().strip() not in fillers


# -------------------- Example Usage --------------------
if __name__ == "__main__":
    import soundfile as sf

    vad = VoiceActivityDetector()
    audio, sr = sf.read("sample_audio.wav")
    has_voice, confidence, primary_speaker = vad.detect_voice(audio, sr)
    print(f"Voice: {has_voice}, confidence: {confidence:.2f}, primary speaker: {primary_speaker}")
