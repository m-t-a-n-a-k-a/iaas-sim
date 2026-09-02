from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResourceReference:
    """Reference to an independently addressable top-level resource."""

    resource_type: str
    resource_id: str
