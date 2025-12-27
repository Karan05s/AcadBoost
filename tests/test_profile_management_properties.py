"""
Property-based tests for profile management functionality
Feature: learning-analytics-platform, Property 34: Learning preference persistence
"""
import pytest
from hypothesis import given, strategies as st, settings as hypothesis_settings, HealthCheck
from unittest.mock import AsyncMock, MagicMock
from app.services.user_service import UserService
from app.models.user import UserRole, LearningStyle, StudyTimePreference, DifficultyPreference


class TestProfileManagementProperties:
    """
    Property 34: Learning preference persistence
    Validates: Requirements 3.1, 3.6
    """
    
    def create_mock_db(self):
        """Create mock database for testing"""
        db = MagicMock()
        db.user_profiles = MagicMock()
        return db
    
    def create_user_service(self, mock_db):
        """Create UserService instance with mocked database"""
        return UserService(mock_db)
    
    @pytest.mark.asyncio
    @given(
        user_id=st.text(min_size=10, max_size=50),
        learning_style=st.sampled_from([LearningStyle.VISUAL, LearningStyle.AUDITORY, LearningStyle.KINESTHETIC, LearningStyle.MIXED]),
        study_time_preference=st.sampled_from([StudyTimePreference.MORNING, StudyTimePreference.AFTERNOON, StudyTimePreference.EVENING, StudyTimePreference.FLEXIBLE]),
        difficulty_preference=st.sampled_from([DifficultyPreference.GRADUAL, DifficultyPreference.CHALLENGING, DifficultyPreference.ADAPTIVE]),
        resource_preferences=st.lists(
            st.sampled_from(["video", "text", "interactive", "practice"]),
            min_size=1,
            max_size=4,
            unique=True
        ),
        email_notifications=st.booleans(),
        push_notifications=st.booleans(),
        achievement_alerts=st.booleans(),
        reminder_frequency=st.sampled_from(["daily", "weekly", "never"])
    )
    @hypothesis_settings(
        max_examples=50, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_learning_preference_persistence_property(
        self,
        user_id,
        learning_style,
        study_time_preference,
        difficulty_preference,
        resource_preferences,
        email_notifications,
        push_notifications,
        achievement_alerts,
        reminder_frequency
    ):
        """
        Feature: learning-analytics-platform, Property 34: Learning preference persistence
        
        For any user learning preferences, they should be stored and retrieved consistently
        across all recommendation generation processes.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        
        # Prepare learning preferences data
        learning_preferences = {
            "learning_style": learning_style.value,
            "study_time_preference": study_time_preference.value,
            "difficulty_preference": difficulty_preference.value,
            "resource_preferences": resource_preferences,
            "notification_preferences": {
                "email_notifications": email_notifications,
                "push_notifications": push_notifications,
                "achievement_alerts": achievement_alerts,
                "reminder_frequency": reminder_frequency
            }
        }
        
        # Mock successful update
        mock_db.user_profiles.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        
        # Update user profile with learning preferences
        update_data = {"learning_preferences": learning_preferences}
        success = await user_service.update_profile(user_id, update_data)
        
        # Verify update was successful
        assert success is True, "Learning preferences update should succeed"
        
        # Verify database was called with correct data
        mock_db.user_profiles.update_one.assert_called_once_with(
            {"user_id": user_id},
            {"$set": update_data}
        )
        
        # Mock retrieval of updated profile
        profile_data = {
            "user_id": user_id,
            "email": "test@example.com",
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
            "role": UserRole.STUDENT.value,
            "institution": "Test University",
            "created_at": "2024-01-01T00:00:00",
            "last_login": None,
            "email_verified": True,
            "profile_completed": True,
            "onboarding_completed": True,
            "learning_preferences": learning_preferences,
            "academic_info": None
        }
        
        mock_db.user_profiles.find_one = AsyncMock(return_value=profile_data)
        
        # Retrieve user profile
        retrieved_profile = await user_service.get_user_by_cognito_id(user_id)
        
        # Verify learning preferences persistence
        assert retrieved_profile is not None, "Profile should be retrievable"
        assert retrieved_profile.learning_preferences is not None, "Learning preferences should be present"
        
        # Verify all learning preference fields are persisted correctly
        prefs = retrieved_profile.learning_preferences
        assert prefs.learning_style.value == learning_style.value, "Learning style should be persisted"
        assert prefs.study_time_preference.value == study_time_preference.value, "Study time preference should be persisted"
        assert prefs.difficulty_preference.value == difficulty_preference.value, "Difficulty preference should be persisted"
        assert prefs.resource_preferences == resource_preferences, "Resource preferences should be persisted"
        
        # Verify notification preferences
        notif_prefs = prefs.notification_preferences
        assert notif_prefs.email_notifications == email_notifications, "Email notification preference should be persisted"
        assert notif_prefs.push_notifications == push_notifications, "Push notification preference should be persisted"
        assert notif_prefs.achievement_alerts == achievement_alerts, "Achievement alert preference should be persisted"
        assert notif_prefs.reminder_frequency == reminder_frequency, "Reminder frequency should be persisted"
    
    @pytest.mark.asyncio
    @given(
        user_id=st.text(min_size=10, max_size=50),
        major=st.text(min_size=1, max_size=100),
        year=st.sampled_from(["freshman", "sophomore", "junior", "senior", "graduate"]),
        gpa=st.floats(min_value=0.0, max_value=4.0, allow_nan=False, allow_infinity=False),
        enrolled_courses=st.lists(
            st.text(min_size=1, max_size=50),
            min_size=1,
            max_size=10,
            unique=True
        )
    )
    @hypothesis_settings(
        max_examples=30, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_academic_info_persistence_property(
        self,
        user_id,
        major,
        year,
        gpa,
        enrolled_courses
    ):
        """
        Feature: learning-analytics-platform, Property 34: Learning preference persistence
        
        For any user academic information, it should be stored and retrieved consistently
        for course and content recommendations.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        
        # Prepare academic info data
        academic_info = {
            "major": major,
            "year": year,
            "gpa": gpa,
            "enrolled_courses": enrolled_courses
        }
        
        # Mock successful update
        mock_db.user_profiles.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        
        # Update user profile with academic info
        update_data = {"academic_info": academic_info}
        success = await user_service.update_profile(user_id, update_data)
        
        # Verify update was successful
        assert success is True, "Academic info update should succeed"
        
        # Verify database was called with correct data
        mock_db.user_profiles.update_one.assert_called_once_with(
            {"user_id": user_id},
            {"$set": update_data}
        )
        
        # Mock retrieval of updated profile
        profile_data = {
            "user_id": user_id,
            "email": "test@example.com",
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
            "role": UserRole.STUDENT.value,
            "institution": "Test University",
            "created_at": "2024-01-01T00:00:00",
            "last_login": None,
            "email_verified": True,
            "profile_completed": True,
            "onboarding_completed": True,
            "learning_preferences": None,
            "academic_info": academic_info
        }
        
        mock_db.user_profiles.find_one = AsyncMock(return_value=profile_data)
        
        # Retrieve user profile
        retrieved_profile = await user_service.get_user_by_cognito_id(user_id)
        
        # Verify academic info persistence
        assert retrieved_profile is not None, "Profile should be retrievable"
        assert retrieved_profile.academic_info is not None, "Academic info should be present"
        
        # Verify all academic info fields are persisted correctly
        academic = retrieved_profile.academic_info
        assert academic.major == major, "Major should be persisted"
        assert academic.year.value == year, "Academic year should be persisted"
        assert academic.gpa == gpa, "GPA should be persisted"
        assert academic.enrolled_courses == enrolled_courses, "Enrolled courses should be persisted"
    
    @pytest.mark.asyncio
    @given(
        user_id=st.text(min_size=10, max_size=50),
        profile_updates=st.dictionaries(
            keys=st.sampled_from(["first_name", "last_name", "institution"]),
            values=st.text(min_size=1, max_size=100),
            min_size=1,
            max_size=3
        )
    )
    @hypothesis_settings(
        max_examples=20, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_profile_update_consistency_property(
        self,
        user_id,
        profile_updates
    ):
        """
        Feature: learning-analytics-platform, Property 34: Learning preference persistence
        
        For any profile updates, all changes should be applied consistently
        and retrievable after update.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        
        # Mock successful update
        mock_db.user_profiles.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        
        # Update user profile
        success = await user_service.update_profile(user_id, profile_updates)
        
        # Verify update was successful
        assert success is True, "Profile update should succeed"
        
        # Verify database was called with correct data
        mock_db.user_profiles.update_one.assert_called_once_with(
            {"user_id": user_id},
            {"$set": profile_updates}
        )
        
        # Mock retrieval of updated profile
        base_profile_data = {
            "user_id": user_id,
            "email": "test@example.com",
            "username": "testuser",
            "first_name": "Original First",
            "last_name": "Original Last",
            "role": UserRole.STUDENT.value,
            "institution": "Original University",
            "created_at": "2024-01-01T00:00:00",
            "last_login": None,
            "email_verified": True,
            "profile_completed": True,
            "onboarding_completed": True,
            "learning_preferences": None,
            "academic_info": None
        }
        
        # Apply updates to mock data
        updated_profile_data = {**base_profile_data, **profile_updates}
        
        mock_db.user_profiles.find_one = AsyncMock(return_value=updated_profile_data)
        
        # Retrieve user profile
        retrieved_profile = await user_service.get_user_by_cognito_id(user_id)
        
        # Verify profile updates persistence
        assert retrieved_profile is not None, "Profile should be retrievable"
        
        # Verify all updated fields are persisted correctly
        for field, expected_value in profile_updates.items():
            actual_value = getattr(retrieved_profile, field)
            assert actual_value == expected_value, f"Field {field} should be updated to {expected_value}"
    
    @pytest.mark.asyncio
    @given(
        user_id=st.text(min_size=10, max_size=50)
    )
    @hypothesis_settings(
        max_examples=10, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_profile_completion_tracking_property(
        self,
        user_id
    ):
        """
        Feature: learning-analytics-platform, Property 34: Learning preference persistence
        
        For any user profile, completion status should be tracked and updated
        when required fields are provided.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        
        # Mock current incomplete profile
        incomplete_profile_data = {
            "user_id": user_id,
            "email": "test@example.com",
            "username": "testuser",
            "first_name": "",  # Missing required field
            "last_name": "",   # Missing required field
            "role": UserRole.STUDENT.value,
            "institution": None,
            "created_at": "2024-01-01T00:00:00",
            "last_login": None,
            "email_verified": True,
            "profile_completed": False,  # Initially incomplete
            "onboarding_completed": False,
            "learning_preferences": None,
            "academic_info": None
        }
        
        # Mock successful update
        mock_db.user_profiles.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        
        # Update with required fields to complete profile
        completion_updates = {
            "first_name": "Test",
            "last_name": "User",
            "learning_preferences": {
                "learning_style": "visual",
                "study_time_preference": "morning"
            },
            "profile_completed": True  # Should be set when profile becomes complete
        }
        
        # Update user profile
        success = await user_service.update_profile(user_id, completion_updates)
        
        # Verify update was successful
        assert success is True, "Profile completion update should succeed"
        
        # Verify database was called with completion flag
        mock_db.user_profiles.update_one.assert_called_once_with(
            {"user_id": user_id},
            {"$set": completion_updates}
        )
        
        # Mock retrieval of completed profile
        completed_profile_data = {**incomplete_profile_data, **completion_updates}
        mock_db.user_profiles.find_one = AsyncMock(return_value=completed_profile_data)
        
        # Retrieve user profile
        retrieved_profile = await user_service.get_user_by_cognito_id(user_id)
        
        # Verify profile completion tracking
        assert retrieved_profile is not None, "Profile should be retrievable"
        assert retrieved_profile.profile_completed is True, "Profile should be marked as completed"
        assert retrieved_profile.first_name == "Test", "First name should be updated"
        assert retrieved_profile.last_name == "User", "Last name should be updated"
        assert retrieved_profile.learning_preferences is not None, "Learning preferences should be present"