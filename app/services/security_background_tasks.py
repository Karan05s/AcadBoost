"""
Security Background Tasks
Handles periodic security monitoring, data integrity checks, and automated alerting
"""
import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.security_monitoring_service import SecurityMonitoringService
from app.services.security_service import SecurityService
from app.core.database import get_database

logger = logging.getLogger(__name__)


class SecurityBackgroundTasks:
    """Service for running security monitoring background tasks"""
    
    def __init__(self):
        self.monitoring_service = None
        self.security_service = None
        self.db = None
        self.running = False
        
        # Task intervals (in seconds)
        self.data_integrity_check_interval = 3600  # 1 hour
        self.security_analysis_interval = 300      # 5 minutes
        self.cleanup_interval = 86400              # 24 hours
        self.compliance_check_interval = 1800      # 30 minutes
    
    async def initialize(self):
        """Initialize the background tasks service"""
        try:
            self.db = await get_database()
            if self.db:
                self.monitoring_service = SecurityMonitoringService(self.db)
                self.security_service = SecurityService(self.db)
                logger.info("Security background tasks initialized successfully")
            else:
                logger.error("Failed to initialize database connection for security background tasks")
        except Exception as e:
            logger.error(f"Error initializing security background tasks: {e}")
    
    async def start_background_monitoring(self):
        """Start all background monitoring tasks"""
        if not self.db or not self.monitoring_service:
            await self.initialize()
        
        if not self.db or not self.monitoring_service:
            logger.error("Cannot start background monitoring: services not initialized")
            return
        
        self.running = True
        logger.info("Starting security background monitoring tasks")
        
        # Start all monitoring tasks concurrently
        tasks = [
            asyncio.create_task(self._periodic_data_integrity_check()),
            asyncio.create_task(self._periodic_security_analysis()),
            asyncio.create_task(self._periodic_cleanup()),
            asyncio.create_task(self._periodic_compliance_check())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Error in background monitoring tasks: {e}")
        finally:
            self.running = False
    
    async def stop_background_monitoring(self):
        """Stop background monitoring tasks"""
        self.running = False
        logger.info("Stopping security background monitoring tasks")
    
    async def _periodic_data_integrity_check(self):
        """Periodically check data integrity across collections"""
        while self.running:
            try:
                logger.info("Starting periodic data integrity check")
                
                # Define collections to check and their schemas
                collections_to_check = {
                    "users": {
                        "user_id": {"type": "string", "required": True},
                        "email": {"type": "string", "required": True, "validation": {"pattern": r"^[^@]+@[^@]+\.[^@]+$"}},
                        "username": {"type": "string", "required": True, "validation": {"min_length": 3}},
                        "created_at": {"type": "datetime", "required": True},
                        "role": {"type": "string", "required": True}
                    },
                    "student_performance": {
                        "student_id": {"type": "string", "required": True},
                        "submission_type": {"type": "string", "required": True},
                        "timestamp": {"type": "datetime", "required": True},
                        "score": {"type": "float", "required": True}
                    },
                    "learning_gaps": {
                        "student_id": {"type": "string", "required": True},
                        "concept_id": {"type": "string", "required": True},
                        "gap_severity": {"type": "float", "required": True},
                        "confidence_score": {"type": "float", "required": True}
                    },
                    "recommendations": {
                        "student_id": {"type": "string", "required": True},
                        "resource_type": {"type": "string", "required": True},
                        "priority_score": {"type": "float", "required": True},
                        "generated_at": {"type": "datetime", "required": True}
                    }
                }
                
                for collection_name, schema in collections_to_check.items():
                    try:
                        # Get sample data from collection
                        collection = self.db[collection_name]
                        sample_data = await collection.find().limit(100).to_list(length=100)
                        
                        if sample_data:
                            # Perform integrity check
                            results = await self.monitoring_service.monitor_data_corruption(
                                collection_name=collection_name,
                                data_sample=sample_data,
                                expected_schema=schema
                            )
                            
                            logger.info(f"Data integrity check completed for {collection_name}: "
                                      f"{results.get('corruption_rate', 0):.2%} corruption rate")
                        
                    except Exception as e:
                        logger.error(f"Error checking integrity for collection {collection_name}: {e}")
                
                logger.info("Periodic data integrity check completed")
                
            except Exception as e:
                logger.error(f"Error in periodic data integrity check: {e}")
            
            # Wait for next check
            await asyncio.sleep(self.data_integrity_check_interval)
    
    async def _periodic_security_analysis(self):
        """Periodically analyze security events for patterns and threats"""
        while self.running:
            try:
                logger.info("Starting periodic security analysis")
                
                # Analyze recent unprocessed events
                cutoff_time = datetime.utcnow() - timedelta(minutes=10)
                
                unprocessed_events = await self.db.security_events.find({
                    "processed": False,
                    "timestamp": {"$gte": cutoff_time}
                }).to_list(length=None)
                
                for event in unprocessed_events:
                    try:
                        # Re-analyze the event (this will trigger pattern detection)
                        await self.monitoring_service._analyze_security_event(event)
                        
                    except Exception as e:
                        logger.error(f"Error analyzing security event {event.get('event_id')}: {e}")
                
                # Check for new threat patterns
                await self._analyze_threat_patterns()
                
                # Check for anomalous user behavior
                await self._analyze_user_behavior_anomalies()
                
                logger.info(f"Periodic security analysis completed - processed {len(unprocessed_events)} events")
                
            except Exception as e:
                logger.error(f"Error in periodic security analysis: {e}")
            
            # Wait for next analysis
            await asyncio.sleep(self.security_analysis_interval)
    
    async def _periodic_cleanup(self):
        """Periodically clean up old data and expired sessions"""
        while self.running:
            try:
                logger.info("Starting periodic cleanup")
                
                # Clean up expired sessions
                if self.security_service:
                    session_cleanup_count = await self.security_service.cleanup_expired_sessions()
                    logger.info(f"Cleaned up {session_cleanup_count} expired sessions")
                
                # Clean up old security events (keep 90 days)
                if self.monitoring_service:
                    events_cleanup_count = await self.monitoring_service.cleanup_old_events(retention_days=90)
                    logger.info(f"Cleaned up {events_cleanup_count} old security events")
                
                # Clean up old resolved alerts (keep 30 days)
                cutoff_date = datetime.utcnow() - timedelta(days=30)
                alerts_result = await self.db.security_alerts.delete_many({
                    "resolved": True,
                    "resolved_at": {"$lt": cutoff_date}
                })
                logger.info(f"Cleaned up {alerts_result.deleted_count} old resolved alerts")
                
                # Clean up old resolved compliance violations (keep 365 days for audit)
                compliance_cutoff = datetime.utcnow() - timedelta(days=365)
                compliance_result = await self.db.compliance_violations.delete_many({
                    "resolved": True,
                    "resolved_at": {"$lt": compliance_cutoff}
                })
                logger.info(f"Cleaned up {compliance_result.deleted_count} old compliance violations")
                
                logger.info("Periodic cleanup completed")
                
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
            
            # Wait for next cleanup (daily)
            await asyncio.sleep(self.cleanup_interval)
    
    async def _periodic_compliance_check(self):
        """Periodically check for compliance violations"""
        while self.running:
            try:
                logger.info("Starting periodic compliance check")
                
                # Check for data retention violations
                await self._check_data_retention_compliance()
                
                # Check for unauthorized data access patterns
                await self._check_data_access_compliance()
                
                # Check for data sharing compliance
                await self._check_data_sharing_compliance()
                
                logger.info("Periodic compliance check completed")
                
            except Exception as e:
                logger.error(f"Error in periodic compliance check: {e}")
            
            # Wait for next compliance check
            await asyncio.sleep(self.compliance_check_interval)
    
    async def _analyze_threat_patterns(self):
        """Analyze recent events for emerging threat patterns"""
        try:
            # Look for coordinated attacks from multiple IPs
            recent_cutoff = datetime.utcnow() - timedelta(hours=1)
            
            # Group events by IP address
            pipeline = [
                {"$match": {
                    "timestamp": {"$gte": recent_cutoff},
                    "threat_score": {"$gte": 5.0}
                }},
                {"$group": {
                    "_id": "$ip_address",
                    "event_count": {"$sum": 1},
                    "max_threat_score": {"$max": "$threat_score"},
                    "event_types": {"$addToSet": "$event_type"}
                }},
                {"$match": {"event_count": {"$gte": 5}}}
            ]
            
            threat_sources = await self.db.security_events.aggregate(pipeline).to_list(length=None)
            
            for source in threat_sources:
                # Create alert for coordinated attack
                await self.monitoring_service.log_security_event(
                    event_type="coordinated_attack_detected",
                    ip_address=source["_id"],
                    event_details={
                        "event_count": source["event_count"],
                        "max_threat_score": source["max_threat_score"],
                        "event_types": source["event_types"],
                        "time_window": "1_hour"
                    },
                    severity="critical"
                )
            
        except Exception as e:
            logger.error(f"Error analyzing threat patterns: {e}")
    
    async def _analyze_user_behavior_anomalies(self):
        """Analyze user behavior for anomalies"""
        try:
            # Check for users with unusual activity patterns
            recent_cutoff = datetime.utcnow() - timedelta(days=7)
            
            # Find users with significantly increased activity
            pipeline = [
                {"$match": {
                    "timestamp": {"$gte": recent_cutoff},
                    "user_id": {"$exists": True, "$ne": None}
                }},
                {"$group": {
                    "_id": "$user_id",
                    "event_count": {"$sum": 1},
                    "unique_ips": {"$addToSet": "$ip_address"},
                    "event_types": {"$addToSet": "$event_type"}
                }},
                {"$match": {"event_count": {"$gte": 50}}}  # More than 50 events in a week
            ]
            
            active_users = await self.db.security_events.aggregate(pipeline).to_list(length=None)
            
            for user in active_users:
                # Check if this is unusual for this user
                historical_cutoff = datetime.utcnow() - timedelta(days=30)
                historical_count = await self.db.security_events.count_documents({
                    "user_id": user["_id"],
                    "timestamp": {"$gte": historical_cutoff, "$lt": recent_cutoff}
                })
                
                # If recent activity is 3x higher than historical average, flag as anomaly
                if historical_count > 0 and user["event_count"] > (historical_count * 3):
                    await self.monitoring_service.log_security_event(
                        event_type="user_behavior_anomaly",
                        user_id=user["_id"],
                        event_details={
                            "recent_event_count": user["event_count"],
                            "historical_average": historical_count,
                            "unique_ips": len(user["unique_ips"]),
                            "event_types": user["event_types"]
                        },
                        severity="high"
                    )
            
        except Exception as e:
            logger.error(f"Error analyzing user behavior anomalies: {e}")
    
    async def _check_data_retention_compliance(self):
        """Check for data retention compliance violations"""
        try:
            # Check for student data older than retention policy (7 years for FERPA)
            retention_cutoff = datetime.utcnow() - timedelta(days=7*365)  # 7 years
            
            # Check student performance data
            old_performance_data = await self.db.student_performance.count_documents({
                "timestamp": {"$lt": retention_cutoff}
            })
            
            if old_performance_data > 0:
                await self.monitoring_service.log_security_event(
                    event_type="data_retention_violation",
                    event_details={
                        "violation_type": "student_data_retention_exceeded",
                        "collection": "student_performance",
                        "old_records_count": old_performance_data,
                        "retention_policy": "7_years"
                    },
                    severity="high"
                )
            
            # Check user data for inactive accounts
            inactive_cutoff = datetime.utcnow() - timedelta(days=2*365)  # 2 years inactive
            
            inactive_users = await self.db.users.count_documents({
                "last_login": {"$lt": inactive_cutoff},
                "account_status": {"$ne": "deleted"}
            })
            
            if inactive_users > 0:
                await self.monitoring_service.log_security_event(
                    event_type="data_retention_violation",
                    event_details={
                        "violation_type": "inactive_user_data_retention",
                        "collection": "users",
                        "inactive_accounts_count": inactive_users,
                        "inactive_period": "2_years"
                    },
                    severity="medium"
                )
            
        except Exception as e:
            logger.error(f"Error checking data retention compliance: {e}")
    
    async def _check_data_access_compliance(self):
        """Check for data access compliance violations"""
        try:
            # Check for cross-student data access by students
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            
            cross_access_events = await self.db.security_events.find({
                "event_type": "data_access_violation",
                "timestamp": {"$gte": recent_cutoff}
            }).to_list(length=None)
            
            if cross_access_events:
                for event in cross_access_events:
                    # This is already logged as a security event, but we need to check
                    # if it constitutes a compliance violation
                    event_details = event.get("event_details", {})
                    
                    if event_details.get("user_role") == "student":
                        # Student accessing another student's data is a FERPA violation
                        await self.monitoring_service._log_compliance_violation(
                            event_id=event["event_id"],
                            user_id=event.get("user_id"),
                            violation_type="unauthorized_student_data_access",
                            regulation="FERPA",
                            description="Student attempted to access another student's educational records",
                            event_details=event_details
                        )
            
        except Exception as e:
            logger.error(f"Error checking data access compliance: {e}")
    
    async def _check_data_sharing_compliance(self):
        """Check for data sharing compliance violations"""
        try:
            # Check for external data sharing events
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            
            sharing_events = await self.db.security_events.find({
                "event_type": "data_export",
                "timestamp": {"$gte": recent_cutoff},
                "event_details.external_sharing": True
            }).to_list(length=None)
            
            for event in sharing_events:
                # Check if proper consent was obtained
                event_details = event.get("event_details", {})
                
                if not event_details.get("consent_obtained"):
                    await self.monitoring_service._log_compliance_violation(
                        event_id=event["event_id"],
                        user_id=event.get("user_id"),
                        violation_type="unauthorized_data_sharing",
                        regulation="FERPA",
                        description="Student data shared externally without proper consent",
                        event_details=event_details
                    )
            
        except Exception as e:
            logger.error(f"Error checking data sharing compliance: {e}")
    
    async def run_manual_security_scan(self) -> Dict[str, Any]:
        """Run a manual comprehensive security scan"""
        try:
            logger.info("Starting manual security scan")
            
            scan_results = {
                "scan_id": f"manual_scan_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                "timestamp": datetime.utcnow().isoformat(),
                "results": {}
            }
            
            # Data integrity check
            logger.info("Running data integrity checks...")
            integrity_results = {}
            
            collections_to_check = ["users", "student_performance", "learning_gaps", "recommendations"]
            for collection_name in collections_to_check:
                try:
                    collection = self.db[collection_name]
                    sample_data = await collection.find().limit(50).to_list(length=50)
                    
                    if sample_data:
                        # Use basic schema for manual scan
                        basic_schema = {
                            "_id": {"type": "string", "required": True},
                            "created_at": {"type": "datetime", "required": False}
                        }
                        
                        results = await self.monitoring_service.monitor_data_corruption(
                            collection_name=collection_name,
                            data_sample=sample_data,
                            expected_schema=basic_schema
                        )
                        
                        integrity_results[collection_name] = {
                            "corruption_rate": results.get("corruption_rate", 0),
                            "corrupted_records": results.get("corrupted_records", 0),
                            "total_records": results.get("total_records", 0)
                        }
                
                except Exception as e:
                    integrity_results[collection_name] = {"error": str(e)}
            
            scan_results["results"]["data_integrity"] = integrity_results
            
            # Security events analysis
            logger.info("Analyzing recent security events...")
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            
            event_stats = await self.db.security_events.aggregate([
                {"$match": {"timestamp": {"$gte": recent_cutoff}}},
                {"$group": {
                    "_id": "$event_type",
                    "count": {"$sum": 1},
                    "avg_threat_score": {"$avg": "$threat_score"}
                }}
            ]).to_list(length=None)
            
            scan_results["results"]["security_events"] = event_stats
            
            # Active alerts
            logger.info("Checking active alerts...")
            active_alerts = await self.db.security_alerts.count_documents({
                "resolved": False
            })
            
            scan_results["results"]["active_alerts"] = active_alerts
            
            # Compliance violations
            logger.info("Checking compliance violations...")
            unresolved_violations = await self.db.compliance_violations.count_documents({
                "resolved": False
            })
            
            scan_results["results"]["unresolved_compliance_violations"] = unresolved_violations
            
            logger.info("Manual security scan completed")
            return scan_results
            
        except Exception as e:
            logger.error(f"Error in manual security scan: {e}")
            return {"error": str(e)}


# Global instance for background tasks
security_background_tasks = SecurityBackgroundTasks()