"""adf2fabric - assess and convert Azure Data Factory pipelines for Microsoft Fabric."""

__version__ = "0.1.0"

from .assess import Assessment, assess  # noqa: E402
from .convert import convert_factory, convert_pipeline  # noqa: E402
from .loader import Factory, load_factory  # noqa: E402

__all__ = [
    "Assessment",
    "Factory",
    "assess",
    "convert_factory",
    "convert_pipeline",
    "load_factory",
    "__version__",
]
