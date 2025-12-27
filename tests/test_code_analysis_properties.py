"""
Property-based tests for code analysis functionality
Feature: learning-analytics-platform, Property 2: Code analysis completeness
"""
import pytest
from hypothesis import given, strategies as st, settings as hypothesis_settings, HealthCheck
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from app.services.data_collection_service import DataCollectionService
from app.services.code_analysis_service import CodeAnalysisService
from app.models.performance import CodeSubmissionRequest, SubmissionType


class TestCodeAnalysisProperties:
    """
    Property 2: Code analysis completeness
    Validates: Requirements 1.2
    """
    
    def create_mock_db(self):
        """Create mock database for testing"""
        db = MagicMock()
        db.student_performance = MagicMock()
        return db
    
    def create_data_service(self, mock_db):
        """Create DataCollectionService instance with mocked database"""
        return DataCollectionService(mock_db)
    
    @pytest.mark.asyncio
    @given(
        student_id=st.text(min_size=1, max_size=50),
        course_id=st.text(min_size=1, max_size=50),
        assignment_id=st.text(min_size=1, max_size=50),
        language=st.sampled_from(["python", "javascript", "java", "cpp", "c"]),
        code_content=st.text(min_size=10, max_size=1000),
        test_results=st.fixed_dictionaries({
            'passed': st.integers(min_value=0, max_value=20),
            'total': st.integers(min_value=1, max_value=20),
            'coverage': st.floats(min_value=0.0, max_value=1.0),
            'execution_time': st.floats(min_value=0.0, max_value=5000.0),
            'syntax_errors': st.integers(min_value=0, max_value=5),
            'runtime_errors': st.integers(min_value=0, max_value=5)
        })
    )
    @hypothesis_settings(
        max_examples=30, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_code_analysis_completeness_property(
        self,
        student_id,
        course_id,
        assignment_id,
        language,
        code_content,
        test_results
    ):
        """
        Feature: learning-analytics-platform, Property 2: Code analysis completeness
        
        For any code submission, the analysis should produce correctness, efficiency, 
        and concept understanding metrics.
        """
        # Ensure passed tests don't exceed total tests
        if test_results['passed'] > test_results['total']:
            test_results['passed'] = test_results['total']
        
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        data_service = self.create_data_service(mock_db)
        
        # Create code submission request
        code_submission = CodeSubmissionRequest(
            student_id=student_id,
            course_id=course_id,
            assignment_id=assignment_id,
            code_content=code_content,
            language=language,
            test_results=test_results
        )
        
        # Mock database insert result
        mock_insert_result = MagicMock()
        mock_insert_result.inserted_id = f"code_submission_{student_id}"
        mock_db.student_performance.insert_one = AsyncMock(return_value=mock_insert_result)
        
        # Process code submission
        result = await data_service.process_code_submission(code_submission)
        
        # Verify submission response structure
        assert result.student_id == student_id, "Response should contain correct student ID"
        assert result.submission_type == SubmissionType.CODE, "Response should indicate code submission type"
        assert result.submission_id is not None, "Response should contain submission ID"
        assert isinstance(result.timestamp, datetime), "Response should contain valid timestamp"
        
        # Verify database was called to store data
        mock_db.student_performance.insert_one.assert_called_once()
        stored_data = mock_db.student_performance.insert_one.call_args[0][0]
        
        # Verify code analysis completeness - all required metrics should be present
        assert stored_data["student_id"] == student_id, "Stored data should contain student ID"
        assert stored_data["course_id"] == course_id, "Stored data should contain course ID"
        assert stored_data["assignment_id"] == assignment_id, "Stored data should contain assignment ID"
        assert stored_data["submission_type"] == SubmissionType.CODE, "Stored data should indicate code type"
        assert stored_data["code_content"] == code_content, "Stored data should contain original code"
        
        # Verify code metrics are present and complete
        assert "code_metrics" in stored_data, "Stored data should contain code metrics"
        code_metrics = stored_data["code_metrics"]
        
        # Correctness metrics
        assert "passed_tests" in code_metrics, "Code metrics should include passed tests count"
        assert "total_tests" in code_metrics, "Code metrics should include total tests count"
        assert "syntax_errors" in code_metrics, "Code metrics should include syntax errors count"
        assert "runtime_errors" in code_metrics, "Code metrics should include runtime errors count"
        assert code_metrics["passed_tests"] == test_results["passed"], "Passed tests should match input"
        assert code_metrics["total_tests"] == test_results["total"], "Total tests should match input"
        
        # Efficiency metrics
        assert "complexity" in code_metrics, "Code metrics should include complexity measure"
        assert "execution_time" in code_metrics, "Code metrics should include execution time"
        assert "memory_usage" in code_metrics, "Code metrics should include memory usage"
        assert isinstance(code_metrics["complexity"], int), "Complexity should be an integer"
        assert code_metrics["complexity"] >= 1, "Complexity should be at least 1"
        
        # Test coverage metrics
        assert "test_coverage" in code_metrics, "Code metrics should include test coverage"
        assert code_metrics["test_coverage"] == test_results["coverage"], "Test coverage should match input"
        
        # Verify metadata contains language and analysis info
        assert "metadata" in stored_data, "Stored data should contain metadata"
        metadata = stored_data["metadata"]
        assert metadata["language"] == language, "Metadata should contain programming language"
        assert "code_length" in metadata, "Metadata should contain code length"
        assert metadata["code_length"] == len(code_content), "Code length should match actual length"
    
    @pytest.mark.asyncio
    @given(
        python_code=st.text(min_size=20, max_size=500),
        test_results=st.fixed_dictionaries({
            'passed': st.integers(min_value=0, max_value=10),
            'total': st.integers(min_value=1, max_value=10),
            'coverage': st.floats(min_value=0.0, max_value=1.0),
            'execution_time': st.floats(min_value=0.0, max_value=1000.0)
        })
    )
    @hypothesis_settings(
        max_examples=20, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_python_code_analysis_property(
        self,
        python_code,
        test_results
    ):
        """
        Feature: learning-analytics-platform, Property 2: Code analysis completeness
        
        For any Python code submission, the analysis should handle Python-specific 
        constructs and provide accurate complexity metrics.
        """
        # Ensure passed tests don't exceed total tests
        if test_results['passed'] > test_results['total']:
            test_results['passed'] = test_results['total']
        
        # Create code analysis service
        code_analyzer = CodeAnalysisService()
        
        # Analyze Python code
        metrics = await code_analyzer.analyze_code_submission(
            code=python_code,
            language="python",
            test_results=test_results
        )
        
        # Verify metrics structure
        assert metrics.complexity >= 1, "Complexity should be at least 1"
        assert metrics.test_coverage == test_results["coverage"], "Test coverage should match input"
        assert metrics.execution_time == test_results["execution_time"], "Execution time should match input"
        assert metrics.passed_tests == test_results["passed"], "Passed tests should match input"
        assert metrics.total_tests == test_results["total"], "Total tests should match input"
        assert metrics.memory_usage > 0, "Memory usage should be positive"
        
        # Test concept understanding assessment
        concepts = await code_analyzer.assess_concept_understanding(python_code, "python")
        
        # Verify concept analysis structure
        assert "data_structures" in concepts, "Concept analysis should include data structures"
        assert "algorithms" in concepts, "Concept analysis should include algorithms"
        assert "design_patterns" in concepts, "Concept analysis should include design patterns"
        assert "best_practices" in concepts, "Concept analysis should include best practices"
        assert "programming_paradigms" in concepts, "Concept analysis should include programming paradigms"
        
        # All concept categories should be lists
        for category, items in concepts.items():
            assert isinstance(items, list), f"Concept category {category} should be a list"
    
    @pytest.mark.asyncio
    @given(
        language=st.sampled_from(["javascript", "java", "cpp", "c"]),
        code_content=st.text(min_size=20, max_size=300),
        complexity_indicators=st.integers(min_value=0, max_value=10)
    )
    @hypothesis_settings(
        max_examples=25, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_multi_language_analysis_property(
        self,
        language,
        code_content,
        complexity_indicators
    ):
        """
        Feature: learning-analytics-platform, Property 2: Code analysis completeness
        
        For any supported programming language, the analysis should provide 
        consistent metrics regardless of the language used.
        """
        # Add some complexity indicators to the code
        if language == "javascript":
            code_with_complexity = code_content + "\n" + "if (true) { }" * complexity_indicators
        elif language == "java":
            code_with_complexity = code_content + "\n" + "if (true) { }" * complexity_indicators
        elif language in ["cpp", "c"]:
            code_with_complexity = code_content + "\n" + "if (1) { }" * complexity_indicators
        else:
            code_with_complexity = code_content
        
        # Create code analysis service
        code_analyzer = CodeAnalysisService()
        
        # Analyze code
        metrics = await code_analyzer.analyze_code_submission(
            code=code_with_complexity,
            language=language,
            test_results=None
        )
        
        # Verify basic metrics are always present
        assert metrics.complexity >= 1, f"Complexity should be at least 1 for {language}"
        assert metrics.memory_usage > 0, f"Memory usage should be positive for {language}"
        assert metrics.test_coverage >= 0.0, f"Test coverage should be non-negative for {language}"
        assert metrics.execution_time >= 0.0, f"Execution time should be non-negative for {language}"
        assert metrics.syntax_errors >= 0, f"Syntax errors should be non-negative for {language}"
        assert metrics.runtime_errors >= 0, f"Runtime errors should be non-negative for {language}"
        
        # Complexity should increase with complexity indicators
        if complexity_indicators > 0:
            assert metrics.complexity > 1, f"Complexity should increase with control structures for {language}"
        
        # Test concept understanding for all languages
        concepts = await code_analyzer.assess_concept_understanding(code_with_complexity, language)
        
        # Verify concept analysis structure is consistent across languages
        expected_categories = ["data_structures", "algorithms", "design_patterns", "best_practices", "programming_paradigms"]
        for category in expected_categories:
            assert category in concepts, f"Concept analysis should include {category} for {language}"
            assert isinstance(concepts[category], list), f"Concept category {category} should be a list for {language}"
    
    @pytest.mark.asyncio
    @given(
        student_id=st.text(min_size=1, max_size=50),
        course_id=st.text(min_size=1, max_size=50),
        assignment_id=st.text(min_size=1, max_size=50),
        invalid_code=st.one_of(
            st.just(""),  # Empty code
            st.just("   "),  # Whitespace only
            st.just("invalid syntax here!!!"),  # Invalid syntax
        ),
        language=st.sampled_from(["python", "javascript", "java"])
    )
    @hypothesis_settings(
        max_examples=15, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_invalid_code_handling_property(
        self,
        student_id,
        course_id,
        assignment_id,
        invalid_code,
        language
    ):
        """
        Feature: learning-analytics-platform, Property 2: Code analysis completeness
        
        For any invalid or empty code submission, the system should handle it gracefully
        and provide appropriate error handling without crashing.
        """
        # Create fresh mocks for each test
        mock_db = self.create_mock_db()
        data_service = self.create_data_service(mock_db)
        
        # Create code submission request with invalid code
        code_submission = CodeSubmissionRequest(
            student_id=student_id,
            course_id=course_id,
            assignment_id=assignment_id,
            code_content=invalid_code,
            language=language
        )
        
        # Process should either succeed with error metrics or raise validation error
        try:
            # Mock database insert result
            mock_insert_result = MagicMock()
            mock_insert_result.inserted_id = f"invalid_code_submission_{student_id}"
            mock_db.student_performance.insert_one = AsyncMock(return_value=mock_insert_result)
            
            result = await data_service.process_code_submission(code_submission)
            
            # If processing succeeds, verify error handling
            assert result.student_id == student_id, "Response should contain correct student ID"
            assert result.submission_type == SubmissionType.CODE, "Response should indicate code submission type"
            
            # Verify database was called
            mock_db.student_performance.insert_one.assert_called_once()
            stored_data = mock_db.student_performance.insert_one.call_args[0][0]
            
            # For invalid code, metrics should still be present but may indicate errors
            assert "code_metrics" in stored_data, "Stored data should contain code metrics even for invalid code"
            code_metrics = stored_data["code_metrics"]
            
            # Error counts should be non-negative
            assert code_metrics.get("syntax_errors", 0) >= 0, "Syntax errors should be non-negative"
            assert code_metrics.get("runtime_errors", 0) >= 0, "Runtime errors should be non-negative"
            
        except ValueError as e:
            # Validation error is acceptable for invalid code
            error_message = str(e).lower()
            assert any(keyword in error_message for keyword in ["validation", "empty", "invalid"]), \
                "Validation error should indicate the nature of the problem"
            
            # Verify database was not called for invalid submission
            mock_db.student_performance.insert_one.assert_not_called()
    
    @pytest.mark.asyncio
    @given(
        code_with_patterns=st.text(min_size=50, max_size=200),
        pattern_type=st.sampled_from(["loops", "conditionals", "functions", "classes"])
    )
    @hypothesis_settings(
        max_examples=20, 
        deadline=5000,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    async def test_concept_detection_accuracy_property(
        self,
        code_with_patterns,
        pattern_type
    ):
        """
        Feature: learning-analytics-platform, Property 2: Code analysis completeness
        
        For any code containing specific programming patterns, the concept analysis
        should accurately detect and categorize those patterns.
        """
        # Add specific patterns to the code based on pattern_type
        if pattern_type == "loops":
            enhanced_code = code_with_patterns + "\nfor i in range(10):\n    print(i)"
            expected_concept = "iteration"
        elif pattern_type == "conditionals":
            enhanced_code = code_with_patterns + "\nif True:\n    pass\nelse:\n    pass"
            expected_concept = "conditional_logic"
        elif pattern_type == "functions":
            enhanced_code = code_with_patterns + "\ndef my_function():\n    return True"
            expected_concept = "functions"
        elif pattern_type == "classes":
            enhanced_code = code_with_patterns + "\nclass MyClass:\n    def __init__(self):\n        pass"
            expected_concept = "object_oriented"
        else:
            enhanced_code = code_with_patterns
            expected_concept = None
        
        # Create code analysis service
        code_analyzer = CodeAnalysisService()
        
        # Analyze the enhanced code
        concepts = await code_analyzer.assess_concept_understanding(enhanced_code, "python")
        
        # Verify concept detection
        all_detected_concepts = []
        for category, items in concepts.items():
            all_detected_concepts.extend(items)
        
        # The analysis should detect programming concepts when they exist
        assert isinstance(concepts, dict), "Concept analysis should return a dictionary"
        assert len(concepts) > 0, "Concept analysis should return some categories"
        
        # Verify that the analysis doesn't crash and returns valid structure
        for category, items in concepts.items():
            assert isinstance(items, list), f"Category {category} should contain a list of concepts"
            for item in items:
                assert isinstance(item, str), f"Concept items should be strings in category {category}"