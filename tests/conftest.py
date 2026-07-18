import os


# Flask app factories created by unit tests must not start process-level daemons.
# Background workers are exercised directly by their dedicated tests.
os.environ.setdefault("VIRALFACTORY_DISABLE_BACKGROUND_WORKERS", "1")
