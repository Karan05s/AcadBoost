"""
Concept Mapping Service for learning analytics
"""
import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid

from app.models.concept import (
    LearningConcept, ConceptMapping, ConceptMappingRequest, ConceptMappingResponse,
    ConceptAssessment, ConceptRelationship, CodeConceptAssessment,
    ConceptDifficulty, ConceptType
)

logger = logging.getLogger(__name__)


class ConceptMappingService:
    """Service for mapping questions and code to learning concepts"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._concept_cache = {}
        self._keyword_index = {}
        
    async def initialize_knowledge_base(self) -> None:
        """Initialize the concept knowledge base with default concepts"""
        try:
            # Check if knowledge base already exists
            existing_concepts = await self.db.concepts.count_documents({})
            if existing_concepts > 0:
                logger.info(f"Knowledge base already initialized with {existing_concepts} concepts")
                await self._build_keyword_index()
                return
            
            # Initialize with computer science concepts
            cs_concepts = [
                {
                    "concept_id": "cs_variables",
                    "name": "Variables and Data Types",
                    "description": "Understanding of variable declaration, assignment, and basic data types",
                    "concept_type": "fundamental",
                    "difficulty_level": "beginner",
                    "keywords": ["variable", "int", "string", "float", "boolean", "declaration", "assignment"],
                    "subject_area": "computer_science",
                    "prerequisites": []
                },
                {
                    "concept_id": "cs_control_flow",
                    "name": "Control Flow Structures",
                    "description": "Understanding of if statements, loops, and conditional logic",
                    "concept_type": "procedural",
                    "difficulty_level": "beginner",
                    "keywords": ["if", "else", "for", "while", "loop", "condition", "branch"],
                    "subject_area": "computer_science",
                    "prerequisites": ["cs_variables"]
                },
                {
                    "concept_id": "cs_functions",
                    "name": "Functions and Methods",
                    "description": "Understanding of function definition, parameters, return values, and scope",
                    "concept_type": "procedural",
                    "difficulty_level": "intermediate",
                    "keywords": ["function", "method", "parameter", "argument", "return", "scope"],
                    "subject_area": "computer_science",
                    "prerequisites": ["cs_variables", "cs_control_flow"]
                },
                {
                    "concept_id": "cs_data_structures",
                    "name": "Data Structures",
                    "description": "Understanding of arrays, lists, dictionaries, and basic data organization",
                    "concept_type": "conceptual",
                    "difficulty_level": "intermediate",
                    "keywords": ["array", "list", "dictionary", "hash", "map", "collection"],
                    "subject_area": "computer_science",
                    "prerequisites": ["cs_variables"]
                },
                {
                    "concept_id": "cs_algorithms",
                    "name": "Basic Algorithms",
                    "description": "Understanding of sorting, searching, and basic algorithmic thinking",
                    "concept_type": "procedural",
                    "difficulty_level": "intermediate",
                    "keywords": ["sort", "search", "algorithm", "complexity", "efficiency"],
                    "subject_area": "computer_science",
                    "prerequisites": ["cs_functions", "cs_data_structures"]
                },
                {
                    "concept_id": "cs_oop",
                    "name": "Object-Oriented Programming",
                    "description": "Understanding of classes, objects, inheritance, and encapsulation",
                    "concept_type": "conceptual",
                    "difficulty_level": "advanced",
                    "keywords": ["class", "object", "inheritance", "encapsulation", "polymorphism"],
                    "subject_area": "computer_science",
                    "prerequisites": ["cs_functions", "cs_data_structures"]
                }
            ]
            
            # Insert concepts into database
            for concept_data in cs_concepts:
                concept_data["created_at"] = datetime.utcnow()
                concept_data["updated_at"] = datetime.utcnow()
                concept_data["related_concepts"] = []
                
            await self.db.concepts.insert_many(cs_concepts)
            
            # Create concept relationships
            relationships = [
                {
                    "relationship_id": str(uuid.uuid4()),
                    "source_concept_id": "cs_variables",
                    "target_concept_id": "cs_control_flow",
                    "relationship_type": "prerequisite",
                    "strength": 0.9,
                    "bidirectional": False,
                    "created_at": datetime.utcnow()
                },
                {
                    "relationship_id": str(uuid.uuid4()),
                    "source_concept_id": "cs_control_flow",
                    "target_concept_id": "cs_functions",
                    "relationship_type": "prerequisite",
                    "strength": 0.8,
                    "bidirectional": False,
                    "created_at": datetime.utcnow()
                },
                {
                    "relationship_id": str(uuid.uuid4()),
                    "source_concept_id": "cs_data_structures",
                    "target_concept_id": "cs_algorithms",
                    "relationship_type": "prerequisite",
                    "strength": 0.9,
                    "bidirectional": False,
                    "created_at": datetime.utcnow()
                }
            ]
            
            await self.db.concept_relationships.insert_many(relationships)
            await self._build_keyword_index()
            
            logger.info(f"Initialized knowledge base with {len(cs_concepts)} concepts and {len(relationships)} relationships")
            
        except Exception as e:
            logger.error(f"Error initializing knowledge base: {e}")
            raise
    
    async def _build_keyword_index(self) -> None:
        """Build an index of keywords to concepts for fast lookup"""
        try:
            concepts = await self.db.concepts.find({}).to_list(None)
            self._keyword_index = {}
            
            for concept in concepts:
                concept_id = concept["concept_id"]
                keywords = concept.get("keywords", [])
                
                for keyword in keywords:
                    keyword_lower = keyword.lower()
                    if keyword_lower not in self._keyword_index:
                        self._keyword_index[keyword_lower] = []
                    self._keyword_index[keyword_lower].append(concept_id)
                    
            logger.info(f"Built keyword index with {len(self._keyword_index)} keywords")
            
        except Exception as e:
            logger.error(f"Error building keyword index: {e}")
            raise
    
    async def map_question_to_concepts(self, request: ConceptMappingRequest) -> ConceptMappingResponse:
        """Map a quiz question to relevant learning concepts"""
        try:
            question_text = request.question_text.lower()
            question_words = re.findall(r'\b\w+\b', question_text)
            
            # Find matching concepts based on keywords
            concept_scores = {}
            
            for word in question_words:
                if word in self._keyword_index:
                    for concept_id in self._keyword_index[word]:
                        if concept_id not in concept_scores:
                            concept_scores[concept_id] = 0
                        concept_scores[concept_id] += 1
            
            # Normalize scores and create mappings
            max_score = max(concept_scores.values()) if concept_scores else 1
            mapped_concepts = []
            
            for concept_id, score in concept_scores.items():
                confidence = min(score / max_score, 1.0)
                if confidence >= 0.3:  # Minimum confidence threshold
                    mapping = ConceptMapping(
                        mapping_id=str(uuid.uuid4()),
                        question_id=request.question_id,
                        concept_id=concept_id,
                        confidence_score=confidence,
                        mapping_type="keyword_match",
                        evidence={"matched_keywords": [w for w in question_words if w in self._keyword_index and concept_id in self._keyword_index[w]]},
                        created_by="concept_mapping_service",
                        created_at=datetime.utcnow()
                    )
                    mapped_concepts.append(mapping)
            
            # Sort by confidence score
            mapped_concepts.sort(key=lambda x: x.confidence_score, reverse=True)
            
            # Determine primary concept
            primary_concept = mapped_concepts[0].concept_id if mapped_concepts else None
            overall_confidence = mapped_concepts[0].confidence_score if mapped_concepts else 0.0
            
            # Store mappings in database
            if mapped_concepts:
                mapping_docs = [mapping.dict() for mapping in mapped_concepts]
                await self.db.concept_mappings.insert_many(mapping_docs)
            
            return ConceptMappingResponse(
                question_id=request.question_id,
                mapped_concepts=mapped_concepts,
                primary_concept=primary_concept,
                confidence_score=overall_confidence,
                mapping_method="keyword_matching",
                suggestions=[]
            )
            
        except Exception as e:
            logger.error(f"Error mapping question to concepts: {e}")
            raise
    
    async def assess_code_concepts(self, submission_id: str, student_id: str, code_content: str) -> CodeConceptAssessment:
        """Assess programming concepts demonstrated in code submission"""
        try:
            # Simple keyword-based analysis for code concepts
            code_lower = code_content.lower()
            
            programming_concepts = {}
            algorithm_concepts = {}
            best_practices = {}
            
            # Check for programming concepts
            concept_patterns = {
                "cs_variables": [r'\b(int|str|float|bool)\b', r'\b\w+\s*=\s*', r'\bvar\b'],
                "cs_control_flow": [r'\bif\b', r'\belse\b', r'\bfor\b', r'\bwhile\b'],
                "cs_functions": [r'\bdef\b', r'\bfunction\b', r'\breturn\b'],
                "cs_data_structures": [r'\blist\b', r'\bdict\b', r'\barray\b', r'\[\]', r'\{\}'],
                "cs_oop": [r'\bclass\b', r'\bself\b', r'\bthis\b', r'\.']
            }
            
            for concept_id, patterns in concept_patterns.items():
                score = 0
                for pattern in patterns:
                    matches = len(re.findall(pattern, code_lower))
                    score += min(matches * 0.2, 1.0)  # Cap individual pattern contribution
                
                programming_concepts[concept_id] = min(score, 1.0)
            
            # Check for algorithmic concepts
            algorithm_patterns = {
                "sorting": [r'\bsort\b', r'\.sort\(', r'sorted\('],
                "searching": [r'\bfind\b', r'\bsearch\b', r'\bin\b'],
                "iteration": [r'\bfor\b', r'\bwhile\b', r'\.map\(', r'\.filter\(']
            }
            
            for concept, patterns in algorithm_patterns.items():
                score = 0
                for pattern in patterns:
                    matches = len(re.findall(pattern, code_lower))
                    score += min(matches * 0.3, 1.0)
                
                algorithm_concepts[concept] = min(score, 1.0)
            
            # Check for best practices
            best_practice_patterns = {
                "meaningful_names": len(re.findall(r'\b[a-z_][a-z0-9_]{2,}\b', code_lower)) > 0,
                "comments": len(re.findall(r'#.*|//.*|/\*.*\*/', code_content)) > 0,
                "proper_indentation": '\n    ' in code_content or '\n\t' in code_content
            }
            
            for practice, present in best_practice_patterns.items():
                best_practices[practice] = 1.0 if present else 0.0
            
            # Create assessment
            assessment = CodeConceptAssessment(
                assessment_id=str(uuid.uuid4()),
                submission_id=submission_id,
                student_id=student_id,
                programming_concepts=programming_concepts,
                algorithm_concepts=algorithm_concepts,
                best_practices=best_practices,
                code_quality_metrics={
                    "lines_of_code": len(code_content.split('\n')),
                    "complexity_estimate": len(re.findall(r'\b(if|for|while)\b', code_lower))
                },
                assessed_at=datetime.utcnow()
            )
            
            # Store assessment in database
            await self.db.code_concept_assessments.insert_one(assessment.dict())
            
            return assessment
            
        except Exception as e:
            logger.error(f"Error assessing code concepts: {e}")
            raise
    
    async def get_concept_relationships(self, concept_id: str) -> List[ConceptRelationship]:
        """Get all relationships for a given concept"""
        try:
            relationships = await self.db.concept_relationships.find({
                "$or": [
                    {"source_concept_id": concept_id},
                    {"target_concept_id": concept_id}
                ]
            }).to_list(None)
            
            return [ConceptRelationship(**rel) for rel in relationships]
            
        except Exception as e:
            logger.error(f"Error getting concept relationships: {e}")
            raise
    
    async def get_concept_by_id(self, concept_id: str) -> Optional[LearningConcept]:
        """Get a concept by its ID"""
        try:
            concept_doc = await self.db.concepts.find_one({"concept_id": concept_id})
            if concept_doc:
                return LearningConcept(**concept_doc)
            return None
            
        except Exception as e:
            logger.error(f"Error getting concept by ID: {e}")
            raise
    
    async def search_concepts(self, query: str, subject_area: Optional[str] = None) -> List[LearningConcept]:
        """Search for concepts by name, description, or keywords"""
        try:
            search_filter = {
                "$or": [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"description": {"$regex": query, "$options": "i"}},
                    {"keywords": {"$in": [query.lower()]}}
                ]
            }
            
            if subject_area:
                search_filter["subject_area"] = subject_area
            
            concept_docs = await self.db.concepts.find(search_filter).to_list(None)
            return [LearningConcept(**doc) for doc in concept_docs]
            
        except Exception as e:
            logger.error(f"Error searching concepts: {e}")
            raise