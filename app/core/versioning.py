"""
API Versioning System
Handles API version management and backward compatibility
"""
from typing import Dict, Any, Optional, List
from fastapi import Request, HTTPException, status
from pydantic import BaseModel
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)


class APIVersion:
    """API Version representation"""
    
    def __init__(self, major: int, minor: int, patch: int = 0):
        self.major = major
        self.minor = minor
        self.patch = patch
    
    def __str__(self):
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __eq__(self, other):
        if not isinstance(other, APIVersion):
            return False
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    
    def __lt__(self, other):
        if not isinstance(other, APIVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __le__(self, other):
        return self == other or self < other
    
    def __gt__(self, other):
        return not self <= other
    
    def __ge__(self, other):
        return not self < other
    
    def is_compatible_with(self, other: 'APIVersion') -> bool:
        """Check if this version is backward compatible with another version"""
        # Same major version is compatible
        if self.major == other.major:
            return True
        
        # Major version differences are not compatible
        return False
    
    @classmethod
    def from_string(cls, version_str: str) -> 'APIVersion':
        """Parse version string like '1.2.3' or '1.2'"""
        pattern = r'^(\d+)\.(\d+)(?:\.(\d+))?$'
        match = re.match(pattern, version_str)
        
        if not match:
            raise ValueError(f"Invalid version format: {version_str}")
        
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3)) if match.group(3) else 0
        
        return cls(major, minor, patch)


class APIVersionManager:
    """Manages API versions and compatibility"""
    
    def __init__(self):
        self.supported_versions = {
            "1.0.0": {
                "version": APIVersion(1, 0, 0),
                "status": "current",
                "deprecated": False,
                "sunset_date": None,
                "features": [
                    "user_management",
                    "data_collection",
                    "analytics",
                    "recommendations",
                    "external_api"
                ]
            },
            "1.1.0": {
                "version": APIVersion(1, 1, 0),
                "status": "beta",
                "deprecated": False,
                "sunset_date": None,
                "features": [
                    "user_management",
                    "data_collection",
                    "analytics",
                    "recommendations",
                    "external_api",
                    "advanced_analytics",
                    "bulk_operations"
                ]
            }
        }
        self.current_version = APIVersion(1, 0, 0)
        self.minimum_supported_version = APIVersion(1, 0, 0)
    
    def get_version_from_request(self, request: Request) -> APIVersion:
        """Extract API version from request headers or path"""
        # Check Accept header for version
        accept_header = request.headers.get("accept", "")
        version_match = re.search(r'application/vnd\.learninganalytics\.v(\d+(?:\.\d+)?)', accept_header)
        
        if version_match:
            version_str = version_match.group(1)
            if "." not in version_str:
                version_str += ".0"
            return APIVersion.from_string(version_str)
        
        # Check custom header
        version_header = request.headers.get("X-API-Version")
        if version_header:
            return APIVersion.from_string(version_header)
        
        # Check path for version (e.g., /api/v1/...)
        path = request.url.path
        path_match = re.search(r'/api/v(\d+)', path)
        if path_match:
            major_version = int(path_match.group(1))
            return APIVersion(major_version, 0, 0)
        
        # Default to current version
        return self.current_version
    
    def validate_version(self, requested_version: APIVersion) -> Dict[str, Any]:
        """Validate if requested version is supported"""
        version_str = str(requested_version)
        
        # Check if exact version is supported
        if version_str in self.supported_versions:
            version_info = self.supported_versions[version_str]
            return {
                "valid": True,
                "version": requested_version,
                "status": version_info["status"],
                "deprecated": version_info["deprecated"],
                "sunset_date": version_info["sunset_date"],
                "features": version_info["features"]
            }
        
        # Check for compatible version
        compatible_version = self._find_compatible_version(requested_version)
        if compatible_version:
            version_info = self.supported_versions[str(compatible_version)]
            return {
                "valid": True,
                "version": compatible_version,
                "requested_version": requested_version,
                "status": version_info["status"],
                "deprecated": version_info["deprecated"],
                "sunset_date": version_info["sunset_date"],
                "features": version_info["features"],
                "compatibility_note": f"Requested version {requested_version} mapped to compatible version {compatible_version}"
            }
        
        # Version not supported
        return {
            "valid": False,
            "version": requested_version,
            "error": f"API version {requested_version} is not supported",
            "supported_versions": list(self.supported_versions.keys()),
            "minimum_version": str(self.minimum_supported_version),
            "current_version": str(self.current_version)
        }
    
    def _find_compatible_version(self, requested_version: APIVersion) -> Optional[APIVersion]:
        """Find a compatible version for the requested version"""
        compatible_versions = []
        
        for version_str, version_info in self.supported_versions.items():
            supported_version = version_info["version"]
            if supported_version.is_compatible_with(requested_version):
                compatible_versions.append(supported_version)
        
        # Return the highest compatible version
        if compatible_versions:
            return max(compatible_versions)
        
        return None
    
    def get_deprecation_warnings(self, version: APIVersion) -> List[str]:
        """Get deprecation warnings for a version"""
        warnings = []
        version_str = str(version)
        
        if version_str in self.supported_versions:
            version_info = self.supported_versions[version_str]
            
            if version_info["deprecated"]:
                warnings.append(f"API version {version} is deprecated")
                
                if version_info["sunset_date"]:
                    warnings.append(f"This version will be sunset on {version_info['sunset_date']}")
            
            if version < self.current_version:
                warnings.append(f"You are using an older API version. Current version is {self.current_version}")
        
        return warnings
    
    def add_version_headers(self, response_headers: Dict[str, str], version: APIVersion):
        """Add version-related headers to response"""
        response_headers["X-API-Version"] = str(version)
        response_headers["X-API-Current-Version"] = str(self.current_version)
        response_headers["X-API-Minimum-Version"] = str(self.minimum_supported_version)
        
        # Add deprecation warnings
        warnings = self.get_deprecation_warnings(version)
        if warnings:
            response_headers["X-API-Deprecation-Warning"] = "; ".join(warnings)


class VersionedResponse(BaseModel):
    """Standard versioned API response"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    api_version: str
    timestamp: datetime = datetime.utcnow()
    warnings: Optional[List[str]] = None


# Global version manager instance
version_manager = APIVersionManager()


def get_api_version(request: Request) -> APIVersion:
    """Dependency to get API version from request"""
    return version_manager.get_version_from_request(request)


def validate_api_version(request: Request) -> Dict[str, Any]:
    """Dependency to validate API version"""
    requested_version = version_manager.get_version_from_request(request)
    validation_result = version_manager.validate_version(requested_version)
    
    if not validation_result["valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation_result["error"],
            headers={
                "X-API-Supported-Versions": ", ".join(validation_result["supported_versions"]),
                "X-API-Current-Version": validation_result["current_version"],
                "X-API-Minimum-Version": validation_result["minimum_version"]
            }
        )
    
    return validation_result


def create_versioned_response(
    success: bool,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    version: Optional[APIVersion] = None,
    warnings: Optional[List[str]] = None
) -> VersionedResponse:
    """Create a standardized versioned response"""
    if version is None:
        version = version_manager.current_version
    
    # Add version-specific warnings
    version_warnings = version_manager.get_deprecation_warnings(version)
    all_warnings = (warnings or []) + version_warnings
    
    return VersionedResponse(
        success=success,
        message=message,
        data=data,
        api_version=str(version),
        warnings=all_warnings if all_warnings else None
    )