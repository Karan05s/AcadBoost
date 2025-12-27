"""
MongoDB database connection and configuration
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, DESCENDING
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Global database client and database instances
client: AsyncIOMotorClient = None
database: AsyncIOMotorDatabase = None


async def init_database():
    """Initialize MongoDB connection and create indexes"""
    global client, database
    
    try:
        # Create MongoDB client
        client = AsyncIOMotorClient(settings.MONGODB_URL)
        database = client[settings.MONGODB_DATABASE]
        
        # Test connection
        await client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
        
        # Create indexes for optimal performance
        await create_indexes()
        
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


async def create_indexes():
    """Create database indexes for optimal query performance"""
    
    # User profiles indexes
    user_indexes = [
        IndexModel([("user_id", ASCENDING)], unique=True),
        IndexModel([("email", ASCENDING)], unique=True),
        IndexModel([("username", ASCENDING)], unique=True),
        IndexModel([("role", ASCENDING)]),
        IndexModel([("institution", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)])
    ]
    await database.user_profiles.create_indexes(user_indexes)
    
    # Student performance indexes
    performance_indexes = [
        IndexModel([("student_id", ASCENDING), ("timestamp", DESCENDING)]),
        IndexModel([("course_id", ASCENDING), ("assignment_id", ASCENDING)]),
        IndexModel([("submission_type", ASCENDING)]),
        IndexModel([("timestamp", DESCENDING)]),
        IndexModel([("student_id", ASCENDING), ("course_id", ASCENDING)])
    ]
    await database.student_performance.create_indexes(performance_indexes)
    
    # Learning gaps indexes
    gap_indexes = [
        IndexModel([("student_id", ASCENDING), ("concept_id", ASCENDING)]),
        IndexModel([("student_id", ASCENDING), ("gap_severity", DESCENDING)]),
        IndexModel([("last_updated", DESCENDING)]),
        IndexModel([("concept_id", ASCENDING)])
    ]
    await database.learning_gaps.create_indexes(gap_indexes)
    
    # Recommendations indexes
    recommendation_indexes = [
        IndexModel([("student_id", ASCENDING), ("priority_score", DESCENDING)]),
        IndexModel([("gap_id", ASCENDING)]),
        IndexModel([("generated_at", DESCENDING)]),
        IndexModel([("completed", ASCENDING)])
    ]
    await database.recommendations.create_indexes(recommendation_indexes)
    
    logger.info("Database indexes created successfully")


async def get_database() -> AsyncIOMotorDatabase:
    """Get database instance"""
    return database


async def close_database():
    """Close database connection"""
    global client
    if client:
        client.close()
        logger.info("MongoDB connection closed")