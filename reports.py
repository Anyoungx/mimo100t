# -*- coding: utf-8 -*-
"""
报告生成模块 - 生成项目质量报告

功能:
1. 生成项目质量报告
2. 支持 Markdown/HTML 格式导出
3. 包含问题统计、修复对比、覆盖率变化、Token 消耗明细

使用示例:
    from reports import ReportGenerator
    
    generator = ReportGenerator()
    report = generator.generate_summary_report(scan_result, fix_result, test_result, verify_result)
    generator.export_markdown(report, "report.md")
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Template

from config import get_config_manager
from logger import get_logger
from mimo_api import get_mimo_api

logger = get_logger(__name__)


@dataclass
class QualityMetrics:
    """质量指标"""
    total_files: int = 0
    total_issues: int = 0
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0
    fixed_issues: int = 0
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    coverage_percent: float = 0.0


@dataclass
class SummaryReport:
    """完整质量报告"""
    project_name: str
    project_path: str
    generated_at: str
    metrics: QualityMetrics
    scan_summary: str = ""
    fix_summary: str = ""
    test_summary: str = ""
    verify_summary: str = ""
    token_usage: Dict[str, Any] = field(default_factory=dict)
    issues_by_category: Dict[str, int] = field(default_factory=dict)
    issues_by_file: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'project_name': self.project_name,
            'project_path': self.project_path,
            'generated_at': self.generated_at,
            'metrics': {
                'total_files': self.metrics.total_files,
                'total_issues': self.metrics.total_issues,
                'critical_issues': self.metrics.critical_issues,
                'high_issues': self.metrics.high_issues,
                'medium_issues': self.metrics.medium_issues,
                'low_issues': self.metrics.low_issues,
                'fixed_issues': self.metrics.fixed_issues,
                'total_tests': self.metrics.total_tests,
                'passed_tests': self.metrics.passed_tests,
                'failed_tests': self.metrics.failed_tests,
                'coverage_percent': self.metrics.coverage_percent
            },
            'scan_summary': self.scan_summary,
            'fix_summary': self.fix_summary,
            'test_summary': self.test_summary,
            'verify_summary': self.verify_summary,
            'token_usage': self.token_usage,
            'issues_by_category': self.issues_by_category,
            'issues_by_file': self.issues_by_file
        }


class ReportGenerator:
    """
    报告生成器
    
    生成项目质量报告，支持多种格式导出。
    
    使用示例:
        generator = ReportGenerator()
        report = generator.generate_summary_report(...)
        generator.export_markdown(report, "report.md")
    """
    
    def __init__(self):
        """初始化报告生成器"""
        self.config = get_config_manager()
        self.config.load_config()
    
    def generate_summary_report(
        self,
        scan_result: Optional[Dict] = None,
        fix_result: Optional[Dict] = None,
        test_result: Optional[Dict] = None,
        verify_result: Optional[Dict] = None,
        project_name: str = "Project",
        project_path: str = ""
    ) -> SummaryReport:
        """
        生成完整质量报告
        
        Args:
            scan_result: 扫描结果
            fix_result: 修复结果
            test_result: 测试结果
            verify_result: 验证结果
            project_name: 项目名称
            project_path: 项目路径
        
        Returns:
            完整质量报告
        """
        # 获取 Token 统计
        api = get_mimo_api()
        token_stats = api.get_token_stats()
        
        # 提取指标
        metrics = self._extract_metrics(
            scan_result, fix_result, test_result, verify_result
        )
        
        # 提取问题统计
        issues_by_category = {}
        issues_by_file = {}
        
        if scan_result and scan_result.get('issues'):
            for issue in scan_result['issues']:
                category = issue.get('category', 'unknown')
                issues_by_category[category] = issues_by_category.get(category, 0) + 1
                
                file_path = issue.get('file', 'unknown')
                issues_by_file[file_path] = issues_by_file.get(file_path, 0) + 1
        
        report = SummaryReport(
            project_name=project_name,
            project_path=project_path,
            generated_at=datetime.now().isoformat(),
            metrics=metrics,
            scan_summary=self._format_scan_summary(scan_result),
            fix_summary=self._format_fix_summary(fix_result),
            test_summary=self._format_test_summary(test_result),
            verify_summary=self._format_verify_summary(verify_result),
            token_usage=token_stats.to_dict(),
            issues_by_category=issues_by_category,
            issues_by_file=issues_by_file
        )
        
        return report
    
    def _extract_metrics(
        self,
        scan_result: Optional[Dict],
        fix_result: Optional[Dict],
        test_result: Optional[Dict],
        verify_result: Optional[Dict]
    ) -> QualityMetrics:
        """提取质量指标"""
        metrics = QualityMetrics()
        
        # 从扫描结果提取
        if scan_result:
            metrics.total_files = scan_result.get('total_files', 0)
            metrics.total_issues = scan_result.get('total_issues', 0)
            
            by_severity = scan_result.get('issues_by_severity', {})
            metrics.critical_issues = by_severity.get('critical', 0)
            metrics.high_issues = by_severity.get('high', 0)
            metrics.medium_issues = by_severity.get('medium', 0)
            metrics.low_issues = by_severity.get('low', 0)
        
        # 从修复结果提取
        if fix_result:
            metrics.fixed_issues = fix_result.get('fixed_count', 0)
        
        # 从验证结果提取
        if verify_result:
            metrics.total_tests = verify_result.get('total_tests', 0)
            metrics.passed_tests = verify_result.get('passed', 0)
            metrics.failed_tests = verify_result.get('failed', 0)
            
            coverage = verify_result.get('coverage')
            if coverage:
                metrics.coverage_percent = coverage.get('line_percent', 0.0)
        
        return metrics
    
    def _format_scan_summary(self, scan_result: Optional[Dict]) -> str:
        """格式化扫描摘要"""
        if not scan_result:
            return "未执行扫描"
        
        total_files = scan_result.get('total_files', 0)
        total_issues = scan_result.get('total_issues', 0)
        
        return f"扫描了 {total_files} 个文件，发现 {total_issues} 个问题"
    
    def _format_fix_summary(self, fix_result: Optional[Dict]) -> str:
        """格式化修复摘要"""
        if not fix_result:
            return "未执行修复"
        
        fixed = fix_result.get('fixed_count', 0)
        skipped = fix_result.get('skipped_count', 0)
        
        return f"生成了 {fixed} 个修复方案，跳过了 {skipped} 个问题"
    
    def _format_test_summary(self, test_result: Optional[Dict]) -> str:
        """格式化测试摘要"""
        if not test_result:
            return "未生成测试"
        
        total_tests = test_result.get('total_tests', 0)
        framework = test_result.get('framework', 'pytest')
        
        return f"生成了 {total_tests} 个测试用例，使用框架: {framework}"
    
    def _format_verify_summary(self, verify_result: Optional[Dict]) -> str:
        """格式化验证摘要"""
        if not verify_result:
            return "未执行验证"
        
        passed = verify_result.get('passed', 0)
        failed = verify_result.get('failed', 0)
        total = verify_result.get('total_tests', 0)
        
        return f"执行了 {total} 个测试，通过 {passed}，失败 {failed}"
    
    def export_markdown(self, report: SummaryReport, filepath: str):
        """
        导出 Markdown 格式报告
        
        Args:
            report: 报告对象
            filepath: 导出路径
        """
        content = self._render_markdown(report)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Markdown report exported to {filepath}")
    
    def export_html(self, report: SummaryReport, filepath: str):
        """
        导出 HTML 格式报告
        
        Args:
            report: 报告对象
            filepath: 导出路径
        """
        content = self._render_html(report)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"HTML report exported to {filepath}")
    
    def export_json(self, report: SummaryReport, filepath: str):
        """
        导出 JSON 格式报告
        
        Args:
            report: 报告对象
            filepath: 导出路径
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"JSON report exported to {filepath}")
    
    def _render_markdown(self, report: SummaryReport) -> str:
        """渲染 Markdown 格式报告"""
        template = """# {{ project_name }} - 代码质量报告

## 项目信息
- **项目名称**: {{ project_name }}
- **项目路径**: {{ project_path }}
- **生成时间**: {{ generated_at }}

## 质量指标总览

| 指标 | 数值 |
|------|------|
| 代码文件数 | {{ metrics.total_files }} |
| 发现问题总数 | {{ metrics.total_issues }} |
| 严重问题 | {{ metrics.critical_issues }} |
| 高优先级问题 | {{ metrics.high_issues }} |
| 中等问题 | {{ metrics.medium_issues }} |
| 低优先级问题 | {{ metrics.low_issues }} |
| 已修复问题 | {{ metrics.fixed_issues }} |
| 测试用例总数 | {{ metrics.total_tests }} |
| 通过测试 | {{ metrics.passed_tests }} |
| 失败测试 | {{ metrics.failed_tests }} |
| 代码覆盖率 | {{ metrics.coverage_percent }}% |

## 执行摘要

### 扫描阶段
{{ scan_summary }}

### 修复阶段
{{ fix_summary }}

### 测试阶段
{{ test_summary }}

### 验证阶段
{{ verify_summary }}

## Token 消耗统计

| 类型 | 数量 |
|------|------|
| 输入 Token | {{ token_usage.total_input_tokens }} |
| 输出 Token | {{ token_usage.total_output_tokens }} |
| 总 Token | {{ token_usage.total_tokens }} |
| 请求次数 | {{ token_usage.request_count }} |
| 预估费用 | ${{ token_usage.estimated_cost_usd }} |

## 问题分布

### 按类别
{% for category, count in issues_by_category.items() %}
- {{ category }}: {{ count }}
{% endfor %}

### 按文件
{% for file, count in issues_by_file.items() %}
- {{ file }}: {{ count }}
{% endfor %}

---
*此报告由 MiMo Code Quality Assurance Tool 自动生成*
"""
        t = Template(template)
        return t.render(
            project_name=report.project_name,
            project_path=report.project_path,
            generated_at=report.generated_at,
            metrics=report.metrics,
            scan_summary=report.scan_summary,
            fix_summary=report.fix_summary,
            test_summary=report.test_summary,
            verify_summary=report.verify_summary,
            token_usage=report.token_usage,
            issues_by_category=report.issues_by_category.items(),
            issues_by_file=report.issues_by_file.items()
        )
    
    def _render_html(self, report: SummaryReport) -> str:
        """渲染 HTML 格式报告"""
        template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ project_name }} - 代码质量报告</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            border-radius: 10px;
            margin-bottom: 30px;
        }
        .header h1 { margin: 0; }
        .header p { margin: 10px 0 0 0; opacity: 0.9; }
        .card {
            background: white;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .metric {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .metric-value {
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }
        .metric-label {
            color: #666;
            font-size: 0.9em;
        }
        .status {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
        }
        .status-success { background: #d4edda; color: #155724; }
        .status-warning { background: #fff3cd; color: #856404; }
        .status-danger { background: #f8d7da; color: #721c24; }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th { background: #f8f9fa; }
        .footer {
            text-align: center;
            color: #666;
            margin-top: 30px;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ project_name }}</h1>
        <p>代码质量报告</p>
        <p>生成时间: {{ generated_at }}</p>
    </div>
    
    <div class="card">
        <h2>质量指标总览</h2>
        <div class="metrics-grid">
            <div class="metric">
                <div class="metric-value">{{ metrics.total_files }}</div>
                <div class="metric-label">代码文件</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ metrics.total_issues }}</div>
                <div class="metric-label">发现问题</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ metrics.fixed_issues }}</div>
                <div class="metric-label">已修复</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ metrics.total_tests }}</div>
                <div class="metric-label">测试用例</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ metrics.passed_tests }}</div>
                <div class="metric-label">通过测试</div>
            </div>
            <div class="metric">
                <div class="metric-value">{{ metrics.coverage_percent }}%</div>
                <div class="metric-label">代码覆盖</div>
            </div>
        </div>
    </div>
    
    <div class="card">
        <h2>执行摘要</h2>
        <p><strong>扫描:</strong> {{ scan_summary }}</p>
        <p><strong>修复:</strong> {{ fix_summary }}</p>
        <p><strong>测试:</strong> {{ test_summary }}</p>
        <p><strong>验证:</strong> {{ verify_summary }}</p>
    </div>
    
    <div class="card">
        <h2>问题严重性分布</h2>
        <table>
            <tr><th>严重级别</th><th>数量</th></tr>
            <tr><td>严重 (Critical)</td><td>{{ metrics.critical_issues }}</td></tr>
            <tr><td>高 (High)</td><td>{{ metrics.high_issues }}</td></tr>
            <tr><td>中 (Medium)</td><td>{{ metrics.medium_issues }}</td></tr>
            <tr><td>低 (Low)</td><td>{{ metrics.low_issues }}</td></tr>
        </table>
    </div>
    
    <div class="card">
        <h2>Token 消耗统计</h2>
        <table>
            <tr><th>类型</th><th>数量</th></tr>
            <tr><td>输入 Token</td><td>{{ token_usage.total_input_tokens }}</td></tr>
            <tr><td>输出 Token</td><td>{{ token_usage.total_output_tokens }}</td></tr>
            <tr><td>总 Token</td><td>{{ token_usage.total_tokens }}</td></tr>
            <tr><td>请求次数</td><td>{{ token_usage.request_count }}</td></tr>
            <tr><td>预估费用</td><td>${{ token_usage.estimated_cost_usd }}</td></tr>
        </table>
    </div>
    
    <div class="footer">
        <p>此报告由 MiMo Code Quality Assurance Tool 自动生成</p>
    </div>
</body>
</html>
"""
        t = Template(template)
        return t.render(
            project_name=report.project_name,
            generated_at=report.generated_at,
            metrics=report.metrics,
            scan_summary=report.scan_summary,
            fix_summary=report.fix_summary,
            test_summary=report.test_summary,
            verify_summary=report.verify_summary,
            token_usage=report.token_usage
        )