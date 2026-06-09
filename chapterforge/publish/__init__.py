"""Publishing built masters to remote destinations.

Primary entry points: PublishService in service.py, Destination/load_destinations/
save_destinations in destinations.py.
"""
from .destinations import Destination, load_destinations, save_destinations
from .service import PublishService, PublishResult

__all__ = [
    "Destination",
    "load_destinations",
    "save_destinations",
    "PublishService",
    "PublishResult",
]
