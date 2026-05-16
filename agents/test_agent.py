# -*- coding: utf-8 -*-
"""
TestAgent - 测试生成 Agent

功能:
1. 根据重构后的代码自动生成测试用例
2. 适配 pytest/jest 等主流测试框架
3. 覆盖关键功能和边界情况

使用示例:
    from agents import TestAgent
    
    test_agent = TestAgent()
    result = test_agent.execute(message)  # message 来自 FixAgent
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import (
    AgentConfig, AgentMessage, AgentResult, BaseAgent, MessageType
)
from project_scanner import ProjectScanner
from config import get_config_manager
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class TestCase:
    """测试用例"""
    name: str
    file: str
    test_code: str
    framework: str
    functions_tested: List[str] = field(default_factory=list)
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'file': self.file,
            'test_code': self.test_code,
            'framework': self.framework,
            'functions_tested': self.functions_tested,
            'description': self.description
        }


@dataclass
class TestReport:
    """测试报告"""
    total_tests: int
    framework: str
    tests: List[TestCase] = field(default_factory=list)
    coverage_estimate: str = ""
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_tests': self.total_tests,
            'tests': [t.to_dict() for t in self.tests],
            'framework': self.framework,
            'coverage_estimate': self.coverage_estimate,
            'summary': self.summary
        }


TEST_GENERATION_PROMPT = """你是一个专业的测试工程师。请为以下代码生成测试用例。

## 项目信息
- 项目路径: {project_path}
- 编程语言: {language}
- 测试框架: {framework}

## 需要测试的代码
{code_content}

## 测试要求
1. 测试用例应该覆盖关键功能路径
2. 包含正常情况和边界情况测试
3. 使用 mock 模拟外部依赖
4. 测试命名清晰，描述测试意图
5. 遵循测试最佳实践

## 输出格式
请以JSON格式输出测试代码，格式如下:
```json
{{
    "tests": [
        {{
            "name": "test_function_name",
            "file": "tests/test_module.py",
            "test_code": "import pytest\\n...",
            "framework": "pytest",
            "functions_tested": ["function_name"],
            "description": "测试描述"
        }}
    ],
    "summary": "测试总结"
}}
```

