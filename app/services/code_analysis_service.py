"""
Advanced code analysis service for code submissions
"""
import ast
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from app.models.performance import CodeMetrics

logger = logging.getLogger(__name__)


class CodeAnalysisService:
    """Service for analyzing code submissions for complexity, quality, and concept understanding"""
    
    def __init__(self):
        self.supported_languages = {
            "python": self._analyze_python_code,
            "javascript": self._analyze_javascript_code,
            "java": self._analyze_java_code,
            "cpp": self._analyze_cpp_code,
            "c": self._analyze_c_code
        }
    
    async def analyze_code_submission(self, code: str, language: str, test_results: Optional[Dict[str, Any]] = None) -> CodeMetrics:
        """
        Analyze code submission for metrics and concept understanding
        
        Requirements: 1.2 - Analyze code for correctness, efficiency, and concept understanding
        """
        try:
            if language not in self.supported_languages:
                logger.warning(f"Unsupported language: {language}")
                return self._create_basic_metrics(code, test_results)
            
            # Use language-specific analysis
            analyzer = self.supported_languages[language]
            metrics = await analyzer(code, test_results)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error analyzing {language} code: {e}")
            return self._create_basic_metrics(code, test_results)
    
    async def _analyze_python_code(self, code: str, test_results: Optional[Dict[str, Any]] = None) -> CodeMetrics:
        """Analyze Python code using AST parsing"""
        try:
            # Parse the code into an AST
            tree = ast.parse(code)
            
            # Calculate cyclomatic complexity
            complexity = self._calculate_python_complexity(tree)
            
            # Analyze code structure and patterns
            structure_analysis = self._analyze_python_structure(tree)
            
            # Extract test results
            test_metrics = self._extract_test_metrics(test_results)
            
            # Calculate execution metrics (simulated)
            execution_time = test_results.get("execution_time", 0.0) if test_results else 0.0
            memory_usage = len(code.encode('utf-8'))  # Approximate
            
            return CodeMetrics(
                complexity=complexity,
                test_coverage=test_metrics["coverage"],
                execution_time=execution_time,
                memory_usage=memory_usage,
                syntax_errors=test_metrics["syntax_errors"],
                runtime_errors=test_metrics["runtime_errors"],
                passed_tests=test_metrics["passed_tests"],
                total_tests=test_metrics["total_tests"]
            )
            
        except SyntaxError as e:
            logger.warning(f"Python syntax error in code: {e}")
            test_metrics = self._extract_test_metrics(test_results)
            return CodeMetrics(
                complexity=1,
                test_coverage=test_metrics["coverage"],
                execution_time=test_results.get("execution_time", 0.0) if test_results else 0.0,
                memory_usage=len(code.encode('utf-8')),
                syntax_errors=test_metrics["syntax_errors"] + 1,
                runtime_errors=test_metrics["runtime_errors"],
                passed_tests=test_metrics["passed_tests"],
                total_tests=test_metrics["total_tests"]
            )
    
    async def _analyze_javascript_code(self, code: str, test_results: Optional[Dict[str, Any]] = None) -> CodeMetrics:
        """Analyze JavaScript code using regex patterns"""
        # Basic JavaScript analysis using regex patterns
        complexity = self._calculate_js_complexity(code)
        test_metrics = self._extract_test_metrics(test_results)
        
        return CodeMetrics(
            complexity=complexity,
            test_coverage=test_metrics["coverage"],
            execution_time=test_results.get("execution_time", 0.0) if test_results else 0.0,
            memory_usage=len(code.encode('utf-8')),
            syntax_errors=test_metrics["syntax_errors"],
            runtime_errors=test_metrics["runtime_errors"],
            passed_tests=test_metrics["passed_tests"],
            total_tests=test_metrics["total_tests"]
        )
    
    async def _analyze_java_code(self, code: str, test_results: Optional[Dict[str, Any]] = None) -> CodeMetrics:
        """Analyze Java code using regex patterns"""
        complexity = self._calculate_java_complexity(code)
        test_metrics = self._extract_test_metrics(test_results)
        
        return CodeMetrics(
            complexity=complexity,
            test_coverage=test_metrics["coverage"],
            execution_time=test_results.get("execution_time", 0.0) if test_results else 0.0,
            memory_usage=len(code.encode('utf-8')),
            syntax_errors=test_metrics["syntax_errors"],
            runtime_errors=test_metrics["runtime_errors"],
            passed_tests=test_metrics["passed_tests"],
            total_tests=test_metrics["total_tests"]
        )
    
    async def _analyze_cpp_code(self, code: str, test_results: Optional[Dict[str, Any]] = None) -> CodeMetrics:
        """Analyze C++ code using regex patterns"""
        complexity = self._calculate_cpp_complexity(code)
        test_metrics = self._extract_test_metrics(test_results)
        
        return CodeMetrics(
            complexity=complexity,
            test_coverage=test_metrics["coverage"],
            execution_time=test_results.get("execution_time", 0.0) if test_results else 0.0,
            memory_usage=len(code.encode('utf-8')),
            syntax_errors=test_metrics["syntax_errors"],
            runtime_errors=test_metrics["runtime_errors"],
            passed_tests=test_metrics["passed_tests"],
            total_tests=test_metrics["total_tests"]
        )
    
    async def _analyze_c_code(self, code: str, test_results: Optional[Dict[str, Any]] = None) -> CodeMetrics:
        """Analyze C code using regex patterns"""
        complexity = self._calculate_c_complexity(code)
        test_metrics = self._extract_test_metrics(test_results)
        
        return CodeMetrics(
            complexity=complexity,
            test_coverage=test_metrics["coverage"],
            execution_time=test_results.get("execution_time", 0.0) if test_results else 0.0,
            memory_usage=len(code.encode('utf-8')),
            syntax_errors=test_metrics["syntax_errors"],
            runtime_errors=test_metrics["runtime_errors"],
            passed_tests=test_metrics["passed_tests"],
            total_tests=test_metrics["total_tests"]
        )
    
    def _calculate_python_complexity(self, tree: ast.AST) -> int:
        """Calculate cyclomatic complexity for Python code"""
        complexity = 1  # Base complexity
        
        for node in ast.walk(tree):
            # Decision points that increase complexity
            if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1
            elif isinstance(node, ast.With, ast.AsyncWith):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                # And/Or operations add complexity
                complexity += len(node.values) - 1
            elif isinstance(node, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp):
                # Comprehensions add complexity
                complexity += 1
        
        return complexity
    
    def _calculate_js_complexity(self, code: str) -> int:
        """Calculate complexity for JavaScript code using regex"""
        complexity = 1
        
        # Count control structures
        control_patterns = [
            r'\bif\s*\(',
            r'\belse\b',
            r'\bwhile\s*\(',
            r'\bfor\s*\(',
            r'\bswitch\s*\(',
            r'\bcase\s+',
            r'\bcatch\s*\(',
            r'\btry\s*\{',
            r'\?\s*.*\s*:',  # Ternary operator
        ]
        
        for pattern in control_patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            complexity += len(matches)
        
        return complexity
    
    def _calculate_java_complexity(self, code: str) -> int:
        """Calculate complexity for Java code using regex"""
        complexity = 1
        
        # Count control structures
        control_patterns = [
            r'\bif\s*\(',
            r'\belse\b',
            r'\bwhile\s*\(',
            r'\bfor\s*\(',
            r'\bswitch\s*\(',
            r'\bcase\s+',
            r'\bcatch\s*\(',
            r'\btry\s*\{',
            r'\?\s*.*\s*:',  # Ternary operator
        ]
        
        for pattern in control_patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            complexity += len(matches)
        
        return complexity
    
    def _calculate_cpp_complexity(self, code: str) -> int:
        """Calculate complexity for C++ code using regex"""
        complexity = 1
        
        # Count control structures
        control_patterns = [
            r'\bif\s*\(',
            r'\belse\b',
            r'\bwhile\s*\(',
            r'\bfor\s*\(',
            r'\bswitch\s*\(',
            r'\bcase\s+',
            r'\bcatch\s*\(',
            r'\btry\s*\{',
            r'\?\s*.*\s*:',  # Ternary operator
        ]
        
        for pattern in control_patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            complexity += len(matches)
        
        return complexity
    
    def _calculate_c_complexity(self, code: str) -> int:
        """Calculate complexity for C code using regex"""
        complexity = 1
        
        # Count control structures
        control_patterns = [
            r'\bif\s*\(',
            r'\belse\b',
            r'\bwhile\s*\(',
            r'\bfor\s*\(',
            r'\bswitch\s*\(',
            r'\bcase\s+',
            r'\?\s*.*\s*:',  # Ternary operator
        ]
        
        for pattern in control_patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            complexity += len(matches)
        
        return complexity
    
    def _analyze_python_structure(self, tree: ast.AST) -> Dict[str, Any]:
        """Analyze Python code structure for concept understanding"""
        analysis = {
            "functions": 0,
            "classes": 0,
            "loops": 0,
            "conditionals": 0,
            "imports": 0,
            "list_comprehensions": 0,
            "exception_handling": 0
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                analysis["functions"] += 1
            elif isinstance(node, ast.ClassDef):
                analysis["classes"] += 1
            elif isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
                analysis["loops"] += 1
            elif isinstance(node, ast.If):
                analysis["conditionals"] += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                analysis["imports"] += 1
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                analysis["list_comprehensions"] += 1
            elif isinstance(node, (ast.Try, ast.ExceptHandler)):
                analysis["exception_handling"] += 1
        
        return analysis
    
    def _extract_test_metrics(self, test_results: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract test metrics from test results"""
        if not test_results:
            return {
                "passed_tests": 0,
                "total_tests": 0,
                "coverage": 0.0,
                "syntax_errors": 0,
                "runtime_errors": 0
            }
        
        return {
            "passed_tests": test_results.get("passed", 0),
            "total_tests": test_results.get("total", 0),
            "coverage": test_results.get("coverage", 0.0),
            "syntax_errors": test_results.get("syntax_errors", 0),
            "runtime_errors": test_results.get("runtime_errors", 0)
        }
    
    def _create_basic_metrics(self, code: str, test_results: Optional[Dict[str, Any]] = None) -> CodeMetrics:
        """Create basic metrics when advanced analysis fails"""
        test_metrics = self._extract_test_metrics(test_results)
        
        return CodeMetrics(
            complexity=1,
            test_coverage=test_metrics["coverage"],
            execution_time=test_results.get("execution_time", 0.0) if test_results else 0.0,
            memory_usage=len(code.encode('utf-8')),
            syntax_errors=test_metrics["syntax_errors"],
            runtime_errors=test_metrics["runtime_errors"],
            passed_tests=test_metrics["passed_tests"],
            total_tests=test_metrics["total_tests"]
        )
    
    async def assess_concept_understanding(self, code: str, language: str) -> Dict[str, Any]:
        """
        Assess programming concept understanding from code
        
        Requirements: 1.2 - Assess understanding of programming concepts, algorithms, and best practices
        """
        try:
            concepts = {
                "data_structures": [],
                "algorithms": [],
                "design_patterns": [],
                "best_practices": [],
                "programming_paradigms": []
            }
            
            if language == "python":
                concepts = await self._assess_python_concepts(code)
            elif language == "javascript":
                concepts = await self._assess_javascript_concepts(code)
            elif language in ["java", "cpp", "c"]:
                concepts = await self._assess_compiled_language_concepts(code, language)
            
            return concepts
            
        except Exception as e:
            logger.error(f"Error assessing concept understanding: {e}")
            return {
                "data_structures": [],
                "algorithms": [],
                "design_patterns": [],
                "best_practices": [],
                "programming_paradigms": []
            }
    
    async def _assess_python_concepts(self, code: str) -> Dict[str, List[str]]:
        """Assess Python-specific programming concepts"""
        concepts = {
            "data_structures": [],
            "algorithms": [],
            "design_patterns": [],
            "best_practices": [],
            "programming_paradigms": []
        }
        
        # Data structures
        if re.search(r'\blist\s*\(|\[.*\]', code):
            concepts["data_structures"].append("lists")
        if re.search(r'\bdict\s*\(|\{.*\}', code):
            concepts["data_structures"].append("dictionaries")
        if re.search(r'\bset\s*\(', code):
            concepts["data_structures"].append("sets")
        if re.search(r'\btuple\s*\(|\(.*,.*\)', code):
            concepts["data_structures"].append("tuples")
        
        # Algorithms
        if re.search(r'\bsort\b|\bsorted\b', code):
            concepts["algorithms"].append("sorting")
        if re.search(r'\bfor\s+.*\bin\s+.*:', code):
            concepts["algorithms"].append("iteration")
        if re.search(r'\brecursion\b|def\s+\w+.*:\s*.*\1\(', code):
            concepts["algorithms"].append("recursion")
        
        # Best practices
        if re.search(r'""".*?"""', code, re.DOTALL):
            concepts["best_practices"].append("documentation")
        if re.search(r'\btry\s*:', code):
            concepts["best_practices"].append("error_handling")
        if re.search(r'\bwith\s+.*:', code):
            concepts["best_practices"].append("context_managers")
        
        # Programming paradigms
        if re.search(r'\bclass\s+\w+', code):
            concepts["programming_paradigms"].append("object_oriented")
        if re.search(r'\blambda\s+', code):
            concepts["programming_paradigms"].append("functional")
        if re.search(r'\bmap\s*\(|\bfilter\s*\(|\breduce\s*\(', code):
            concepts["programming_paradigms"].append("functional")
        
        return concepts
    
    async def _assess_javascript_concepts(self, code: str) -> Dict[str, List[str]]:
        """Assess JavaScript-specific programming concepts"""
        concepts = {
            "data_structures": [],
            "algorithms": [],
            "design_patterns": [],
            "best_practices": [],
            "programming_paradigms": []
        }
        
        # Data structures
        if re.search(r'\[.*\]', code):
            concepts["data_structures"].append("arrays")
        if re.search(r'\{.*\}', code):
            concepts["data_structures"].append("objects")
        if re.search(r'\bnew\s+Map\s*\(', code):
            concepts["data_structures"].append("maps")
        if re.search(r'\bnew\s+Set\s*\(', code):
            concepts["data_structures"].append("sets")
        
        # Programming paradigms
        if re.search(r'\bclass\s+\w+', code):
            concepts["programming_paradigms"].append("object_oriented")
        if re.search(r'=>', code):
            concepts["programming_paradigms"].append("functional")
        if re.search(r'\basync\s+function|\basync\s+\w+\s*=>', code):
            concepts["programming_paradigms"].append("asynchronous")
        
        return concepts
    
    async def _assess_compiled_language_concepts(self, code: str, language: str) -> Dict[str, List[str]]:
        """Assess concepts for compiled languages (Java, C++, C)"""
        concepts = {
            "data_structures": [],
            "algorithms": [],
            "design_patterns": [],
            "best_practices": [],
            "programming_paradigms": []
        }
        
        # Common patterns for compiled languages
        if re.search(r'\bclass\s+\w+', code):
            concepts["programming_paradigms"].append("object_oriented")
        if re.search(r'\bstruct\s+\w+', code):
            concepts["data_structures"].append("structures")
        if re.search(r'\bfor\s*\(', code):
            concepts["algorithms"].append("iteration")
        if re.search(r'\bif\s*\(', code):
            concepts["algorithms"].append("conditional_logic")
        
        return concepts