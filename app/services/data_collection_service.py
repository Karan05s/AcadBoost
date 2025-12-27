"""
Data Collection Service for quiz and code submissions
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.performance import (
    PerformanceSubmission, QuizSubmissionRequest, CodeSubmissionRequest,
    SubmissionResponse, SubmissionType, CodeMetrics, DataValidationError
)
from app.services.code_analysis_service import CodeAnalysisService
from app.services.error_handling_service import ErrorHandlingService

logger = logging.getLogger(__name__)


class DataCollectionService:
    """Service for collecting and processing student performance data"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.code_analyzer = CodeAnalysisService()
        self.error_handler = ErrorHandlingService(db)
    
    async def process_quiz_submission(self, submission: QuizSubmissionRequest) -> SubmissionResponse:
        """
        Process a quiz submission and store performance data
        
        Requirements: 1.1, 1.3
        """
        try:
            # Validate submission data
            validation_errors = await self._validate_quiz_submission(submission)
            if validation_errors:
                raise ValueError(f"Validation errors: {validation_errors}")
            
            # Check for data corruption
            submission_dict = submission.dict()
            corruption_report = await self.error_handler.detect_data_corruption(submission_dict)
            
            if corruption_report["is_corrupted"] and corruption_report["recommended_action"] == "reject":
                raise ValueError(f"Submission rejected due to data corruption: {corruption_report['corruption_indicators']}")
            
            # Calculate quiz score
            total_questions = len(submission.question_responses)
            correct_answers = sum(1 for response in submission.question_responses if response.correct)
            score = correct_answers
            max_score = total_questions
            
            # Create performance submission record
            performance_data = PerformanceSubmission(
                student_id=submission.student_id,
                submission_type=SubmissionType.QUIZ,
                course_id=submission.course_id,
                assignment_id=submission.assignment_id,
                score=score,
                max_score=max_score,
                question_responses=submission.question_responses,
                metadata={
                    "total_time_spent": submission.total_time_spent,
                    "accuracy_rate": score / max_score if max_score > 0 else 0,
                    "concept_tags": self._extract_concept_tags(submission.question_responses),
                    "corruption_report": corruption_report if corruption_report["is_corrupted"] else None
                }
            )
            
            # Store in database with retry logic
            async def store_operation():
                return await self.db.student_performance.insert_one(performance_data.dict())
            
            success, result, retry_attempts = await self.error_handler.implement_retry_logic(store_operation)
            
            if not success:
                raise RuntimeError(f"Failed to store submission after retries: {retry_attempts}")
            
            submission_id = str(result.inserted_id)
            
            logger.info(f"Quiz submission processed for student {submission.student_id}, score: {score}/{max_score}")
            
            return SubmissionResponse(
                submission_id=submission_id,
                student_id=submission.student_id,
                submission_type=SubmissionType.QUIZ,
                score=score,
                max_score=max_score,
                timestamp=performance_data.timestamp
            )
            
        except Exception as e:
            # Use enhanced error handling
            error_info = await self.error_handler.handle_submission_error(e, submission.dict())
            
            # If recovery was successful, try to process the corrected data
            if error_info.get("recovery_successful") and "corrected_data" in error_info:
                try:
                    corrected_submission = QuizSubmissionRequest(**error_info["corrected_data"])
                    logger.info(f"Attempting to process corrected quiz submission for student {submission.student_id}")
                    return await self.process_quiz_submission(corrected_submission)
                except Exception as recovery_error:
                    logger.error(f"Recovery attempt failed: {recovery_error}")
            
            logger.error(f"Error processing quiz submission for student {submission.student_id}: {e}")
            raise
    
    async def process_code_submission(self, submission: CodeSubmissionRequest) -> SubmissionResponse:
        """
        Process a code submission and analyze for correctness and efficiency
        
        Requirements: 1.2, 1.4
        """
        try:
            # Validate submission data
            validation_errors = await self._validate_code_submission(submission)
            if validation_errors:
                raise ValueError(f"Validation errors: {validation_errors}")
            
            # Check for data corruption
            submission_dict = submission.dict()
            corruption_report = await self.error_handler.detect_data_corruption(submission_dict)
            
            if corruption_report["is_corrupted"] and corruption_report["recommended_action"] == "reject":
                raise ValueError(f"Submission rejected due to data corruption: {corruption_report['corruption_indicators']}")
            
            # Analyze code submission
            code_metrics = await self._analyze_code_submission(submission)
            
            # Calculate score based on test results and code quality
            score, max_score = self._calculate_code_score(code_metrics, submission.test_results)
            
            # Create performance submission record
            performance_data = PerformanceSubmission(
                student_id=submission.student_id,
                submission_type=SubmissionType.CODE,
                course_id=submission.course_id,
                assignment_id=submission.assignment_id,
                score=score,
                max_score=max_score,
                code_content=submission.code_content,
                code_metrics=code_metrics,
                metadata={
                    "language": submission.language,
                    "code_length": len(submission.code_content),
                    "test_results": submission.test_results,
                    "corruption_report": corruption_report if corruption_report["is_corrupted"] else None
                }
            )
            
            # Store in database with retry logic
            async def store_operation():
                return await self.db.student_performance.insert_one(performance_data.dict())
            
            success, result, retry_attempts = await self.error_handler.implement_retry_logic(store_operation)
            
            if not success:
                raise RuntimeError(f"Failed to store submission after retries: {retry_attempts}")
            
            submission_id = str(result.inserted_id)
            
            logger.info(f"Code submission processed for student {submission.student_id}, score: {score}/{max_score}")
            
            return SubmissionResponse(
                submission_id=submission_id,
                student_id=submission.student_id,
                submission_type=SubmissionType.CODE,
                score=score,
                max_score=max_score,
                timestamp=performance_data.timestamp
            )
            
        except Exception as e:
            # Use enhanced error handling
            error_info = await self.error_handler.handle_submission_error(e, submission.dict())
            
            # If recovery was successful, try to process the corrected data
            if error_info.get("recovery_successful") and "corrected_data" in error_info:
                try:
                    corrected_submission = CodeSubmissionRequest(**error_info["corrected_data"])
                    logger.info(f"Attempting to process corrected code submission for student {submission.student_id}")
                    return await self.process_code_submission(corrected_submission)
                except Exception as recovery_error:
                    logger.error(f"Recovery attempt failed: {recovery_error}")
            
            logger.error(f"Error processing code submission for student {submission.student_id}: {e}")
            raise
    
    async def get_student_performance(self, student_id: str, course_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve performance data for a student
        
        Requirements: 1.3
        """
        try:
            query = {"student_id": student_id}
            if course_id:
                query["course_id"] = course_id
            
            cursor = self.db.student_performance.find(query).sort("timestamp", -1)
            performance_data = await cursor.to_list(length=None)
            
            # Convert ObjectId to string for JSON serialization
            for record in performance_data:
                record["_id"] = str(record["_id"])
            
            return performance_data
            
        except Exception as e:
            logger.error(f"Error retrieving performance data for student {student_id}: {e}")
            raise
    
    async def update_submission(self, submission_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update an existing submission record
        
        Requirements: 1.4
        """
        try:
            from bson import ObjectId
            
            # Add update timestamp
            updates["updated_at"] = datetime.utcnow()
            
            result = await self.db.student_performance.update_one(
                {"_id": ObjectId(submission_id)},
                {"$set": updates}
            )
            
            if result.modified_count > 0:
                logger.info(f"Submission {submission_id} updated successfully")
                return True
            else:
                logger.warning(f"No submission found with id {submission_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating submission {submission_id}: {e}")
            raise
    
    async def _validate_quiz_submission(self, submission: QuizSubmissionRequest) -> List[DataValidationError]:
        """Validate quiz submission data"""
        errors = []
        
        # Check required fields
        if not submission.student_id:
            errors.append(DataValidationError(field="student_id", error="Required field", value=submission.student_id))
        
        if not submission.course_id:
            errors.append(DataValidationError(field="course_id", error="Required field", value=submission.course_id))
        
        if not submission.assignment_id:
            errors.append(DataValidationError(field="assignment_id", error="Required field", value=submission.assignment_id))
        
        if not submission.question_responses:
            errors.append(DataValidationError(field="question_responses", error="At least one response required", value=submission.question_responses))
        
        # Validate question responses
        for i, response in enumerate(submission.question_responses or []):
            if not response.question_id:
                errors.append(DataValidationError(field=f"question_responses[{i}].question_id", error="Required field", value=response.question_id))
            
            if response.response is None or response.response == "":
                errors.append(DataValidationError(field=f"question_responses[{i}].response", error="Response cannot be empty", value=response.response))
        
        return errors
    
    async def _validate_code_submission(self, submission: CodeSubmissionRequest) -> List[DataValidationError]:
        """Validate code submission data"""
        errors = []
        
        # Check required fields
        if not submission.student_id:
            errors.append(DataValidationError(field="student_id", error="Required field", value=submission.student_id))
        
        if not submission.course_id:
            errors.append(DataValidationError(field="course_id", error="Required field", value=submission.course_id))
        
        if not submission.assignment_id:
            errors.append(DataValidationError(field="assignment_id", error="Required field", value=submission.assignment_id))
        
        if not submission.code_content or submission.code_content.strip() == "":
            errors.append(DataValidationError(field="code_content", error="Code content cannot be empty", value=submission.code_content))
        
        # Validate language
        supported_languages = ["python", "javascript", "java", "cpp", "c"]
        if submission.language not in supported_languages:
            errors.append(DataValidationError(field="language", error=f"Unsupported language. Supported: {supported_languages}", value=submission.language))
        
        return errors
    
    async def _analyze_code_submission(self, submission: CodeSubmissionRequest) -> CodeMetrics:
        """
        Analyze code submission for metrics using enhanced code analysis service
        
        Requirements: 1.2 - Analyze code for correctness, efficiency, and concept understanding
        """
        try:
            # Use the enhanced code analysis service
            code_metrics = await self.code_analyzer.analyze_code_submission(
                code=submission.code_content,
                language=submission.language,
                test_results=submission.test_results
            )
            
            # Assess concept understanding
            concept_analysis = await self.code_analyzer.assess_concept_understanding(
                code=submission.code_content,
                language=submission.language
            )
            
            # Store concept analysis in metadata for later use
            if hasattr(code_metrics, 'metadata'):
                code_metrics.metadata = concept_analysis
            
            return code_metrics
            
        except Exception as e:
            logger.error(f"Error in enhanced code analysis: {e}")
            # Fallback to basic analysis
            return await self._basic_code_analysis(submission)
    
    def _calculate_code_score(self, metrics: CodeMetrics, test_results: Optional[Dict[str, Any]]) -> tuple[float, float]:
        """Calculate score for code submission based on metrics and test results"""
        max_score = 100.0
        score = 0.0
        
        # Test passing score (60% of total)
        if metrics.total_tests > 0:
            test_score = (metrics.passed_tests / metrics.total_tests) * 60
            score += test_score
        
        # Code quality score (40% of total)
        quality_score = 40.0
        
        # Deduct for errors
        if metrics.syntax_errors > 0:
            quality_score -= min(20, metrics.syntax_errors * 5)
        
        if metrics.runtime_errors > 0:
            quality_score -= min(10, metrics.runtime_errors * 2)
        
        # Bonus for good test coverage
        if metrics.test_coverage and metrics.test_coverage > 0.8:
            quality_score += 5
        
        score += max(0, quality_score)
        
        return min(score, max_score), max_score
    
    def _extract_concept_tags(self, responses: List) -> List[str]:
        """Extract unique concept tags from question responses"""
        concept_tags = set()
        for response in responses:
            if hasattr(response, 'concept_tags') and response.concept_tags:
                concept_tags.update(response.concept_tags)
        return list(concept_tags)
    
    async def validate_data_integrity(self, submission_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate data integrity and handle corrupted submissions
        
        Requirements: 1.4
        """
        try:
            integrity_report = {
                "valid": True,
                "errors": [],
                "warnings": [],
                "corrected_fields": []
            }
            
            # Check for required fields
            required_fields = ["student_id", "course_id", "assignment_id", "submission_type"]
            for field in required_fields:
                if field not in submission_data or not submission_data[field]:
                    integrity_report["valid"] = False
                    integrity_report["errors"].append(f"Missing required field: {field}")
            
            # Check timestamp validity
            if "timestamp" in submission_data:
                try:
                    if isinstance(submission_data["timestamp"], str):
                        datetime.fromisoformat(submission_data["timestamp"])
                except ValueError:
                    integrity_report["warnings"].append("Invalid timestamp format, using current time")
                    submission_data["timestamp"] = datetime.utcnow()
                    integrity_report["corrected_fields"].append("timestamp")
            
            # Check score validity
            if "score" in submission_data and "max_score" in submission_data:
                score = submission_data["score"]
                max_score = submission_data["max_score"]
                
                if score < 0:
                    integrity_report["warnings"].append("Negative score corrected to 0")
                    submission_data["score"] = 0
                    integrity_report["corrected_fields"].append("score")
                
                if score > max_score:
                    integrity_report["warnings"].append("Score exceeds max_score, capped to max_score")
                    submission_data["score"] = max_score
                    integrity_report["corrected_fields"].append("score")
            
            return integrity_report
            
        except Exception as e:
            logger.error(f"Error validating data integrity: {e}")
            return {
                "valid": False,
                "errors": [f"Integrity validation failed: {str(e)}"],
                "warnings": [],
                "corrected_fields": []
            }
    
    async def _basic_code_analysis(self, submission: CodeSubmissionRequest) -> CodeMetrics:
        """
        Basic code analysis fallback method
        """
        code = submission.code_content
        test_results = submission.test_results or {}
        
        # Basic code analysis
        lines = code.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        
        # Simple complexity calculation (number of control structures)
        complexity = 1  # Base complexity
        control_keywords = ['if', 'elif', 'else', 'for', 'while', 'try', 'except', 'with']
        for line in non_empty_lines:
            for keyword in control_keywords:
                if keyword in line:
                    complexity += 1
        
        # Extract test results
        passed_tests = test_results.get("passed", 0)
        total_tests = test_results.get("total", 0)
        test_coverage = test_results.get("coverage", 0.0)
        execution_time = test_results.get("execution_time", 0.0)
        
        # Count syntax and runtime errors
        syntax_errors = test_results.get("syntax_errors", 0)
        runtime_errors = test_results.get("runtime_errors", 0)
        
        return CodeMetrics(
            complexity=complexity,
            test_coverage=test_coverage,
            execution_time=execution_time,
            memory_usage=len(code.encode('utf-8')),  # Approximate memory usage
            syntax_errors=syntax_errors,
            runtime_errors=runtime_errors,
            passed_tests=passed_tests,
            total_tests=total_tests
        )
    async def update_grade_from_lms(
        self,
        student_id: str,
        assignment_id: str,
        score: float,
        max_score: float
    ):
        """Update grade from LMS webhook"""
        try:
            # Find existing submission or create new one
            existing_submission = await self.collection.find_one({
                "student_id": student_id,
                "assignment_id": assignment_id
            })
            
            if existing_submission:
                # Update existing submission
                await self.collection.update_one(
                    {"_id": existing_submission["_id"]},
                    {
                        "$set": {
                            "score": score,
                            "max_score": max_score,
                            "updated_at": datetime.utcnow(),
                            "source": "lms_webhook"
                        }
                    }
                )
            else:
                # Create new submission record
                submission_data = {
                    "student_id": student_id,
                    "assignment_id": assignment_id,
                    "submission_type": "lms_grade",
                    "score": score,
                    "max_score": max_score,
                    "timestamp": datetime.utcnow(),
                    "source": "lms_webhook",
                    "question_responses": [],
                    "code_metrics": {}
                }
                
                await self.collection.insert_one(submission_data)
            
            logger.info(f"Updated LMS grade for student {student_id}, assignment {assignment_id}")
            
        except Exception as e:
            logger.error(f"Error updating LMS grade: {e}")
            raise
    
    async def process_lms_submission(
        self,
        student_id: str,
        assignment_id: str,
        submission_data: Dict[str, Any]
    ):
        """Process submission from LMS webhook"""
        try:
            # Determine submission type
            submission_type = submission_data.get("type", "assignment")
            
            # Create submission record
            submission_record = {
                "student_id": student_id,
                "assignment_id": assignment_id,
                "submission_type": submission_type,
                "timestamp": datetime.utcnow(),
                "source": "lms_webhook",
                "raw_data": submission_data
            }
            
            # Process based on type
            if submission_type == "quiz":
                submission_record.update({
                    "score": submission_data.get("score", 0),
                    "max_score": submission_data.get("max_score", 100),
                    "question_responses": submission_data.get("responses", [])
                })
            elif submission_type == "code":
                submission_record.update({
                    "code_content": submission_data.get("code", ""),
                    "language": submission_data.get("language", "unknown"),
                    "score": submission_data.get("score", 0),
                    "max_score": submission_data.get("max_score", 100)
                })
            
            await self.collection.insert_one(submission_record)
            
            logger.info(f"Processed LMS submission for student {student_id}")
            
        except Exception as e:
            logger.error(f"Error processing LMS submission: {e}")
            raise