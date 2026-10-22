import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_TTL_HOURS = int(os.getenv("JWT_TTL_HOURS", "12"))
# Если задан — внешние проверки идут по HTTP в сервис моков, иначе вызываются в процессе
MOCKS_URL = os.getenv("MOCKS_URL", "").rstrip("/")
SEED_ON_START = os.getenv("SEED_ON_START", "1") == "1"
