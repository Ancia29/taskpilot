import os
from dotenv import load_dotenv
load_dotenv()
class Config:
    SECRET_KEY = os.environ["SECRET_KEY"] if os.getenv("SECRET_KEY") else "dev-only-change-me"
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///taskpilot.db")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production"
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
    ALLOWED_EXT = {"pdf", "docx", "txt", "csv", "xlsx", "py", "js", "java", "sql", "md"}
