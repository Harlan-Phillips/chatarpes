"""
ChatARPES Configuration

Environment-based config. Copy .env.example to .env and fill in values.
"""

import os

# LLM Configuration
# PLACEHOLDER: Confirm API access with lab lead
# Berkeley Lab may provide AI access - need to confirm if API tokens or chatbot-only
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")  # "anthropic", "local", or "berkeley"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")  # Recommended for v1

# Analysis
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100"))
TEMP_DATA_DIR = os.getenv("TEMP_DATA_DIR", "/tmp/chatarpes")

# Auth
# PLACEHOLDER: Decide auth method with lab lead
AUTH_METHOD = os.getenv("AUTH_METHOD", "none")  # "google_oauth", "passphrase", "calnet", "none"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "berkeley.edu")

# Knowledge Base
MATERIALS_DB_PATH = os.getenv("MATERIALS_DB_PATH", "data/materials/materials_db.json")
RAG_CORPUS_DIR = os.getenv("RAG_CORPUS_DIR", "knowledge/rag_corpus")

# Laser System - 1030nm Carbide (NOT the one in the setup paper)
LASER_WAVELENGTH_NM = 1030
LASER_TYPE = "Carbide"
