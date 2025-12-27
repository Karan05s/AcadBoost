"""
Data Privacy and Security Service
Handles FERPA compliance, data access requests, and secure data deletion
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.redis_client import cache_manager
import logging
import json
import hashlib
import uuid

logger = logging.getLogger(__name__)


class DataPrivacyService:
    """Service for handling data privacy, access requests, and secure deletion"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.audit_collection = db.audit_trail
        self.data_requests_collection = db.data_requests
    
    async def create_audit_entry(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """Create audit trail entry for data access or modification"""
        
        audit_entry = {
            "audit_id": str(uuid.uuid4()),
            "user_id": user_id,
            "action": action,  # "access", "modify", "delete", "export", "login", "failed_access"
            "resource_type": resource_type,  # "profile", "performance", "recommendations", "gaps"
            "resource_id": resource_id,
            "timestamp": datetime.utcnow(),
            "details": details or {},
            "ip_address": ip_address,
            "user_agent": user_agent,
            "compliance_flags": {
                "ferpa_applicable": True,
                "data_sensitivity": self._classify_data_sensitivity(resource_type),
                "retention_period": self._get_retention_period(resource_type)
            }
        }
        
        try:
            result = await self.audit_collection.insert_one(audit_entry)
            logger.info(f"Created audit entry: {audit_entry['audit_id']} for user {user_id}")
            return audit_entry["audit_id"]
            
        except Exception as e:
            logger.error(f"Failed to create audit entry: {e}")
            raise
    
    def _classify_data_sensitivity(self, resource_type: str) -> str:
        """Classify data sensitivity level for FERPA compliance"""
        sensitivity_map = {
            "profile": "high",  # PII data
            "performance": "high",  # Educational records
            "recommendations": "medium",  # Derived insights
            "gaps": "medium",  # Learning analytics
            "preferences": "low",  # User preferences
            "system": "low"  # System logs
        }
        return sensitivity_map.get(resource_type, "medium")
    
    def _get_retention_period(self, resource_type: str) -> int:
        """Get data retention period in days based on FERPA requirements"""
        retention_map = {
            "profile": 2555,  # 7 years for educational records
            "performance": 2555,  # 7 years for educational records
            "recommendations": 1095,  # 3 years for analytics
            "gaps": 1095,  # 3 years for analytics
            "preferences": 365,  # 1 year for preferences
            "audit": 2555,  # 7 years for audit logs
            "system": 90  # 90 days for system logs
        }
        return retention_map.get(resource_type, 1095)
    
    async def get_complete_user_data(
        self,
        user_id: str,
        requesting_user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieve complete user data for FERPA data access requests
        Creates audit trail for the access
        """
        
        try:
            # Create audit entry for data access
            await self.create_audit_entry(
                user_id=requesting_user_id,
                action="export",
                resource_type="complete_profile",
                resource_id=user_id,
                details={"export_type": "complete_data_request"},
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # Collect data from all relevant collections
            user_data = {
                "export_metadata": {
                    "user_id": user_id,
                    "export_date": datetime.utcnow().isoformat(),
                    "export_type": "complete_user_data",
                    "ferpa_compliance": True
                },
                "profile": None,
                "performance_data": [],
                "learning_gaps": [],
                "recommendations": [],
                "onboarding_data": None,
                "assessments": [],
                "course_enrollments": [],
                "lti_contexts": [],
                "audit_trail": []
            }
            
            # Get user profile
            profile = await self.db.user_profiles.find_one({"user_id": user_id})
            if profile:
                # Remove internal MongoDB _id
                profile.pop("_id", None)
                user_data["profile"] = profile
            
            # Get performance data
            performance_cursor = self.db.student_performance.find({"student_id": user_id})
            performance_data = await performance_cursor.to_list(length=None)
            for record in performance_data:
                record.pop("_id", None)
            user_data["performance_data"] = performance_data
            
            # Get learning gaps
            gaps_cursor = self.db.learning_gaps.find({"student_id": user_id})
            gaps_data = await gaps_cursor.to_list(length=None)
            for record in gaps_data:
                record.pop("_id", None)
            user_data["learning_gaps"] = gaps_data
            
            # Get recommendations
            recommendations_cursor = self.db.recommendations.find({"student_id": user_id})
            recommendations_data = await recommendations_cursor.to_list(length=None)
            for record in recommendations_data:
                record.pop("_id", None)
            user_data["recommendations"] = recommendations_data
            
            # Get onboarding data
            onboarding = await self.db.user_onboarding.find_one({"user_id": user_id})
            if onboarding:
                onboarding.pop("_id", None)
                user_data["onboarding_data"] = onboarding
            
            # Get assessments
            assessments_cursor = self.db.user_assessments.find({"user_id": user_id})
            assessments_data = await assessments_cursor.to_list(length=None)
            for record in assessments_data:
                record.pop("_id", None)
            user_data["assessments"] = assessments_data
            
            # Get course enrollments
            enrollments_cursor = self.db.course_enrollments.find({"user_id": user_id})
            enrollments_data = await enrollments_cursor.to_list(length=None)
            for record in enrollments_data:
                record.pop("_id", None)
            user_data["course_enrollments"] = enrollments_data
            
            # Get LTI contexts
            lti_cursor = self.db.lti_contexts.find({"user_id": user_id})
            lti_data = await lti_cursor.to_list(length=None)
            for record in lti_data:
                record.pop("_id", None)
            user_data["lti_contexts"] = lti_data
            
            # Get audit trail (last 90 days for privacy)
            audit_start_date = datetime.utcnow() - timedelta(days=90)
            audit_cursor = self.audit_collection.find({
                "user_id": user_id,
                "timestamp": {"$gte": audit_start_date}
            }).sort("timestamp", -1)
            audit_data = await audit_cursor.to_list(length=None)
            for record in audit_data:
                record.pop("_id", None)
            user_data["audit_trail"] = audit_data
            
            logger.info(f"Complete data export generated for user {user_id}")
            return user_data
            
        except Exception as e:
            logger.error(f"Error generating complete user data for {user_id}: {e}")
            raise
    
    async def delete_user_data_with_analytics_preservation(
        self,
        user_id: str,
        requesting_user_id: str,
        preserve_analytics: bool = True,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Delete user personal data while preserving anonymized analytics
        Complies with FERPA and GDPR right to be forgotten
        """
        
        try:
            # Create audit entry for data deletion
            deletion_audit_id = await self.create_audit_entry(
                user_id=requesting_user_id,
                action="delete",
                resource_type="complete_profile",
                resource_id=user_id,
                details={
                    "deletion_type": "user_data_with_analytics_preservation",
                    "preserve_analytics": preserve_analytics
                },
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            deletion_summary = {
                "user_id": user_id,
                "deletion_date": datetime.utcnow().isoformat(),
                "audit_id": deletion_audit_id,
                "collections_processed": [],
                "records_deleted": 0,
                "records_anonymized": 0,
                "errors": []
            }
            
            # 1. Delete user profile (contains PII)
            profile_result = await self.db.user_profiles.delete_one({"user_id": user_id})
            deletion_summary["collections_processed"].append("user_profiles")
            deletion_summary["records_deleted"] += profile_result.deleted_count
            
            # 2. Delete onboarding data (contains PII)
            onboarding_result = await self.db.user_onboarding.delete_one({"user_id": user_id})
            deletion_summary["collections_processed"].append("user_onboarding")
            deletion_summary["records_deleted"] += onboarding_result.deleted_count
            
            # 3. Delete LTI contexts (may contain PII)
            lti_result = await self.db.lti_contexts.delete_many({"user_id": user_id})
            deletion_summary["collections_processed"].append("lti_contexts")
            deletion_summary["records_deleted"] += lti_result.deleted_count
            
            # 4. Delete LTI sessions
            lti_sessions_result = await self.db.lti_sessions.delete_many({"user_id": user_id})
            deletion_summary["collections_processed"].append("lti_sessions")
            deletion_summary["records_deleted"] += lti_sessions_result.deleted_count
            
            # 5. Delete course enrollments (contains PII)
            enrollments_result = await self.db.course_enrollments.delete_many({"user_id": user_id})
            deletion_summary["collections_processed"].append("course_enrollments")
            deletion_summary["records_deleted"] += enrollments_result.deleted_count
            
            if preserve_analytics:
                # Anonymize analytics data instead of deleting
                anonymized_id = self._generate_anonymous_id(user_id)
                
                # Anonymize performance data
                performance_result = await self.db.student_performance.update_many(
                    {"student_id": user_id},
                    {
                        "$set": {
                            "student_id": anonymized_id,
                            "anonymized": True,
                            "anonymized_date": datetime.utcnow()
                        },
                        "$unset": {
                            "student_name": "",
                            "student_email": ""
                        }
                    }
                )
                deletion_summary["collections_processed"].append("student_performance (anonymized)")
                deletion_summary["records_anonymized"] += performance_result.modified_count
                
                # Anonymize learning gaps
                gaps_result = await self.db.learning_gaps.update_many(
                    {"student_id": user_id},
                    {
                        "$set": {
                            "student_id": anonymized_id,
                            "anonymized": True,
                            "anonymized_date": datetime.utcnow()
                        }
                    }
                )
                deletion_summary["collections_processed"].append("learning_gaps (anonymized)")
                deletion_summary["records_anonymized"] += gaps_result.modified_count
                
                # Anonymize recommendations
                recommendations_result = await self.db.recommendations.update_many(
                    {"student_id": user_id},
                    {
                        "$set": {
                            "student_id": anonymized_id,
                            "anonymized": True,
                            "anonymized_date": datetime.utcnow()
                        }
                    }
                )
                deletion_summary["collections_processed"].append("recommendations (anonymized)")
                deletion_summary["records_anonymized"] += recommendations_result.modified_count
                
                # Delete assessments (may contain identifiable responses)
                assessments_result = await self.db.user_assessments.delete_many({"user_id": user_id})
                deletion_summary["collections_processed"].append("user_assessments")
                deletion_summary["records_deleted"] += assessments_result.deleted_count
                
            else:
                # Delete all analytics data
                collections_to_delete = [
                    ("student_performance", "student_id"),
                    ("learning_gaps", "student_id"),
                    ("recommendations", "student_id"),
                    ("user_assessments", "user_id")
                ]
                
                for collection_name, field_name in collections_to_delete:
                    collection = getattr(self.db, collection_name)
                    result = await collection.delete_many({field_name: user_id})
                    deletion_summary["collections_processed"].append(collection_name)
                    deletion_summary["records_deleted"] += result.deleted_count
            
            # 6. Clear all caches
            await self._clear_user_caches(user_id)
            
            # 7. Create final audit entry
            await self.create_audit_entry(
                user_id="system",
                action="delete_completed",
                resource_type="complete_profile",
                resource_id=user_id,
                details=deletion_summary
            )
            
            logger.info(f"User data deletion completed for {user_id}: {deletion_summary}")
            return deletion_summary
            
        except Exception as e:
            error_msg = f"Error deleting user data for {user_id}: {e}"
            logger.error(error_msg)
            deletion_summary["errors"].append(error_msg)
            
            # Create error audit entry
            await self.create_audit_entry(
                user_id="system",
                action="delete_failed",
                resource_type="complete_profile",
                resource_id=user_id,
                details={"error": str(e)}
            )
            
            raise
    
    def _generate_anonymous_id(self, user_id: str) -> str:
        """Generate consistent anonymous ID for analytics preservation"""
        # Use SHA-256 hash with salt for consistent anonymization
        salt = "learning_analytics_anonymization_salt_2024"
        hash_input = f"{user_id}_{salt}".encode('utf-8')
        return f"anon_{hashlib.sha256(hash_input).hexdigest()[:16]}"
    
    async def _clear_user_caches(self, user_id: str) -> None:
        """Clear all cached data for a user"""
        try:
            cache_patterns = [
                f"dashboard:{user_id}",
                f"profile:{user_id}",
                f"recommendations:{user_id}",
                f"precomputed_analytics:{user_id}",
                f"gaps:{user_id}",
                f"performance:{user_id}"
            ]
            
            for pattern in cache_patterns:
                await cache_manager.delete_cache(pattern)
                
        except Exception as e:
            logger.warning(f"Error clearing caches for user {user_id}: {e}")
    
    async def create_data_request(
        self,
        user_id: str,
        request_type: str,  # "access", "deletion", "correction"
        requesting_user_id: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """Create a formal data request for tracking and compliance"""
        
        request_id = str(uuid.uuid4())
        
        data_request = {
            "request_id": request_id,
            "user_id": user_id,
            "request_type": request_type,
            "requesting_user_id": requesting_user_id,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "details": details or {},
            "ip_address": ip_address,
            "ferpa_compliance": {
                "applicable": True,
                "request_category": self._categorize_ferpa_request(request_type),
                "response_deadline": datetime.utcnow() + timedelta(days=45)  # FERPA 45-day requirement
            },
            "processing_log": []
        }
        
        try:
            await self.data_requests_collection.insert_one(data_request)
            
            # Create audit entry
            await self.create_audit_entry(
                user_id=requesting_user_id,
                action="data_request_created",
                resource_type="data_request",
                resource_id=request_id,
                details={
                    "request_type": request_type,
                    "target_user_id": user_id
                },
                ip_address=ip_address
            )
            
            logger.info(f"Created data request {request_id} for user {user_id}")
            return request_id
            
        except Exception as e:
            logger.error(f"Error creating data request: {e}")
            raise
    
    def _categorize_ferpa_request(self, request_type: str) -> str:
        """Categorize request type for FERPA compliance"""
        ferpa_categories = {
            "access": "directory_information_access",
            "deletion": "record_correction_deletion",
            "correction": "record_correction_deletion",
            "disclosure": "disclosure_request"
        }
        return ferpa_categories.get(request_type, "general_inquiry")
    
    async def update_data_request_status(
        self,
        request_id: str,
        status: str,
        processing_notes: Optional[str] = None,
        completed_by: Optional[str] = None
    ) -> bool:
        """Update data request status and add processing log entry"""
        
        try:
            log_entry = {
                "timestamp": datetime.utcnow(),
                "status": status,
                "notes": processing_notes,
                "processed_by": completed_by
            }
            
            update_data = {
                "status": status,
                "last_updated": datetime.utcnow(),
                "$push": {"processing_log": log_entry}
            }
            
            if status == "completed":
                update_data["completed_at"] = datetime.utcnow()
                update_data["completed_by"] = completed_by
            
            result = await self.data_requests_collection.update_one(
                {"request_id": request_id},
                {"$set": update_data}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error updating data request {request_id}: {e}")
            return False
    
    async def get_audit_trail(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        action_filter: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get audit trail for a user with optional filtering"""
        
        try:
            # Build query
            query = {"user_id": user_id}
            
            if start_date or end_date:
                date_filter = {}
                if start_date:
                    date_filter["$gte"] = start_date
                if end_date:
                    date_filter["$lte"] = end_date
                query["timestamp"] = date_filter
            
            if action_filter:
                query["action"] = action_filter
            
            # Execute query
            cursor = self.audit_collection.find(query).sort("timestamp", -1).limit(limit)
            audit_records = await cursor.to_list(length=limit)
            
            # Remove MongoDB _id field
            for record in audit_records:
                record.pop("_id", None)
            
            return audit_records
            
        except Exception as e:
            logger.error(f"Error retrieving audit trail for user {user_id}: {e}")
            return []
    
    async def check_ferpa_compliance(self, user_id: str) -> Dict[str, Any]:
        """Check FERPA compliance status for a user's data"""
        
        try:
            compliance_report = {
                "user_id": user_id,
                "check_date": datetime.utcnow().isoformat(),
                "ferpa_status": "compliant",
                "issues": [],
                "recommendations": [],
                "data_retention": {},
                "access_controls": {}
            }
            
            # Check data retention periods
            collections_to_check = [
                ("user_profiles", "created_at", 2555),
                ("student_performance", "timestamp", 2555),
                ("learning_gaps", "identified_at", 1095),
                ("recommendations", "generated_at", 1095)
            ]
            
            for collection_name, date_field, retention_days in collections_to_check:
                collection = getattr(self.db, collection_name)
                cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
                
                # Count records older than retention period
                old_records_count = await collection.count_documents({
                    "user_id": user_id,
                    date_field: {"$lt": cutoff_date}
                })
                
                compliance_report["data_retention"][collection_name] = {
                    "retention_days": retention_days,
                    "old_records_count": old_records_count,
                    "compliant": old_records_count == 0
                }
                
                if old_records_count > 0:
                    compliance_report["ferpa_status"] = "non_compliant"
                    compliance_report["issues"].append(
                        f"{collection_name} contains {old_records_count} records exceeding retention period"
                    )
                    compliance_report["recommendations"].append(
                        f"Archive or delete old records in {collection_name}"
                    )
            
            # Check access controls
            recent_access = await self.audit_collection.count_documents({
                "user_id": user_id,
                "action": "access",
                "timestamp": {"$gte": datetime.utcnow() - timedelta(days=30)}
            })
            
            compliance_report["access_controls"] = {
                "recent_access_count": recent_access,
                "audit_trail_complete": recent_access > 0
            }
            
            return compliance_report
            
        except Exception as e:
            logger.error(f"Error checking FERPA compliance for user {user_id}: {e}")
            return {
                "user_id": user_id,
                "check_date": datetime.utcnow().isoformat(),
                "ferpa_status": "error",
                "error": str(e)
            }