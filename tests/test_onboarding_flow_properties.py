"""
Property-based tests for onboarding flow functionality
Feature: learning-analytics-platform, Property 33: Profile completion tracking
"""
import pytest
from hypothesis import given, strategies as st, settings as hypothesis_settings, HealthCheck
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from app.services.user_service import UserService
from app.models.user import UserRole, LearningStyle, StudyTimePreference


class TestOnboardingFlowProperties:
    """
    Property 33: Profile completion tracking
    Validates: Requirements 4.3
    """
    
    def create_mock_db(self):
        """Create mock database for testing"""
        db = MagicMock()
        db.user_onboarding = MagicMock()
        db.user_assessments = MagicMock()
        db.user_profiles = MagicMock()
        return db
    
    def create_user_service(self, mock_db):
        """Create UserService instance with mocked database"""
        return UserService(mock_db)
    
    @pytest.mark.asyncio
    @given(
        user_id=st.text(min_size=10, max_size=50)
    )
    @hypothesis_settings(
        max_examples=20, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_onboarding_initialization_property(
        self,
        user_id
    ):
        """
        Feature: learning-analytics-platform, Property 33: Profile completion tracking
        
        For any user starting onboarding, the system should initialize tracking
        with correct step progression and progress calculation.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        
        # Mock database insert for onboarding initialization
        mock_db.user_onboarding.insert_one = AsyncMock()
        
        # Initialize onboarding
        result = await user_service.initialize_onboarding(user_id)
        
        # Verify onboarding initialization structure
        assert "current_step" in result, "Result should contain current_step"
        assert "progress_percentage" in result, "Result should contain progress_percentage"
        assert "next_action" in result, "Result should contain next_action"
        
        # Verify initial state
        assert result["current_step"] == "profile_setup", "Should start with profile_setup step"
        assert result["total_steps"] == 4, "Should have 4 total onboarding steps"
        assert result["progress_percentage"] == 0.0, "Should start with 0% progress"
        assert result["completed_steps"] == [], "Should start with no completed steps"
        
        # Verify database was called to store onboarding data
        mock_db.user_onboarding.insert_one.assert_called_once()
        call_args = mock_db.user_onboarding.insert_one.call_args[0][0]
        
        assert call_args["user_id"] == user_id, "Should store correct user_id"
        assert call_args["current_step"] == "profile_setup", "Should store initial step"
        assert call_args["completed_steps"] == [], "Should store empty completed steps"
        assert call_args["total_steps"] == 4, "Should store correct total steps"
        assert call_args["progress_percentage"] == 0.0, "Should store initial progress"
    
    @pytest.mark.asyncio
    @given(
        user_id=st.text(min_size=10, max_size=50),
        step=st.sampled_from(["profile_setup", "preferences", "assessment", "dashboard_setup"]),
        completed_steps_count=st.integers(min_value=0, max_value=3)
    )
    @hypothesis_settings(
        max_examples=30, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_onboarding_progress_tracking_property(
        self,
        user_id,
        step,
        completed_steps_count
    ):
        """
        Feature: learning-analytics-platform, Property 33: Profile completion tracking
        
        For any onboarding step completion, progress should be tracked accurately
        with correct percentage calculation and step advancement.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        
        # Create list of completed steps based on count
        all_steps = ["profile_setup", "preferences", "assessment", "dashboard_setup"]
        completed_steps = all_steps[:completed_steps_count]
        
        # Calculate expected progress
        expected_progress = (completed_steps_count / 4) * 100
        
        # Mock existing onboarding data
        mock_onboarding_data = {
            "user_id": user_id,
            "current_step": step,
            "completed_steps": completed_steps,
            "total_steps": 4,
            "progress_percentage": expected_progress
        }
        
        mock_db.user_onboarding.find_one = AsyncMock(return_value=mock_onboarding_data)
        
        # Get onboarding progress
        progress = await user_service.get_onboarding_progress(user_id)
        
        # Verify progress tracking accuracy
        assert progress["current_step"] == step, "Should track current step correctly"
        assert progress["completed_steps"] == completed_steps, "Should track completed steps correctly"
        assert progress["total_steps"] == 4, "Should maintain correct total steps"
        assert progress["progress_percentage"] == expected_progress, "Should calculate progress percentage correctly"
        
        # Verify database query
        mock_db.user_onboarding.find_one.assert_called_once_with({"user_id": user_id})
    
    @pytest.mark.asyncio
    @given(
        user_id=st.text(min_size=10, max_size=50),
        step=st.sampled_from(["profile_setup", "preferences", "assessment", "dashboard_setup"]),
        step_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.text(), st.booleans(), st.integers()),
            min_size=1,
            max_size=5
        )
    )
    @hypothesis_settings(
        max_examples=40, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_onboarding_step_completion_property(
        self,
        user_id,
        step,
        step_data
    ):
        """
        Feature: learning-analytics-platform, Property 33: Profile completion tracking
        
        For any onboarding step completion, the system should update progress,
        advance to next step, and store step data correctly.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        
        # Define step order for progression logic
        step_order = ["profile_setup", "preferences", "assessment", "dashboard_setup"]
        current_index = step_order.index(step)
        
        # Mock existing onboarding data (step not yet completed)
        mock_onboarding_data = {
            "user_id": user_id,
            "current_step": step,
            "completed_steps": step_order[:current_index],  # Previous steps completed
            "total_steps": 4,
            "progress_percentage": (current_index / 4) * 100
        }
        
        mock_db.user_onboarding.find_one = AsyncMock(return_value=mock_onboarding_data)
        mock_db.user_onboarding.update_one = AsyncMock()
        
        # Mock user service methods
        user_service.update_profile = AsyncMock(return_value=True)
        user_service.get_user_by_cognito_id = AsyncMock(return_value=None)  # Mock this method too
        
        # Complete the onboarding step
        success = await user_service.complete_onboarding_step(user_id, step, step_data)
        
        # Verify step completion success
        assert success is True, "Step completion should succeed"
        
        # Verify database update was called
        mock_db.user_onboarding.update_one.assert_called_once()
        update_call = mock_db.user_onboarding.update_one.call_args
        
        # Verify update query structure
        assert update_call[0][0] == {"user_id": user_id}, "Should update correct user"
        update_data = update_call[0][1]["$set"]
        
        # Verify progress tracking updates
        expected_completed_steps = step_order[:current_index + 1]  # Include current step
        expected_progress = ((current_index + 1) / 4) * 100
        
        assert step in update_data["completed_steps"], "Current step should be added to completed steps"
        assert update_data["progress_percentage"] == expected_progress, "Progress percentage should be updated correctly"
        assert f"step_data.{step}" in update_data, "Step data should be stored"
        assert update_data[f"step_data.{step}"] == step_data, "Step data should match input"
        
        # Verify next step advancement
        if current_index + 1 < len(step_order):
            expected_next_step = step_order[current_index + 1]
            assert update_data["current_step"] == expected_next_step, "Should advance to next step"
        else:
            assert update_data["current_step"] == "completed", "Should mark as completed when all steps done"
    
    @pytest.mark.asyncio
    @given(
        user_id=st.text(min_size=10, max_size=50),
        questions_count=st.integers(min_value=1, max_value=10),
        correct_answers_count=st.integers(min_value=0, max_value=10)
    )
    @hypothesis_settings(
        max_examples=25, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_initial_assessment_processing_property(
        self,
        user_id,
        questions_count,
        correct_answers_count
    ):
        """
        Feature: learning-analytics-platform, Property 33: Profile completion tracking
        
        For any initial assessment, skill level should be determined correctly
        based on score percentage and stored with assessment results.
        """
        # Ensure correct answers don't exceed total questions
        correct_answers_count = min(correct_answers_count, questions_count)
        
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        
        # Generate assessment data
        questions = [{"id": f"q{i}", "correct_answer": "A"} for i in range(questions_count)]
        answers = []
        
        for i in range(questions_count):
            # First 'correct_answers_count' answers are correct, rest are wrong
            answer = "A" if i < correct_answers_count else "B"
            answers.append({"question_id": f"q{i}", "answer": answer})
        
        assessment_data = {
            "questions": questions,
            "answers": answers
        }
        
        # Mock database insert for assessment storage
        mock_db.user_assessments.insert_one = AsyncMock()
        
        # Process initial assessment
        result = await user_service.process_initial_assessment(user_id, assessment_data)
        
        # Verify assessment result structure
        assert "skill_level" in result, "Result should contain skill_level"
        assert "score_percentage" in result, "Result should contain score_percentage"
        assert "total_questions" in result, "Result should contain total_questions"
        assert "correct_answers" in result, "Result should contain correct_answers"
        
        # Verify scoring accuracy
        expected_score = (correct_answers_count / questions_count) * 100 if questions_count > 0 else 0
        assert result["total_questions"] == questions_count, "Should count questions correctly"
        assert result["correct_answers"] == correct_answers_count, "Should count correct answers correctly"
        assert abs(result["score_percentage"] - expected_score) < 0.01, "Should calculate score percentage correctly"
        
        # Verify skill level determination logic
        if expected_score >= 80:
            expected_skill_level = "advanced"
        elif expected_score >= 60:
            expected_skill_level = "intermediate"
        else:
            expected_skill_level = "beginner"
        
        assert result["skill_level"] == expected_skill_level, f"Should determine skill level correctly for {expected_score}% score"
        
        # Verify database storage
        mock_db.user_assessments.insert_one.assert_called_once()
        stored_data = mock_db.user_assessments.insert_one.call_args[0][0]
        
        assert stored_data["user_id"] == user_id, "Should store correct user_id"
        assert stored_data["assessment_type"] == "initial_onboarding", "Should store correct assessment type"
        assert stored_data["skill_level"] == expected_skill_level, "Should store determined skill level"
        assert stored_data["score_percentage"] == expected_score, "Should store calculated score"
    
    @pytest.mark.asyncio
    @given(
        user_id=st.text(min_size=10, max_size=50)
    )
    @hypothesis_settings(
        max_examples=15, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_onboarding_completion_property(
        self,
        user_id
    ):
        """
        Feature: learning-analytics-platform, Property 33: Profile completion tracking
        
        For any user completing onboarding, the system should mark both
        the user profile and onboarding record as completed.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        
        # Mock successful profile update
        user_service.update_profile = AsyncMock(return_value=True)
        
        # Mock onboarding record update
        mock_db.user_onboarding.update_one = AsyncMock()
        
        # Complete onboarding
        success = await user_service.complete_onboarding(user_id)
        
        # Verify completion success
        assert success is True, "Onboarding completion should succeed"
        
        # Verify profile was updated with completion status
        user_service.update_profile.assert_called_once()
        profile_update_call = user_service.update_profile.call_args
        
        assert profile_update_call[0][0] == user_id, "Should update correct user profile"
        update_data = profile_update_call[0][1]
        assert update_data["onboarding_completed"] is True, "Should mark onboarding as completed in profile"
        assert "onboarding_completed_at" in update_data, "Should set completion timestamp"
        
        # Verify onboarding record was updated
        mock_db.user_onboarding.update_one.assert_called_once()
        onboarding_update_call = mock_db.user_onboarding.update_one.call_args
        
        assert onboarding_update_call[0][0] == {"user_id": user_id}, "Should update correct onboarding record"
        onboarding_update_data = onboarding_update_call[0][1]["$set"]
        assert onboarding_update_data["completed"] is True, "Should mark onboarding record as completed"
        assert "completed_at" in onboarding_update_data, "Should set completion timestamp in onboarding record"
    
    @pytest.mark.asyncio
    @given(
        user_id=st.text(min_size=10, max_size=50),
        learning_preferences=st.fixed_dictionaries({
            'learning_style': st.sampled_from(['visual', 'auditory', 'kinesthetic', 'mixed']),
            'study_time_preference': st.sampled_from(['morning', 'afternoon', 'evening', 'flexible'])
        })
    )
    @hypothesis_settings(
        max_examples=20, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_preferences_step_integration_property(
        self,
        user_id,
        learning_preferences
    ):
        """
        Feature: learning-analytics-platform, Property 33: Profile completion tracking
        
        For any preferences step completion, learning preferences should be
        stored in both onboarding data and user profile.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        
        # Mock existing onboarding data
        mock_onboarding_data = {
            "user_id": user_id,
            "current_step": "preferences",
            "completed_steps": ["profile_setup"],
            "total_steps": 4,
            "progress_percentage": 25.0
        }
        
        mock_db.user_onboarding.find_one = AsyncMock(return_value=mock_onboarding_data)
        mock_db.user_onboarding.update_one = AsyncMock()
        
        # Mock user service methods
        user_service.update_profile = AsyncMock(return_value=True)
        user_service.get_user_by_cognito_id = AsyncMock(return_value=None)  # Mock this method too
        
        # Complete preferences step
        step_data = {"learning_preferences": learning_preferences}
        success = await user_service.complete_onboarding_step(user_id, "preferences", step_data)
        
        # Verify step completion success
        assert success is True, "Preferences step completion should succeed"
        
        # Verify onboarding data was updated
        mock_db.user_onboarding.update_one.assert_called_once()
        onboarding_update = mock_db.user_onboarding.update_one.call_args[0][1]["$set"]
        
        assert "preferences" in onboarding_update["completed_steps"], "Preferences step should be marked completed"
        assert onboarding_update["step_data.preferences"] == step_data, "Preferences data should be stored in onboarding"
        assert onboarding_update["progress_percentage"] == 50.0, "Progress should advance to 50%"
        assert onboarding_update["current_step"] == "assessment", "Should advance to assessment step"
        
        # Verify profile was updated with learning preferences
        user_service.update_profile.assert_called_once()
        profile_update = user_service.update_profile.call_args[0][1]
        
        assert "learning_preferences" in profile_update, "Learning preferences should be updated in profile"
        assert profile_update["learning_preferences"] == learning_preferences, "Learning preferences should match input"