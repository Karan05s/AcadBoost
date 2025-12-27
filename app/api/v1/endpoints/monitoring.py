"""
Monitoring API endpoints
Provides access to system performance metrics and background processing status
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timedelta

from app.core.auth import get_current_user
from app.services.background_worker_service import background_worker_service
from app.services.performance_monitoring_service import performance_monitoring_service
from app.services.enhanced_cache_service import enhanced_cache_service
from app.services.data_flow_validation_service import data_flow_validation_service
from app.core.service_registry import service_registry
from app.core.api_gateway import api_gateway

router = APIRouter()


@router.get("/performance/current")
async def get_current_performance_metrics(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current system performance metrics
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        metrics = await performance_monitoring_service.get_current_metrics()
        return {
            "status": "success",
            "data": metrics,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving performance metrics: {str(e)}")


@router.get("/performance/summary")
async def get_performance_summary(
    hours: int = Query(default=24, ge=1, le=168),  # 1 hour to 1 week
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get performance summary for specified time period
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        summary = await performance_monitoring_service.get_performance_summary(hours)
        return {
            "status": "success",
            "data": summary,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving performance summary: {str(e)}")


@router.get("/background-workers/status")
async def get_background_worker_status(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get background worker status and queue information
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        queue_status = background_worker_service.get_queue_status()
        performance_metrics = background_worker_service.get_performance_metrics()
        
        return {
            "status": "success",
            "data": {
                "queue_status": queue_status,
                "performance_metrics": performance_metrics,
                "is_running": background_worker_service.is_running
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving background worker status: {str(e)}")


@router.get("/cache/statistics")
async def get_cache_statistics(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get cache performance statistics
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        cache_stats = await enhanced_cache_service.get_cache_statistics()
        return {
            "status": "success",
            "data": cache_stats,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving cache statistics: {str(e)}")


@router.post("/cache/cleanup")
async def cleanup_cache(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Clean up expired cache entries
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        cleanup_result = await enhanced_cache_service.cleanup_expired_cache()
        return {
            "status": "success",
            "data": cleanup_result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cleaning up cache: {str(e)}")


@router.post("/cache/warm/{user_id}")
async def warm_user_cache(
    user_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Warm cache for a specific user
    Requires admin role or own user access
    """
    # Check if user has admin role or is accessing their own data
    if current_user.get("role") != "admin" and current_user.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        success = await enhanced_cache_service.warm_cache_for_user(user_id)
        return {
            "status": "success" if success else "failed",
            "data": {
                "user_id": user_id,
                "cache_warmed": success
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error warming cache for user: {str(e)}")


@router.post("/background-workers/schedule/analytics")
async def schedule_analytics_task(
    user_id: str,
    task_type: str = Query(default="user_analytics_precompute"),
    priority: str = Query(default="normal"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Schedule an analytics computation task
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    valid_task_types = [
        "user_analytics_precompute",
        "gap_analysis_update",
        "recommendation_generation",
        "batch_analytics_update"
    ]
    
    if task_type not in valid_task_types:
        raise HTTPException(status_code=400, detail=f"Invalid task type. Must be one of: {valid_task_types}")
    
    try:
        task = {
            "task_type": task_type,
            "user_id": user_id,
            "priority": priority,
            "scheduled_by": current_user.get("user_id"),
            "scheduled_at": datetime.utcnow().isoformat()
        }
        
        success = await background_worker_service.schedule_analytics_task(task)
        
        return {
            "status": "success" if success else "failed",
            "data": {
                "task_scheduled": success,
                "task": task
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scheduling analytics task: {str(e)}")


@router.post("/background-workers/schedule/ml-training")
async def schedule_ml_training_task(
    task_type: str = Query(default="gap_detection_training"),
    priority: str = Query(default="normal"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Schedule an ML model training task
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    valid_task_types = [
        "gap_detection_training",
        "recommendation_training",
        "concept_mapping_training"
    ]
    
    if task_type not in valid_task_types:
        raise HTTPException(status_code=400, detail=f"Invalid task type. Must be one of: {valid_task_types}")
    
    try:
        task = {
            "task_type": task_type,
            "priority": priority,
            "scheduled_by": current_user.get("user_id"),
            "scheduled_at": datetime.utcnow().isoformat()
        }
        
        success = await background_worker_service.schedule_ml_training_task(task)
        
        return {
            "status": "success" if success else "failed",
            "data": {
                "task_scheduled": success,
                "task": task
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scheduling ML training task: {str(e)}")


@router.post("/performance/cleanup")
async def cleanup_old_performance_data(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Clean up old performance metrics and alerts
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        cleanup_result = await performance_monitoring_service.cleanup_old_metrics()
        return {
            "status": "success",
            "data": cleanup_result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cleaning up performance data: {str(e)}")


@router.get("/system/health")
async def get_system_health(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get overall system health status
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get current metrics
        performance_metrics = await performance_monitoring_service.get_current_metrics()
        cache_stats = await enhanced_cache_service.get_cache_statistics()
        worker_status = background_worker_service.get_queue_status()
        
        # Determine overall health
        health_status = "healthy"
        issues = []
        
        # Check system metrics
        system_metrics = performance_metrics.get("system", {})
        if system_metrics:
            if system_metrics.get("cpu_usage", 0) > 80:
                health_status = "warning"
                issues.append("High CPU usage")
            
            if system_metrics.get("memory_usage", 0) > 85:
                health_status = "critical"
                issues.append("High memory usage")
            
            if system_metrics.get("disk_usage", 0) > 90:
                health_status = "critical"
                issues.append("High disk usage")
        
        # Check cache performance
        if cache_stats.get("hit_rate_percentage", 0) < 70:
            health_status = "warning"
            issues.append("Low cache hit rate")
        
        # Check background workers
        if not worker_status.get("is_running", False):
            health_status = "critical"
            issues.append("Background workers not running")
        
        total_queue_size = sum(worker_status.get("queue_sizes", {}).values())
        if total_queue_size > 100:
            health_status = "warning"
            issues.append("High background task queue size")
        
        return {
            "status": "success",
            "data": {
                "health_status": health_status,
                "issues": issues,
                "metrics_summary": {
                    "system": system_metrics,
                    "cache_hit_rate": cache_stats.get("hit_rate_percentage", 0),
                    "background_workers_running": worker_status.get("is_running", False),
                    "total_queued_tasks": total_queue_size
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving system health: {str(e)}")


@router.get("/optimization/recommendations")
async def get_optimization_recommendations(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get system optimization recommendations
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get current metrics for analysis
        performance_metrics = await performance_monitoring_service.get_current_metrics()
        cache_stats = await enhanced_cache_service.get_cache_statistics()
        worker_status = background_worker_service.get_queue_status()
        
        recommendations = []
        
        # Analyze system performance
        system_metrics = performance_metrics.get("system", {})
        if system_metrics.get("cpu_usage", 0) > 70:
            recommendations.append({
                "type": "performance",
                "priority": "high",
                "title": "High CPU Usage",
                "description": "Consider scaling up compute resources or optimizing CPU-intensive operations",
                "current_value": f"{system_metrics.get('cpu_usage', 0):.1f}%"
            })
        
        if system_metrics.get("memory_usage", 0) > 75:
            recommendations.append({
                "type": "performance",
                "priority": "high",
                "title": "High Memory Usage",
                "description": "Consider increasing memory allocation or implementing memory optimization",
                "current_value": f"{system_metrics.get('memory_usage', 0):.1f}%"
            })
        
        # Analyze cache performance
        hit_rate = cache_stats.get("hit_rate_percentage", 0)
        if hit_rate < 80:
            recommendations.append({
                "type": "caching",
                "priority": "medium",
                "title": "Low Cache Hit Rate",
                "description": "Consider implementing cache warming strategies or adjusting cache TTL values",
                "current_value": f"{hit_rate:.1f}%"
            })
        
        # Analyze background worker performance
        total_queue_size = sum(worker_status.get("queue_sizes", {}).values())
        if total_queue_size > 50:
            recommendations.append({
                "type": "background_processing",
                "priority": "medium",
                "title": "High Background Task Queue",
                "description": "Consider increasing the number of background workers or optimizing task processing",
                "current_value": f"{total_queue_size} queued tasks"
            })
        
        # Database optimization recommendations
        db_metrics = performance_metrics.get("database", {})
        if db_metrics:
            connections = db_metrics.get("connections", {})
            current_connections = connections.get("current", 0)
            available_connections = connections.get("available", 1)
            
            if current_connections / (current_connections + available_connections) > 0.8:
                recommendations.append({
                    "type": "database",
                    "priority": "high",
                    "title": "High Database Connection Usage",
                    "description": "Consider implementing connection pooling optimization or increasing connection limits",
                    "current_value": f"{current_connections} active connections"
                })
        
        # If no issues found
        if not recommendations:
            recommendations.append({
                "type": "general",
                "priority": "low",
                "title": "System Running Optimally",
                "description": "No immediate optimization recommendations. Continue monitoring performance metrics.",
                "current_value": "All metrics within normal ranges"
            })
        
        return {
            "status": "success",
            "data": {
                "total_recommendations": len(recommendations),
                "recommendations": recommendations,
                "analysis_timestamp": datetime.utcnow().isoformat()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating optimization recommendations: {str(e)}")


@router.get("/services/registry")
async def get_service_registry_status(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get service registry status and topology
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        topology = await service_registry.get_service_topology()
        return {
            "status": "success",
            "data": topology,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving service registry status: {str(e)}")


@router.get("/services/health/{service_name}")
async def check_service_health(
    service_name: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Check health of a specific service
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        health_status = await service_registry.check_service_health(service_name)
        service_info = await service_registry.get_service(service_name)
        
        return {
            "status": "success",
            "data": {
                "service_name": service_name,
                "health_status": health_status,
                "service_info": service_info.__dict__ if service_info else None
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking service health: {str(e)}")


@router.get("/api-gateway/status")
async def get_api_gateway_status(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get API gateway status and configuration
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        gateway_status = await api_gateway.get_gateway_status()
        return {
            "status": "success",
            "data": gateway_status,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving API gateway status: {str(e)}")


@router.post("/integration/validate")
async def validate_service_integration(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Validate end-to-end service integration
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        validation_result = await api_gateway.validate_service_integration()
        return {
            "status": "success",
            "data": validation_result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error validating service integration: {str(e)}")


@router.post("/data-flow/validate")
async def validate_data_flow(
    test_user_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Validate end-to-end data flow
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        validation_result = await data_flow_validation_service.validate_complete_data_flow(test_user_id)
        return {
            "status": "success",
            "data": validation_result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error validating data flow: {str(e)}")


@router.post("/data-flow/validate/{flow_name}")
async def validate_specific_data_flow(
    flow_name: str,
    test_user_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Validate a specific data flow
    Requires admin role
    """
    # Check if user has admin role
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        validation_result = await data_flow_validation_service.validate_specific_flow(flow_name, test_user_id)
        return {
            "status": "success",
            "data": validation_result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error validating specific data flow: {str(e)}")