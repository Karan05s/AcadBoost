"""
Property-based tests for data privacy and FERPA compliance
**Feature: learning-analytics-platform, Property 17: Complete data retrieval**
**Validates: Requirements 4.3**
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings, HealthCheck
from hypothesis.strategies import composite
from unittest.mock import AsyncMock, MagicMock
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.data_privacy_service import DataPrivacyService


@composite
def user_data_strategy(draw):
    """Generate realistic user data for testing"""
    user_id = draw(st.text(min_size=8, max_size=32, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    
    # Generate profile data
    profile = {
        "user_id": user_id,
        "email": draw(st.emails()),
        "username": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))),
        "first_name": draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll')))),
        "last_name": draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll')))),
        "role": draw(st.sampled_from(["student", "instructor", "admin"])),
        "created_at": draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime.now())),
        "profile_completed": draw(st.booleans()),
        "learning_preferences": {
            "learning_style": draw(st.sampled_from(["visual", "auditory", "kinesthetic", "mixed"])),
            "study_time_preference": draw(st.sampled_from(["morning", "afternoon", "evening", "flexible"])),
            "difficulty_preference": draw(st.sampled_from(["gradual", "challenging", "adaptive"]))
        }
    }
    
    # Generate performance data
    performance_records = []
    num_records = draw(st.integers(min_value=0, max_value=10))
    for _ in range(num_records):
        performance_records.append({
            "student_id": user_id,
            "submission_type": draw(st.sampled_from(["quiz", "code"])),
            "course_id": draw(st.text(min_size=5, max_size=20)),
            "assignment_id": draw(st.text(min_size=5, max_size=20)),
            "timestamp": draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime.now())),
            "score": draw(st.floats(min_value=0.0, max_value=100.0)),
            "max_score": draw(st.floats(min_value=50.0, max_value=100.0))
        })
    
    # Generate learning gaps
    gap_records = []
    num_gaps = draw(st.integers(min_value=0, max_value=5))
    for _ in range(num_gaps):
        gap_records.append({
            "student_id": user_id,
            "concept_id": draw(st.text(min_size=5, max_size=20)),
            "gap_severity": draw(st.floats(min_value=0.0, max_value=1.0)),
            "confidence_score": draw(st.floats(min_value=0.0, max_value=1.0)),
            "identified_at": draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime.now()))
        })
    
    # Generate recommendations
    recommendation_records = []
    num_recommendations = draw(st.integers(min_value=0, max_value=8))
    for _ in range(num_recommendations):
        recommendation_records.append({
            "student_id": user_id,
            "resource_type": draw(st.sampled_from(["video", "article", "exercise", "practice"])),
            "resource_url": draw(st.text(min_size=10, max_size=100)),
            "title": draw(st.text(min_size=5, max_size=100)),
            "generated_at": draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime.now())),
            "completed": draw(st.booleans())
        })
    
    return {
        "user_id": user_id,
        "profile": profile,
        "performance_data": performance_records,
        "learning_gaps": gap_records,
        "recommendations": recommendation_records
    }


@pytest.fixture
def mock_db():
    """Create a mock database for testing"""
    db = MagicMock(spec=AsyncIOMotorDatabase)
    
    # Mock collections
    db.user_profiles = AsyncMock()
    db.student_performance = AsyncMock()
    db.learning_gaps = AsyncMock()
    db.recommendations = AsyncMock()
    db.user_onboarding = AsyncMock()
    db.user_assessments = AsyncMock()
    db.course_enrollments = AsyncMock()
    db.lti_contexts = AsyncMock()
    db.lti_sessions = AsyncMock()
    db.audit_trail = AsyncMock()
    db.data_requests = AsyncMock()
    
    return db


@pytest.fixture
def data_privacy_service(mock_db):
    """Create a data privacy service instance for testing"""
    return DataPrivacyService(mock_db)


@pytest.mark.asyncio
@given(user_data=user_data_strategy())
@settings(max_examples=50, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
async def test_complete_data_retrieval_property(user_data):
    """
    Property 17: Complete data retrieval
    **Feature: learning-analytics-platform, Property 17: Complete data retrieval**
    **Validates: Requirements 4.3**
    
    For any student data access request, the system should return all stored information 
    associated with that student
    """
    
    # Create mock database inside the test
    mock_db = MagicMock(spec=AsyncIOMotorDatabase)
    
    # Mock collections
    mock_db.user_profiles = MagicMock()
    mock_db.student_performance = MagicMock()
    mock_db.learning_gaps = MagicMock()
    mock_db.recommendations = MagicMock()
    mock_db.user_onboarding = MagicMock()
    mock_db.user_assessments = MagicMock()
    mock_db.course_enrollments = MagicMock()
    mock_db.lti_contexts = MagicMock()
    mock_db.lti_sessions = MagicMock()
    mock_db.audit_trail = MagicMock()
    mock_db.data_requests = MagicMock()
    
    # Create service
    data_privacy_service = DataPrivacyService(mock_db)
    
    user_id = user_data["user_id"]
    
    # Mock database responses with the generated test data
    mock_db.user_profiles.find_one = AsyncMock(return_value=user_data["profile"])
    
    # Mock cursors for collections that return lists
    def create_mock_cursor(data_list):
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=data_list)
        return cursor
    
    mock_db.student_performance.find.return_value = create_mock_cursor(user_data["performance_data"])
    mock_db.learning_gaps.find.return_value = create_mock_cursor(user_data["learning_gaps"])
    mock_db.recommendations.find.return_value = create_mock_cursor(user_data["recommendations"])
    mock_db.user_assessments.find.return_value = create_mock_cursor([])
    mock_db.course_enrollments.find.return_value = create_mock_cursor([])
    mock_db.lti_contexts.find.return_value = create_mock_cursor([])
    
    # Mock onboarding data
    mock_db.user_onboarding.find_one = AsyncMock(return_value=None)
    
    # Mock audit trail
    mock_db.audit_trail.find.return_value = create_mock_cursor([])
    
    # Mock audit collection for creating audit entries
    data_privacy_service.audit_collection = MagicMock()
    data_privacy_service.audit_collection.insert_one = AsyncMock()
    
    # Mock audit collection find method to return a cursor that supports chaining
    def create_audit_cursor():
        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)  # Return self for chaining
        cursor.to_list = AsyncMock(return_value=[])
        return cursor
    
    data_privacy_service.audit_collection.find = MagicMock(return_value=create_audit_cursor())
    
    # Retrieve complete user data
    complete_data = await data_privacy_service.get_complete_user_data(
        user_id=user_id,
        requesting_user_id=user_id,
        ip_address="192.168.1.100",
        user_agent="test-agent"
    )
    
    # Property: All stored data should be included in the export
    
    # 1. Export metadata should be present and correct
    assert "export_metadata" in complete_data
    assert complete_data["export_metadata"]["user_id"] == user_id
    assert complete_data["export_metadata"]["export_type"] == "complete_user_data"
    assert complete_data["export_metadata"]["ferpa_compliance"] is True
    
    # 2. Profile data should be included if it exists
    if user_data["profile"]:
        assert complete_data["profile"] == user_data["profile"]
        # Verify no internal MongoDB fields are exposed
        assert "_id" not in complete_data["profile"]
    
    # 3. All performance data should be included
    assert "performance_data" in complete_data
    assert len(complete_data["performance_data"]) == len(user_data["performance_data"])
    for i, record in enumerate(complete_data["performance_data"]):
        assert record["student_id"] == user_id
        assert "_id" not in record  # MongoDB internal field should be removed
    
    # 4. All learning gaps should be included
    assert "learning_gaps" in complete_data
    assert len(complete_data["learning_gaps"]) == len(user_data["learning_gaps"])
    for record in complete_data["learning_gaps"]:
        assert record["student_id"] == user_id
        assert "_id" not in record
    
    # 5. All recommendations should be included
    assert "recommendations" in complete_data
    assert len(complete_data["recommendations"]) == len(user_data["recommendations"])
    for record in complete_data["recommendations"]:
        assert record["student_id"] == user_id
        assert "_id" not in record
    
    # 6. All expected data categories should be present
    expected_categories = [
        "export_metadata", "profile", "performance_data", "learning_gaps", 
        "recommendations", "onboarding_data", "assessments", "course_enrollments",
        "lti_contexts", "audit_trail"
    ]
    
    for category in expected_categories:
        assert category in complete_data, f"Missing data category: {category}"
    
    # 7. Audit trail should be created for the data access
    data_privacy_service.audit_collection.insert_one.assert_called_once()
    audit_call = data_privacy_service.audit_collection.insert_one.call_args[0][0]
    assert audit_call["user_id"] == user_id
    assert audit_call["action"] == "export"
    assert audit_call["resource_type"] == "complete_profile"
    
    # 8. Data integrity - no sensitive internal fields should be exposed
    def check_no_internal_fields(data_structure, path=""):
        if isinstance(data_structure, dict):
            assert "_id" not in data_structure, f"Internal _id field found at {path}"
            for key, value in data_structure.items():
                check_no_internal_fields(value, f"{path}.{key}")
        elif isinstance(data_structure, list):
            for i, item in enumerate(data_structure):
                check_no_internal_fields(item, f"{path}[{i}]")
    
    check_no_internal_fields(complete_data)
    
    # 9. FERPA compliance indicators should be present
    assert complete_data["export_metadata"]["ferpa_compliance"] is True
    assert "export_date" in complete_data["export_metadata"]


@pytest.mark.asyncio
@given(user_id=st.text(min_size=8, max_size=32, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
@settings(max_examples=30, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
async def test_data_retrieval_with_no_data_property(user_id):
    """
    Property: Data retrieval should work correctly even when user has no data
    **Feature: learning-analytics-platform, Property 17: Complete data retrieval**
    **Validates: Requirements 4.3**
    """
    
    # Create mock database inside the test
    mock_db = MagicMock(spec=AsyncIOMotorDatabase)
    
    # Mock collections
    mock_db.user_profiles = MagicMock()
    mock_db.student_performance = MagicMock()
    mock_db.learning_gaps = MagicMock()
    mock_db.recommendations = MagicMock()
    mock_db.user_onboarding = MagicMock()
    mock_db.user_assessments = MagicMock()
    mock_db.course_enrollments = MagicMock()
    mock_db.lti_contexts = MagicMock()
    mock_db.lti_sessions = MagicMock()
    mock_db.audit_trail = MagicMock()
    mock_db.data_requests = MagicMock()
    
    # Create service
    data_privacy_service = DataPrivacyService(mock_db)
    
    # Mock database responses with no data
    mock_db.user_profiles.find_one = AsyncMock(return_value=None)
    
    def create_empty_cursor():
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=[])
        return cursor
    
    mock_db.student_performance.find.return_value = create_empty_cursor()
    mock_db.learning_gaps.find.return_value = create_empty_cursor()
    mock_db.recommendations.find.return_value = create_empty_cursor()
    mock_db.user_onboarding.find_one = AsyncMock(return_value=None)
    mock_db.user_assessments.find.return_value = create_empty_cursor()
    mock_db.course_enrollments.find.return_value = create_empty_cursor()
    mock_db.lti_contexts.find.return_value = create_empty_cursor()
    mock_db.audit_trail.find.return_value = create_empty_cursor()
    
    # Mock audit collection
    data_privacy_service.audit_collection = MagicMock()
    data_privacy_service.audit_collection.insert_one = AsyncMock()
    
    # Mock audit collection find method to return a cursor that supports chaining
    def create_audit_cursor():
        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)  # Return self for chaining
        cursor.to_list = AsyncMock(return_value=[])
        return cursor
    
    data_privacy_service.audit_collection.find = MagicMock(return_value=create_audit_cursor())
    
    # Retrieve complete user data
    complete_data = await data_privacy_service.get_complete_user_data(
        user_id=user_id,
        requesting_user_id=user_id,
        ip_address="192.168.1.100",
        user_agent="test-agent"
    )
    
    # Property: Even with no data, the export should be complete and well-formed
    
    # 1. Export metadata should still be present
    assert "export_metadata" in complete_data
    assert complete_data["export_metadata"]["user_id"] == user_id
    assert complete_data["export_metadata"]["ferpa_compliance"] is True
    
    # 2. All data categories should be present but empty
    assert complete_data["profile"] is None
    assert complete_data["performance_data"] == []
    assert complete_data["learning_gaps"] == []
    assert complete_data["recommendations"] == []
    assert complete_data["onboarding_data"] is None
    assert complete_data["assessments"] == []
    assert complete_data["course_enrollments"] == []
    assert complete_data["lti_contexts"] == []
    assert complete_data["audit_trail"] == []
    
    # 3. Audit trail should still be created
    data_privacy_service.audit_collection.insert_one.assert_called_once()


@pytest.mark.asyncio
@given(
    user_id=st.text(min_size=8, max_size=32, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
    requesting_user_id=st.text(min_size=8, max_size=32, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
    ip_address=st.ip_addresses(v=4).map(str)
)
@settings(max_examples=20, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
async def test_data_retrieval_audit_trail_property(user_id, requesting_user_id, ip_address):
    """
    Property: Data retrieval should always create proper audit trail entries
    **Feature: learning-analytics-platform, Property 17: Complete data retrieval**
    **Validates: Requirements 4.3**
    """
    
    # Create mock database inside the test
    mock_db = MagicMock(spec=AsyncIOMotorDatabase)
    
    # Mock collections
    mock_db.user_profiles = MagicMock()
    mock_db.student_performance = MagicMock()
    mock_db.learning_gaps = MagicMock()
    mock_db.recommendations = MagicMock()
    mock_db.user_onboarding = MagicMock()
    mock_db.user_assessments = MagicMock()
    mock_db.course_enrollments = MagicMock()
    mock_db.lti_contexts = MagicMock()
    mock_db.lti_sessions = MagicMock()
    mock_db.audit_trail = MagicMock()
    mock_db.data_requests = MagicMock()
    
    # Create service
    data_privacy_service = DataPrivacyService(mock_db)
    
    # Mock database responses
    mock_db.user_profiles.find_one = AsyncMock(return_value=None)
    
    def create_empty_cursor():
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=[])
        return cursor
    
    for collection_name in ["student_performance", "learning_gaps", "recommendations", 
                           "user_assessments", "course_enrollments", "lti_contexts", "audit_trail"]:
        getattr(mock_db, collection_name).find.return_value = create_empty_cursor()
    
    mock_db.user_onboarding.find_one = AsyncMock(return_value=None)
    
    # Mock audit collection
    data_privacy_service.audit_collection = MagicMock()
    data_privacy_service.audit_collection.insert_one = AsyncMock()
    
    # Mock audit collection find method to return a cursor that supports chaining
    def create_audit_cursor():
        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)  # Return self for chaining
        cursor.to_list = AsyncMock(return_value=[])
        return cursor
    
    data_privacy_service.audit_collection.find = MagicMock(return_value=create_audit_cursor())
    
    # Retrieve complete user data
    await data_privacy_service.get_complete_user_data(
        user_id=user_id,
        requesting_user_id=requesting_user_id,
        ip_address=ip_address,
        user_agent="test-agent"
    )
    
    # Property: Audit trail should always be created with correct information
    
    # 1. Audit entry should be created
    data_privacy_service.audit_collection.insert_one.assert_called_once()
    
    # 2. Audit entry should contain all required fields
    audit_entry = data_privacy_service.audit_collection.insert_one.call_args[0][0]
    
    required_fields = ["audit_id", "user_id", "action", "resource_type", "timestamp", 
                      "details", "ip_address", "user_agent", "compliance_flags"]
    
    for field in required_fields:
        assert field in audit_entry, f"Missing required audit field: {field}"
    
    # 3. Audit entry should have correct values
    assert audit_entry["user_id"] == requesting_user_id
    assert audit_entry["action"] == "export"
    assert audit_entry["resource_type"] == "complete_profile"
    assert audit_entry["resource_id"] == user_id
    assert audit_entry["ip_address"] == ip_address
    assert audit_entry["user_agent"] == "test-agent"
    
    # 4. Compliance flags should be set correctly
    compliance_flags = audit_entry["compliance_flags"]
    assert compliance_flags["ferpa_applicable"] is True
    assert "data_sensitivity" in compliance_flags
    assert "retention_period" in compliance_flags


if __name__ == "__main__":
    pytest.main([__file__, "-v"])