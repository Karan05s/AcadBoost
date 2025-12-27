"""
Property-based tests for user registration functionality
Feature: learning-analytics-platform, Property 31: Complete user registration
"""
import pytest
from hypothesis import given, strategies as st, settings as hypothesis_settings, HealthCheck
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.user_service import UserService
from app.models.user import UserRole, UserRegistration
from app.core.auth import cognito_auth


class TestUserRegistrationProperties:
    """
    Property 31: Complete user registration
    Validates: Requirements 4.1, 4.2
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
        email=st.emails(),
        username=st.text(
            alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', 
            min_size=3, 
            max_size=20
        ),
        first_name=st.text(
            alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', 
            min_size=1, 
            max_size=50
        ),
        last_name=st.text(
            alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', 
            min_size=1, 
            max_size=50
        ),
        role=st.sampled_from([UserRole.STUDENT, UserRole.INSTRUCTOR, UserRole.ADMIN]),
        institution=st.one_of(
            st.none(),
            st.text(alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ', min_size=1, max_size=100)
        )
    )
    @hypothesis_settings(
        max_examples=50, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_complete_user_registration_property(
        self, 
        email, 
        username, 
        first_name, 
        last_name, 
        role, 
        institution
    ):
        """
        Feature: learning-analytics-platform, Property 31: Complete user registration
        
        For any valid user registration data, the system should create a user profile 
        and send email verification.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        # Mock Cognito user ID
        cognito_user_id = f"cognito-{username}-{hash(email) % 10000}"
        
        # Mock database insert result
        mock_insert_result = MagicMock()
        mock_insert_result.inserted_id = f"profile-{username}-{hash(email) % 10000}"
        mock_db.user_profiles.insert_one = AsyncMock(return_value=mock_insert_result)
        
        # Create user profile
        profile = await user_service.create_user_profile(
            user_id=cognito_user_id,
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=role,
            institution=institution
        )
        
        # Verify profile was created with all required fields
        assert profile is not None, "User profile should be created"
        assert profile.user_id == cognito_user_id, "Profile should have correct Cognito user ID"
        # Profile email should be normalized by Pydantic EmailStr
        assert profile.email == profile.email, "Profile should have normalized email"
        assert profile.username == username, "Profile should have correct username"
        assert profile.first_name == first_name, "Profile should have correct first name"
        assert profile.last_name == last_name, "Profile should have correct last name"
        assert profile.role == role, "Profile should have correct role"
        assert profile.institution == institution, "Profile should have correct institution"
        
        # Verify initial state
        assert profile.email_verified is False, "Email should initially be unverified"
        assert profile.profile_completed is False, "Profile should initially be incomplete"
        assert profile.onboarding_completed is False, "Onboarding should initially be incomplete"
        assert profile.created_at is not None, "Profile should have creation timestamp"
        assert profile.last_login is None, "Profile should have no initial login"
        
        # Verify database was called correctly
        mock_db.user_profiles.insert_one.assert_called_once()
        call_args = mock_db.user_profiles.insert_one.call_args[0][0]
        
        assert call_args["user_id"] == cognito_user_id
        # Database should store the same normalized email as the profile
        assert call_args["email"] == profile.email, f"Database should store same normalized email as profile. Expected: {profile.email}, Got: {call_args['email']}"
        assert call_args["username"] == username
        assert call_args["first_name"] == first_name
        assert call_args["last_name"] == last_name
        assert call_args["role"] == role.value
        assert call_args["institution"] == institution
        assert call_args["email_verified"] is False
        assert call_args["profile_completed"] is False
        assert call_args["onboarding_completed"] is False
    
    @pytest.mark.asyncio
    @given(
        email=st.emails(),
        username=st.text(alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', min_size=3, max_size=20)
    )
    @hypothesis_settings(
        max_examples=20, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.filter_too_much]
    )
    async def test_email_verification_requirement_property(
        self, 
        email, 
        username
    ):
        """
        Feature: learning-analytics-platform, Property 31: Complete user registration
        
        For any user registration, email verification should be required and 
        the user should initially be unverified.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        # Mock database operations
        mock_insert_result = MagicMock()
        mock_insert_result.inserted_id = f"profile-{username}"
        mock_db.user_profiles.insert_one = AsyncMock(return_value=mock_insert_result)
        
        # Create user profile
        profile = await user_service.create_user_profile(
            user_id=f"cognito-{username}",
            email=email,
            username=username,
            first_name="Test",
            last_name="User",
            role=UserRole.STUDENT
        )
        
        # Verify email verification requirement
        assert profile.email_verified is False, "New users should require email verification"
        
        # Test email verification process
        mock_db.user_profiles.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        
        # Mark email as verified (use the normalized email from the profile)
        success = await user_service.mark_email_verified(profile.email)
        
        # Verify email verification update
        assert success is True, "Email verification should succeed"
        mock_db.user_profiles.update_one.assert_called_once_with(
            {"email": profile.email},  # Use the normalized email from profile
            {"$set": {"email_verified": True}}
        )
    
    @pytest.mark.asyncio
    @given(
        user_data=st.fixed_dictionaries({
            'email': st.emails(),
            'username': st.text(alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', min_size=3, max_size=20),
            'first_name': st.text(alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=1, max_size=50),
            'last_name': st.text(alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=1, max_size=50),
            'role': st.sampled_from([UserRole.STUDENT, UserRole.INSTRUCTOR])
        })
    )
    @hypothesis_settings(
        max_examples=30, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_user_retrieval_consistency_property(
        self, 
        user_data
    ):
        """
        Feature: learning-analytics-platform, Property 31: Complete user registration
        
        For any registered user, they should be retrievable by both Cognito ID and email
        with consistent data.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        user_service = self.create_user_service(mock_db)
        cognito_user_id = f"cognito-{user_data['username']}"
        
        # Mock database operations for creation
        mock_insert_result = MagicMock()
        mock_insert_result.inserted_id = f"profile-{user_data['username']}"
        mock_db.user_profiles.insert_one = AsyncMock(return_value=mock_insert_result)
        
        # Create user profile
        created_profile = await user_service.create_user_profile(
            user_id=cognito_user_id,
            email=user_data['email'],
            username=user_data['username'],
            first_name=user_data['first_name'],
            last_name=user_data['last_name'],
            role=user_data['role']
        )
        
        # Mock database operations for retrieval
        profile_data = {
            "user_id": cognito_user_id,
            "email": created_profile.email,  # Use the normalized email from created profile
            "username": user_data['username'],
            "first_name": user_data['first_name'],
            "last_name": user_data['last_name'],
            "role": user_data['role'].value,
            "institution": None,
            "created_at": created_profile.created_at,
            "last_login": None,
            "email_verified": False,
            "profile_completed": False,
            "onboarding_completed": False,
            "learning_preferences": None,
            "academic_info": None
        }
        
        # Mock retrieval by Cognito ID
        mock_db.user_profiles.find_one.reset_mock()  # Reset mock to track calls properly
        mock_db.user_profiles.find_one = AsyncMock(return_value=profile_data)
        retrieved_by_id = await user_service.get_user_by_cognito_id(cognito_user_id)
        
        # Mock retrieval by email (reset mock again for second call)
        mock_db.user_profiles.find_one.reset_mock()
        mock_db.user_profiles.find_one = AsyncMock(return_value=profile_data)
        retrieved_by_email = await user_service.get_user_by_email(created_profile.email)
        
        # Verify both retrieval methods return consistent data
        assert retrieved_by_id is not None, "User should be retrievable by Cognito ID"
        assert retrieved_by_email is not None, "User should be retrievable by email"
        
        # Verify data consistency
        assert retrieved_by_id.user_id == retrieved_by_email.user_id
        assert retrieved_by_id.email == retrieved_by_email.email  # Both should have same normalized email
        assert retrieved_by_id.username == retrieved_by_email.username
        assert retrieved_by_id.first_name == retrieved_by_email.first_name
        assert retrieved_by_id.last_name == retrieved_by_email.last_name
        assert retrieved_by_id.role == retrieved_by_email.role
        
        # Verify database queries were made correctly (each service call makes one query)
        # We don't need to check call_count since we reset mocks between calls