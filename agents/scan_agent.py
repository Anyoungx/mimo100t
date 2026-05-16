# -*- coding: utf-8 -*-
"""
ScanAgent - 代码扫描 Agent

功能:
1. 调用 MiMo 分析代码文件
2. 识别技术债、规范问题、安全隐患
3. 输出结构化问题清单

使用示例:
    from agents import ScanAgent
    
    scan_agent = ScanAgent()
    result = scan_agent.execute(
        AgentMessage(
            type=MessageType.REQUEST,
            sender="user",
            receiver="ScanAgent",
            content={"project_path": "/path/to/project"}
        )
    )
    print(result.data)  # 结构化问题清单
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents.base_agent import (
    AgentConfig, AgentMessage, AgentResult, AgentStatus, BaseAgent, MessageType
)
from project_scanner import ProjectScanner
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class CodeIssue:
    """代码问题"""
    severity: str  # "critical", "high", "medium", "low"
    category: str  # "tech_debt", "style", "security", "performance", "bug"
    file: str
    description: str
    line: Optional[int] = None
    suggestion: str = ""
    code_snippet: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'severity': self.severity,
            'category': self.category,
            'file': self.file,
            'line': self.line,
            'description': self.description,
            'suggestion': self.suggestion,
            'code_snippet': self.code_snippet
        }


@dataclass
class ScanReport:
    """扫描报告"""
    project_path: str
    total_files: int
    total_issues: int
    issues_by_severity: Dict[str, int] = field(default_factory=dict)
    issues_by_category: Dict[str, int] = field(default_factory=dict)
    issues: List[CodeIssue] = field(default_factory=list)
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'project_path': self.project_path,
            'total_files': self.total_files,
            'total_issues': self.total_issues,
            'issues_by_severity': self.issues_by_severity,
            'issues_by_category': self.issues_by_category,
            'issues': [i.to_dict() for i in self.issues],
            'summary': self.summary
        }


SCAN_PROMPT_TEMPLATE = """你是一个专业的代码质量分析专家。请分析以下代码文件，识别其中的问题。

## 项目信息
- 项目路径: {project_path}
- 编程语言: {language}
- 框架: {framework}

## 分析要求
请从以下几个维度分析代码:

1. **技术债 (tech_debt)**: 过时代码、未使用的导入/变量、重复代码、硬编码常量
2. **代码规范 (style)**: 命名不规范、缺少文档字符串、代码风格不一致、行过长
3. **安全隐患 (security)**: SQL注入风险、XSS风险、硬编码密钥、敏感信息泄露
4. **性能问题 (performance)**: 低效算法、不必要的循环、深层嵌套
5. **Bug 风险 (bug)**: 空指针风险、异常未捕获、边界条件未处理

## 代码文件列表
{files_list}

## 代码内容
{code_content}

## 输出格式
请以JSON格式输出分析结果，格式如下:
```json
{{
    "issues": [
        {{
            "severity": "high",  // critical/high/medium/low
            "category": "tech_debt",  // tech_debt/style/security/performance/bug
            "file": "path/to/file.py",
            "line": 42,
            "description": "问题描述",
            "suggestion": "修复建议",
            "code_snippet": "相关代码片段"
        }}
    ],
    "summary": "总体评估摘要"
}}
```

