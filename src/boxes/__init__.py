"""THE BOXES: an autonomous multimodal research agent for film development.

Agentic Cinema hackathon, Parallel track.
"""

__version__ = "0.0.1"

# ADK discovery expects `root_agent` here. The backend service imports this
# package without google-adk installed, so keep the import optional.
try:
    from .agent import root_agent  # noqa: F401
except ModuleNotFoundError:  # google-adk not installed (e.g. the Cloud Run service)
    root_agent = None  # type: ignore[assignment]
