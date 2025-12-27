"""
Pytest configuration and fixtures
"""
import pytest
import asyncio
import os
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def client():
    """Create test client"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_db():
    """Create mock database for testing"""
    db = MagicMock()
    
    # Mock collections
    db.student_performance = AsyncMock()
    db.error_logs = AsyncMock()
    db.users = AsyncMock()
    db.user_profiles = AsyncMock()
    db.onboarding_progress = AsyncMock()
    
    # Security monitoring collections
    db.security_events = AsyncMock()
    db.security_alerts = AsyncMock()
    db.compliance_violations = AsyncMock()
    db.data_integrity_checks = AsyncMock()
    
    # Mock common database operations
    db.student_performance.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test_id"))
    db.student_performance.find = AsyncMock()
    db.student_performance.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    
    db.error_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="error_log_id"))
    
    # Mock security collections operations
    db.security_events.insert_one = AsyncMock(return_value=MagicMock(inserted_id="security_event_id"))
    db.security_events.find = AsyncMock()
    db.security_events.aggregate = AsyncMock()
    
    db.security_alerts.insert_one = AsyncMock(return_value=MagicMock(inserted_id="security_alert_id"))
    db.security_alerts.aggregate = AsyncMock()
    
    db.compliance_violations.insert_one = AsyncMock(return_value=MagicMock(inserted_id="compliance_violation_id"))
    db.compliance_violations.count_documents = AsyncMock(return_value=0)
    
    return db


@pytest.fixture(scope="session")
def setup_test_database():
    """Set up test database configuration"""
    # Set test environment variables
    os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
    os.environ["MONGODB_DATABASE"] = "learning_analytics_test"
    os.environ["ENVIRONMENT"] = "test"
    
    # Create a mock database instance
    mock_database = MagicMock()
    
    # Mock collections with proper async methods
    collections = [
        "user_profiles", "student_performance", "learning_gaps", 
        "recommendations", "test_connection", "test_concurrent"
    ]
    
    for collection_name in collections:
        mock_collection = MagicMock()
        
        # Mock async methods
        mock_collection.insert_one = AsyncMock()
        mock_collection.find_one = AsyncMock()
        mock_collection.update_one = AsyncMock()
        mock_collection.delete_one = AsyncMock()
        mock_collection.count_documents = AsyncMock()
        mock_collection.drop = AsyncMock()
        mock_collection.create_indexes = AsyncMock()
        
        # Mock list_indexes
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {"key": {"_id": 1}, "name": "_id_"},
            {"key": {"user_id": 1}, "name": "user_id_1"}
        ])
        mock_collection.list_indexes.return_value = mock_cursor
        
        # Set up collection access
        setattr(mock_database, collection_name, mock_collection)
        mock_database.__getitem__.return_value = mock_collection
    
    # Patch the global database variable and get_database function
    with patch('app.core.database.database', mock_database):
        with patch('app.core.database.get_database', return_value=mock_database):
            yield mock_database