"""
ML-based Gap Detection Service for learning analytics
"""
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import joblib
import os

from app.models.performance import PerformanceData, LearningGap
from app.models.concept import ConceptAssessment

logger = logging.getLogger(__name__)


class GapDetectionService:
    """Service for ML-based learning gap detection and analysis"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.gap_classifier = None
        self.severity_regressor = None
        self.scaler = StandardScaler()
        self.model_trained = False
        self.model_path = "models/gap_detection"
        
    async def initialize_models(self) -> None:
        """Initialize or load ML models for gap detection"""
        try:
            # Try to load existing models
            if os.path.exists(f"{self.model_path}_classifier.joblib"):
                self.gap_classifier = joblib.load(f"{self.model_path}_classifier.joblib")
                self.severity_regressor = joblib.load(f"{self.model_path}_regressor.joblib")
                self.scaler = joblib.load(f"{self.model_path}_scaler.joblib")
                self.model_trained = True
                logger.info("Loaded existing gap detection models")
            else:
                # Initialize new models
                self.gap_classifier = RandomForestClassifier(
                    n_estimators=100,
                    max_depth=10,
                    random_state=42
                )
                self.severity_regressor = GradientBoostingRegressor(
                    n_estimators=100,
                    max_depth=6,
                    random_state=42
                )
                logger.info("Initialized new gap detection models")
                
                # Train models if we have enough data
                await self._train_models_if_ready()
                
        except Exception as e:
            logger.error(f"Error initializing gap detection models: {e}")
            raise
    
    async def _train_models_if_ready(self) -> bool:
        """Train models if we have sufficient data"""
        try:
            # Check if we have enough performance data
            performance_count = await self.db.performance_data.count_documents({})
            if performance_count < 100:  # Minimum data threshold
                logger.info(f"Insufficient data for training ({performance_count} records). Need at least 100.")
                return False
            
            # Prepare training data
            X, y_gaps, y_severity = await self._prepare_training_data()
            
            if len(X) < 50:  # Minimum processed samples
                logger.info(f"Insufficient processed samples for training ({len(X)}). Need at least 50.")
                return False
            
            # Split data
            X_train, X_test, y_gaps_train, y_gaps_test, y_severity_train, y_severity_test = train_test_split(
                X, y_gaps, y_severity, test_size=0.2, random_state=42
            )
            
            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Train gap classifier
            self.gap_classifier.fit(X_train_scaled, y_gaps_train)
            gap_accuracy = self.gap_classifier.score(X_test_scaled, y_gaps_test)
            
            # Train severity regressor (only on samples with gaps)
            gap_indices = np.where(y_gaps_train == 1)[0]
            if len(gap_indices) > 10:  # Need some positive samples
                X_gap_train = X_train_scaled[gap_indices]
                y_severity_gap_train = y_severity_train[gap_indices]
                
                self.severity_regressor.fit(X_gap_train, y_severity_gap_train)
                
                # Test on gap samples
                gap_test_indices = np.where(y_gaps_test == 1)[0]
                if len(gap_test_indices) > 0:
                    X_gap_test = X_test_scaled[gap_test_indices]
                    y_severity_gap_test = y_severity_test[gap_test_indices]
                    severity_score = self.severity_regressor.score(X_gap_test, y_severity_gap_test)
                    logger.info(f"Severity regressor R² score: {severity_score:.3f}")
            
            self.model_trained = True
            
            # Save models
            os.makedirs(self.model_path.rsplit('/', 1)[0], exist_ok=True)
            joblib.dump(self.gap_classifier, f"{self.model_path}_classifier.joblib")
            joblib.dump(self.severity_regressor, f"{self.model_path}_regressor.joblib")
            joblib.dump(self.scaler, f"{self.model_path}_scaler.joblib")
            
            logger.info(f"Models trained successfully. Gap classifier accuracy: {gap_accuracy:.3f}")
            return True
            
        except Exception as e:
            logger.error(f"Error training gap detection models: {e}")
            return False
    
    async def _prepare_training_data(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Prepare training data from performance records"""
        try:
            # Get performance data with concept assessments
            pipeline = [
                {
                    "$lookup": {
                        "from": "concept_assessments",
                        "localField": "student_id",
                        "foreignField": "student_id",
                        "as": "assessments"
                    }
                },
                {
                    "$lookup": {
                        "from": "learning_gaps",
                        "localField": "student_id",
                        "foreignField": "student_id",
                        "as": "gaps"
                    }
                }
            ]
            
            records = await self.db.performance_data.aggregate(pipeline).to_list(None)
            
            features = []
            gap_labels = []
            severity_labels = []
            
            for record in records:
                # Extract features
                feature_vector = self._extract_features(record)
                if feature_vector is None:
                    continue
                
                features.append(feature_vector)
                
                # Determine if student has gaps (binary classification)
                has_gaps = len(record.get("gaps", [])) > 0
                gap_labels.append(1 if has_gaps else 0)
                
                # Calculate average gap severity for regression
                gaps = record.get("gaps", [])
                if gaps:
                    avg_severity = np.mean([gap.get("gap_severity", 0.5) for gap in gaps])
                else:
                    avg_severity = 0.0
                severity_labels.append(avg_severity)
            
            return np.array(features), np.array(gap_labels), np.array(severity_labels)
            
        except Exception as e:
            logger.error(f"Error preparing training data: {e}")
            raise
    
    def _extract_features(self, record: Dict[str, Any]) -> Optional[List[float]]:
        """Extract feature vector from performance record"""
        try:
            features = []
            
            # Basic performance features
            score = record.get("score", 0)
            max_score = record.get("max_score", 1)
            normalized_score = score / max_score if max_score > 0 else 0
            features.append(normalized_score)
            
            # Question-level accuracy
            responses = record.get("question_responses", [])
            if responses:
                correct_count = sum(1 for r in responses if r.get("correct", False))
                accuracy = correct_count / len(responses)
                features.append(accuracy)
                features.append(len(responses))  # Number of questions
            else:
                features.extend([0.0, 0.0])
            
            # Code metrics (if available)
            code_metrics = record.get("code_metrics", {})
            features.append(code_metrics.get("complexity", 0))
            features.append(code_metrics.get("test_coverage", 0))
            features.append(code_metrics.get("execution_time", 0))
            
            # Time-based features
            timestamp = record.get("timestamp")
            if timestamp:
                # Time since submission (days)
                days_ago = (datetime.utcnow() - timestamp).days
                features.append(min(days_ago, 365))  # Cap at 1 year
            else:
                features.append(0)
            
            # Concept assessment features
            assessments = record.get("assessments", [])
            if assessments:
                mastery_scores = [a.get("mastery_level", 0.5) for a in assessments]
                features.append(np.mean(mastery_scores))
                features.append(np.std(mastery_scores))
                features.append(len(assessments))
            else:
                features.extend([0.5, 0.0, 0])
            
            return features
            
        except Exception as e:
            logger.error(f"Error extracting features: {e}")
            return None
    
    async def detect_learning_gaps(self, student_id: str) -> List[LearningGap]:
        """Detect learning gaps for a specific student"""
        try:
            if not self.model_trained:
                logger.warning("Models not trained yet. Using rule-based gap detection.")
                return await self._rule_based_gap_detection(student_id)
            
            # Get student's recent performance data
            recent_data = await self.db.performance_data.find({
                "student_id": student_id,
                "timestamp": {"$gte": datetime.utcnow() - timedelta(days=90)}
            }).to_list(None)
            
            if not recent_data:
                logger.info(f"No recent performance data for student {student_id}")
                return []
            
            gaps = []
            
            # Analyze each performance record
            for record in recent_data:
                feature_vector = self._extract_features(record)
                if feature_vector is None:
                    continue
                
                # Scale features
                features_scaled = self.scaler.transform([feature_vector])
                
                # Predict gap probability
                gap_probability = self.gap_classifier.predict_proba(features_scaled)[0][1]
                
                if gap_probability > 0.6:  # Threshold for gap detection
                    # Predict severity
                    severity = self.severity_regressor.predict(features_scaled)[0]
                    severity = max(0.0, min(1.0, severity))  # Clamp to [0, 1]
                    
                    # Identify specific concepts with gaps
                    concept_gaps = await self._identify_concept_gaps(record, severity)
                    gaps.extend(concept_gaps)
            
            # Deduplicate and rank gaps
            gaps = self._deduplicate_and_rank_gaps(gaps)
            
            # Store gaps in database
            if gaps:
                gap_docs = [gap.dict() for gap in gaps]
                await self.db.learning_gaps.insert_many(gap_docs)
            
            return gaps
            
        except Exception as e:
            logger.error(f"Error detecting learning gaps: {e}")
            raise
    
    async def _rule_based_gap_detection(self, student_id: str) -> List[LearningGap]:
        """Fallback rule-based gap detection when ML models aren't available"""
        try:
            # Get student's performance data
            performance_data = await self.db.performance_data.find({
                "student_id": student_id,
                "timestamp": {"$gte": datetime.utcnow() - timedelta(days=30)}
            }).to_list(None)
            
            if not performance_data:
                return []
            
            gaps = []
            concept_performance = {}
            
            # Analyze performance by concept
            for record in performance_data:
                responses = record.get("question_responses", [])
                for response in responses:
                    concept_tags = response.get("concept_tags", [])
                    correct = response.get("correct", False)
                    
                    for concept_id in concept_tags:
                        if concept_id not in concept_performance:
                            concept_performance[concept_id] = {"correct": 0, "total": 0}
                        
                        concept_performance[concept_id]["total"] += 1
                        if correct:
                            concept_performance[concept_id]["correct"] += 1
            
            # Identify gaps based on low accuracy
            for concept_id, perf in concept_performance.items():
                if perf["total"] >= 3:  # Minimum attempts
                    accuracy = perf["correct"] / perf["total"]
                    if accuracy < 0.6:  # Gap threshold
                        severity = 1.0 - accuracy  # Higher severity for lower accuracy
                        confidence = min(perf["total"] / 10.0, 1.0)  # More data = higher confidence
                        
                        gap = LearningGap(
                            gap_id=str(uuid.uuid4()),
                            student_id=student_id,
                            concept_id=concept_id,
                            gap_severity=severity,
                            confidence_score=confidence,
                            identified_at=datetime.utcnow(),
                            last_updated=datetime.utcnow(),
                            supporting_evidence=[],
                            improvement_trend=0.0
                        )
                        gaps.append(gap)
            
            return gaps
            
        except Exception as e:
            logger.error(f"Error in rule-based gap detection: {e}")
            raise
    
    async def _identify_concept_gaps(self, record: Dict[str, Any], base_severity: float) -> List[LearningGap]:
        """Identify specific concept gaps from a performance record"""
        try:
            gaps = []
            student_id = record["student_id"]
            
            # Analyze question responses
            responses = record.get("question_responses", [])
            concept_errors = {}
            
            for response in responses:
                if not response.get("correct", False):
                    concept_tags = response.get("concept_tags", [])
                    for concept_id in concept_tags:
                        if concept_id not in concept_errors:
                            concept_errors[concept_id] = 0
                        concept_errors[concept_id] += 1
            
            # Create gaps for concepts with errors
            for concept_id, error_count in concept_errors.items():
                severity = min(base_severity * (error_count / len(responses)), 1.0)
                confidence = min(error_count / 5.0, 1.0)  # Higher confidence with more errors
                
                gap = LearningGap(
                    gap_id=str(uuid.uuid4()),
                    student_id=student_id,
                    concept_id=concept_id,
                    gap_severity=severity,
                    confidence_score=confidence,
                    identified_at=datetime.utcnow(),
                    last_updated=datetime.utcnow(),
                    supporting_evidence=[{
                        "submission_id": str(record["_id"]),
                        "evidence_type": "incorrect_responses",
                        "weight": 1.0
                    }],
                    improvement_trend=0.0
                )
                gaps.append(gap)
            
            return gaps
            
        except Exception as e:
            logger.error(f"Error identifying concept gaps: {e}")
            return []
    
    def _deduplicate_and_rank_gaps(self, gaps: List[LearningGap]) -> List[LearningGap]:
        """Remove duplicate gaps and rank by severity"""
        try:
            # Group gaps by student and concept
            gap_groups = {}
            for gap in gaps:
                key = (gap.student_id, gap.concept_id)
                if key not in gap_groups:
                    gap_groups[key] = []
                gap_groups[key].append(gap)
            
            # Merge duplicate gaps
            merged_gaps = []
            for gap_list in gap_groups.values():
                if len(gap_list) == 1:
                    merged_gaps.append(gap_list[0])
                else:
                    # Merge multiple gaps for same concept
                    merged_gap = gap_list[0]
                    merged_gap.gap_severity = max(g.gap_severity for g in gap_list)
                    merged_gap.confidence_score = np.mean([g.confidence_score for g in gap_list])
                    
                    # Combine evidence
                    all_evidence = []
                    for g in gap_list:
                        all_evidence.extend(g.supporting_evidence)
                    merged_gap.supporting_evidence = all_evidence
                    
                    merged_gaps.append(merged_gap)
            
            # Sort by severity (descending)
            merged_gaps.sort(key=lambda x: x.gap_severity, reverse=True)
            
            return merged_gaps
            
        except Exception as e:
            logger.error(f"Error deduplicating and ranking gaps: {e}")
            return gaps
    
    async def calculate_confidence_intervals(self, student_id: str, concept_id: str) -> Dict[str, float]:
        """Calculate confidence intervals for gap predictions"""
        try:
            # Get historical data for this student-concept pair
            performance_data = await self.db.performance_data.find({
                "student_id": student_id,
                "question_responses.concept_tags": concept_id
            }).to_list(None)
            
            if len(performance_data) < 3:
                return {
                    "lower_bound": 0.0,
                    "upper_bound": 1.0,
                    "confidence_level": 0.5
                }
            
            # Calculate accuracy scores
            accuracies = []
            for record in performance_data:
                responses = record.get("question_responses", [])
                concept_responses = [r for r in responses if concept_id in r.get("concept_tags", [])]
                
                if concept_responses:
                    correct = sum(1 for r in concept_responses if r.get("correct", False))
                    accuracy = correct / len(concept_responses)
                    accuracies.append(accuracy)
            
            if not accuracies:
                return {
                    "lower_bound": 0.0,
                    "upper_bound": 1.0,
                    "confidence_level": 0.5
                }
            
            # Calculate confidence interval (assuming normal distribution)
            mean_accuracy = np.mean(accuracies)
            std_accuracy = np.std(accuracies)
            n = len(accuracies)
            
            # 95% confidence interval
            margin_of_error = 1.96 * (std_accuracy / np.sqrt(n))
            
            return {
                "lower_bound": max(0.0, mean_accuracy - margin_of_error),
                "upper_bound": min(1.0, mean_accuracy + margin_of_error),
                "confidence_level": min(n / 10.0, 1.0)  # Higher confidence with more data
            }
            
        except Exception as e:
            logger.error(f"Error calculating confidence intervals: {e}")
            return {
                "lower_bound": 0.0,
                "upper_bound": 1.0,
                "confidence_level": 0.5
            }
    
    async def retrain_models(self) -> bool:
        """Retrain models with latest data"""
        try:
            logger.info("Starting model retraining...")
            self.model_trained = False
            return await self._train_models_if_ready()
            
        except Exception as e:
            logger.error(f"Error retraining models: {e}")
            return False