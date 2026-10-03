import logging
import shutil
import subprocess
from typing import TypedDict

from anse.infrastructure.fabrication import TelemetryUnavailableError

logger = logging.getLogger(__name__)


class GPUTelemetryData(TypedDict):
    """Real GPU telemetry data from nvidia-smi."""
    gpu_temp_c: float
    gpu_utilization_percent: float
    memory_used_mb: int
    memory_total_mb: int


class GPUTelemetryHook:
    """
    Interfaces with the GPU via nvidia-smi to extract real CUDA telemetry.
    """
    def __init__(self) -> None:
        exe = shutil.which("nvidia-smi")
        if exe is None:
            self.connected = False
            logger.warning("nvidia-smi not found on PATH; GPU telemetry unavailable.")
        else:
            self.connected = True
            logger.info("GPUTelemetryHook initialized with nvidia-smi access.")

    def get_real_telemetry(self) -> GPUTelemetryData:
        """Fetches live GPU temperature, utilization, and memory via nvidia-smi.

        Returns:
            GPUTelemetryData with actual measurements from the GPU.

        Raises:
            TelemetryUnavailableError: If nvidia-smi is not available or fails.
        """
        exe = shutil.which("nvidia-smi")
        if exe is None:
            raise TelemetryUnavailableError(
                "GPU telemetry unavailable: nvidia-smi not found",
                component="gpu_telemetry",
                remedy="Install NVIDIA driver (see card P0-3)"
            )

        try:
            result = subprocess.run(
                [
                    exe,
                    "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits"
                ],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise TelemetryUnavailableError(
                "GPU telemetry unavailable: nvidia-smi timed out",
                component="gpu_telemetry",
                remedy="Check nvidia-smi responsiveness"
            )
        except OSError as exc:
            raise TelemetryUnavailableError(
                f"GPU telemetry unavailable: {exc}",
                component="gpu_telemetry",
                remedy="Install NVIDIA driver (see card P0-3)"
            )

        if result.returncode != 0:
            error_msg = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
            raise TelemetryUnavailableError(
                f"GPU telemetry unavailable: {error_msg}",
                component="gpu_telemetry",
                remedy="Install NVIDIA driver (see card P0-3)"
            )

        if not result.stdout.strip():
            raise TelemetryUnavailableError(
                "GPU telemetry unavailable: no devices returned",
                component="gpu_telemetry",
                remedy="Install NVIDIA driver (see card P0-3)"
            )

        line = next((ln for ln in result.stdout.strip().splitlines() if ln.strip()), "")
        fields = [f.strip() for f in line.split(",")]

        if len(fields) < 4:
            raise TelemetryUnavailableError(
                f"GPU telemetry unavailable: unexpected nvidia-smi output format",
                component="gpu_telemetry",
                remedy="Verify NVIDIA driver installation"
            )

        try:
            temp_c = float(fields[0])
            util_percent = float(fields[1])
            mem_used_mb = int(float(fields[2]))
            mem_total_mb = int(float(fields[3]))
        except ValueError as exc:
            raise TelemetryUnavailableError(
                f"GPU telemetry unavailable: could not parse nvidia-smi output: {exc}",
                component="gpu_telemetry",
                remedy="Verify NVIDIA driver installation"
            )

        return GPUTelemetryData(
            gpu_temp_c=temp_c,
            gpu_utilization_percent=util_percent,
            memory_used_mb=mem_used_mb,
            memory_total_mb=mem_total_mb,
        )
