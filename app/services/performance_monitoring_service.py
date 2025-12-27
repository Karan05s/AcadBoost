"""
Performance Monitoring Service
Monitors system performance, resource usage, and optimization metrics
"""
import asyncio
import logging
import psutil
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.core.redis_client import cache_manager
from app.services.enhanced_cache_service import enhanced_cache_service

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics data structure"""
    timestamp: str
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_io: Dict[str, int]
    database_connections: int
    redis_connections: int
    active_requests: int
    response_times: Dict[str, float]
    cache_hit_rate: float
    queue_sizes: Dict[str, int]
    error_rate: float


class PerformanceMonitoringService:
    """Service for monitoring system performance and optimization"""
    
    def __init__(self):
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.is_monitoring = False
        
        # Monitoring configuration
        self.monitoring_interval = 30  # seconds
        self.metrics_retention_days = 7
        self.alert_thresholds = {
            "cpu_usage": 80.0,
            "memory_usage": 85.0,
            "disk_usage": 90.0,
            "response_time": 2.0,  # seconds
            "error_rate": 5.0,  # percentage
            "cache_hit_rate": 70.0  # minimum percentage
        }
        
        # Performance tracking
        self.request_times = []
        self.error_count = 0
        self.request_count = 0
        self.active_requests = 0
        
        # Background tasks
        self.background_tasks = set()
    
    async def initialize(self):
        """Initialize the performance monitoring service"""
        try:
            self.db = await get_database()
            if self.db:
                # Ensure indexes for performance metrics collection
                await self.db.performance_metrics.create_index([("timestamp", -1)])
                await self.db.performance_alerts.create_index([("created_at", -1)])
                logger.info("Performance monitoring service initialized successfully")
            else:
                logger.error("Failed to initialize database connection for performance monitoring")
        except Exception as e:
            logger.error(f"Error initializing performance monitoring service: {e}")
    
    async def start_monitoring(self):
        """Start performance monitoring"""
        if not self.db:
            await self.initialize()
        
        if not self.db:
            logger.error("Cannot start performance monitoring: database not initialized")
            return
        
        self.is_monitoring = True
        logger.info("Starting performance monitoring")
        
        # Start monitoring tasks
        monitoring_tasks = [
            asyncio.create_task(self._system_metrics_monitor()),
            asyncio.create_task(self._database_performance_monitor()),
            asyncio.create_task(self._cache_performance_monitor()),
            asyncio.create_task(self._application_performance_monitor()),
            asyncio.create_task(self._alert_processor())
        ]
        
        # Add tasks to tracking set
        for task in monitoring_tasks:
            self.background_tasks.add(task)
            task.add_done_callback(self.background_tasks.discard)
        
        try:
            await asyncio.gather(*monitoring_tasks)
        except Exception as e:
            logger.error(f"Error in performance monitoring: {e}")
        finally:
            self.is_monitoring = False
    
    async def stop_monitoring(self):
        """Stop performance monitoring"""
        self.is_monitoring = False
        logger.info("Stopping performance monitoring")
        
        # Cancel all background tasks
        for task in self.background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        logger.info("Performance monitoring stopped")
    
    async def _system_metrics_monitor(self):
        """Monitor system-level metrics"""
        while self.is_monitoring:
            try:
                # Collect system metrics
                cpu_usage = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                network = psutil.net_io_counters()
                
                # Create metrics object
                metrics = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "cpu_usage": cpu_usage,
                    "memory_usage": memory.percent,
                    "disk_usage": (disk.used / disk.total) * 100,
                    "network_io": {
                        "bytes_sent": network.bytes_sent,
                        "bytes_recv": network.bytes_recv,
                        "packets_sent": network.packets_sent,
                        "packets_recv": network.packets_recv
                    }
                }
                
                # Store metrics
                await self._store_metrics("system", metrics)
                
                # Check for alerts
                await self._check_system_alerts(metrics)
                
                # Cache current metrics
                await cache_manager.set_cache(
                    "current_system_metrics",
                    metrics,
                    expire=60
                )
                
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in system metrics monitor: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def _database_performance_monitor(self):
        """Monitor database performance"""
        while self.is_monitoring:
            try:
                # Get database stats
                db_stats = await self.db.command("serverStatus")
                
                # Extract relevant metrics
                connections = db_stats.get("connections", {})
                opcounters = db_stats.get("opcounters", {})
                memory = db_stats.get("mem", {})
                
                metrics = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "connections": {
                        "current": connections.get("current", 0),
                        "available": connections.get("available", 0),
                        "total_created": connections.get("totalCreated", 0)
                    },
                    "operations": {
                        "insert": opcounters.get("insert", 0),
                        "query": opcounters.get("query", 0),
                        "update": opcounters.get("update", 0),
                        "delete": opcounters.get("delete", 0)
                    },
                    "memory": {
                        "resident": memory.get("resident", 0),
                        "virtual": memory.get("virtual", 0),
                        "mapped": memory.get("mapped", 0)
                    }
                }
                
                # Store metrics
                await self._store_metrics("database", metrics)
                
                # Check for database alerts
                await self._check_database_alerts(metrics)
                
                # Cache current metrics
                await cache_manager.set_cache(
                    "current_database_metrics",
                    metrics,
                    expire=60
                )
                
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in database performance monitor: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def _cache_performance_monitor(self):
        """Monitor cache performance"""
        while self.is_monitoring:
            try:
                # Get cache statistics
                cache_stats = await enhanced_cache_service.get_cache_statistics()
                
                metrics = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "cache_stats": cache_stats.get("cache_stats", {}),
                    "hit_rate": cache_stats.get("hit_rate_percentage", 0),
                    "memory_usage": cache_stats.get("redis_memory_usage", "unknown"),
                    "memory_peak": cache_stats.get("redis_memory_peak", "unknown")
                }
                
                # Store metrics
                await self._store_metrics("cache", metrics)
                
                # Check for cache alerts
                await self._check_cache_alerts(metrics)
                
                # Cache current metrics
                await cache_manager.set_cache(
                    "current_cache_metrics",
                    metrics,
                    expire=60
                )
                
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in cache performance monitor: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def _application_performance_monitor(self):
        """Monitor application-level performance"""
        while self.is_monitoring:
            try:
                # Calculate application metrics
                total_requests = self.request_count
                error_rate = (self.error_count / total_requests * 100) if total_requests > 0 else 0
                
                avg_response_time = 0
                if self.request_times:
                    avg_response_time = sum(self.request_times) / len(self.request_times)
                    # Keep only recent request times (last 100)
                    self.request_times = self.request_times[-100:]
                
                metrics = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "total_requests": total_requests,
                    "error_count": self.error_count,
                    "error_rate": error_rate,
                    "average_response_time": avg_response_time,
                    "active_requests": self.active_requests,
                    "requests_per_minute": self._calculate_requests_per_minute()
                }
                
                # Store metrics
                await self._store_metrics("application", metrics)
                
                # Check for application alerts
                await self._check_application_alerts(metrics)
                
                # Cache current metrics
                await cache_manager.set_cache(
                    "current_application_metrics",
                    metrics,
                    expire=60
                )
                
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in application performance monitor: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def _alert_processor(self):
        """Process and handle performance alerts"""
        while self.is_monitoring:
            try:
                # Check for unprocessed alerts
                unprocessed_alerts = await self.db.performance_alerts.find({
                    "processed": False,
                    "created_at": {"$gte": datetime.utcnow() - timedelta(minutes=5)}
                }).to_list(length=None)
                
                for alert in unprocessed_alerts:
                    await self._process_alert(alert)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in alert processor: {e}")
                await asyncio.sleep(30)
    
    async def _store_metrics(self, metric_type: str, metrics: Dict[str, Any]):
        """Store performance metrics in database"""
        try:
            metrics_doc = {
                "metric_type": metric_type,
                "metrics": metrics,
                "created_at": datetime.utcnow()
            }
            
            await self.db.performance_metrics.insert_one(metrics_doc)
            
        except Exception as e:
            logger.error(f"Error storing {metric_type} metrics: {e}")
    
    async def _check_system_alerts(self, metrics: Dict[str, Any]):
        """Check system metrics for alert conditions"""
        try:
            alerts = []
            
            # CPU usage alert
            if metrics["cpu_usage"] > self.alert_thresholds["cpu_usage"]:
                alerts.append({
                    "alert_type": "high_cpu_usage",
                    "severity": "high",
                    "message": f"CPU usage is {metrics['cpu_usage']:.1f}%",
                    "threshold": self.alert_thresholds["cpu_usage"],
                    "current_value": metrics["cpu_usage"]
                })
            
            # Memory usage alert
            if metrics["memory_usage"] > self.alert_thresholds["memory_usage"]:
                alerts.append({
                    "alert_type": "high_memory_usage",
                    "severity": "high",
                    "message": f"Memory usage is {metrics['memory_usage']:.1f}%",
                    "threshold": self.alert_thresholds["memory_usage"],
                    "current_value": metrics["memory_usage"]
                })
            
            # Disk usage alert
            if metrics["disk_usage"] > self.alert_thresholds["disk_usage"]:
                alerts.append({
                    "alert_type": "high_disk_usage",
                    "severity": "critical",
                    "message": f"Disk usage is {metrics['disk_usage']:.1f}%",
                    "threshold": self.alert_thresholds["disk_usage"],
                    "current_value": metrics["disk_usage"]
                })
            
            # Create alerts
            for alert in alerts:
                await self._create_alert(alert)
                
        except Exception as e:
            logger.error(f"Error checking system alerts: {e}")
    
    async def _check_database_alerts(self, metrics: Dict[str, Any]):
        """Check database metrics for alert conditions"""
        try:
            alerts = []
            
            # Connection usage alert
            connections = metrics.get("connections", {})
            current_connections = connections.get("current", 0)
            available_connections = connections.get("available", 1)
            
            connection_usage = (current_connections / (current_connections + available_connections)) * 100
            
            if connection_usage > 80:
                alerts.append({
                    "alert_type": "high_database_connections",
                    "severity": "medium",
                    "message": f"Database connection usage is {connection_usage:.1f}%",
                    "threshold": 80,
                    "current_value": connection_usage
                })
            
            # Create alerts
            for alert in alerts:
                await self._create_alert(alert)
                
        except Exception as e:
            logger.error(f"Error checking database alerts: {e}")
    
    async def _check_cache_alerts(self, metrics: Dict[str, Any]):
        """Check cache metrics for alert conditions"""
        try:
            alerts = []
            
            # Cache hit rate alert
            hit_rate = metrics.get("hit_rate", 0)
            if hit_rate < self.alert_thresholds["cache_hit_rate"]:
                alerts.append({
                    "alert_type": "low_cache_hit_rate",
                    "severity": "medium",
                    "message": f"Cache hit rate is {hit_rate:.1f}%",
                    "threshold": self.alert_thresholds["cache_hit_rate"],
                    "current_value": hit_rate
                })
            
            # Create alerts
            for alert in alerts:
                await self._create_alert(alert)
                
        except Exception as e:
            logger.error(f"Error checking cache alerts: {e}")
    
    async def _check_application_alerts(self, metrics: Dict[str, Any]):
        """Check application metrics for alert conditions"""
        try:
            alerts = []
            
            # Error rate alert
            error_rate = metrics.get("error_rate", 0)
            if error_rate > self.alert_thresholds["error_rate"]:
                alerts.append({
                    "alert_type": "high_error_rate",
                    "severity": "high",
                    "message": f"Error rate is {error_rate:.1f}%",
                    "threshold": self.alert_thresholds["error_rate"],
                    "current_value": error_rate
                })
            
            # Response time alert
            avg_response_time = metrics.get("average_response_time", 0)
            if avg_response_time > self.alert_thresholds["response_time"]:
                alerts.append({
                    "alert_type": "high_response_time",
                    "severity": "medium",
                    "message": f"Average response time is {avg_response_time:.2f}s",
                    "threshold": self.alert_thresholds["response_time"],
                    "current_value": avg_response_time
                })
            
            # Create alerts
            for alert in alerts:
                await self._create_alert(alert)
                
        except Exception as e:
            logger.error(f"Error checking application alerts: {e}")
    
    async def _create_alert(self, alert_data: Dict[str, Any]):
        """Create a performance alert"""
        try:
            alert_doc = {
                **alert_data,
                "created_at": datetime.utcnow(),
                "processed": False,
                "resolved": False
            }
            
            # Check if similar alert exists recently
            recent_cutoff = datetime.utcnow() - timedelta(minutes=10)
            existing_alert = await self.db.performance_alerts.find_one({
                "alert_type": alert_data["alert_type"],
                "created_at": {"$gte": recent_cutoff},
                "resolved": False
            })
            
            if not existing_alert:
                await self.db.performance_alerts.insert_one(alert_doc)
                logger.warning(f"Performance alert created: {alert_data['alert_type']} - {alert_data['message']}")
            
        except Exception as e:
            logger.error(f"Error creating alert: {e}")
    
    async def _process_alert(self, alert: Dict[str, Any]):
        """Process a performance alert"""
        try:
            alert_type = alert.get("alert_type")
            severity = alert.get("severity")
            
            # Log the alert
            logger.warning(f"Processing alert: {alert_type} (severity: {severity})")
            
            # Take automated actions based on alert type
            if alert_type == "high_memory_usage":
                await self._handle_high_memory_usage()
            elif alert_type == "low_cache_hit_rate":
                await self._handle_low_cache_hit_rate()
            elif alert_type == "high_error_rate":
                await self._handle_high_error_rate()
            
            # Mark alert as processed
            await self.db.performance_alerts.update_one(
                {"_id": alert["_id"]},
                {"$set": {"processed": True, "processed_at": datetime.utcnow()}}
            )
            
        except Exception as e:
            logger.error(f"Error processing alert: {e}")
    
    async def _handle_high_memory_usage(self):
        """Handle high memory usage alert"""
        try:
            # Clear expired cache entries
            await enhanced_cache_service.cleanup_expired_cache()
            
            # Reset cache statistics to free up memory
            enhanced_cache_service.reset_cache_statistics()
            
            logger.info("Handled high memory usage by cleaning up cache")
            
        except Exception as e:
            logger.error(f"Error handling high memory usage: {e}")
    
    async def _handle_low_cache_hit_rate(self):
        """Handle low cache hit rate alert"""
        try:
            # This could trigger cache warming for active users
            logger.info("Low cache hit rate detected - consider cache warming")
            
        except Exception as e:
            logger.error(f"Error handling low cache hit rate: {e}")
    
    async def _handle_high_error_rate(self):
        """Handle high error rate alert"""
        try:
            # Log additional debugging information
            logger.error(f"High error rate detected - Total errors: {self.error_count}, Total requests: {self.request_count}")
            
        except Exception as e:
            logger.error(f"Error handling high error rate: {e}")
    
    def _calculate_requests_per_minute(self) -> float:
        """Calculate requests per minute"""
        # This is a simplified calculation
        # In a real implementation, you'd track requests over time windows
        return self.request_count / max(1, (datetime.utcnow().minute or 1))
    
    # Public methods for tracking application metrics
    def track_request_start(self):
        """Track the start of a request"""
        self.active_requests += 1
    
    def track_request_end(self, response_time: float, success: bool = True):
        """Track the end of a request"""
        self.active_requests = max(0, self.active_requests - 1)
        self.request_count += 1
        self.request_times.append(response_time)
        
        if not success:
            self.error_count += 1
    
    async def get_current_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        try:
            # Get cached metrics
            system_metrics = await cache_manager.get_cache("current_system_metrics")
            database_metrics = await cache_manager.get_cache("current_database_metrics")
            cache_metrics = await cache_manager.get_cache("current_cache_metrics")
            application_metrics = await cache_manager.get_cache("current_application_metrics")
            
            return {
                "system": system_metrics,
                "database": database_metrics,
                "cache": cache_metrics,
                "application": application_metrics,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting current metrics: {e}")
            return {"error": str(e)}
    
    async def get_performance_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get performance summary for the specified time period"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            # Get metrics from database
            metrics_cursor = self.db.performance_metrics.find({
                "created_at": {"$gte": cutoff_time}
            }).sort("created_at", -1)
            
            metrics_list = await metrics_cursor.to_list(length=None)
            
            # Get alerts
            alerts_cursor = self.db.performance_alerts.find({
                "created_at": {"$gte": cutoff_time}
            }).sort("created_at", -1)
            
            alerts_list = await alerts_cursor.to_list(length=None)
            
            return {
                "time_period_hours": hours,
                "total_metrics_collected": len(metrics_list),
                "total_alerts": len(alerts_list),
                "unresolved_alerts": len([a for a in alerts_list if not a.get("resolved", False)]),
                "alert_types": list(set(a.get("alert_type") for a in alerts_list)),
                "metrics_by_type": self._group_metrics_by_type(metrics_list),
                "recent_alerts": alerts_list[:10]  # Last 10 alerts
            }
            
        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return {"error": str(e)}
    
    def _group_metrics_by_type(self, metrics_list: List[Dict[str, Any]]) -> Dict[str, int]:
        """Group metrics by type"""
        grouped = {}
        for metric in metrics_list:
            metric_type = metric.get("metric_type", "unknown")
            grouped[metric_type] = grouped.get(metric_type, 0) + 1
        return grouped
    
    async def cleanup_old_metrics(self):
        """Clean up old performance metrics"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.metrics_retention_days)
            
            # Delete old metrics
            metrics_result = await self.db.performance_metrics.delete_many({
                "created_at": {"$lt": cutoff_date}
            })
            
            # Delete old resolved alerts
            alerts_result = await self.db.performance_alerts.delete_many({
                "created_at": {"$lt": cutoff_date},
                "resolved": True
            })
            
            logger.info(f"Cleaned up {metrics_result.deleted_count} old metrics and "
                       f"{alerts_result.deleted_count} old alerts")
            
            return {
                "metrics_deleted": metrics_result.deleted_count,
                "alerts_deleted": alerts_result.deleted_count
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up old metrics: {e}")
            return {"error": str(e)}


# Global instance for performance monitoring service
performance_monitoring_service = PerformanceMonitoringService()