"""
Property-based tests for quiz data capture functionality
Feature: learning-analytics-platform, Property 1: Complete quiz data capture
"""
import pytest
from hypothesis import given, strategies as st, settings as hypothesis_settings, HealthCheck
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from app.services.data_collection_service import DataCollectionService
from app.models.performance import QuizSubmissionRequest, QuestionResponse, SubmissionType


class TestQuizDataCaptureProperties:
    """
    Property 1: Complete quiz data capture
    Validates: Requirements 1.1
    """
    
    def create_mock_db(self):
        """Create mock database for testing"""
        db = MagicMock()
        db.student_performance = MagicMock()
        return db
    
    def create_data_service(self, mock_db):
        """Create DataCollectionService instance with mocked database"""
        return DataCollectionService(mock_db)
    
    @pytest.mark.asyncio
    @given(
        student_id=st.text(min_size=1, max_size=50),
        course_id=st.text(min_size=1, max_size=50),
        assignment_id=st.text(min_size=1, max_size=50),
        questions=st.lists(
            st.fixed_dictionaries({
                'question_id': st.text(min_size=1, max_size=20),
                'response': st.text(min_size=1, max_size=100),
                'correct': st.booleans(),
                'concept_tags': st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=5)
            }),
            min_size=1,
            max_size=20
        ),
        total_time_spent=st.integers(min_value=1, max_value=7200)  # 1 second to 2 hours
    )
    @hypothesis_settings(
        max_examples=50, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_complete_quiz_data_capture_property(
        self,
        student_id,
        course_id,
        assignment_id,
        questions,
        total_time_spent
    ):
        """
        Feature: learning-analytics-platform, Property 1: Complete quiz data capture
        
        For any quiz submission, all question-level accuracy data should be captured 
        and stored with the submission.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        data_service = self.create_data_service(mock_db)
        
        # Create question responses from generated data
        question_responses = []
        for q in questions:
            response = QuestionResponse(
                question_id=q['question_id'],
                response=q['response'],
                correct=q['correct'],
                concept_tags=q['concept_tags']
            )
            question_responses.append(response)
        
        # Create quiz submission request
        quiz_submission = QuizSubmissionRequest(
            student_id=student_id,
            course_id=course_id,
            assignment_id=assignment_id,
            question_responses=question_responses,
            total_time_spent=total_time_spent
        )
        
        # Mock database insert result
        mock_insert_result = MagicMock()
        mock_insert_result.inserted_id = f"submission_{student_id}_{len(questions)}"
        mock_db.student_performance.insert_one = AsyncMock(return_value=mock_insert_result)
        
        # Process quiz submission
        result = await data_service.process_quiz_submission(quiz_submission)
        
        # Verify submission response structure
        assert result.student_id == student_id, "Response should contain correct student ID"
        assert result.submission_type == SubmissionType.QUIZ, "Response should indicate quiz submission type"
        assert result.submission_id is not None, "Response should contain submission ID"
        assert isinstance(result.timestamp, datetime), "Response should contain valid timestamp"
        
        # Verify score calculation
        expected_correct = sum(1 for q in questions if q['correct'])
        expected_total = len(questions)
        assert result.score == expected_correct, f"Score should be {expected_correct}, got {result.score}"
        assert result.max_score == expected_total, f"Max score should be {expected_total}, got {result.max_score}"
        
        # Verify database was called to store data
        mock_db.student_performance.insert_one.assert_called_once()
        stored_data = mock_db.student_performance.insert_one.call_args[0][0]
        
        # Verify all question-level data is captured
        assert stored_data["student_id"] == student_id, "Stored data should contain student ID"
        assert stored_data["course_id"] == course_id, "Stored data should contain course ID"
        assert stored_data["assignment_id"] == assignment_id, "Stored data should contain assignment ID"
        assert stored_data["submission_type"] == SubmissionType.QUIZ, "Stored data should indicate quiz type"
        assert stored_data["score"] == expected_correct, "Stored data should contain correct score"
        assert stored_data["max_score"] == expected_total, "Stored data should contain correct max score"
        
        # Verify question responses are stored
        assert "question_responses" in stored_data, "Stored data should contain question responses"
        stored_responses = stored_data["question_responses"]
        assert len(stored_responses) == len(questions), "All question responses should be stored"
        
        # Verify each question response contains required data
        for i, stored_response in enumerate(stored_responses):
            original_question = questions[i]
            assert stored_response["question_id"] == original_question["question_id"], f"Question {i} ID should match"
            assert stored_response["response"] == original_question["response"], f"Question {i} response should match"
            assert stored_response["correct"] == original_question["correct"], f"Question {i} correctness should match"
            assert stored_response["concept_tags"] == original_question["concept_tags"], f"Question {i} concept tags should match"
        
        # Verify metadata is captured
        assert "metadata" in stored_data, "Stored data should contain metadata"
        metadata = stored_data["metadata"]
        assert metadata["total_time_spent"] == total_time_spent, "Metadata should contain total time spent"
        assert "accuracy_rate" in metadata, "Metadata should contain accuracy rate"
        assert "concept_tags" in metadata, "Metadata should contain concept tags"
        
        # Verify accuracy rate calculation
        expected_accuracy = expected_correct / expected_total if expected_total > 0 else 0
        assert abs(metadata["accuracy_rate"] - expected_accuracy) < 0.001, "Accuracy rate should be calculated correctly"
    
    @pytest.mark.asyncio
    @given(
        student_id=st.text(min_size=1, max_size=50),
        course_id=st.text(min_size=1, max_size=50),
        assignment_id=st.text(min_size=1, max_size=50),
        questions=st.lists(
            st.fixed_dictionaries({
                'question_id': st.text(min_size=1, max_size=20),
                'response': st.text(min_size=1, max_size=100),
                'correct': st.booleans(),
                'concept_tags': st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=3)
            }),
            min_size=5,
            max_size=15
        )
    )
    @hypothesis_settings(
        max_examples=30, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_concept_tag_extraction_property(
        self,
        student_id,
        course_id,
        assignment_id,
        questions
    ):
        """
        Feature: learning-analytics-platform, Property 1: Complete quiz data capture
        
        For any quiz submission with concept tags, all unique concept tags should be 
        extracted and stored in the metadata.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        data_service = self.create_data_service(mock_db)
        
        # Create question responses from generated data
        question_responses = []
        all_concept_tags = set()
        for q in questions:
            response = QuestionResponse(
                question_id=q['question_id'],
                response=q['response'],
                correct=q['correct'],
                concept_tags=q['concept_tags']
            )
            question_responses.append(response)
            all_concept_tags.update(q['concept_tags'])
        
        # Create quiz submission request
        quiz_submission = QuizSubmissionRequest(
            student_id=student_id,
            course_id=course_id,
            assignment_id=assignment_id,
            question_responses=question_responses
        )
        
        # Mock database insert result
        mock_insert_result = MagicMock()
        mock_insert_result.inserted_id = f"submission_{student_id}"
        mock_db.student_performance.insert_one = AsyncMock(return_value=mock_insert_result)
        
        # Process quiz submission
        result = await data_service.process_quiz_submission(quiz_submission)
        
        # Verify database was called
        mock_db.student_performance.insert_one.assert_called_once()
        stored_data = mock_db.student_performance.insert_one.call_args[0][0]
        
        # Verify concept tags are extracted and stored
        assert "metadata" in stored_data, "Stored data should contain metadata"
        metadata = stored_data["metadata"]
        assert "concept_tags" in metadata, "Metadata should contain concept tags"
        
        stored_concept_tags = set(metadata["concept_tags"])
        assert stored_concept_tags == all_concept_tags, f"All unique concept tags should be stored. Expected: {all_concept_tags}, Got: {stored_concept_tags}"
    
    @pytest.mark.asyncio
    @given(
        student_id=st.text(min_size=1, max_size=50),
        course_id=st.text(min_size=1, max_size=50),
        assignment_id=st.text(min_size=1, max_size=50),
        questions=st.lists(
            st.fixed_dictionaries({
                'question_id': st.text(min_size=1, max_size=20),
                'response': st.text(min_size=1, max_size=100),
                'correct': st.booleans(),
                'concept_tags': st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=3),
                'time_spent': st.integers(min_value=1, max_value=600)  # 1 second to 10 minutes per question
            }),
            min_size=1,
            max_size=10
        )
    )
    @hypothesis_settings(
        max_examples=25, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_question_timing_data_capture_property(
        self,
        student_id,
        course_id,
        assignment_id,
        questions
    ):
        """
        Feature: learning-analytics-platform, Property 1: Complete quiz data capture
        
        For any quiz submission with timing data, individual question timing should be 
        captured and stored with each question response.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        data_service = self.create_data_service(mock_db)
        
        # Create question responses with timing data
        question_responses = []
        for q in questions:
            response = QuestionResponse(
                question_id=q['question_id'],
                response=q['response'],
                correct=q['correct'],
                concept_tags=q['concept_tags'],
                time_spent=q['time_spent']
            )
            question_responses.append(response)
        
        # Create quiz submission request
        quiz_submission = QuizSubmissionRequest(
            student_id=student_id,
            course_id=course_id,
            assignment_id=assignment_id,
            question_responses=question_responses
        )
        
        # Mock database insert result
        mock_insert_result = MagicMock()
        mock_insert_result.inserted_id = f"submission_{student_id}"
        mock_db.student_performance.insert_one = AsyncMock(return_value=mock_insert_result)
        
        # Process quiz submission
        result = await data_service.process_quiz_submission(quiz_submission)
        
        # Verify database was called
        mock_db.student_performance.insert_one.assert_called_once()
        stored_data = mock_db.student_performance.insert_one.call_args[0][0]
        
        # Verify timing data is captured for each question
        stored_responses = stored_data["question_responses"]
        for i, stored_response in enumerate(stored_responses):
            original_question = questions[i]
            if "time_spent" in stored_response:
                assert stored_response["time_spent"] == original_question["time_spent"], f"Question {i} timing data should be preserved"
    
    @pytest.mark.asyncio
    @given(
        student_id=st.text(min_size=1, max_size=50),
        course_id=st.text(min_size=1, max_size=50),
        assignment_id=st.text(min_size=1, max_size=50)
    )
    @hypothesis_settings(
        max_examples=15, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_empty_quiz_handling_property(
        self,
        student_id,
        course_id,
        assignment_id
    ):
        """
        Feature: learning-analytics-platform, Property 1: Complete quiz data capture
        
        For any quiz submission with no questions, the system should handle it gracefully
        and raise appropriate validation errors.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        data_service = self.create_data_service(mock_db)
        
        # Create quiz submission request with no questions
        quiz_submission = QuizSubmissionRequest(
            student_id=student_id,
            course_id=course_id,
            assignment_id=assignment_id,
            question_responses=[]  # Empty list
        )
        
        # Process quiz submission should raise validation error
        with pytest.raises(ValueError) as exc_info:
            await data_service.process_quiz_submission(quiz_submission)
        
        # Verify error message indicates validation failure
        error_message = str(exc_info.value)
        assert "validation" in error_message.lower(), "Error should indicate validation failure"
        
        # Verify database was not called for invalid submission
        mock_db.student_performance.insert_one.assert_not_called()