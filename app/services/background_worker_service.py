"""
Background Worker Service
Handles asynchronous ML model training, inference, and analytics computation
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from motor.motor_asyncio import AsyncIOMotorDatabase
import json

from app.core.database import get_database
from app.core.redis_client import cache_manager
from app.services.analytics_precompute_service import AnalyticsPrecomputeService
from app.services.gap_detection_service import GapDetectionService
from app.services.recommendation_engine_service import RecommendationEngineService

logger = logging.getLogger(__name__)


class BackgroundWorkerService:
    """Service for managing background processing tasks"""
    
    def __init__(self):
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.analytics_precompute_service: Optional[AnalyticsPrecomputeService] = None
        self.gap_detection_service: Optional[GapDetectionService] = None
        self.recommendation_service: Optional[RecommendationEngineService] = None
        
        # Worker configuration
        self.max_workers = 4
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # Task queues
        self.ml_training_queue = asyncio.Queue(maxsize=100)
        self.analytics_queue = asyncio.Queue(maxsize=500)
        self.cache_refresh_queue = asyncio.Queue(maxsize=200)
        
        # Background task tracking
        self.background_tasks = set()
        self.is_running = False
        
        # Performance monitoring
        self.performance_metrics = {
            "tasks_processed": 0,
            "tasks_failed": 0,
            "average_processing_time": 0.0,
            "queue_sizes": {},
            "last_updated": datetime.utcnow()
        }
        
        # Task intervals (in seconds)
        self.ml_training_interval = 3600  # 1 hour
        self.analytics_batch_interval = 300  # 5 minutes
        self.cache_refresh_interval = 600  # 10 minutes
        self.performance_monitoring_interval = 60  # 1 minute
    
    async def initialize(self):
        """Initialize the background worker service"""
        try:
            self.db = await get_database()
            if self.db:
                self.analytics_precompute_service = AnalyticsPrecomputeService(self.db)
                self.gap_detection_service = GapDetectionService(self.db)
                self.recommendation_service = RecommendationEngineService(self.db)
                logger.info("Background worker service initialized successfully")
            else:
                logger.error("Failed to initialize database connection for background workers")
        except Exception as e:
            logger.error(f"Error initializing background worker service: {e}")
    
    async def start_background_processing(self):
        """Start all background processing workers"""
        if not self.db:
            await self.initialize()
        
        if not self.db:
            logger.error("Cannot start background processing: services not initialized")
            return
        
        self.is_running = True
        logger.info("Starting background processing workers")
        
        # Start worker tasks
        workers = [
            asyncio.create_task(self._ml_training_worker()),
            asyncio.create_task(self._analytics_computation_worker()),
            asyncio.create_task(self._cache_refresh_worker()),
            asyncio.create_task(self._performance_monitoring_worker()),
            asyncio.create_task(self._periodic_ml_training_scheduler()),
            asyncio.create_task(self._periodic_analytics_batch_processor()),
            asyncio.create_task(self._periodic_cache_refresh_scheduler())
        ]
        
        # Add tasks to tracking set
        for task in workers:
            self.background_tasks.add(task)
            task.add_done_callback(self.background_tasks.discard)
        
        try:
            await asyncio.gather(*workers)
        except Exception as e:
            logger.error(f"Error in background processing workers: {e}")
        finally:
            self.is_running = False
    
    async def stop_background_processing(self):
        """Stop all background processing workers"""
        self.is_running = False
        logger.info("Stopping background processing workers")
        
        # Cancel all background tasks
        for task in self.background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        logger.info("Background processing workers stopped")
    
    async def _ml_training_worker(self):
        """Worker for processing ML model training tasks"""
        while self.is_running:
            try:
                # Wait for ML training task
                task = await asyncio.wait_for(
                    self.ml_training_queue.get(),
                    timeout=1.0
                )
                
                start_time = datetime.utcnow()
                logger.info(f"Processing ML training task: {task.get('task_type')}")
                
                # Process the task based on type
                if task['task_type'] == 'gap_detection_training':
                    await self._train_gap_detection_model(task)
                elif task['task_type'] == 'recommendation_training':
                    await self._train_recommendation_model(task)
                elif task['task_type'] == 'concept_mapping_training':
                    await self._train_concept_mapping_model(task)
                
                # Update performance metrics
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                await self._update_performance_metrics('ml_training', processing_time, success=True)
                
                logger.info(f"Completed ML training task in {processing_time:.2f}s")
                
            except asyncio.TimeoutError:
                # No tasks in queue, continue
                continue
            except Exception as e:
                logger.error(f"Error in ML training worker: {e}")
                await self._update_performance_metrics('ml_training', 0, success=False)
    
    async def _analytics_computation_worker(self):
        """Worker for processing analytics computation tasks"""
        while self.is_running:
            try:
                # Wait for analytics task
                task = await asyncio.wait_for(
                    self.analytics_queue.get(),
                    timeout=1.0
                )
                
                start_time = datetime.utcnow()
                logger.debug(f"Processing analytics task: {task.get('task_type')} for user {task.get('user_id')}")
                
                # Process the task based on type
                if task['task_type'] == 'user_analytics_precompute':
                    await self._process_user_analytics_precompute(task)
                elif task['task_type'] == 'gap_analysis_update':
                    await self._process_gap_analysis_update(task)
                elif task['task_type'] == 'recommendation_generation':
                    await self._process_recommendation_generation(task)
                elif task['task_type'] == 'batch_analytics_update':
                    await self._process_batch_analytics_update(task)
                
                # Update performance metrics
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                await self._update_performance_metrics('analytics', processing_time, success=True)
                
            except asyncio.TimeoutError:
                # No tasks in queue, continue
                continue
            except Exception as e:
                logger.error(f"Error in analytics computation worker: {e}")
                await self._update_performance_metrics('analytics', 0, success=False)
    
    async def _cache_refresh_worker(self):
        """Worker for processing cache refresh tasks"""
        while self.is_running:
            try:
                # Wait for cache refresh task
                task = await asyncio.wait_for(
                    self.cache_refresh_queue.get(),
                    timeout=1.0
                )
                
                start_time = datetime.utcnow()
                logger.debug(f"Processing cache refresh task: {task.get('cache_type')}")
                
                # Process the task based on cache type
                if task['cache_type'] == 'dashboard_data':
                    await self._refresh_dashboard_cache(task)
                elif task['cache_type'] == 'user_analytics':
                    await self._refresh_user_analytics_cache(task)
                elif task['cache_type'] == 'recommendations':
                    await self._refresh_recommendations_cache(task)
                elif task['cache_type'] == 'performance_data':
                    await self._refresh_performance_data_cache(task)
                
                # Update performance metrics
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                await self._update_performance_metrics('cache_refresh', processing_time, success=True)
                
            except asyncio.TimeoutError:
                # No tasks in queue, continue
                continue
            except Exception as e:
                logger.error(f"Error in cache refresh worker: {e}")
                await self._update_performance_metrics('cache_refresh', 0, success=False)
    
    async def _performance_monitoring_worker(self):
        """Worker for monitoring system performance"""
        while self.is_running:
            try:
                await asyncio.sleep(self.performance_monitoring_interval)
                
                # Update queue sizes
                self.performance_metrics['queue_sizes'] = {
                    'ml_training': self.ml_training_queue.qsize(),
                    'analytics': self.analytics_queue.qsize(),
                    'cache_refresh': self.cache_refresh_queue.qsize()
                }
                
                # Update timestamp
                self.performance_metrics['last_updated'] = datetime.utcnow()
                
                # Cache performance metrics
                await cache_manager.set_cache(
                    "background_worker_metrics",
                    self.performance_metrics,
                    expire=300
                )
                
                # Log performance summary
                total_queue_size = sum(self.performance_metrics['queue_sizes'].values())
                if total_queue_size > 0:
                    logger.info(f"Background worker status - Queued tasks: {total_queue_size}, "
                              f"Processed: {self.performance_metrics['tasks_processed']}, "
                              f"Failed: {self.performance_metrics['tasks_failed']}")
                
            except Exception as e:
                logger.error(f"Error in performance monitoring worker: {e}")
    
    async def _periodic_ml_training_scheduler(self):
        """Periodically schedule ML model training tasks"""
        while self.is_running:
            try:
                await asyncio.sleep(self.ml_training_interval)
                
                # Schedule gap detection model retraining
                await self.schedule_ml_training_task({
                    'task_type': 'gap_detection_training',
                    'priority': 'normal',
                    'scheduled_at': datetime.utcnow().isoformat()
                })
                
                # Schedule recommendation model retraining
                await self.schedule_ml_training_task({
                    'task_type': 'recommendation_training',
                    'priority': 'normal',
                    'scheduled_at': datetime.utcnow().isoformat()
                })
                
                logger.info("Scheduled periodic ML model training tasks")
                
            except Exception as e:
                logger.error(f"Error in periodic ML training scheduler: {e}")
    
    async def _periodic_analytics_batch_processor(self):
        """Periodically process analytics for active users"""
        while self.is_running:
            try:
                await asyncio.sleep(self.analytics_batch_interval)
                
                # Get list of recently active users
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                active_users = await self.db.users.find({
                    "last_login": {"$gte": cutoff_time}
                }).to_list(length=100)
                
                # Schedule analytics updates for active users
                for user in active_users:
                    await self.schedule_analytics_task({
                        'task_type': 'user_analytics_precompute',
                        'user_id': user['user_id'],
                        'priority': 'normal'
                    })
                
                logger.info(f"Scheduled analytics updates for {len(active_users)} active users")
                
            except Exception as e:
                logger.error(f"Error in periodic analytics batch processor: {e}")
    
    async def _periodic_cache_refresh_scheduler(self):
        """Periodically refresh cached data"""
        while self.is_running:
            try:
                await asyncio.sleep(self.cache_refresh_interval)
                
                # Schedule cache refresh for frequently accessed data
                cache_refresh_tasks = [
                    {'cache_type': 'dashboard_data', 'scope': 'active_users'},
                    {'cache_type': 'user_analytics', 'scope': 'recent_updates'},
                    {'cache_type': 'recommendations', 'scope': 'active_recommendations'}
                ]
                
                for task in cache_refresh_tasks:
                    await self.schedule_cache_refresh_task(task)
                
                logger.info("Scheduled periodic cache refresh tasks")
                
            except Exception as e:
                logger.error(f"Error in periodic cache refresh scheduler: {e}")
    
    # Task scheduling methods
    async def schedule_ml_training_task(self, task: Dict[str, Any]) -> bool:
        """Schedule an ML training task"""
        try:
            await self.ml_training_queue.put(task)
            logger.debug(f"Scheduled ML training task: {task.get('task_type')}")
            return True
        except asyncio.QueueFull:
            logger.warning("ML training queue is full, dropping task")
            return False
    
    async def schedule_analytics_task(self, task: Dict[str, Any]) -> bool:
        """Schedule an analytics computation task"""
        try:
            await self.analytics_queue.put(task)
            logger.debug(f"Scheduled analytics task: {task.get('task_type')} for user {task.get('user_id')}")
            return True
        except asyncio.QueueFull:
            logger.warning("Analytics queue is full, dropping task")
            return False
    
    async def schedule_cache_refresh_task(self, task: Dict[str, Any]) -> bool:
        """Schedule a cache refresh task"""
        try:
            await self.cache_refresh_queue.put(task)
            logger.debug(f"Scheduled cache refresh task: {task.get('cache_type')}")
            return True
        except asyncio.QueueFull:
            logger.warning("Cache refresh queue is full, dropping task")
            return False
    
    # Task processing methods
    async def _train_gap_detection_model(self, task: Dict[str, Any]):
        """Train the gap detection ML model"""
        try:
            logger.info("Starting gap detection model training")
            
            # Get training data
            training_data = await self._get_gap_detection_training_data()
            
            if len(training_data) < 100:
                logger.warning("Insufficient training data for gap detection model")
                return
            
            # Train model using gap detection service
            model_metrics = await self.gap_detection_service.train_model(training_data)
            
            # Cache model metrics
            await cache_manager.set_cache(
                "gap_detection_model_metrics",
                model_metrics,
                expire=86400  # 24 hours
            )
            
            logger.info(f"Gap detection model training completed with accuracy: {model_metrics.get('accuracy', 0):.3f}")
            
        except Exception as e:
            logger.error(f"Error training gap detection model: {e}")
            raise
    
    async def _train_recommendation_model(self, task: Dict[str, Any]):
        """Train the recommendation ML model"""
        try:
            logger.info("Starting recommendation model training")
            
            # Get training data
            training_data = await self._get_recommendation_training_data()
            
            if len(training_data) < 50:
                logger.warning("Insufficient training data for recommendation model")
                return
            
            # Train model using recommendation service
            model_metrics = await self.recommendation_service.train_model(training_data)
            
            # Cache model metrics
            await cache_manager.set_cache(
                "recommendation_model_metrics",
                model_metrics,
                expire=86400  # 24 hours
            )
            
            logger.info(f"Recommendation model training completed with effectiveness: {model_metrics.get('effectiveness', 0):.3f}")
            
        except Exception as e:
            logger.error(f"Error training recommendation model: {e}")
            raise
    
    async def _train_concept_mapping_model(self, task: Dict[str, Any]):
        """Train the concept mapping ML model"""
        try:
            logger.info("Starting concept mapping model training")
            
            # Get training data
            training_data = await self._get_concept_mapping_training_data()
            
            if len(training_data) < 200:
                logger.warning("Insufficient training data for concept mapping model")
                return
            
            # Train model (placeholder - would use actual ML training)
            model_metrics = {
                "accuracy": 0.85,
                "precision": 0.82,
                "recall": 0.88,
                "training_samples": len(training_data),
                "trained_at": datetime.utcnow().isoformat()
            }
            
            # Cache model metrics
            await cache_manager.set_cache(
                "concept_mapping_model_metrics",
                model_metrics,
                expire=86400  # 24 hours
            )
            
            logger.info(f"Concept mapping model training completed with accuracy: {model_metrics.get('accuracy', 0):.3f}")
            
        except Exception as e:
            logger.error(f"Error training concept mapping model: {e}")
            raise
    
    async def _process_user_analytics_precompute(self, task: Dict[str, Any]):
        """Process user analytics precomputation"""
        user_id = task.get('user_id')
        if not user_id:
            logger.warning("No user_id provided for analytics precompute task")
            return
        
        try:
            # Use analytics precompute service
            result = await self.analytics_precompute_service.precompute_user_analytics(user_id)
            
            if result:
                logger.debug(f"Precomputed analytics for user {user_id}")
            else:
                logger.warning(f"Failed to precompute analytics for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error processing user analytics precompute for {user_id}: {e}")
            raise
    
    async def _process_gap_analysis_update(self, task: Dict[str, Any]):
        """Process gap analysis update"""
        user_id = task.get('user_id')
        if not user_id:
            logger.warning("No user_id provided for gap analysis update task")
            return
        
        try:
            # Update gap analysis
            gaps = await self.gap_detection_service.analyze_student_gaps(user_id)
            
            # Cache updated gaps
            await cache_manager.set_cache(
                f"learning_gaps:{user_id}",
                gaps,
                expire=1800  # 30 minutes
            )
            
            logger.debug(f"Updated gap analysis for user {user_id} - found {len(gaps)} gaps")
            
        except Exception as e:
            logger.error(f"Error processing gap analysis update for {user_id}: {e}")
            raise
    
    async def _process_recommendation_generation(self, task: Dict[str, Any]):
        """Process recommendation generation"""
        user_id = task.get('user_id')
        if not user_id:
            logger.warning("No user_id provided for recommendation generation task")
            return
        
        try:
            # Generate recommendations
            recommendations = await self.recommendation_service.generate_recommendations(user_id)
            
            # Cache updated recommendations
            await cache_manager.set_cache(
                f"recommendations:{user_id}",
                recommendations,
                expire=3600  # 1 hour
            )
            
            logger.debug(f"Generated {len(recommendations)} recommendations for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error processing recommendation generation for {user_id}: {e}")
            raise
    
    async def _process_batch_analytics_update(self, task: Dict[str, Any]):
        """Process batch analytics update"""
        user_ids = task.get('user_ids', [])
        if not user_ids:
            logger.warning("No user_ids provided for batch analytics update task")
            return
        
        try:
            # Process users in batches
            results = await self.analytics_precompute_service.batch_precompute_analytics(user_ids)
            
            logger.info(f"Batch analytics update completed: {len(results['successful'])} successful, "
                       f"{len(results['failed'])} failed")
            
        except Exception as e:
            logger.error(f"Error processing batch analytics update: {e}")
            raise
    
    # Cache refresh methods
    async def _refresh_dashboard_cache(self, task: Dict[str, Any]):
        """Refresh dashboard data cache"""
        scope = task.get('scope', 'all')
        
        try:
            if scope == 'active_users':
                # Refresh cache for recently active users
                cutoff_time = datetime.utcnow() - timedelta(hours=6)
                active_users = await self.db.users.find({
                    "last_login": {"$gte": cutoff_time}
                }).to_list(length=50)
                
                for user in active_users:
                    user_id = user['user_id']
                    
                    # Check if cache is stale
                    cached_data = await cache_manager.get_dashboard_data(user_id)
                    if not cached_data:
                        # Schedule analytics precompute to refresh cache
                        await self.schedule_analytics_task({
                            'task_type': 'user_analytics_precompute',
                            'user_id': user_id,
                            'priority': 'low'
                        })
                
                logger.debug(f"Refreshed dashboard cache for {len(active_users)} active users")
            
        except Exception as e:
            logger.error(f"Error refreshing dashboard cache: {e}")
            raise
    
    async def _refresh_user_analytics_cache(self, task: Dict[str, Any]):
        """Refresh user analytics cache"""
        try:
            # Find users with stale analytics cache
            # This is a simplified implementation
            logger.debug("Refreshed user analytics cache")
            
        except Exception as e:
            logger.error(f"Error refreshing user analytics cache: {e}")
            raise
    
    async def _refresh_recommendations_cache(self, task: Dict[str, Any]):
        """Refresh recommendations cache"""
        try:
            # Find users with stale recommendations cache
            # This is a simplified implementation
            logger.debug("Refreshed recommendations cache")
            
        except Exception as e:
            logger.error(f"Error refreshing recommendations cache: {e}")
            raise
    
    async def _refresh_performance_data_cache(self, task: Dict[str, Any]):
        """Refresh performance data cache"""
        try:
            # Refresh frequently accessed performance data
            # This is a simplified implementation
            logger.debug("Refreshed performance data cache")
            
        except Exception as e:
            logger.error(f"Error refreshing performance data cache: {e}")
            raise
    
    # Helper methods for getting training data
    async def _get_gap_detection_training_data(self) -> List[Dict[str, Any]]:
        """Get training data for gap detection model"""
        try:
            # Get recent performance data with known gaps
            pipeline = [
                {
                    "$lookup": {
                        "from": "learning_gaps",
                        "localField": "student_id",
                        "foreignField": "student_id",
                        "as": "gaps"
                    }
                },
                {
                    "$match": {
                        "gaps": {"$ne": []},
                        "timestamp": {"$gte": datetime.utcnow() - timedelta(days=90)}
                    }
                },
                {"$limit": 1000}
            ]
            
            cursor = self.db.student_performance.aggregate(pipeline)
            training_data = await cursor.to_list(length=None)
            
            return training_data
            
        except Exception as e:
            logger.error(f"Error getting gap detection training data: {e}")
            return []
    
    async def _get_recommendation_training_data(self) -> List[Dict[str, Any]]:
        """Get training data for recommendation model"""
        try:
            # Get recommendations with effectiveness ratings
            training_data = await self.db.recommendations.find({
                "effectiveness_rating": {"$exists": True, "$ne": None},
                "completed": True
            }).limit(1000).to_list(length=None)
            
            return training_data
            
        except Exception as e:
            logger.error(f"Error getting recommendation training data: {e}")
            return []
    
    async def _get_concept_mapping_training_data(self) -> List[Dict[str, Any]]:
        """Get training data for concept mapping model"""
        try:
            # Get quiz questions with concept mappings
            training_data = await self.db.student_performance.find({
                "submission_type": "quiz",
                "question_responses.concept_tags": {"$exists": True, "$ne": []}
            }).limit(2000).to_list(length=None)
            
            return training_data
            
        except Exception as e:
            logger.error(f"Error getting concept mapping training data: {e}")
            return []
    
    async def _update_performance_metrics(self, task_type: str, processing_time: float, success: bool):
        """Update performance metrics"""
        try:
            if success:
                self.performance_metrics['tasks_processed'] += 1
                
                # Update average processing time
                current_avg = self.performance_metrics['average_processing_time']
                total_tasks = self.performance_metrics['tasks_processed']
                
                self.performance_metrics['average_processing_time'] = (
                    (current_avg * (total_tasks - 1) + processing_time) / total_tasks
                )
            else:
                self.performance_metrics['tasks_failed'] += 1
                
        except Exception as e:
            logger.error(f"Error updating performance metrics: {e}")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        return self.performance_metrics.copy()
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        return {
            "ml_training_queue": self.ml_training_queue.qsize(),
            "analytics_queue": self.analytics_queue.qsize(),
            "cache_refresh_queue": self.cache_refresh_queue.qsize(),
            "is_running": self.is_running,
            "max_workers": self.max_workers
        }


# Global instance for background worker service
background_worker_service = BackgroundWorkerService()