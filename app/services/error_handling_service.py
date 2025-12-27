"""
Enhanced error handling and data integrity service
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import json
import hashlib

logger = logging.getLogger(__name__)


class ErrorHandlingService:
    """Service for advanced error handling and data integrity management"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def handle_submission_error(self, error: Exception, submission_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle submission processing errors with recovery strategies
        
        Requirements: 1.4 - Handle missing or corrupted submissions gracefully
        """
        try:
            error_info = {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "timestamp": datetime.utcnow(),
                "submission_data": submission_data,
                "recovery_attempted": False,
                "recovery_successful": False
            }
            
            # Attempt recovery based on error type
            if isinstance(error, ValueError):
                recovery_result = await self._handle_validation_error(error, submission_data)
            elif isinstance(error, KeyError):
                recovery_result = await self._handle_missing_field_error(error, submission_data)
            elif isinstance(error, TypeError):
                recovery_result = await self._handle_type_error(error, submission_data)
            else:
                recovery_result = await self._handle_generic_error(error, submission_data)
            
            error_info.update(recovery_result)
            
            # Log the error and recovery attempt
            await self._log_error_event(error_info)
            
            return error_info
            
        except Exception as e:
            logger.error(f"Error in error handling: {e}")
            return {
                "error_type": "ErrorHandlingFailure",
                "error_message": f"Failed to handle original error: {str(e)}",
                "timestamp": datetime.utcnow(),
                "recovery_attempted": False,
                "recovery_successful": False
            }
    
    async def _handle_validation_error(self, error: ValueError, submission_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle validation errors with data correction attempts"""
        recovery_info = {
            "recovery_attempted": True,
            "recovery_strategy": "validation_correction",
            "corrections_made": []
        }
        
        try:
            # Attempt to correct common validation issues
            corrected_data = submission_data.copy()
            
            # Fix missing required fields with defaults
            if "student_id" not in corrected_data or not corrected_data["student_id"]:
                corrected_data["student_id"] = "unknown_student"
                recovery_info["corrections_made"].append("Added default student_id")
            
            if "timestamp" not in corrected_data:
                corrected_data["timestamp"] = datetime.utcnow()
                recovery_info["corrections_made"].append("Added current timestamp")
            
            # Fix invalid score values
            if "score" in corrected_data:
                try:
                    score = float(corrected_data["score"])
                    if score < 0:
                        corrected_data["score"] = 0
                        recovery_info["corrections_made"].append("Corrected negative score to 0")
                except (ValueError, TypeError):
                    corrected_data["score"] = 0
                    recovery_info["corrections_made"].append("Replaced invalid score with 0")
            
            # Fix invalid max_score values
            if "max_score" in corrected_data:
                try:
                    max_score = float(corrected_data["max_score"])
                    if max_score <= 0:
                        corrected_data["max_score"] = 1
                        recovery_info["corrections_made"].append("Corrected invalid max_score to 1")
                except (ValueError, TypeError):
                    corrected_data["max_score"] = 1
                    recovery_info["corrections_made"].append("Replaced invalid max_score with 1")
            
            recovery_info["corrected_data"] = corrected_data
            recovery_info["recovery_successful"] = len(recovery_info["corrections_made"]) > 0
            
        except Exception as e:
            logger.error(f"Error in validation error recovery: {e}")
            recovery_info["recovery_successful"] = False
            recovery_info["recovery_error"] = str(e)
        
        return recovery_info
    
    async def _handle_missing_field_error(self, error: KeyError, submission_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle missing field errors"""
        recovery_info = {
            "recovery_attempted": True,
            "recovery_strategy": "missing_field_correction",
            "missing_field": str(error).strip("'\""),
            "corrections_made": []
        }
        
        try:
            corrected_data = submission_data.copy()
            missing_field = recovery_info["missing_field"]
            
            # Provide defaults for common missing fields
            field_defaults = {
                "student_id": "unknown_student",
                "course_id": "unknown_course",
                "assignment_id": "unknown_assignment",
                "submission_type": "unknown",
                "timestamp": datetime.utcnow(),
                "score": 0,
                "max_score": 1,
                "question_responses": [],
                "code_content": "",
                "metadata": {}
            }
            
            if missing_field in field_defaults:
                corrected_data[missing_field] = field_defaults[missing_field]
                recovery_info["corrections_made"].append(f"Added default value for {missing_field}")
                recovery_info["recovery_successful"] = True
            else:
                recovery_info["recovery_successful"] = False
                recovery_info["recovery_error"] = f"No default available for field: {missing_field}"
            
            recovery_info["corrected_data"] = corrected_data
            
        except Exception as e:
            logger.error(f"Error in missing field recovery: {e}")
            recovery_info["recovery_successful"] = False
            recovery_info["recovery_error"] = str(e)
        
        return recovery_info
    
    async def _handle_type_error(self, error: TypeError, submission_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle type conversion errors"""
        recovery_info = {
            "recovery_attempted": True,
            "recovery_strategy": "type_correction",
            "corrections_made": []
        }
        
        try:
            corrected_data = submission_data.copy()
            
            # Attempt to fix common type issues
            for field, value in corrected_data.items():
                if field in ["score", "max_score"] and not isinstance(value, (int, float)):
                    try:
                        corrected_data[field] = float(value)
                        recovery_info["corrections_made"].append(f"Converted {field} to float")
                    except (ValueError, TypeError):
                        corrected_data[field] = 0.0
                        recovery_info["corrections_made"].append(f"Reset {field} to 0.0 due to conversion error")
                
                elif field == "timestamp" and not isinstance(value, datetime):
                    if isinstance(value, str):
                        try:
                            corrected_data[field] = datetime.fromisoformat(value)
                            recovery_info["corrections_made"].append("Converted timestamp string to datetime")
                        except ValueError:
                            corrected_data[field] = datetime.utcnow()
                            recovery_info["corrections_made"].append("Reset timestamp to current time")
                    else:
                        corrected_data[field] = datetime.utcnow()
                        recovery_info["corrections_made"].append("Reset timestamp to current time")
            
            recovery_info["corrected_data"] = corrected_data
            recovery_info["recovery_successful"] = len(recovery_info["corrections_made"]) > 0
            
        except Exception as e:
            logger.error(f"Error in type error recovery: {e}")
            recovery_info["recovery_successful"] = False
            recovery_info["recovery_error"] = str(e)
        
        return recovery_info
    
    async def _handle_generic_error(self, error: Exception, submission_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle generic errors with basic recovery"""
        recovery_info = {
            "recovery_attempted": True,
            "recovery_strategy": "generic_fallback",
            "recovery_successful": False
        }
        
        try:
            # For generic errors, attempt to create a minimal valid submission
            minimal_submission = {
                "student_id": submission_data.get("student_id", "error_recovery_student"),
                "course_id": submission_data.get("course_id", "error_recovery_course"),
                "assignment_id": submission_data.get("assignment_id", "error_recovery_assignment"),
                "submission_type": submission_data.get("submission_type", "unknown"),
                "timestamp": datetime.utcnow(),
                "score": 0,
                "max_score": 1,
                "metadata": {
                    "error_recovery": True,
                    "original_error": str(error),
                    "recovery_timestamp": datetime.utcnow().isoformat()
                }
            }
            
            recovery_info["corrected_data"] = minimal_submission
            recovery_info["recovery_successful"] = True
            recovery_info["corrections_made"] = ["Created minimal valid submission for error recovery"]
            
        except Exception as e:
            logger.error(f"Error in generic error recovery: {e}")
            recovery_info["recovery_error"] = str(e)
        
        return recovery_info
    
    async def _log_error_event(self, error_info: Dict[str, Any]) -> None:
        """Log error events to database for analysis"""
        try:
            # Create error log entry
            error_log = {
                "timestamp": error_info["timestamp"],
                "error_type": error_info["error_type"],
                "error_message": error_info["error_message"],
                "recovery_attempted": error_info["recovery_attempted"],
                "recovery_successful": error_info.get("recovery_successful", False),
                "recovery_strategy": error_info.get("recovery_strategy"),
                "corrections_made": error_info.get("corrections_made", []),
                "submission_hash": self._hash_submission_data(error_info.get("submission_data", {}))
            }
            
            # Store in error_logs collection
            await self.db.error_logs.insert_one(error_log)
            
        except Exception as e:
            logger.error(f"Failed to log error event: {e}")
    
    def _hash_submission_data(self, submission_data: Dict[str, Any]) -> str:
        """Create a hash of submission data for privacy-preserving logging"""
        try:
            # Remove sensitive data and create hash
            safe_data = {
                "submission_type": submission_data.get("submission_type"),
                "has_student_id": bool(submission_data.get("student_id")),
                "has_course_id": bool(submission_data.get("course_id")),
                "data_size": len(str(submission_data))
            }
            
            data_string = json.dumps(safe_data, sort_keys=True)
            return hashlib.sha256(data_string.encode()).hexdigest()[:16]
            
        except Exception:
            return "hash_error"
    
    async def detect_data_corruption(self, submission_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect potential data corruption in submissions
        
        Requirements: 1.4 - Validate data integrity and handle corrupted submissions
        """
        try:
            corruption_report = {
                "is_corrupted": False,
                "corruption_indicators": [],
                "severity": "none",
                "recommended_action": "accept"
            }
            
            # Check for various corruption indicators
            
            # 1. Impossible score values
            if "score" in submission_data and "max_score" in submission_data:
                try:
                    score = float(submission_data["score"])
                    max_score = float(submission_data["max_score"])
                    
                    if score > max_score:
                        corruption_report["corruption_indicators"].append("Score exceeds maximum possible score")
                    if score < 0:
                        corruption_report["corruption_indicators"].append("Negative score value")
                    if max_score <= 0:
                        corruption_report["corruption_indicators"].append("Invalid maximum score")
                        
                except (ValueError, TypeError):
                    corruption_report["corruption_indicators"].append("Non-numeric score values")
            
            # 2. Timestamp anomalies
            if "timestamp" in submission_data:
                try:
                    if isinstance(submission_data["timestamp"], str):
                        timestamp = datetime.fromisoformat(submission_data["timestamp"])
                    else:
                        timestamp = submission_data["timestamp"]
                    
                    now = datetime.utcnow()
                    if timestamp > now + timedelta(hours=1):
                        corruption_report["corruption_indicators"].append("Future timestamp")
                    if timestamp < now - timedelta(days=365):
                        corruption_report["corruption_indicators"].append("Very old timestamp")
                        
                except (ValueError, TypeError):
                    corruption_report["corruption_indicators"].append("Invalid timestamp format")
            
            # 3. Empty or malformed content
            if submission_data.get("submission_type") == "quiz":
                responses = submission_data.get("question_responses", [])
                if not responses:
                    corruption_report["corruption_indicators"].append("Quiz submission with no responses")
                else:
                    for i, response in enumerate(responses):
                        if not isinstance(response, dict):
                            corruption_report["corruption_indicators"].append(f"Malformed response at index {i}")
                        elif not response.get("question_id"):
                            corruption_report["corruption_indicators"].append(f"Missing question_id at index {i}")
            
            elif submission_data.get("submission_type") == "code":
                code_content = submission_data.get("code_content", "")
                if not code_content or not code_content.strip():
                    corruption_report["corruption_indicators"].append("Code submission with empty content")
            
            # 4. Missing critical fields
            required_fields = ["student_id", "course_id", "assignment_id", "submission_type"]
            for field in required_fields:
                if field not in submission_data or not submission_data[field]:
                    corruption_report["corruption_indicators"].append(f"Missing required field: {field}")
            
            # Determine corruption severity and recommended action
            indicator_count = len(corruption_report["corruption_indicators"])
            
            if indicator_count == 0:
                corruption_report["severity"] = "none"
                corruption_report["recommended_action"] = "accept"
            elif indicator_count <= 2:
                corruption_report["severity"] = "low"
                corruption_report["recommended_action"] = "accept_with_correction"
                corruption_report["is_corrupted"] = True
            elif indicator_count <= 4:
                corruption_report["severity"] = "medium"
                corruption_report["recommended_action"] = "quarantine_for_review"
                corruption_report["is_corrupted"] = True
            else:
                corruption_report["severity"] = "high"
                corruption_report["recommended_action"] = "reject"
                corruption_report["is_corrupted"] = True
            
            return corruption_report
            
        except Exception as e:
            logger.error(f"Error detecting data corruption: {e}")
            return {
                "is_corrupted": True,
                "corruption_indicators": [f"Corruption detection failed: {str(e)}"],
                "severity": "high",
                "recommended_action": "reject"
            }
    
    async def implement_retry_logic(self, operation_func, max_retries: int = 3, delay_seconds: float = 1.0) -> Tuple[bool, Any, List[str]]:
        """
        Implement retry logic for database operations
        
        Requirements: 1.4 - Implement retry logic for database failures
        """
        retry_attempts = []
        last_error = None
        
        for attempt in range(max_retries):
            try:
                result = await operation_func()
                return True, result, retry_attempts
                
            except Exception as e:
                last_error = e
                retry_attempts.append(f"Attempt {attempt + 1}: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Wait before retrying (exponential backoff)
                    import asyncio
                    wait_time = delay_seconds * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    logger.warning(f"Retry attempt {attempt + 1} failed, waiting {wait_time}s before next attempt")
        
        # All retries failed
        logger.error(f"All {max_retries} retry attempts failed. Last error: {last_error}")
        return False, None, retry_attempts