"""
Real-time Gap Analysis Service for learning analytics
"""
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
from concurrent.futures import ThreadPoolExecutor

from app.models.performance import PerformanceData, LearningGap, GapAnalysisRequest, GapAnalysisResponse
from app.services.gap_detection_service import GapDetectionService
from app.services.concept_mapping_service import ConceptMappingService

logger = logging.getLogger(__name__)


class RealtimeGapAnalysisService:
    """Service for real-time gap analysis updates and background processing"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.gap_detection_service = GapDetectionService(db)
        self.concept_mapping_service = ConceptMappingService(db)
        self.processing_queue = asyncio.Queue()
        self.background_tasks = set()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.is_running = False
        
    async def initialize(self) -> None:
        """Initialize the real-time analysis service"""
        try:
            await self.gap_detection_service.initialize_models()
            await self.concept_mapping_service.initialize_knowledge_base()
            logger.info("Real-time gap analysis service initialized")
            
        except Exception as e:
            logger.error(f"Error initializing real-time gap analysis service: {e}")
            raise
    
    async def start_background_processing(self) -> None:
        """Start background processing of gap analysis updates"""
        if self.is_running:
            logger.warning("Background processing already running")
            return
        
        self.is_running = True
        
        # Start the main processing loop
        task = asyncio.create_task(self._background_processing_loop())
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
        
        # Start periodic model retraining
        retrain_task = asyncio.create_task(self._periodic_model_retraining())
        self.background_tasks.add(retrain_task)
        retrain_task.add_done_callback(self.background_tasks.discard)
        
        logger.info("Started background gap analysis processing")
    
    async def stop_background_processing(self) -> None:
        """Stop background processing"""
        self.is_running = False
        
        # Cancel all background tasks
        for task in self.background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        logger.info("Stopped background gap analysis processing")
    
    async def trigger_gap_analysis(self, student_id: str, submission_data: Dict[str, Any]) -> None:
        """Trigger gap analysis for new performance data"""
        try:
            # Add to processing queue for background analysis
            analysis_request = {
                "type": "gap_analysis",
                "student_id": student_id,
                "submission_data": submission_data,
                "timestamp": datetime.utcnow(),
                "priority": "normal"
            }
            
            await self.processing_queue.put(analysis_request)
            logger.debug(f"Queued gap analysis for student {student_id}")
            
        except Exception as e:
            logger.error(f"Error triggering gap analysis: {e}")
            raise
    
    async def trigger_urgent_analysis(self, student_id: str, reason: str = "urgent_request") -> GapAnalysisResponse:
        """Trigger immediate gap analysis (bypasses queue)"""
        try:
            logger.info(f"Starting urgent gap analysis for student {student_id}: {reason}")
            
            # Perform immediate analysis
            gaps = await self.gap_detection_service.detect_learning_gaps(student_id)
            
            # Calculate statistics
            total_gaps = len(gaps)
            average_severity = sum(gap.gap_severity for gap in gaps) / total_gaps if total_gaps > 0 else 0.0
            
            # Calculate confidence intervals for each gap
            confidence_intervals = {}
            for gap in gaps:
                intervals = await self.gap_detection_service.calculate_confidence_intervals(
                    student_id, gap.concept_id
                )
                confidence_intervals[gap.concept_id] = intervals
            
            response = GapAnalysisResponse(
                student_id=student_id,
                identified_gaps=gaps,
                total_gaps=total_gaps,
                average_severity=average_severity,
                confidence_intervals=confidence_intervals,
                recommendations_generated=False
            )
            
            # Store analysis results
            await self._store_analysis_results(response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error in urgent gap analysis: {e}")
            raise
    
    async def _background_processing_loop(self) -> None:
        """Main background processing loop"""
        logger.info("Started background processing loop")
        
        while self.is_running:
            try:
                # Wait for items in the queue with timeout
                try:
                    request = await asyncio.wait_for(self.processing_queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
                
                # Process the request
                await self._process_analysis_request(request)
                
                # Mark task as done
                self.processing_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in background processing loop: {e}")
                await asyncio.sleep(1)  # Brief pause before continuing
    
    async def _process_analysis_request(self, request: Dict[str, Any]) -> None:
        """Process a single analysis request"""
        try:
            request_type = request.get("type")
            student_id = request.get("student_id")
            
            if request_type == "gap_analysis":
                await self._process_gap_analysis_request(request)
            elif request_type == "model_retrain":
                await self._process_model_retrain_request(request)
            else:
                logger.warning(f"Unknown request type: {request_type}")
            
        except Exception as e:
            logger.error(f"Error processing analysis request: {e}")
    
    async def _process_gap_analysis_request(self, request: Dict[str, Any]) -> None:
        """Process a gap analysis request"""
        try:
            student_id = request["student_id"]
            submission_data = request["submission_data"]
            
            # Check if we have sufficient data for analysis
            data_sufficiency = await self._check_data_sufficiency(student_id)
            
            if data_sufficiency["sufficient"]:
                # Perform full gap analysis
                gaps = await self.gap_detection_service.detect_learning_gaps(student_id)
                
                # Update existing gaps with new trends
                await self._update_gap_trends(student_id, gaps)
                
                # Calculate confidence intervals
                confidence_intervals = {}
                for gap in gaps:
                    intervals = await self.gap_detection_service.calculate_confidence_intervals(
                        student_id, gap.concept_id
                    )
                    confidence_intervals[gap.concept_id] = intervals
                
                # Create analysis response
                response = GapAnalysisResponse(
                    student_id=student_id,
                    identified_gaps=gaps,
                    total_gaps=len(gaps),
                    average_severity=sum(gap.gap_severity for gap in gaps) / len(gaps) if gaps else 0.0,
                    confidence_intervals=confidence_intervals
                )
                
                # Store results
                await self._store_analysis_results(response)
                
                logger.info(f"Completed gap analysis for student {student_id}: {len(gaps)} gaps identified")
                
            else:
                # Handle insufficient data
                await self._handle_insufficient_data(student_id, data_sufficiency)
            
        except Exception as e:
            logger.error(f"Error processing gap analysis request: {e}")
    
    async def _check_data_sufficiency(self, student_id: str) -> Dict[str, Any]:
        """Check if we have sufficient data for reliable gap analysis"""
        try:
            # Count recent submissions
            recent_submissions = await self.db.performance_data.count_documents({
                "student_id": student_id,
                "timestamp": {"$gte": datetime.utcnow() - timedelta(days=30)}
            })
            
            # Count total submissions
            total_submissions = await self.db.performance_data.count_documents({
                "student_id": student_id
            })
            
            # Check concept coverage
            concept_coverage = await self.db.performance_data.aggregate([
                {"$match": {"student_id": student_id}},
                {"$unwind": "$question_responses"},
                {"$unwind": "$question_responses.concept_tags"},
                {"$group": {"_id": "$question_responses.concept_tags"}},
                {"$count": "unique_concepts"}
            ]).to_list(None)
            
            unique_concepts = concept_coverage[0]["unique_concepts"] if concept_coverage else 0
            
            # Determine sufficiency
            sufficient = (
                recent_submissions >= 3 and  # At least 3 recent submissions
                total_submissions >= 5 and   # At least 5 total submissions
                unique_concepts >= 2         # At least 2 different concepts
            )
            
            return {
                "sufficient": sufficient,
                "recent_submissions": recent_submissions,
                "total_submissions": total_submissions,
                "unique_concepts": unique_concepts,
                "recommendations": self._generate_data_collection_recommendations(
                    recent_submissions, total_submissions, unique_concepts
                )
            }
            
        except Exception as e:
            logger.error(f"Error checking data sufficiency: {e}")
            return {"sufficient": False, "error": str(e)}
    
    def _generate_data_collection_recommendations(self, recent: int, total: int, concepts: int) -> List[str]:
        """Generate recommendations for additional data collection"""
        recommendations = []
        
        if recent < 3:
            recommendations.append("Complete more recent assignments to improve analysis accuracy")
        
        if total < 5:
            recommendations.append("Complete additional assignments for better trend analysis")
        
        if concepts < 2:
            recommendations.append("Complete assignments covering different topics for comprehensive analysis")
        
        return recommendations
    
    async def _handle_insufficient_data(self, student_id: str, data_sufficiency: Dict[str, Any]) -> None:
        """Handle cases where there's insufficient data for analysis"""
        try:
            # Create a placeholder analysis with recommendations
            insufficient_data_response = GapAnalysisResponse(
                student_id=student_id,
                identified_gaps=[],
                total_gaps=0,
                average_severity=0.0,
                confidence_intervals={},
                recommendations_generated=False
            )
            
            # Store with metadata about insufficient data
            analysis_doc = insufficient_data_response.dict()
            analysis_doc["insufficient_data"] = True
            analysis_doc["data_sufficiency"] = data_sufficiency
            
            await self.db.gap_analyses.insert_one(analysis_doc)
            
            logger.info(f"Stored insufficient data analysis for student {student_id}")
            
        except Exception as e:
            logger.error(f"Error handling insufficient data: {e}")
    
    async def _update_gap_trends(self, student_id: str, current_gaps: List[LearningGap]) -> None:
        """Update improvement trends for existing gaps"""
        try:
            # Get previous gap analysis
            previous_analysis = await self.db.gap_analyses.find_one(
                {"student_id": student_id},
                sort=[("analysis_timestamp", -1)]
            )
            
            if not previous_analysis:
                return  # No previous data to compare
            
            previous_gaps = {gap["concept_id"]: gap["gap_severity"] 
                           for gap in previous_analysis.get("identified_gaps", [])}
            
            # Update trends for current gaps
            for gap in current_gaps:
                if gap.concept_id in previous_gaps:
                    previous_severity = previous_gaps[gap.concept_id]
                    current_severity = gap.gap_severity
                    
                    # Calculate improvement trend (-1 to 1)
                    if previous_severity > 0:
                        trend = (previous_severity - current_severity) / previous_severity
                        gap.improvement_trend = max(-1.0, min(1.0, trend))
                    else:
                        gap.improvement_trend = 0.0
                else:
                    gap.improvement_trend = 0.0  # New gap
            
        except Exception as e:
            logger.error(f"Error updating gap trends: {e}")
    
    async def _store_analysis_results(self, response: GapAnalysisResponse) -> None:
        """Store gap analysis results in database"""
        try:
            # Store main analysis
            analysis_doc = response.dict()
            await self.db.gap_analyses.insert_one(analysis_doc)
            
            # Update individual gap records
            for gap in response.identified_gaps:
                await self.db.learning_gaps.update_one(
                    {
                        "student_id": gap.student_id,
                        "concept_id": gap.concept_id
                    },
                    {"$set": gap.dict()},
                    upsert=True
                )
            
            logger.debug(f"Stored analysis results for student {response.student_id}")
            
        except Exception as e:
            logger.error(f"Error storing analysis results: {e}")
    
    async def _periodic_model_retraining(self) -> None:
        """Periodically retrain ML models with new data"""
        logger.info("Started periodic model retraining task")
        
        while self.is_running:
            try:
                # Wait 24 hours between retraining attempts
                await asyncio.sleep(24 * 60 * 60)
                
                if not self.is_running:
                    break
                
                # Check if we have enough new data to warrant retraining
                last_retrain = await self.db.model_metadata.find_one(
                    {"model_type": "gap_detection"},
                    sort=[("last_trained", -1)]
                )
                
                if last_retrain:
                    last_train_time = last_retrain["last_trained"]
                    new_data_count = await self.db.performance_data.count_documents({
                        "timestamp": {"$gte": last_train_time}
                    })
                    
                    if new_data_count < 50:  # Not enough new data
                        logger.info(f"Skipping retraining: only {new_data_count} new records")
                        continue
                
                # Queue model retraining
                retrain_request = {
                    "type": "model_retrain",
                    "timestamp": datetime.utcnow(),
                    "priority": "low"
                }
                
                await self.processing_queue.put(retrain_request)
                logger.info("Queued model retraining")
                
            except Exception as e:
                logger.error(f"Error in periodic model retraining: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    async def _process_model_retrain_request(self, request: Dict[str, Any]) -> None:
        """Process a model retraining request"""
        try:
            logger.info("Starting model retraining...")
            
            # Retrain models
            success = await self.gap_detection_service.retrain_models()
            
            if success:
                # Update metadata
                metadata = {
                    "model_type": "gap_detection",
                    "last_trained": datetime.utcnow(),
                    "training_success": True,
                    "version": str(uuid.uuid4())
                }
                
                await self.db.model_metadata.insert_one(metadata)
                logger.info("Model retraining completed successfully")
            else:
                logger.warning("Model retraining failed")
            
        except Exception as e:
            logger.error(f"Error processing model retrain request: {e}")
    
    async def get_analysis_history(self, student_id: str, limit: int = 10) -> List[GapAnalysisResponse]:
        """Get historical gap analysis results for a student"""
        try:
            analyses = await self.db.gap_analyses.find(
                {"student_id": student_id}
            ).sort("analysis_timestamp", -1).limit(limit).to_list(None)
            
            return [GapAnalysisResponse(**analysis) for analysis in analyses]
            
        except Exception as e:
            logger.error(f"Error getting analysis history: {e}")
            return []
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current status of the processing queue"""
        try:
            return {
                "queue_size": self.processing_queue.qsize(),
                "is_running": self.is_running,
                "active_tasks": len(self.background_tasks)
            }
            
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {"error": str(e)}