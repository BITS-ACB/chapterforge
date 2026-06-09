import platform
import subprocess
import shutil
import logging

logger = logging.getLogger(__name__)

class HardwareCapabilities:
    """Probes the system to determine the optimal AI execution provider."""
    
    def __init__(self):
        self.device = "cpu"
        self.compute_type = "int8"
        self.acceleration = "None"
        self._probe()

    def _probe(self):
        # 1. Check for NVIDIA CUDA
        if self._has_cuda():
            self.device = "cuda"
            self.compute_type = "float16" # High performance on GPU
            self.acceleration = "NVIDIA CUDA"
            return

        # 2. Check for Apple Silicon (M-series)
        if platform.system() == "Darwin" and self._is_apple_silicon():
            self.device = "cpu" # faster-whisper uses CPU but optimized for M-series
            self.compute_type = "int8" 
            self.acceleration = "Apple Silicon (CoreML/Metal)"
            return

        # 3. Check for AVX/AVX512 support on CPU
        if self._has_avx():
            self.device = "cpu"
            self.compute_type = "int8"
            self.acceleration = "Modern CPU (AVX/AVX512)"
            return

        # Fallback
        self.device = "cpu"
        self.compute_type = "float32"
        self.acceleration = "Legacy CPU"

    def _has_cuda(self):
        try:
            subprocess.check_output(
                ["nvidia-smi"], stderr=subprocess.STDOUT, timeout=2.0
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError,
                subprocess.TimeoutExpired):
            return False

    def _is_apple_silicon(self):
        # Check machine architecture
        return platform.machine() == "arm64"

    def _has_avx(self):
        # Simplified check for x86_64 systems
        if platform.machine().lower() in ("amd64", "x86_64"):
            return True
        return False

    def get_config(self):
        return {
            "device": self.device,
            "compute_type": self.compute_type,
            "acceleration": self.acceleration
        }
