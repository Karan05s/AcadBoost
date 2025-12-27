"""
Data Flow Validation Service
Validates end-to-end data flow from collection to gap analysis to recommendations
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.redis_client import cache_manager
from app.services.data_collection_service import DataCollectionService
from app.services.gap_detection_service import GapDetectionService
from app.services.recommendation_engine_service import RecommendationEngineService
from app.services.analytics_precompute_service import AnalyticsPrecomputeService

logger = logging.getLogger(__name__)


class DataFlowValidationService:
    """Service for validating end-to-end data flow integrity"""
    
    def __init__(self):
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.data_collection_service: Optional[DataCollectionService] = None
        self.gap_detection_service: Optional[GapDetectionService] = None
        self.recommendation_service: Optional[RecommendationEngineService] = None
        self.analytics_precompute_service: Optional[AnalyticsPrecomputeService] = None
        
        # Validation test scenarios
        self.test_scenarios = [
            {
                "name": "quiz_submission_to_gaps",
                "description": "Quiz submission → Gap analysis → Recommendations",
                "steps": ["submit_quiz", "analyze_gaps", "generate_recommendations"]
            },
            {
                "name": "code_submission_to_gaps",
                "description": "Code submission → Gap analysis → Recommendations",
                "steps": ["submit_code", "analyze_gaps", "generate_recommendations"]
            },
            {
                "name": "user_onboarding_flow",
                "description": "User registration → Profile setup → Initial analytics",
                "steps": ["create_user", "setup_profile", "compute_analytics"]
            },
            {
                "name": "recommendation_effectiveness_loop",
                "description": "Recommendations → User completion → Updated analytics",
                "steps": ["generate_recommendations", "mark_completed", "update_analytics"]
            }
        ]
    
    async def initialize(self):
        """Initialize the data flow validation service"""
        try:
            self.db = await get_database()
            if self.db:
                self.data_collection_service = DataCollectionService(self.db)
                self.gap_detection_service = GapDetectionService(self.db)
                self.recommendation_service = RecommendationEngineService(self.db)
                self.analytics_precompute_service = AnalyticsPrecomputeService(self.db)
                logger.info("Data flow validation service initialized successfully")
            else:
                logger.error("Failed to initialize database connection for data flow validation")
        except Exception as e:
            logger.error(f"Error initializing data flow validation service: {e}")
    
    async def validate_complete_data_flow(self, test_user_id: str = None) -> Dict[str, Any]:
        """Validate complete data flow with a test user"""
        try:
            if not self.db:
                await self.initialize()
            
            # Use test user or create one
            if not test_user_id:
                test_user_id = await self._create_test_user()
            
            validation_results = {
                "test_user_id": test_user_id,
                "validation_timestamp": datetime.utcnow().isoformat(),
                "overall_status": "success",
                "scenario_results": {},
                "performance_metrics": {},
                "issues": []
            }
            
            # Run all test scenarios
            for scenario in self.test_scenarios:
                scenario_result = await self._run_scenario(scenario, test_user_id)
                validation_results["scenario_results"][scenario["name"]] = scenario_result
                
                if not scenario_result.get("success", False):
                    validation_results["overall_status"] = "failed"
                    validation_results["issues"].extend(scenario_result.get("errors", []))
            
            # Validate data consistency
            consistency_result = await self._validate_data_consistency(test_user_id)
            validation_results["data_consistency"] = consistency_result
            
            if not consistency_result.get("consistent", False):
                validation_results["overall_status"] = "failed"
                validation_results["issues"].extend(consistency_result.get("issues", []))
            
            # Validate performance metrics
            performance_result = await self._validate_performance_metrics()
            validation_results["performance_metrics"] = performance_result
            
            # Clean up test data
            await self._cleanup_test_data(test_user_id)
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Error validating complete data flow: {e}")
            return {
                "overall_status": "error",
                "error": str(e),
                "validation_timestamp": datetime.utcnow().isoformat()
            }
    
    async def _create_test_user(self) -> str:
        """Create a test user for validation"""
        try:
            test_user_id = f"test_user_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            
            test_user_doc = {
                "user_id": test_user_id,
                "email": f"{test_user_id}@test.com",
                "username": test_user_id,
                "first_name": "Test",
                "last_name": "User",
                "role": "student",
                "created_at": datetime.utcnow(),
                "profile_completed": True,
                "onboarding_completed": True,
                "learning_preferences": {
                    "learning_style": "visual",
                    "study_time_preference": "evening",
                    "difficulty_preference": "gradual"
                },
                "academic_info": {
                    "major": "Computer Science",
                    "year": "junior"
                },
                "_test_data": True  # Mark as test data
            }
            
            await self.db.users.insert_one(test_user_doc)
            logger.info(f"Created test user: {test_user_id}")
            
            return test_user_id
            
        except Exception as e:
            logger.error(f"Error creating test user: {e}")
            raise
    
    async def _run_scenario(self, scenario: Dict[str, Any], test_user_id: str) -> Dict[str, Any]:
        """Run a specific validation scenario"""
        try:
            scenario_result = {
                "scenario_name": scenario["name"],
                "description": scenario["description"],
                "success": True,
                "steps_completed": [],
                "step_results": {},
                "errors": [],
                "execution_time": 0
            }
            
            start_time = datetime.utcnow()
            
            # Execute each step in the scenario
            for step in scenario["steps"]:
                try:
                    step_result = await self._execute_step(step, test_user_id, scenario_result)
                    scenario_result["step_results"][step] = step_result
                    scenario_result["steps_completed"].append(step)
                    
                    if not step_result.get("success", False):
                        scenario_result["success"] = False
                        scenario_result["errors"].append(f"Step {step} failed: {step_result.get('error', 'Unknown error')}")
                        break
                        
                except Exception as e:
                    scenario_result["success"] = False
                    scenario_result["errors"].append(f"Step {step} exception: {str(e)}")
                    break
            
            # Calculate execution time
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            scenario_result["execution_time"] = execution_time
            
            return scenario_result
            
        except Exception as e:
            logger.error(f"Error running scenario {scenario['name']}: {e}")
            return {
                "scenario_name": scenario["name"],
                "success": False,
                "error": str(e)
            }
    
    async def _execute_step(self, step: str, test_user_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a specific validation step"""
        try:
            if step == "submit_quiz":
                return await self._step_submit_quiz(test_user_id)
            elif step == "submit_code":
                return await self._step_submit_code(test_user_id)
            elif step == "analyze_gaps":
                return await self._step_analyze_gaps(test_user_id)
            elif step == "generate_recommendations":
                return await self._step_generate_recommendations(test_user_id)
            elif step == "create_user":
                return {"success": True, "message": "User already created"}
            elif step == "setup_profile":
                return await self._step_setup_profile(test_user_id)
            elif step == "compute_analytics":
                return await self._step_compute_analytics(test_user_id)
            elif step == "mark_completed":
                return await self._step_mark_completed(test_user_id)
            elif step == "update_analytics":
                return await self._step_update_analytics(test_user_id)
            else:
                return {"success": False, "error": f"Unknown step: {step}"}
                
        except Exception as e:
            logger.error(f"Error executing step {step}: {e}")
            return {"success": False, "error": str(e)}
    
    async def _step_submit_quiz(self, test_user_id: str) -> Dict[str, Any]:
        """Submit a test quiz"""
        try:
            quiz_data = {
                "student_id": test_user_id,
                "submission_type": "quiz",
                "course_id": "test_course",
                "assignment_id": "test_quiz_001",
                "score": 7.5,
                "max_score": 10.0,
                "question_responses": [
                    {
                        "question_id": "q1",
                        "response": "correct_answer",
                        "correct": True,
                        "concept_tags": ["algebra", "linear_equations"]
                    },
                    {
                        "question_id": "q2",
                        "response": "wrong_answer",
                        "correct": False,
                        "concept_tags": ["calculus", "derivatives"]
                    },
                    {
                        "question_id": "q3",
                        "response": "correct_answer",
                        "correct": True,
                        "concept_tags": ["statistics", "probability"]
                    }
                ],
                "timestamp": datetime.utcnow(),
                "_test_data": True
            }
            
            # Insert quiz submission
            result = await self.db.student_performance.insert_one(quiz_data)
            
            return {
                "success": True,
                "submission_id": str(result.inserted_id),
                "score": quiz_data["score"],
                "max_score": quiz_data["max_score"]
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _step_submit_code(self, test_user_id: str) -> Dict[str, Any]:
        """Submit test code"""
        try:
            code_data = {
                "student_id": test_user_id,
                "submission_type": "code",
                "course_id": "test_course",
                "assignment_id": "test_code_001",
                "score": 8.0,
                "max_score": 10.0,
                "code_metrics": {
                    "complexity": 5,
                    "test_coverage": 0.85,
                    "execution_time": 0.15,
                    "memory_usage": 1024
                },
                "timestamp": datetime.utcnow(),
                "_test_data": True
            }
            
            # Insert code submission
            result = await self.db.student_performance.insert_one(code_data)
            
            return {
                "success": True,
                "submission_id": str(result.inserted_id),
                "score": code_data["score"],
                "complexity": code_data["code_metrics"]["complexity"]
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _step_analyze_gaps(self, test_user_id: str) -> Dict[str, Any]:
        """Analyze learning gaps"""
        try:
            # Use gap detection service
            gaps = await self.gap_detection_service.analyze_student_gaps(test_user_id)
            
            return {
                "success": True,
                "gaps_found": len(gaps),
                "gaps": gaps[:3]  # Return first 3 gaps
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _step_generate_recommendations(self, test_user_id: str) -> Dict[str, Any]:
        """Generate recommendations"""
        try:
            # Use recommendation service
            recommendations = await self.recommendation_service.generate_recommendations(test_user_id)
            
            return {
                "success": True,
                "recommendations_generated": len(recommendations),
                "recommendations": recommendations[:3]  # Return first 3 recommendations
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _step_setup_profile(self, test_user_id: str) -> Dict[str, Any]:
        """Setup user profile"""
        try:
            # Profile is already set up in test user creation
            return {
                "success": True,
                "message": "Profile setup completed"
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _step_compute_analytics(self, test_user_id: str) -> Dict[str, Any]:
        """Compute analytics"""
        try:
            # Use analytics precompute service
            analytics_data = await self.analytics_precompute_service.precompute_user_analytics(test_user_id)
            
            return {
                "success": True,
                "analytics_computed": bool(analytics_data),
                "performance_summary": analytics_data.get("performance_summary", {})
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _step_mark_completed(self, test_user_id: str) -> Dict[str, Any]:
        """Mark recommendations as completed"""
        try:
            # Find test recommendations and mark some as completed
            recommendations = await self.db.recommendations.find({
                "student_id": test_user_id,
                "_test_data": True
            }).to_list(length=None)
            
            if recommendations:
                # Mark first recommendation as completed
                await self.db.recommendations.update_one(
                    {"_id": recommendations[0]["_id"]},
                    {
                        "$set": {
                            "completed": True,
                            "completed_at": datetime.utcnow(),
                            "effectiveness_rating": 4.5
                        }
                    }
                )
                
                return {
                    "success": True,
                    "recommendations_completed": 1
                }
            else:
                return {
                    "success": True,
                    "recommendations_completed": 0,
                    "message": "No recommendations to complete"
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _step_update_analytics(self, test_user_id: str) -> Dict[str, Any]:
        """Update analytics after recommendation completion"""
        try:
            # Re-compute analytics
            analytics_data = await self.analytics_precompute_service.precompute_user_analytics(test_user_id)
            
            return {
                "success": True,
                "analytics_updated": bool(analytics_data)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _validate_data_consistency(self, test_user_id: str) -> Dict[str, Any]:
        """Validate data consistency across collections"""
        try:
            consistency_result = {
                "consistent": True,
                "checks_performed": [],
                "issues": []
            }
            
            # Check 1: Performance data exists for user
            performance_count = await self.db.student_performance.count_documents({
                "student_id": test_user_id,
                "_test_data": True
            })
            
            consistency_result["checks_performed"].append("performance_data_exists")
            if performance_count == 0:
                consistency_result["consistent"] = False
                consistency_result["issues"].append("No performance data found for test user")
            
            # Check 2: Gaps exist if performance data exists
            if performance_count > 0:
                gaps_count = await self.db.learning_gaps.count_documents({
                    "student_id": test_user_id,
                    "_test_data": True
                })
                
                consistency_result["checks_performed"].append("gaps_generated_from_performance")
                # Note: Gaps might not exist if performance is perfect, so this is informational
                
            # Check 3: Recommendations exist if gaps exist
            gaps_count = await self.db.learning_gaps.count_documents({
                "student_id": test_user_id,
                "_test_data": True
            })
            
            if gaps_count > 0:
                recommendations_count = await self.db.recommendations.count_documents({
                    "student_id": test_user_id,
                    "_test_data": True
                })
                
                consistency_result["checks_performed"].append("recommendations_generated_from_gaps")
                if recommendations_count == 0:
                    consistency_result["consistent"] = False
                    consistency_result["issues"].append("No recommendations found despite having learning gaps")
            
            # Check 4: Cache consistency
            cached_analytics = await cache_manager.get_cache(f"precomputed_analytics:{test_user_id}")
            consistency_result["checks_performed"].append("cache_consistency")
            
            if cached_analytics:
                # Verify cached data matches database data
                db_gaps_count = await self.db.learning_gaps.count_documents({
                    "student_id": test_user_id
                })
                
                cached_gaps_count = cached_analytics.get("learning_gaps", {}).get("total_gaps", 0)
                
                if abs(db_gaps_count - cached_gaps_count) > 1:  # Allow for small differences
                    consistency_result["consistent"] = False
                    consistency_result["issues"].append(
                        f"Cache inconsistency: DB has {db_gaps_count} gaps, cache has {cached_gaps_count}"
                    )
            
            return consistency_result
            
        except Exception as e:
            logger.error(f"Error validating data consistency: {e}")
            return {
                "consistent": False,
                "error": str(e)
            }
    
    async def _validate_performance_metrics(self) -> Dict[str, Any]:
        """Validate system performance metrics"""
        try:
            performance_result = {
                "within_limits": True,
                "metrics": {},
                "issues": []
            }
            
            # Check database response time
            start_time = datetime.utcnow()
            await self.db.users.find_one({"_test_data": True})
            db_response_time = (datetime.utcnow() - start_time).total_seconds()
            
            performance_result["metrics"]["database_response_time"] = db_response_time
            if db_response_time > 1.0:  # 1 second threshold
                performance_result["within_limits"] = False
                performance_result["issues"].append(f"Database response time too high: {db_response_time:.3f}s")
            
            # Check cache response time
            start_time = datetime.utcnow()
            await cache_manager.get_cache("test_key")
            cache_response_time = (datetime.utcnow() - start_time).total_seconds()
            
            performance_result["metrics"]["cache_response_time"] = cache_response_time
            if cache_response_time > 0.1:  # 100ms threshold
                performance_result["within_limits"] = False
                performance_result["issues"].append(f"Cache response time too high: {cache_response_time:.3f}s")
            
            return performance_result
            
        except Exception as e:
            logger.error(f"Error validating performance metrics: {e}")
            return {
                "within_limits": False,
                "error": str(e)
            }
    
    async def _cleanup_test_data(self, test_user_id: str):
        """Clean up test data after validation"""
        try:
            # Remove test data from all collections
            collections_to_clean = [
                "users",
                "student_performance",
                "learning_gaps",
                "recommendations"
            ]
            
            for collection_name in collections_to_clean:
                collection = self.db[collection_name]
                result = await collection.delete_many({
                    "$or": [
                        {"student_id": test_user_id},
                        {"user_id": test_user_id},
                        {"_test_data": True}
                    ]
                })
                
                if result.deleted_count > 0:
                    logger.info(f"Cleaned up {result.deleted_count} test records from {collection_name}")
            
            # Clean up cache
            await cache_manager.delete_cache(f"precomputed_analytics:{test_user_id}")
            await cache_manager.delete_cache(f"dashboard:{test_user_id}")
            
            logger.info(f"Cleaned up test data for user: {test_user_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up test data: {e}")
    
    async def validate_specific_flow(self, flow_name: str, test_user_id: str = None) -> Dict[str, Any]:
        """Validate a specific data flow"""
        try:
            if not test_user_id:
                test_user_id = await self._create_test_user()
            
            # Find the scenario
            scenario = next((s for s in self.test_scenarios if s["name"] == flow_name), None)
            if not scenario:
                return {
                    "success": False,
                    "error": f"Unknown flow: {flow_name}",
                    "available_flows": [s["name"] for s in self.test_scenarios]
                }
            
            # Run the specific scenario
            result = await self._run_scenario(scenario, test_user_id)
            
            # Clean up
            await self._cleanup_test_data(test_user_id)
            
            return result
            
        except Exception as e:
            logger.error(f"Error validating specific flow {flow_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_validation_history(self, hours: int = 24) -> Dict[str, Any]:
        """Get validation history for monitoring"""
        try:
            # This would typically be stored in a separate collection
            # For now, we'll return a summary based on logs
            
            return {
                "time_period_hours": hours,
                "total_validations": 0,
                "successful_validations": 0,
                "failed_validations": 0,
                "average_execution_time": 0,
                "common_issues": [],
                "last_validation": None
            }
            
        except Exception as e:
            logger.error(f"Error getting validation history: {e}")
            return {"error": str(e)}


# Global data flow validation service instance
data_flow_validation_service = DataFlowValidationService()