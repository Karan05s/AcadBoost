"""
Security Monitoring Service
Handles security event logging, unauthorized access detection, and compliance monitoring
"""
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.redis_client import cache_manager
import logging
import json
import hashlib
import uuid
import asyncio
from collections import defaultdict

logger = logging.getLogger(__name__)


class SecurityMonitoringService:
    """Service for security monitoring, alerting, and compliance violation detection"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.security_events_collection = db.security_events
        self.security_alerts_collection = db.security_alerts
        self.compliance_violations_collection = db.compliance_violations
        self.data_integrity_checks_collection = db.data_integrity_checks
        
        # Security thresholds
        self.failed_login_threshold = 5
        self.suspicious_access_threshold = 10
        self.data_corruption_threshold = 0.01  # 1% corruption rate
        self.alert_cooldown_minutes = 15
    
    async def log_security_event(
        self,
        event_type: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_accessed: Optional[str] = None,
        event_details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
        source: str = "system"
    ) -> str:
        """
        Log security event with automatic threat detection
        
        Args:
            event_type: Type of security event (login_failed, unauthorized_access, etc.)
            user_id: User ID if applicable
            ip_address: Client IP address
            user_agent: Client user agent
            resource_accessed: Resource that was accessed
            event_details: Additional event details
            severity: Event severity (info, warning, critical)
            source: Event source (system, user, external)
        """
        
        event_id = str(uuid.uuid4())
        
        security_event = {
            "event_id": event_id,
            "event_type": event_type,
            "user_id": user_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "resource_accessed": resource_accessed,
            "event_details": event_details or {},
            "severity": severity,
            "source": source,
            "timestamp": datetime.utcnow(),
            "processed": False,
            "threat_score": 0,
            "geolocation": await self._get_geolocation(ip_address) if ip_address else None,
            "device_fingerprint": self._generate_device_fingerprint(user_agent, ip_address)
        }
        
        try:
            # Calculate threat score
            security_event["threat_score"] = await self._calculate_threat_score(security_event)
            
            # Store security event
            await self.security_events_collection.insert_one(security_event)
            
            # Trigger real-time analysis
            asyncio.create_task(self._analyze_security_event(security_event))
            
            logger.info(f"Security event logged: {event_id} - {event_type} (severity: {severity})")
            return event_id
            
        except Exception as e:
            logger.error(f"Failed to log security event: {e}")
            raise
    
    async def _calculate_threat_score(self, event: Dict[str, Any]) -> float:
        """Calculate threat score based on event characteristics"""
        
        score = 0.0
        
        # Base scores by event type
        event_scores = {
            "login_failed": 2.0,
            "unauthorized_access": 8.0,
            "data_access_violation": 7.0,
            "suspicious_activity": 5.0,
            "data_corruption_detected": 9.0,
            "compliance_violation": 6.0,
            "brute_force_attempt": 8.0,
            "privilege_escalation": 9.0,
            "data_exfiltration": 10.0
        }
        
        score += event_scores.get(event["event_type"], 1.0)
        
        # IP reputation check
        if event.get("ip_address"):
            ip_reputation = await self._check_ip_reputation(event["ip_address"])
            score += ip_reputation * 3.0
        
        # Frequency analysis
        if event.get("user_id"):
            recent_events = await self._get_recent_events_count(
                event["user_id"], 
                event["ip_address"], 
                minutes=60
            )
            if recent_events > 10:
                score += min(recent_events * 0.5, 5.0)
        
        # Time-based analysis (unusual hours)
        hour = event["timestamp"].hour
        if hour < 6 or hour > 22:  # Outside normal business hours
            score += 1.0
        
        # Geographic anomaly
        if event.get("geolocation"):
            geo_score = await self._check_geographic_anomaly(event["user_id"], event["geolocation"])
            score += geo_score
        
        return min(score, 10.0)  # Cap at 10.0
    
    async def _analyze_security_event(self, event: Dict[str, Any]) -> None:
        """Analyze security event and trigger alerts if necessary"""
        
        try:
            # Check for immediate threats
            if event["threat_score"] >= 7.0:
                await self._create_security_alert(
                    alert_type="high_threat_detected",
                    event_id=event["event_id"],
                    severity="critical",
                    details={
                        "threat_score": event["threat_score"],
                        "event_type": event["event_type"],
                        "user_id": event.get("user_id"),
                        "ip_address": event.get("ip_address")
                    }
                )
            
            # Check for patterns
            await self._check_attack_patterns(event)
            
            # Check for compliance violations
            await self._check_compliance_violations(event)
            
            # Update event as processed
            await self.security_events_collection.update_one(
                {"event_id": event["event_id"]},
                {"$set": {"processed": True, "processed_at": datetime.utcnow()}}
            )
            
        except Exception as e:
            logger.error(f"Error analyzing security event {event['event_id']}: {e}")
    
    async def _check_attack_patterns(self, event: Dict[str, Any]) -> None:
        """Check for common attack patterns"""
        
        try:
            # Brute force detection
            if event["event_type"] == "login_failed":
                await self._check_brute_force_attack(event)
            
            # Suspicious access patterns
            if event.get("user_id"):
                await self._check_suspicious_access_patterns(event)
            
            # Data exfiltration detection
            if event["event_type"] in ["data_access", "data_export"]:
                await self._check_data_exfiltration_patterns(event)
                
        except Exception as e:
            logger.error(f"Error checking attack patterns: {e}")
    
    async def _check_brute_force_attack(self, event: Dict[str, Any]) -> None:
        """Check for brute force attack patterns"""
        
        try:
            # Check failed login attempts in last 15 minutes
            cutoff_time = datetime.utcnow() - timedelta(minutes=15)
            
            query = {
                "event_type": "login_failed",
                "timestamp": {"$gte": cutoff_time}
            }
            
            # Check by IP address
            if event.get("ip_address"):
                ip_query = {**query, "ip_address": event["ip_address"]}
                ip_attempts = await self.security_events_collection.count_documents(ip_query)
                
                if ip_attempts >= self.failed_login_threshold:
                    await self._create_security_alert(
                        alert_type="brute_force_attack",
                        event_id=event["event_id"],
                        severity="critical",
                        details={
                            "ip_address": event["ip_address"],
                            "failed_attempts": ip_attempts,
                            "time_window": "15_minutes"
                        }
                    )
            
            # Check by user ID
            if event.get("user_id"):
                user_query = {**query, "user_id": event["user_id"]}
                user_attempts = await self.security_events_collection.count_documents(user_query)
                
                if user_attempts >= self.failed_login_threshold:
                    await self._create_security_alert(
                        alert_type="account_compromise_attempt",
                        event_id=event["event_id"],
                        severity="high",
                        details={
                            "user_id": event["user_id"],
                            "failed_attempts": user_attempts,
                            "time_window": "15_minutes"
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Error checking brute force attack: {e}")
    
    async def _check_suspicious_access_patterns(self, event: Dict[str, Any]) -> None:
        """Check for suspicious access patterns"""
        
        try:
            user_id = event.get("user_id")
            if not user_id:
                return
            
            # Check for unusual access times
            hour = event["timestamp"].hour
            if hour < 6 or hour > 22:
                # Check if this is unusual for this user
                normal_hours_query = {
                    "user_id": user_id,
                    "timestamp": {
                        "$gte": datetime.utcnow() - timedelta(days=30),
                        "$lt": datetime.utcnow()
                    }
                }
                
                total_events = await self.security_events_collection.count_documents(normal_hours_query)
                
                unusual_hours_query = {
                    **normal_hours_query,
                    "$expr": {
                        "$or": [
                            {"$lt": [{"$hour": "$timestamp"}, 6]},
                            {"$gt": [{"$hour": "$timestamp"}, 22]}
                        ]
                    }
                }
                
                unusual_events = await self.security_events_collection.count_documents(unusual_hours_query)
                
                if total_events > 10 and unusual_events / total_events > 0.8:
                    await self._create_security_alert(
                        alert_type="unusual_access_time",
                        event_id=event["event_id"],
                        severity="medium",
                        details={
                            "user_id": user_id,
                            "access_hour": hour,
                            "unusual_ratio": unusual_events / total_events
                        }
                    )
            
            # Check for rapid successive access attempts
            recent_cutoff = datetime.utcnow() - timedelta(minutes=5)
            recent_events = await self.security_events_collection.count_documents({
                "user_id": user_id,
                "timestamp": {"$gte": recent_cutoff}
            })
            
            if recent_events > self.suspicious_access_threshold:
                await self._create_security_alert(
                    alert_type="rapid_access_attempts",
                    event_id=event["event_id"],
                    severity="high",
                    details={
                        "user_id": user_id,
                        "events_count": recent_events,
                        "time_window": "5_minutes"
                    }
                )
                
        except Exception as e:
            logger.error(f"Error checking suspicious access patterns: {e}")
    
    async def _check_data_exfiltration_patterns(self, event: Dict[str, Any]) -> None:
        """Check for data exfiltration patterns"""
        
        try:
            user_id = event.get("user_id")
            if not user_id:
                return
            
            # Check for large data exports in short time
            cutoff_time = datetime.utcnow() - timedelta(hours=1)
            
            export_events = await self.security_events_collection.find({
                "user_id": user_id,
                "event_type": {"$in": ["data_export", "data_access"]},
                "timestamp": {"$gte": cutoff_time}
            }).to_list(length=None)
            
            if len(export_events) > 5:
                total_records = sum(
                    event.get("event_details", {}).get("records_accessed", 0) 
                    for event in export_events
                )
                
                if total_records > 1000:  # Threshold for large data access
                    await self._create_security_alert(
                        alert_type="potential_data_exfiltration",
                        event_id=event["event_id"],
                        severity="critical",
                        details={
                            "user_id": user_id,
                            "export_events": len(export_events),
                            "total_records": total_records,
                            "time_window": "1_hour"
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Error checking data exfiltration patterns: {e}")
    
    async def _check_compliance_violations(self, event: Dict[str, Any]) -> None:
        """Check for compliance violations (FERPA, etc.)"""
        
        try:
            violation_detected = False
            violation_details = {}
            
            # Check for unauthorized student data access
            if event["event_type"] == "data_access_violation":
                violation_detected = True
                violation_details = {
                    "violation_type": "unauthorized_student_data_access",
                    "regulation": "FERPA",
                    "description": "Attempted access to student data without proper authorization"
                }
            
            # Check for data retention violations
            if event["event_type"] == "data_retention_violation":
                violation_detected = True
                violation_details = {
                    "violation_type": "data_retention_policy_violation",
                    "regulation": "FERPA",
                    "description": "Data retained beyond allowed retention period"
                }
            
            # Check for improper data sharing
            if event.get("event_details", {}).get("data_shared_externally"):
                violation_detected = True
                violation_details = {
                    "violation_type": "unauthorized_data_sharing",
                    "regulation": "FERPA",
                    "description": "Student data shared with unauthorized external parties"
                }
            
            if violation_detected:
                await self._log_compliance_violation(
                    event_id=event["event_id"],
                    user_id=event.get("user_id"),
                    violation_type=violation_details["violation_type"],
                    regulation=violation_details["regulation"],
                    description=violation_details["description"],
                    event_details=event.get("event_details", {})
                )
                
        except Exception as e:
            logger.error(f"Error checking compliance violations: {e}")
    
    async def _log_compliance_violation(
        self,
        event_id: str,
        user_id: Optional[str],
        violation_type: str,
        regulation: str,
        description: str,
        event_details: Dict[str, Any]
    ) -> None:
        """Log compliance violation"""
        
        try:
            violation_record = {
                "violation_id": str(uuid.uuid4()),
                "event_id": event_id,
                "user_id": user_id,
                "violation_type": violation_type,
                "regulation": regulation,
                "description": description,
                "event_details": event_details,
                "timestamp": datetime.utcnow(),
                "severity": "critical",
                "resolved": False,
                "resolution_notes": None,
                "resolved_at": None
            }
            
            await self.compliance_violations_collection.insert_one(violation_record)
            
            # Create critical alert for compliance violation
            await self._create_security_alert(
                alert_type="compliance_violation",
                event_id=event_id,
                severity="critical",
                details={
                    "violation_type": violation_type,
                    "regulation": regulation,
                    "description": description,
                    "user_id": user_id
                }
            )
            
            logger.critical(f"Compliance violation detected: {violation_type} - {description}")
            
        except Exception as e:
            logger.error(f"Error logging compliance violation: {e}")
    
    async def detect_unauthorized_access(
        self,
        user_id: str,
        resource_id: str,
        resource_type: str,
        access_type: str,
        user_role: str,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Detect unauthorized access attempts
        
        Returns True if access is unauthorized, False if authorized
        """
        
        try:
            # Define access rules based on resource type and user role
            access_rules = {
                "student_data": {
                    "student": ["read_own"],
                    "instructor": ["read_class", "read_own"],
                    "admin": ["read_all", "write_all", "delete_all"]
                },
                "analytics_data": {
                    "student": ["read_own"],
                    "instructor": ["read_class"],
                    "admin": ["read_all", "write_all"]
                },
                "system_config": {
                    "admin": ["read_all", "write_all"]
                }
            }
            
            allowed_actions = access_rules.get(resource_type, {}).get(user_role, [])
            
            # Check if access type is allowed
            unauthorized = False
            
            # First check if the access type is generally allowed for this role
            if access_type not in allowed_actions:
                unauthorized = True
            else:
                # Even if access type is allowed, check for specific restrictions
                if access_type == "read_own" and resource_id != user_id:
                    unauthorized = True
                elif access_type == "read_class" and user_role not in ["instructor", "admin"]:
                    unauthorized = True
            
            if unauthorized:
                # Log unauthorized access attempt
                await self.log_security_event(
                    event_type="unauthorized_access",
                    user_id=user_id,
                    ip_address=ip_address,
                    resource_accessed=f"{resource_type}:{resource_id}",
                    event_details={
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "access_type": access_type,
                        "user_role": user_role,
                        "allowed_actions": allowed_actions
                    },
                    severity="high"
                )
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error detecting unauthorized access: {e}")
            return False
    
    async def monitor_data_corruption(
        self,
        collection_name: str,
        data_sample: List[Dict[str, Any]],
        expected_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Monitor data corruption in collections
        
        Returns corruption analysis results
        """
        
        try:
            corruption_results = {
                "collection": collection_name,
                "total_records": len(data_sample),
                "corrupted_records": 0,
                "corruption_types": defaultdict(int),
                "corruption_rate": 0.0,
                "timestamp": datetime.utcnow(),
                "alert_triggered": False
            }
            
            for record in data_sample:
                corruption_issues = await self._check_record_integrity(record, expected_schema)
                
                if corruption_issues:
                    corruption_results["corrupted_records"] += 1
                    
                    for issue_type in corruption_issues:
                        corruption_results["corruption_types"][issue_type] += 1
            
            # Calculate corruption rate
            if corruption_results["total_records"] > 0:
                corruption_results["corruption_rate"] = (
                    corruption_results["corrupted_records"] / corruption_results["total_records"]
                )
            
            # Check if corruption rate exceeds threshold
            if corruption_results["corruption_rate"] > self.data_corruption_threshold:
                corruption_results["alert_triggered"] = True
                
                await self._create_security_alert(
                    alert_type="data_corruption_detected",
                    event_id=str(uuid.uuid4()),
                    severity="critical",
                    details={
                        "collection": collection_name,
                        "corruption_rate": corruption_results["corruption_rate"],
                        "corrupted_records": corruption_results["corrupted_records"],
                        "total_records": corruption_results["total_records"],
                        "corruption_types": dict(corruption_results["corruption_types"])
                    }
                )
                
                # Log security event
                await self.log_security_event(
                    event_type="data_corruption_detected",
                    event_details={
                        "collection": collection_name,
                        "corruption_analysis": corruption_results
                    },
                    severity="critical"
                )
            
            # Store integrity check results
            await self.data_integrity_checks_collection.insert_one(corruption_results)
            
            return corruption_results
            
        except Exception as e:
            logger.error(f"Error monitoring data corruption: {e}")
            return {"error": str(e)}
    
    async def _check_record_integrity(
        self,
        record: Dict[str, Any],
        expected_schema: Dict[str, Any]
    ) -> List[str]:
        """Check individual record integrity against expected schema"""
        
        issues = []
        
        try:
            # Check required fields
            for field, field_config in expected_schema.items():
                if field_config.get("required", False) and field not in record:
                    issues.append(f"missing_required_field_{field}")
                
                if field in record:
                    expected_type = field_config.get("type")
                    actual_value = record[field]
                    
                    # Type checking
                    if expected_type and not self._check_field_type(actual_value, expected_type):
                        issues.append(f"invalid_type_{field}")
                    
                    # Value validation
                    if "validation" in field_config:
                        validation_rules = field_config["validation"]
                        
                        if "min_length" in validation_rules and isinstance(actual_value, str):
                            if len(actual_value) < validation_rules["min_length"]:
                                issues.append(f"invalid_length_{field}")
                        
                        if "pattern" in validation_rules and isinstance(actual_value, str):
                            import re
                            if not re.match(validation_rules["pattern"], actual_value):
                                issues.append(f"invalid_pattern_{field}")
            
            # Check for suspicious data patterns
            if self._detect_suspicious_data_patterns(record):
                issues.append("suspicious_data_pattern")
            
            return issues
            
        except Exception as e:
            logger.error(f"Error checking record integrity: {e}")
            return ["integrity_check_error"]
    
    def _check_field_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type"""
        
        type_mapping = {
            "string": str,
            "integer": int,
            "float": float,
            "boolean": bool,
            "datetime": datetime,
            "list": list,
            "dict": dict
        }
        
        expected_python_type = type_mapping.get(expected_type)
        if not expected_python_type:
            return True  # Unknown type, skip validation
        
        return isinstance(value, expected_python_type)
    
    def _detect_suspicious_data_patterns(self, record: Dict[str, Any]) -> bool:
        """Detect suspicious patterns in data that might indicate corruption or tampering"""
        
        try:
            # Check for SQL injection patterns
            string_fields = [v for v in record.values() if isinstance(v, str)]
            sql_patterns = [
                "' OR '1'='1",
                "'; DROP TABLE",
                "UNION SELECT",
                "<script>",
                "javascript:",
                "eval(",
                "document.cookie"
            ]
            
            for field_value in string_fields:
                for pattern in sql_patterns:
                    if pattern.lower() in field_value.lower():
                        return True
            
            # Check for unusual character patterns
            for field_value in string_fields:
                # Check for excessive special characters
                special_char_count = sum(1 for c in field_value if not c.isalnum() and c not in " .-_@")
                if len(field_value) > 0 and special_char_count / len(field_value) > 0.5:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error detecting suspicious data patterns: {e}")
            return False
    
    async def _create_security_alert(
        self,
        alert_type: str,
        event_id: str,
        severity: str,
        details: Dict[str, Any]
    ) -> None:
        """Create security alert"""
        
        try:
            # Check for alert cooldown to prevent spam
            cooldown_key = f"alert_cooldown:{alert_type}:{details.get('user_id', 'system')}"
            
            if await cache_manager.get_cache(cooldown_key):
                return  # Alert is in cooldown period
            
            alert_record = {
                "alert_id": str(uuid.uuid4()),
                "alert_type": alert_type,
                "event_id": event_id,
                "severity": severity,
                "details": details,
                "timestamp": datetime.utcnow(),
                "acknowledged": False,
                "acknowledged_by": None,
                "acknowledged_at": None,
                "resolved": False,
                "resolved_by": None,
                "resolved_at": None,
                "resolution_notes": None
            }
            
            await self.security_alerts_collection.insert_one(alert_record)
            
            # Set cooldown period
            await cache_manager.set_cache(
                cooldown_key,
                {"created_at": datetime.utcnow().isoformat()},
                expire=self.alert_cooldown_minutes * 60
            )
            
            # Log alert creation
            logger.warning(f"Security alert created: {alert_type} (severity: {severity}) - {details}")
            
            # In production, this would trigger external alerting systems
            # (email, Slack, PagerDuty, etc.)
            
        except Exception as e:
            logger.error(f"Error creating security alert: {e}")
    
    async def _get_geolocation(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Get geolocation for IP address (mock implementation)"""
        
        try:
            # In production, this would use a real geolocation service
            # For now, return mock data for non-local IPs
            if ip_address and not ip_address.startswith(("127.", "192.168.", "10.", "172.")):
                return {
                    "country": "Unknown",
                    "region": "Unknown",
                    "city": "Unknown",
                    "latitude": 0.0,
                    "longitude": 0.0
                }
            return None
            
        except Exception as e:
            logger.error(f"Error getting geolocation for {ip_address}: {e}")
            return None
    
    def _generate_device_fingerprint(self, user_agent: Optional[str], ip_address: Optional[str]) -> str:
        """Generate device fingerprint for tracking"""
        
        try:
            fingerprint_data = f"{user_agent or 'unknown'}:{ip_address or 'unknown'}"
            return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
            
        except Exception as e:
            logger.error(f"Error generating device fingerprint: {e}")
            return "unknown"
    
    async def _check_ip_reputation(self, ip_address: str) -> float:
        """Check IP reputation (mock implementation)"""
        
        try:
            # In production, this would check against threat intelligence feeds
            # For now, return higher score for certain patterns
            
            # Check if IP is in known bad ranges (simplified)
            bad_patterns = ["192.168.1.666", "10.0.0.666"]  # Mock bad IPs
            
            for pattern in bad_patterns:
                if ip_address.startswith(pattern):
                    return 0.8  # High reputation score (bad)
            
            return 0.0  # Good reputation
            
        except Exception as e:
            logger.error(f"Error checking IP reputation for {ip_address}: {e}")
            return 0.0
    
    async def _get_recent_events_count(
        self,
        user_id: Optional[str],
        ip_address: Optional[str],
        minutes: int = 60
    ) -> int:
        """Get count of recent events for user or IP"""
        
        try:
            cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
            
            query = {"timestamp": {"$gte": cutoff_time}}
            
            if user_id:
                query["user_id"] = user_id
            elif ip_address:
                query["ip_address"] = ip_address
            else:
                return 0
            
            return await self.security_events_collection.count_documents(query)
            
        except Exception as e:
            logger.error(f"Error getting recent events count: {e}")
            return 0
    
    async def _check_geographic_anomaly(
        self,
        user_id: Optional[str],
        current_location: Dict[str, Any]
    ) -> float:
        """Check for geographic anomalies in user access"""
        
        try:
            if not user_id or not current_location:
                return 0.0
            
            # Get user's recent locations
            recent_cutoff = datetime.utcnow() - timedelta(days=7)
            
            recent_events = await self.security_events_collection.find({
                "user_id": user_id,
                "timestamp": {"$gte": recent_cutoff},
                "geolocation": {"$exists": True, "$ne": None}
            }).to_list(length=50)
            
            if not recent_events:
                return 0.0
            
            # Calculate distance from usual locations
            # This is a simplified implementation
            usual_countries = set()
            for event in recent_events:
                geo = event.get("geolocation", {})
                if geo.get("country"):
                    usual_countries.add(geo["country"])
            
            current_country = current_location.get("country", "Unknown")
            
            # If accessing from a new country, increase score
            if current_country not in usual_countries and len(usual_countries) > 0:
                return 2.0
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error checking geographic anomaly: {e}")
            return 0.0
    
    async def get_security_dashboard_data(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get security dashboard data for monitoring"""
        
        try:
            if not start_date:
                start_date = datetime.utcnow() - timedelta(days=7)
            if not end_date:
                end_date = datetime.utcnow()
            
            date_filter = {
                "timestamp": {"$gte": start_date, "$lte": end_date}
            }
            
            # Get event statistics
            event_stats = await self.security_events_collection.aggregate([
                {"$match": date_filter},
                {"$group": {
                    "_id": "$event_type",
                    "count": {"$sum": 1},
                    "avg_threat_score": {"$avg": "$threat_score"}
                }}
            ]).to_list(length=None)
            
            # Get alert statistics
            alert_stats = await self.security_alerts_collection.aggregate([
                {"$match": date_filter},
                {"$group": {
                    "_id": "$severity",
                    "count": {"$sum": 1}
                }}
            ]).to_list(length=None)
            
            # Get compliance violations
            compliance_violations = await self.compliance_violations_collection.count_documents({
                **date_filter,
                "resolved": False
            })
            
            # Get top threat sources
            top_threats = await self.security_events_collection.aggregate([
                {"$match": {**date_filter, "threat_score": {"$gte": 5.0}}},
                {"$group": {
                    "_id": "$ip_address",
                    "threat_count": {"$sum": 1},
                    "max_threat_score": {"$max": "$threat_score"}
                }},
                {"$sort": {"threat_count": -1}},
                {"$limit": 10}
            ]).to_list(length=10)
            
            return {
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "event_statistics": event_stats,
                "alert_statistics": alert_stats,
                "compliance_violations": compliance_violations,
                "top_threat_sources": top_threats,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting security dashboard data: {e}")
            return {"error": str(e)}
    
    async def cleanup_old_events(self, retention_days: int = 90) -> int:
        """Clean up old security events"""
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            # Delete old events
            result = await self.security_events_collection.delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            
            logger.info(f"Cleaned up {result.deleted_count} old security events")
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old events: {e}")
            return 0