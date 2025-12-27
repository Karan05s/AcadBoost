# Learning Analytics Platform Backend

AI-driven learning analytics platform for personalized education built with FastAPI, MongoDB, Redis, and AWS services.

## Features

- **Microservices Architecture**: Modular design with separate services for data collection, analytics, and recommendations
- **AI-Powered Gap Analysis**: Machine learning algorithms to identify learning gaps
- **Personalized Recommendations**: Tailored learning paths based on individual performance
- **Real-time Analytics**: Live dashboard updates and progress tracking
- **Secure Authentication**: AWS Cognito integration with JWT tokens
- **Scalable Infrastructure**: Docker containerization and cloud-ready deployment

## Technology Stack

- **Backend**: Python 3.11, FastAPI
- **Database**: MongoDB Atlas
- **Cache**: Redis
- **Authentication**: AWS Cognito
- **ML Platform**: AWS SageMaker
- **Containerization**: Docker, Docker Compose
- **Testing**: Pytest, Hypothesis (Property-based testing)

## Project Structure

```
app/
├── api/v1/           # API endpoints
├── core/             # Core configuration and utilities
├── models/           # Pydantic data models
├── services/         # Business logic services
└── main.py           # FastAPI application entry point

tests/                # Test suite
scripts/              # Database initialization scripts
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- MongoDB (or use Docker)
- Redis (or use Docker)

### Development Setup

1. **Clone and setup environment**:

   ```bash
   git clone <repository-url>
   cd learning-analytics-platform
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Run with Docker Compose** (Recommended):

   ```bash
   docker-compose up -d
   ```

4. **Or run locally**:

   ```bash
   # Start MongoDB and Redis separately
   python run.py
   ```

5. **Access the application**:
   - API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - MongoDB Express (dev): http://localhost:8081

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run property-based tests only
pytest -m property
```

## API Documentation

Once running, visit http://localhost:8000/docs for interactive API documentation.

## Configuration

Key environment variables:

- `MONGODB_URL`: MongoDB connection string
- `REDIS_URL`: Redis connection string
- `COGNITO_USER_POOL_ID`: AWS Cognito User Pool ID
- `COGNITO_CLIENT_ID`: AWS Cognito Client ID
- `AWS_ACCESS_KEY_ID`: AWS Access Key
- `AWS_SECRET_ACCESS_KEY`: AWS Secret Key

See `.env.example` for complete configuration options.

## Development

### Adding New Services

1. Create service in `app/services/`
2. Add API endpoints in `app/api/v1/endpoints/`
3. Include router in `app/api/v1/api.py`
4. Add tests in `tests/`

### Database Migrations

MongoDB schema changes are handled through the application code. Update models in `app/models/` and services will automatically use the new schema.

## Deployment

### Docker Production

```bash
docker build -t learning-analytics-platform .
docker run -p 8000:8000 learning-analytics-platform
```

### AWS Deployment

The application is designed for AWS deployment using:

- ECS for container orchestration
- MongoDB Atlas for database
- ElastiCache for Redis
- Cognito for authentication
- SageMaker for ML models

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

[Add your license here]
