"""
Configuration settings for the Learning Analytics Platform
"""
from typing import List, Optional
from pydantic import validator
from pydantic_settings import BaseSettings
import secrets


class Settings(BaseSettings):
    """Application settings"""
    
    # API Configuration
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    
    # CORS Configuration
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v):
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    # Database Configuration
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "learning_analytics"
    
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_DB: int = 0
    
    # AWS Configuration
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    
    # AWS Cognito Configuration
    COGNITO_USER_POOL_ID: Optional[str] = None
    COGNITO_CLIENT_ID: Optional[str] = None
    COGNITO_CLIENT_SECRET: Optional[str] = None
    COGNITO_REGION: str = "us-east-1"
    
    # JWT Configuration
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Application Configuration
    PROJECT_NAME: str = "Learning Analytics Platform"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()