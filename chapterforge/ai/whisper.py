import logging
from typing import Callable, List, Dict, Any
from dataclasses import dataclass
from faster_whisper import WhisperModel
from .engine import ASREngine, TranscriptionSegment
from .hardware import HardwareCapabilities

logger = logging.getLogger(__name__)

class WhisperEngine(ASREngine):
    """Handles a magical, hardware-aware transcription process using faster-whisper."""
    
    MODELS = {
        "tiny": "tiny",
        "base": "base",
        "small": "small",
        "medium": "medium",
        "large": "large-v3"
    }

    def __init__(self, model_size: str = "base", progress_callback: Callable[[float], None] = None):
        self.hw = HardwareCapabilities()
        config = self.hw.get_config()
        
        self.device = config["device"]
        self.compute_type = config["compute_type"]
        self.acceleration = config["acceleration"]
        
        # Select the actual model identifier
        model_id = self.MODELS.get(model_size, "base")
        
        logger.info(f"Initializing Whisper Engine: Model={model_id}, Device={self.device}, Compute={self.compute_type} ({self.acceleration})")
        
        try:
            # faster-whisper doesn't have a direct progress callback for downloads, 
            # but we can simulate it or log it. For a truly magical experience,
            # we ensure this is called in a thread.
            self.model = WhisperModel(model_id, device=self.device, compute_type=self.compute_type)
            if progress_callback:
                progress_callback(100.0)
        except Exception as e:
            logger.error(f"Failed to initialize WhisperModel: {e}")
            # Fallback to CPU if CUDA fails
            self.device = "cpu"
            self.compute_type = "int8"
            self.model = WhisperModel(model_id, device="cpu", compute_type="int8")
            if progress_callback:
                progress_callback(100.0)

    def transcribe(self, audio_path: str, progress_callback: Callable[[float], None] = None) -> List[TranscriptionSegment]:
        """Transcribes an audio file into time-stamped segments with optional progress reporting."""
        
        # Determine total duration for progress calculation
        duration = 0.0
        try:
            import mutagen
            audio = mutagen.File(audio_path)
            duration = audio.info.length if audio else 0.0
        except Exception:
            logger.warning(f"Could not determine duration for {audio_path}, progress will be unavailable.")

        segments, info = self.model.transcribe(audio_path, beam_size=5)
        
        logger.info(f"Language detected: {info.language} with probability {info.language_probability:.2f}")
        
        results = []
        for s in segments:
            results.append(TranscriptionSegment(
                start=s.start,
                end=s.end,
                text=s.text.strip(),
                confidence=s.avg_logprob
            ))
            
            if progress_callback and duration > 0:
                percent = (s.end / duration) * 100
                progress_callback(min(percent, 100.0))
                
        return results

    def suggest_chapters(self, segments: List[TranscriptionSegment]) -> List[Dict[str, Any]]:
        """
        Magically suggests chapters based on semantic pauses and text content.
        """
        if not segments:
            return []

        chapters = []
        current_chapter_text = []
        start_time = segments[0].start
        
        # Heuristic for semantic splitting:
        # 1. Gaps > 1.5s often indicate a topic change.
        # 2. Very long segments (> 30s) should be split.
        
        for i in range(len(segments)):
            s = segments[i]
            current_chapter_text.append(s.text)
            
            is_last = (i == len(segments) - 1)
            if not is_last:
                next_s = segments[i+1]
                gap = next_s.start - s.end
                
                # Split if gap is large or if we've reached a reasonable chapter length (e.g. ~2 mins)
                if gap > 1.5 or (s.end - start_time > 120):
                    # Create a chapter
                    title = self._generate_title(current_chapter_text)
                    chapters.append({
                        "title": title,
                        "start": start_time,
                        "end": s.end
                    })
                    # Reset for next chapter
                    start_time = next_s.start
                    current_chapter_text = []
        
        # Handle the final segment
        if current_chapter_text:
            chapters.append({
                "title": self._generate_title(current_chapter_text),
                "start": start_time,
                "end": segments[-1].end
            })
            
        return chapters

    def _generate_title(self, text_list: List[str]) -> str:
        """
        Generates a suggested title from the first few meaningful sentences.
        """
        full_text = " ".join(text_list).strip()
        if not full_text:
            return "Unnamed Chapter"
            
        # Take the first sentence or first 60 characters as a title
        first_sentence = full_text.split(".")[0].split("?")[0].split("!")[0]
        title = first_sentence.strip()
        
        if len(title) > 60:
            title = title[:57] + "..."
            
        return title if title else "Untitled Section"