只输出JSON，不要有其他内容。"""


class TestAgent(BaseAgent):
    """
    测试生成 Agent
    
    根据代码生成测试用例。
    
    使用示例:
        test_agent = TestAgent()
        result = test_agent.execute(message)
    """
    
    def __init__(self):
        """初始化 TestAgent"""
        super().__init__(
            AgentConfig(
                name="TestAgent",
                description="测试生成 Agent - 自动生成测试用例"
            )
        )
        self.scanner = ProjectScanner()
        self.config = get_config_manager()
        self.config.load_config()
    
    @property
    def framework(self) -> str:
        """获取测试框架"""
        return self.config.config.project.test_framework
    
    def _execute_impl(self, message: AgentMessage) -> TestReport:
        """执行测试生成"""
        content = message.content
        
        # 解析输入
        project_path = content.get('project_path')
        fix_result = content.get('fix_result')
        
        if not project_path:
            raise ValueError("project_path is required")
        
        logger.info(f"Generating tests for project: {project_path}")
        
        # 扫描项目获取文件
        project_info = self.scanner.scan(project_path, include_content=True)
        
        # 获取需要测试的文件
        files_to_test = self._get_files_to_test(project_info, fix_result)
        
        # 生成测试
        all_tests = []
        
        for file_info in files_to_test:
            tests = self._generate_tests_for_file(
                project_path,
                file_info,
                project_info.config.language
            )
            all_tests.extend(tests)
        
        # 生成报告
        report = TestReport(
            total_tests=len(all_tests),
            tests=all_tests,
            framework=self.framework,
            coverage_estimate=self._estimate_coverage(project_info, all_tests),
            summary=self._generate_summary(all_tests)
        )
        
        logger.info(f"Generated {len(all_tests)} test cases")
        return report
    
    def _get_files_to_test(self, project_info, fix_result: Optional[Dict]) -> List:
        """获取需要测试的文件"""
        # 如果有修复结果，优先测试修改过的文件
        if fix_result and fix_result.get('suggestions'):
            modified_files = set()
            for suggestion in fix_result.get('suggestions', []):
                modified_files.add(suggestion.get('file', ''))
            
            return [f for f in project_info.files if f.relative_path in modified_files]
        
        # 否则测试所有主代码文件
        return [
            f for f in project_info.files 
            if not f.relative_path.startswith('test_') 
            and not f.relative_path.endswith('_test.py')
        ][:20]  # 限制数量
    
    def _generate_tests_for_file(self, project_path: str, file_info, language: str) -> List[TestCase]:
        """为单个文件生成测试"""
        if not file_info.content:
            return []
        
        prompt = TEST_GENERATION_PROMPT.format(
            project_path=project_path,
            language=language,
            framework=self.framework,
            code_content=file_info.content[:8000]  # 限制长度
        )
        
        messages = [
            {"role": "system", "content": "你是一个专业的测试工程师。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_api(messages)
            tests = self._parse_tests_from_response(response, file_info.relative_path)
            return tests
        except Exception as e:
            logger.error(f"Failed to generate tests for {file_info.relative_path}: {e}")
            return []
    
    def _parse_tests_from_response(self, response: str, default_file: str) -> List[TestCase]:
        """从 API 响应中解析测试用例"""
        tests = []
        
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{.*"tests".*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
            else:
                data = json.loads(response)
            
            for test_data in data.get('tests', []):
                test_file = test_data.get('file', '')
                if not test_file:
                    test_file = self._get_test_file_path(default_file)
                
                test = TestCase(
                    name=test_data.get('name', 'test_'),
                    file=test_file,
                    test_code=test_data.get('test_code', ''),
                    framework=test_data.get('framework', self.framework),
                    functions_tested=test_data.get('functions_tested', []),
                    description=test_data.get('description', '')
                )
                tests.append(test)
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
        
        return tests
    
    def _get_test_file_path(self, source_file: str) -> str:
        """根据源文件路径生成测试文件路径"""
        path = Path(source_file)
        parent = path.parent
        name = path.stem
        
        if self.framework == 'pytest':
            test_name = f"test_{name}.py"
        elif self.framework == 'jest':
            test_name = f"{name}.test.js"
        else:
            test_name = f"test_{name}.py"
        
        if str(parent) == '.':
            return f"tests/{test_name}"
        else:
            return f"{parent}/tests/{test_name}"
    
    def _estimate_coverage(self, project_info, tests: List[TestCase]) -> str:
        """估算覆盖率"""
        total_functions = sum(f.lines for f in project_info.files if f.lines > 0)
        tested_functions = sum(len(t.functions_tested) for t in tests)
        
        if total_functions > 0:
            estimated = min(100, int((tested_functions / max(1, len(project_info.files))) * 100))
            return f"~{estimated}%"
        
        return "N/A"
    
    def _generate_summary(self, tests: List[TestCase]) -> str:
        """生成测试总结"""
        if not tests:
            return "未生成任何测试用例"
        
        summary = f"共生成 {len(tests)} 个测试用例:\n"
        
        by_file = {}
        for test in tests:
            if test.file not in by_file:
                by_file[test.file] = []
            by_file[test.file].append(test)
        
        for file_path, file_tests in by_file.items():
            summary += f"\n📝 {file_path}: {len(file_tests)} 个测试\n"
        
        summary += f"\n使用测试框架: {self.framework}"
        
        return summary
    
    def write_tests(self, project_path: str, report: TestReport) -> List[str]:
        """
        写入测试文件
        
        Args:
            project_path: 项目路径
            report: 测试报告
        
        Returns:
            已写入的文件路径列表
        """
        written_files = []
        
        # 按文件分组测试
        tests_by_file = {}
        for test in report.tests:
            if test.file not in tests_by_file:
                tests_by_file[test.file] = []
            tests_by_file[test.file].append(test)
        
        for file_path, tests in tests_by_file.items():
            try:
                full_path = Path(project_path) / file_path
                
                # 确保目录存在
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 合并测试代码
                test_content = self._combine_test_code(tests)
                
                # 写入文件
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(test_content)
                
                written_files.append(file_path)
                logger.info(f"Written test file: {file_path}")
                
            except Exception as e:
                logger.error(f"Failed to write test file {file_path}: {e}")
        
        return written_files
    
    def _combine_test_code(self, tests: List[TestCase]) -> str:
        """合并多个测试到单个文件"""
        if not tests:
            return ""
        
        parts = []
        
        # 添加文件头注释
        parts.append('"""\n')
        parts.append('测试文件 - 自动生成\n')
        parts.append('"""\n\n')
        
        # 根据框架添加导入
        if self.framework == 'pytest':
            parts.append("import pytest\n")
            parts.append("from unittest.mock import Mock, patch\n\n")
        elif self.framework == 'jest':
            parts.append("import { describe, it, expect, jest } from '@jest/globals';\n\n")
        
        # 添加每个测试
        for test in tests:
            if test.description:
                parts.append(f'\n# {test.description}\n')
            parts.append(test.test_code)
            parts.append('\n')
        
        return ''.join(parts)
    
    def export_tests(self, report: TestReport, filepath: str):
        """导出测试报告到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Test report exported to {filepath}")