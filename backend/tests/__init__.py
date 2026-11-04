import os

# Tests never call a live Muse endpoint, even when backend/.env enables it
# (config only fills blank variables from .env). Model tests mock the client.
os.environ["MODEL_ASK_ENABLED"] = "false"
