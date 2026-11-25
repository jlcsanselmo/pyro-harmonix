from dataclasses import dataclass
from enum import Enum


class ObservationState(str, Enum):
    DETECTED = "detected"
    VALID_NO_DETECTION = "valid_no_detection"
    NO_VALID_OBSERVATION = "no_valid_observation"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Observation:
    state: ObservationState
    value: float | None = None

    @classmethod
    def from_detection(cls, count: int, nominally_operating: bool):
        if not nominally_operating:
            return cls(ObservationState.UNAVAILABLE)
        if count:
            return cls(ObservationState.DETECTED, count)
        return cls(ObservationState.UNKNOWN)

    def measured_value(self) -> float | None:
        if self.state is ObservationState.DETECTED:
            return self.value
        if self.state is ObservationState.VALID_NO_DETECTION:
            return 0.0
        return None


def fuse_observations(modis: Observation, viirs: Observation, factor: float) -> float | None:
    """Use available measurements; a valid observed zero needs coverage evidence."""
    reference = modis.measured_value()
    other = viirs.measured_value()
    if other is None:
        return reference
    adjusted = other * factor
    return adjusted if reference is None else (reference + adjusted) / 2
