# UltraCode — AI-assisted coding tool
try:
    from importlib.metadata import version as _pkg_version

    try:
        __version__ = _pkg_version("ultracode")
    except Exception:
        __version__ = _pkg_version("aicode")
except Exception:
    __version__ = "0.1.0"
