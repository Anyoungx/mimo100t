# -*- coding: utf-8 -*-
"""
VerifyAgent - 测试验证 Agent

功能:
1. 执行本地测试命令
2. 收集测试结果与覆盖率数据
3. 反馈给 FixAgent 进行迭代优化

使用示例:
    from agents import VerifyAgent
    
    verify_agent = VerifyAgent()
    result = verify_agent.execute(message)  # message 来自 TestAgent
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import (
    AgentConfig, AgentMessage, AgentResult, BaseAgent, MessageType
)
from config import get_config_manager
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class TestResult:
    """单个测试结果"""
    name: str
    status: str  # "passed", "failed", "skipped"
    duration: float = 0.0
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'status': self.status,
            'duration': self.duration,
            'error_message': self.error_message
        }


@dataclass
class CoverageData:
    """覆盖率数据"""
    line_percent: float = 0.0
    branch_percent: float = 0.0
    function_percent: float = 0.0
    covered_lines: int = 0
    total_lines: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'line_percent': self.line_percent,
            'branch_percent': self.branch_percent,
            'function_percent': self.function_percent,
            'covered_lines': self.covered_lines,
            'total_lines': self.total_lines
        }


@dataclass
class VerifyReport:
    """验证报告"""
    total_tests: int
    passed: int
    failed: int
    skipped: int
    results: List[TestResult] = field(default_factory=list)
    coverage: Optional[CoverageData] = None
    execution_time: float = 0.0
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_tests': self.total_tests,
            'passed': self.passed,
            'failed': self.failed,
            'skipped': self.skipped,
            'results': [r.to_dict() for r in self.results],
            'coverage': self.coverage.to_dict() if self.coverage else None,
            'execution_time': self.execution_time,
            'summary': self.summary
        }
    
    @property
    def pass_rate(self) -> float:
        """通过率"""
        if self.total_tests == 0:
            return 0.0
        return (self.passed / self.total_tests) * 100


class VerifyAgent(BaseAgent):
    """
    测试验证 Agent
    
    执行测试并收集结果。
    
    使用示例:
        verify_agent = VerifyAgent()
        result = verify_agent.execute(message)
    """
    
    def __init__(self):
        """初始化 VerifyAgent"""
        super().__init__(
            AgentConfig(
                name="VerifyAgent",
                description="测试验证 Agent - 执行测试并收集结果"
            )
        )
        self.config = get_config_manager()
        self.config.load_config()
    
    def _execute_impl(self, message: AgentMessage) -> VerifyReport:
        """执行测试验证"""
        content = message.content
        
        # 解析输入
        project_path = content.get('project_path')
        test_files = content.get('test_files', [])
        
        if not project_path:
            raise ValueError("project_path is required")
        
        logger.info(f"Verifying tests in: {project_path}")
        
        # 确定测试命令
        framework = self.config.config.project.test_framework
        test_command = self._get_test_command(framework, test_files)
        coverage_command = self._get_coverage_command(framework)
        
        # 执行测试
        test_results = []
        coverage = None
        
        # 执行测试命令
        test_output, test_time = self._run_command(
            test_command, 
            project_path,
            timeout=300
        )
        test_results = self._parse_test_output(test_output, framework)
        
        # 执行覆盖率命令
        coverage_output, _ = self._run_command(
            coverage_command,
            project_path,
            timeout=300
        )
        coverage = self._parse_coverage_output(coverage_output, framework)
        
        # 生成报告
        passed = sum(1 for r in test_results if r.status == 'passed')
        failed = sum(1 for r in test_results if r.status == 'failed')
        skipped = sum(1 for r in test_results if r.status == 'skipped')
        
        report = VerifyReport(
            total_tests=len(test_results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            results=test_results,
            coverage=coverage,
            execution_time=test_time,
            summary=self._generate_summary(passed, failed, skipped, coverage)
        )
        
        logger.info(f"Verification completed: {passed}/{len(test_results)} passed")
        return report
    
    def _get_test_command(self, framework: str, test_files: List[str]) -> List[str]:
        """获取测试命令"""
        if framework == 'pytest':
            if test_files:
                return ['pytest', '-v', '--tb=short'] + test_files
            return ['pytest', '-v', '--tb=short']
        elif framework == 'jest':
            if test_files:
                return ['jest', '--verbose'] + test_files
            return ['jest', '--verbose']
        elif framework == 'unittest':
            return ['python', '-m', 'unittest', 'discover', '-v']
        else:
            return ['pytest', '-v']
    
    def _get_coverage_command(self, framework: str) -> List[str]:
        """获取覆盖率命令"""
        if framework == 'pytest':
            return ['pytest', '--cov=.', '--cov-report=json', '-v']
        elif framework == 'jest':
            return ['jest', '--coverage', '--coverage-reporters=json']
        else:
            return ['pytest', '--cov=.', '-v']
    
    def _run_command(self, command: List[str], cwd: str, timeout: int = 300) -> tuple:
        """运行命令"""
        try:
            logger.info(f"Running command: {' '.join(command)}")
            
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            output = result.stdout + result.stderr
            return output, result.returncode == 0
            
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {timeout}s")
            return f"Command timed out after {timeout}s", False
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return str(e), False
    
    def _parse_test_output(self, output: str, framework: str) -> List[TestResult]:
        """解析测试输出"""
        results = []
        
        if framework == 'pytest':
            results = self._parse_pytest_output(output)
        elif framework == 'jest':
            results = self._parse_jest_output(output)
        elif framework == 'unittest':
            results = self._parse_unittest_output(output)
        else:
            results = self._parse_pytest_output(output)
        
        return results
    
    def _parse_pytest_output(self, output: str) -> List[TestResult]:
        """解析 pytest 输出"""
        results = []
        
        # 匹配测试结果行
        pattern = r'(PASSED|FAILED|SKIPPED|ERROR)\s+\[([\d%]+)\]\s+(.+?)(?::|\n)'
        matches = re.findall(pattern, output, re.MULTILINE)
        
        for status, _, name, _ in matches:
            results.append(TestResult(
                name=name.strip(),
                status=status.lower(),
                duration=0.0
            ))
        
        # 备用解析：匹配 "test_xxx PASSED" 格式
        if not results:
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith('test_'):
                    parts = line.split()
                    if len(parts) >= 2:
                        status = parts[1].lower()
                        if status in ('passed', 'failed', 'skipped'):
                            results.append(TestResult(
                                name=parts[0],
                                status=status
                            ))
        
        return results
    
    def _parse_jest_output(self, output: str) -> List[TestResult]:
        """解析 jest 输出"""
        results = []
        
        # 匹配测试结果
        pattern = r'(✓|✕|○)\s+(.+)'
        for line in output.split('\n'):
            match = re.search(pattern, line)
            if match:
                status_map = {'✓': 'passed', '✕': 'failed', '○': 'skipped'}
                results.append(TestResult(
                    name=match.group(2).strip(),
                    status=status_map.get(match.group(1), 'unknown')
                ))
        
        return results
    
    def _parse_unittest_output(self, output: str) -> List[TestResult]:
        """解析 unittest 输出"""
        results = []
        
        # 匹配测试结果
        pattern = r'(OK|FAIL|ERROR):\s+(.+)'
        for line in output.split('\n'):
            match = re.search(pattern, line)
            if match:
                status_map = {'OK': 'passed', 'FAIL': 'failed', 'ERROR': 'failed'}
                results.append(TestResult(
                    name=match.group(2).strip(),
                    status=status_map.get(match.group(1), 'unknown')
                ))
        
        return results
    
    def _parse_coverage_output(self, output: str, framework: str) -> Optional[CoverageData]:
        """解析覆盖率输出"""
        if framework == 'pytest':
            return self._parse_pytest_coverage(output)
        elif framework == 'jest':
            return self._parse_jest_coverage(output)
        
        return None
    
    def _parse_pytest_coverage(self, output: str) -> Optional[CoverageData]:
        """解析 pytest-cov 输出"""
        # 查找覆盖率报告文件
        coverage_file = Path('coverage.json')
        if not coverage_file.exists():
            coverage_file = Path('.coverage')
        
        if coverage_file.exists():
            try:
                import json
                with open(coverage_file, 'r') as f:
                    data = json.load(f)
                
                totals = data.get('totals', {})
                return CoverageData(
                    line_percent=totals.get('percent_covered', 0),
                    branch_percent=totals.get('branch_percent', 0),
                    function_percent=totals.get('function_percent', 0),
                    covered_lines=totals.get('covered_lines', 0),
                    total_lines=totals.get('empty_lines', 0) + totals.get('covered_lines', 0)
                )
            except Exception as e:
                logger.warning(f"Failed to parse coverage file: {e}")
        
        # 备用：从输出中解析
        for line in output.split('\n'):
            if 'TOTAL' in line or 'coverage' in line.lower():
                match = re.search(r'(\d+)%', line)
                if match:
                    return CoverageData(
                        line_percent=float(match.group(1)),
                        branch_percent=0.0,
                        function_percent=0.0
                    )
        
        return None
    
    def _parse_jest_coverage(self, output: str) -> Optional[CoverageData]:
        """解析 jest coverage 输出"""
        for line in output.split('\n'):
            if 'All files' in line or 'Line' in line:
                # 提取行覆盖率
                match = re.search(r'Line\s+\|\s+(\d+\.?\d*)%', line)
                if match:
                    return CoverageData(
                        line_percent=float(match.group(1)),
                        branch_percent=0.0,
                        function_percent=0.0
                    )
        
        return None
    
    def _generate_summary(self, passed: int, failed: int, skipped: int, 
                         coverage: Optional[CoverageData]) -> str:
        """生成验证总结"""
        summary_parts = [f"测试执行完成: {passed} 通过, {failed} 失败, {skipped} 跳过"]
        
        if coverage:
            summary_parts.append(f"\n覆盖率: {coverage.line_percent:.1f}%")
        
        if failed > 0:
            summary_parts.append("\n⚠️  存在失败的测试，建议检查并修复。")
        else:
            summary_parts.append("\n✅ 所有测试通过！")
        
        return ''.join(summary_parts)
    
    def get_failed_tests(self, report: VerifyReport) -> List[TestResult]:
        """获取失败的测试"""
        return [r for r in report.results if r.status == 'failed']
    
    def get_fix_suggestions(self, report: VerifyReport) -> Dict[str, List[str]]:
        """获取修复建议"""
        suggestions = {}
        
        for result in report.results:
            if result.status == 'failed':
                if result.error_message:
                    suggestions[result.name] = [result.error_message]
                else:
                    suggestions[result.name] = ["检查测试逻辑和预期结果"]
        
        return suggestions
    
    def export_report(self, report: VerifyReport, filepath: str):
        """导出验证报告到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Verify report exported to {filepath}")