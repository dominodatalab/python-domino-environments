from .utils import parse_version

from domino import __version__

min_version = "1.0.5"
if parse_version(__version__) < parse_version(min_version):
    raise ImportError(f"python-domino>={min_version} is required, {__version__} is installed")

from ._environments import Environment, EnvironmentManager, ImageType, ClusterType, Visibility

__all__ = [
    "Environment",
    "EnvironmentManager",
    "ImageType",
    "ClusterType",
    "Visibility",
]
