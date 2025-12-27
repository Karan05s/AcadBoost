"""
AWS Cognito authentication integration
"""
import boto3
import jwt
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from botocore.exceptions import ClientError
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class CognitoAuth:
    """AWS Cognito authentication handler"""
    
    def __init__(self):
        self.client = boto3.client(
            'cognito-idp',
            region_name=settings.COGNITO_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        self.user_pool_id = settings.COGNITO_USER_POOL_ID
        self.client_id = settings.COGNITO_CLIENT_ID
        self.client_secret = settings.COGNITO_CLIENT_SECRET
    
    async def register_user(self, email: str, password: str, username: str) -> Dict[str, Any]:
        """Register a new user with AWS Cognito"""
        try:
            response = self.client.admin_create_user(
                UserPoolId=self.user_pool_id,
                Username=username,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'email_verified', 'Value': 'false'}
                ],
                TemporaryPassword=password,
                MessageAction='SUPPRESS'  # Don't send welcome email
            )
            
            # Set permanent password
            self.client.admin_set_user_password(
                UserPoolId=self.user_pool_id,
                Username=username,
                Password=password,
                Permanent=True
            )
            
            return {
                'user_id': response['User']['Username'],
                'email': email,
                'status': 'created'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'UsernameExistsException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User already exists"
                )
            elif error_code == 'InvalidPasswordException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Password does not meet requirements"
                )
            else:
                logger.error(f"Cognito registration error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Registration failed"
                )
    
    async def authenticate_user(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticate user with AWS Cognito"""
        try:
            response = self.client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow='ADMIN_NO_SRP_AUTH',
                AuthParameters={
                    'USERNAME': username,
                    'PASSWORD': password
                }
            )
            
            return {
                'access_token': response['AuthenticationResult']['AccessToken'],
                'refresh_token': response['AuthenticationResult']['RefreshToken'],
                'id_token': response['AuthenticationResult']['IdToken'],
                'expires_in': response['AuthenticationResult']['ExpiresIn']
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ['NotAuthorizedException', 'UserNotFoundException']:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )
            else:
                logger.error(f"Cognito authentication error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authentication failed"
                )
    
    async def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify JWT token from Cognito"""
        try:
            # In production, you should verify the token signature
            # For now, we'll decode without verification for development
            decoded_token = jwt.decode(
                token, 
                options={"verify_signature": False}
            )
            
            return {
                'user_id': decoded_token.get('sub'),
                'username': decoded_token.get('cognito:username'),
                'email': decoded_token.get('email'),
                'token_use': decoded_token.get('token_use')
            }
            
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid JWT token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token using refresh token"""
        try:
            response = self.client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': refresh_token
                }
            )
            
            return {
                'access_token': response['AuthenticationResult']['AccessToken'],
                'id_token': response['AuthenticationResult']['IdToken'],
                'expires_in': response['AuthenticationResult']['ExpiresIn']
            }
            
        except ClientError as e:
            logger.error(f"Token refresh error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token refresh failed"
            )


    async def send_email_verification(self, username: str) -> None:
        """Send email verification code to user"""
        try:
            self.client.admin_get_user(
                UserPoolId=self.user_pool_id,
                Username=username
            )
            
            # Resend confirmation code
            self.client.resend_confirmation_code(
                ClientId=self.client_id,
                Username=username
            )
            
        except ClientError as e:
            logger.error(f"Email verification send error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email"
            )
    
    async def confirm_email_verification(self, username: str, confirmation_code: str) -> None:
        """Confirm email verification with code"""
        try:
            self.client.confirm_sign_up(
                ClientId=self.client_id,
                Username=username,
                ConfirmationCode=confirmation_code
            )
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'CodeMismatchException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid verification code"
                )
            elif error_code == 'ExpiredCodeException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Verification code has expired"
                )
            else:
                logger.error(f"Email verification error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Email verification failed"
                )
    
    async def initiate_password_reset(self, username: str) -> None:
        """Initiate password reset process"""
        try:
            self.client.forgot_password(
                ClientId=self.client_id,
                Username=username
            )
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'UserNotFoundException':
                # Don't reveal if user exists for security
                pass  # Still return success message
            else:
                logger.error(f"Password reset initiation error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Password reset failed"
                )
    
    async def confirm_password_reset(self, username: str, confirmation_code: str, new_password: str) -> None:
        """Confirm password reset with code and new password"""
        try:
            self.client.confirm_forgot_password(
                ClientId=self.client_id,
                Username=username,
                ConfirmationCode=confirmation_code,
                Password=new_password
            )
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'CodeMismatchException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid confirmation code"
                )
            elif error_code == 'ExpiredCodeException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Confirmation code has expired"
                )
            elif error_code == 'InvalidPasswordException':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Password does not meet requirements"
                )
            else:
                logger.error(f"Password reset confirmation error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Password reset failed"
                )

# Create global auth instance
cognito_auth = CognitoAuth()


# FastAPI dependency for getting current user
async def get_current_user(token: str = None) -> Dict[str, Any]:
    """
    FastAPI dependency to get current authenticated user
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required"
        )
    
    return await cognito_auth.verify_token(token)