"""FastAPI web service for the MTG Deck Analyzer.

For local development (without Docker) environment variables are loaded from a
``.env`` file if present. Real environment variables always take precedence, so
this is a no-op in Docker/production where the environment is set explicitly.
"""

from dotenv import load_dotenv

load_dotenv()
