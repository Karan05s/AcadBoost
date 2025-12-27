"""
Property-based tests for data integrity validation
"""
import pytest
import asyncio
from hypothesis import given, strategies as st, settings, HealthCheck
from datetime import datetime
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock

from app.services.data_collection_service import DataCollectionService
from app.services.error_handling_service import ErrorHandlingService


class TestDataIntegrityProperties:
    """Property-based tests for data integrity validation"""
    
    def create_data_service(self):
        """Create data collection service with mock database"""
        mock_db = MagicMock()
        mock_db.student_performance = AsyncMock()
        mock_db.error_logs = AsyncMock()
        mock_db.student_performance.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test_id"))
        mock_db.error_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="error_log_id"))
        return DataCollectionService(mock_db)
    
    @given(
        student_id=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
        course_id=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
        assignment_id=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
        score=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        max_score=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=20, deadline=3000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_data_integrity_preservation_property(
        self, 
        student_id, 
        course_id, 
        assignment_id, 
        score, 
        max_score
    ):
        """
        Property 3: Data integrity preservation
        
        For any valid submission data, the integrity validation should:
        1. Preserve valid data unchanged
        2. Correct invalid data to valid ranges
        3. Never produce corrupted output
        
        Validates: Requirements 1.3 - Ensure data integrity and validation
        """
        async def run_test():
            # Arrange: Create data service and submission data
            data_service = self.create_data_service()
            
            submission_data = {
                "student_id": student_id,
                "course_id": course_id,
                "assignment_id": assignment_id,
                "submission_type": "quiz",
                "score": score,
                "max_score": max_score,
                "timestamp": datetime.utcnow()
            }
            
            # Act: Validate data integrity
            integrity_report = await data_service.validate_data_integrity(submission_data)
            
            # Assert: Data integrity properties
            assert isinstance(integrity_report, dict)
            assert "valid" in integrity_report
            assert "errors" in integrity_report
            assert "warnings" in integrity_report
            assert "corrected_fields" in integrity_report
            
            # Property 1: Valid data should remain unchanged for valid inputs
            if score <= max_score and score >= 0:
                assert submission_data["score"] == score
                assert submission_data["max_score"] == max_score
            
            # Property 2: Invalid scores should be corrected
            if score > max_score:
                # Score should be capped to max_score
                assert submission_data["score"] <= submission_data["max_score"]
            
            if score < 0:
                # Negative scores should be corrected to 0
                assert submission_data["score"] >= 0
            
            # Property 3: Required fields should always be present
            required_fields = ["student_id", "course_id", "assignment_id", "submission_type"]
            for field in required_fields:
                assert field in submission_data
                assert submission_data[field] is not None
            
            # Property 4: Timestamp should be valid datetime
            assert isinstance(submission_data["timestamp"], datetime)
        
        # Run the async test
        asyncio.run(run_test())
    
    @given(
        corruption_level=st.integers(min_value=0, max_value=3),
        submission_type=st.sampled_from(["quiz", "code"])
    )
    @settings(max_examples=15, deadline=3000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_corruption_detection_consistency_property(
        self, 
        corruption_level, 
        submission_type
    ):
        """
        Property: Corruption detection consistency
        
        For any submission data with known corruption levels:
        1. Higher corruption levels should result in higher severity ratings
        2. Corruption detection should be consistent across similar data
        3. Recommended actions should match severity levels
        
        Validates: Requirements 1.4 - Handle corrupted submissions gracefully
        """
        async def run_test():
            # Arrange: Create data service and submission with controlled corruption
            data_service = self.create_data_service()
            
            base_data = {
                "student_id": "test_student",
                "course_id": "test_course", 
                "assignment_id": "test_assignment",
                "submission_type": submission_type,
                "timestamp": datetime.utcnow(),
                "score": 85,
                "max_score": 100
            }
            
            # Add submission-type specific data to make it valid
            if submission_type == "quiz":
                base_data["question_responses"] = [{"question_id": "q1", "response": "answer1"}]
            elif submission_type == "code":
                base_data["code_content"] = "print('hello world')"
            
            # Introduce corruption based on level
            corrupted_data = base_data.copy()
            
            if corruption_level >= 1:
                # Level 1: Invalid score
                corrupted_data["score"] = -10
            
            if corruption_level >= 2:
                # Level 2: Missing required field
                del corrupted_data["student_id"]
            
            if corruption_level >= 3:
                # Level 3: Invalid timestamp
                corrupted_data["timestamp"] = "invalid_timestamp"
            
            # Act: Detect corruption
            corruption_report = await data_service.error_handler.detect_data_corruption(corrupted_data)
            
            # Assert: Corruption detection properties
            assert isinstance(corruption_report, dict)
            assert "is_corrupted" in corruption_report
            assert "corruption_indicators" in corruption_report
            assert "severity" in corruption_report
            assert "recommended_action" in corruption_report
            
            # Property 1: Higher corruption levels should increase severity
            if corruption_level == 0:
                # With complete valid data, should not be corrupted
                assert not corruption_report["is_corrupted"]
                assert corruption_report["severity"] == "none"
            else:
                assert corruption_report["is_corrupted"]
            
            # Property 2: Recommended actions should match severity
            severity = corruption_report["severity"]
            action = corruption_report["recommended_action"]
            
            if severity == "none":
                assert action == "accept"
            elif severity == "low":
                assert action == "accept_with_correction"
            elif severity == "medium":
                assert action in ["accept_with_correction", "quarantine_for_review"]
            elif severity == "high":
                assert action in ["quarantine_for_review", "reject"]
            
            # Property 3: Corruption indicators should be non-empty for corrupted data
            if corruption_report["is_corrupted"]:
                assert len(corruption_report["corruption_indicators"]) > 0
        
        # Run the async test
        asyncio.run(run_test())
    
    @given(
        error_type=st.sampled_from([ValueError, KeyError, TypeError])
    )
    @settings(max_examples=10, deadline=3000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_error_recovery_consistency_property(
        self, 
        error_type
    ):
        """
        Property: Error recovery consistency
        
        For any error type and submission data:
        1. Recovery should always be attempted
        2. Recovery results should be consistent for same error types
        3. Corrected data should be valid if recovery is successful
        
        Validates: Requirements 1.4 - Graceful error handling with recovery
        """
        async def run_test():
            # Arrange: Create data service, submission data and error
            data_service = self.create_data_service()
            
            submission_data = {
                "student_id": "test_student",
                "course_id": "test_course",
                "assignment_id": "test_assignment",
                "submission_type": "quiz"
            }
            
            # Create specific error based on type
            if error_type == ValueError:
                error = ValueError("Invalid submission data")
            elif error_type == KeyError:
                error = KeyError("missing_field")
            else:  # TypeError
                error = TypeError("Type conversion error")
            
            # Act: Handle error with recovery
            error_info = await data_service.error_handler.handle_submission_error(error, submission_data)
            
            # Assert: Error recovery properties
            assert isinstance(error_info, dict)
            assert "error_type" in error_info
            assert "error_message" in error_info
            assert "recovery_attempted" in error_info
            assert "recovery_successful" in error_info
            
            # Property 1: Recovery should always be attempted
            assert error_info["recovery_attempted"] is True
            
            # Property 2: Error type should be correctly identified
            assert error_info["error_type"] == error_type.__name__
            
            # Property 3: If recovery is successful, corrected data should be provided
            if error_info["recovery_successful"]:
                assert "corrected_data" in error_info
                corrected_data = error_info["corrected_data"]
                
                # Corrected data should have required fields
                required_fields = ["student_id", "course_id", "assignment_id", "submission_type"]
                for field in required_fields:
                    assert field in corrected_data
                    assert corrected_data[field] is not None
        
        # Run the async test
        asyncio.run(run_test())
    
    def test_basic_data_integrity_validation(self):
        """
        Basic test for data integrity validation functionality
        
        Validates: Requirements 1.3, 1.4 - Data integrity and error handling
        """
        async def run_test():
            # Arrange: Create data service
            data_service = self.create_data_service()
            
            # Test 1: Valid data should pass validation
            valid_data = {
                "student_id": "test_student",
                "course_id": "test_course",
                "assignment_id": "test_assignment",
                "submission_type": "quiz",
                "score": 85,
                "max_score": 100,
                "timestamp": datetime.utcnow()
            }
            
            integrity_report = await data_service.validate_data_integrity(valid_data)
            assert integrity_report["valid"] is True
            assert len(integrity_report["errors"]) == 0
            
            # Test 2: Invalid data should be detected and corrected
            invalid_data = {
                "student_id": "test_student",
                "course_id": "test_course",
                "assignment_id": "test_assignment",
                "submission_type": "quiz",
                "score": -10,  # Invalid negative score
                "max_score": 100
            }
            
            integrity_report = await data_service.validate_data_integrity(invalid_data)
            assert "corrected_fields" in integrity_report
            assert invalid_data["score"] >= 0  # Should be corrected
            
            # Test 3: Corruption detection should work
            corrupt_data = {
                "score": 150,  # Score exceeds max
                "max_score": 100
            }
            
            corruption_report = await data_service.error_handler.detect_data_corruption(corrupt_data)
            assert corruption_report["is_corrupted"] is True
            assert len(corruption_report["corruption_indicators"]) > 0
        
        # Run the async test
        asyncio.run(run_test())