只输出JSON，不要有其他内容。"""


class ScanAgent(BaseAgent):
    """
    代码扫描 Agent
    
    使用 MiMo API 分析代码文件，识别技术债、规范问题、安全隐患等。
    
    使用示例:
        scan_agent = ScanAgent()
        result = scan_agent.execute(message)
    """
    
    def __init__(self, max_file_size: int = 50000):
        """
        初始化 ScanAgent
        
        Args:
            max_file_size: 单个文件最大分析大小（字符数）
        """
        super().__init__(
            AgentConfig(
                name="ScanAgent",
                description="代码扫描 Agent - 分析代码文件，识别技术债、规范问题、安全隐患"
            )
        )
        self.scanner = ProjectScanner()
        self.max_file_size = max_file_size
    
    def _execute_impl(self, message: AgentMessage) -> ScanReport:
        """执行代码扫描"""
        content = message.content
        
        # 解析输入
        project_path = content.get('project_path')
        if not project_path:
            raise ValueError("project_path is required")
        
        # 扫描项目
        logger.info(f"Scanning project: {project_path}")
        project_info = self.scanner.scan(project_path, include_content=True)
        
        # 按文件分组代码
        code_groups = self._group_files_by_size(project_info.files)
        
        # 并发分析文件组
        all_issues = []
        
        for group_name, files in code_groups.items():
            issues = self._analyze_file_group(files, project_info)
            all_issues.extend(issues)
        
        # 生成报告
        report = self._generate_report(project_path, project_info, all_issues)
        
        return report
    
    def _group_files_by_size(self, files: List) -> Dict[str, List]:
        """按大小分组文件"""
        groups = {
            'small': [],   # < 5KB
            'medium': [],  # 5KB - 20KB
            'large': []    # > 20KB
        }
        
        for file in files:
            size = file.size
            if size < 5000:
                groups['small'].append(file)
            elif size < 20000:
                groups['medium'].append(file)
            else:
                groups['large'].append(file)
        
        return groups
    
    def _analyze_file_group(self, files: List, project_info) -> List[CodeIssue]:
        """分析文件组"""
        issues = []
        
        # 构建文件列表
        files_list = "\n".join([
            f"{i+1}. {f.relative_path} ({f.lines} lines, {f.size} bytes)"
            for i, f in enumerate(files)
        ])
        
        # 截取代码内容
        code_content = self._prepare_code_content(files)
        
        # 调用 API 分析
        prompt = SCAN_PROMPT_TEMPLATE.format(
            project_path=project_info.config.path,
            language=project_info.config.language,
            framework=project_info.config.framework or "Unknown",
            files_list=files_list,
            code_content=code_content
        )
        
        messages = [
            {"role": "system", "content": "你是一个专业的代码质量分析专家。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_api(messages)
            
            # 解析 JSON 响应
            issues = self._parse_issues_from_response(response)
            logger.info(f"Found {len(issues)} issues in file group")
            
        except Exception as e:
            logger.error(f"Failed to analyze file group: {e}")
        
        return issues
    
    def _prepare_code_content(self, files: List) -> str:
        """准备代码内容"""
        content_parts = []
        total_length = 0
        
        for file in files[:10]:  # 限制文件数量
            if total_length >= self.max_file_size:
                break
            
            file_content = file.content[:5000]  # 限制单个文件长度
            content_parts.append(f"\n{'='*60}\n")
            content_parts.append(f"文件: {file.relative_path}\n")
            content_parts.append(f"{'='*60}\n")
            content_parts.append(file_content)
            content_parts.append("\n")
            
            total_length += len(file_content)
        
        return ''.join(content_parts)
    
    def _parse_issues_from_response(self, response: str) -> List[CodeIssue]:
        """从 API 响应中解析问题列表"""
        issues = []
        
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{.*"issues".*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
            else:
                # 尝试解析整个响应
                data = json.loads(response)
            
            for issue_data in data.get('issues', []):
                issue = CodeIssue(
                    severity=issue_data.get('severity', 'medium'),
                    category=issue_data.get('category', 'style'),
                    file=issue_data.get('file', ''),
                    line=issue_data.get('line'),
                    description=issue_data.get('description', ''),
                    suggestion=issue_data.get('suggestion', ''),
                    code_snippet=issue_data.get('code_snippet', '')
                )
                issues.append(issue)
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            # 尝试文本解析作为后备
            issues = self._parse_issues_from_text(response)
        
        return issues
    
    def _parse_issues_from_text(self, text: str) -> List[CodeIssue]:
        """从文本中解析问题（后备方案）"""
        issues = []
        
        # 简单的文本解析
        lines = text.split('\n')
        current_issue = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检测问题开始
            if line.startswith(('1.', '2.', '3.', '4.', '5.', 'Issue')):
                if current_issue:
                    issues.append(current_issue)
                current_issue = {
                    'severity': 'medium',
                    'category': 'style',
                    'file': '',
                    'description': line
                }
            elif current_issue:
                if 'file:' in line.lower():
                    current_issue['file'] = line.split(':', 1)[-1].strip()
                elif 'severity:' in line.lower():
                    current_issue['severity'] = line.split(':', 1)[-1].strip().lower()
        
        if current_issue:
            issues.append(current_issue)
        
        return [CodeIssue(**{k: v for k, v in i.items()}) for i in issues]
    
    def _generate_report(self, project_path: str, project_info, issues: List[CodeIssue]) -> ScanReport:
        """生成扫描报告"""
        # 统计问题
        issues_by_severity = {}
        issues_by_category = {}
        
        for issue in issues:
            severity = issue.severity.lower()
            category = issue.category.lower()
            
            issues_by_severity[severity] = issues_by_severity.get(severity, 0) + 1
            issues_by_category[category] = issues_by_category.get(category, 0) + 1
        
        # 生成摘要
        summary = self._generate_summary(project_info, issues, issues_by_severity, issues_by_category)
        
        report = ScanReport(
            project_path=project_path,
            total_files=len(project_info.files),
            total_issues=len(issues),
            issues_by_severity=issues_by_severity,
            issues_by_category=issues_by_category,
            issues=issues,
            summary=summary
        )
        
        logger.info(f"Scan completed: {len(issues)} issues found in {len(project_info.files)} files")
        return report
    
    def _generate_summary(self, project_info, issues: List[CodeIssue],
                         by_severity: Dict, by_category: Dict) -> str:
        """生成报告摘要"""
        critical_count = by_severity.get('critical', 0)
        high_count = by_severity.get('high', 0)
        
        summary_parts = [
            f"扫描完成！共分析了 {len(project_info.files)} 个代码文件，发现 {len(issues)} 个问题。",
        ]
        
        if critical_count > 0:
            summary_parts.append(f"\n⚠️  发现 {critical_count} 个严重问题，需要立即修复！")
        elif high_count > 0:
            summary_parts.append(f"\n⚡ 发现 {high_count} 个高优先级问题，建议尽快处理。")
        else:
            summary_parts.append(f"\n✅ 代码质量良好，问题较少。")
        
        # 按类别统计
        if by_category:
            category_strs = [f"{cat}: {count}" for cat, count in sorted(by_category.items())]
            summary_parts.append(f"\n问题分布: {', '.join(category_strs)}")
        
        return ''.join(summary_parts)
    
    def get_issues_by_file(self, report: ScanReport) -> Dict[str, List[CodeIssue]]:
        """按文件分组问题"""
        file_issues = {}
        
        for issue in report.issues:
            if issue.file not in file_issues:
                file_issues[issue.file] = []
            file_issues[issue.file].append(issue)
        
        return file_issues
    
    def get_issues_by_severity(self, report: ScanReport, severity: str) -> List[CodeIssue]:
        """按严重级别筛选问题"""
        return [i for i in report.issues if i.severity.lower() == severity.lower()]
    
    def export_report(self, report: ScanReport, filepath: str):
        """导出报告到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Report exported to {filepath}")