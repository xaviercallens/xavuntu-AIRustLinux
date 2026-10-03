"""Exceptions raised when components report fabricated or unverified results."""


class FabricatedResultError(RuntimeError):
    """Base exception for results that were fabricated or reported without verification.

    This exception is raised when a component reports success but has not actually
    performed the required work. It stores diagnostic information about which
    component failed and what the caller should do instead.
    """

    def __init__(self, message: str, *, component: str, remedy: str) -> None:
        """Initialize the fabricated result exception.

        Args:
            message: Description of the fabricated result.
            component: Name of the component that fabricated the result.
            remedy: Instructions for what the caller should do instead.
        """
        super().__init__(message)
        self.component = component
        self.remedy = remedy

    def __str__(self) -> str:
        """Return a formatted string representation including component and remedy."""
        base_msg = super().__str__()
        return f"{base_msg} [component={self.component}; remedy: {self.remedy}]"


class TelemetryUnavailableError(FabricatedResultError):
    """Raised when telemetry or metrics were reported but not actually collected.

    This occurs when a component claims to have gathered telemetry (e.g., performance
    metrics, resource usage) but the data was fabricated or unavailable.
    """

    pass


class SimulationRefusedError(FabricatedResultError):
    """Raised when a simulation was reported as complete but was not actually run.

    This occurs when a component claims to have executed a simulation but skipped it,
    cached an old result, or refused to run it without documenting the refusal.
    """

    pass


class UnverifiedDataError(FabricatedResultError):
    """Raised when data was returned without verification or validation.

    This occurs when a component returns data it has not actually validated, checked,
    or confirmed to be correct.
    """

    pass
