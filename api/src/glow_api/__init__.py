from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("glow-api")
except PackageNotFoundError as e:
    raise RuntimeError(
        "Package 'glow-api' is not installed. "
        "Run 'pip install .' from the api/ directory."
    ) from e
