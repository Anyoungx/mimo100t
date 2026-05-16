# -*- coding: utf-8 -*-
"""
FixAgent - 代码修复 Agent

功能:
1. 接收问题清单，生成重构方案
2. 输出可直接替换的修复代码
3. 支持用户审批和手动修改

使用示例:
    from agents import FixAgent
    
    fix_agent = FixAgent()
    result = fix_agent.execute(message)  # message 来自 ScanAgent
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
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class FixSuggestion:
    """修复建议"""
    issue_id: int
    file: str
    original_code: str
    fixed_code: str
    description: str
    justification: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'issue_id': self.issue_id,
            'file': self.file,
            'original_code': self.original_code,
            'fixed_code': self.fixed_code,
            'description': self.description,
            'justification': self.justification
        }


@dataclass
class FixReport:
    """修复报告"""
    total_issues: int
    fixed_count: int
    skipped_count: int
    suggestions: List[FixSuggestion] = field(default_factory=list)
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_issues': self.total_issues,
            'fixed_count': self.fixed_count,
            'skipped_count': self.skipped_count,
            'suggestions': [s.to_dict() for s in self.suggestions],
            'summary': self.summary
        }


FIX_PROMPT_TEMPLATE = """你是一个专业的代码重构专家。请根据发现的问题，生成修复代码。

## 项目信息
- 项目路径: {project_path}
- 编程语言: {language}

## 需要修复的问题列表
{issues_list}

## 原始代码
{code_content}

## 修复要求
1. 只修改有问题的部分，保持其他代码不变
2. 确保修复后的代码语法正确
3. 遵循语言最佳实践和代码规范
4. 保持代码的可读性和可维护性

## 输出格式
请以JSON格式输出修复方案，格式如下:
```json
{{
    "fixes": [
        {{
            "issue_id": 1,
            "file": "path/to/file.py",
            "original_code": "原始代码片段",
            "fixed_code": "修复后的代码片段",
            "description": "修复说明",
            "justification": "修复理由"
        }}
    ],
    "summary": "修复总结"
}}
```

只输出JSON，不要有其他内容。"""


class FixAgent(BaseAgent):
    """
    代码修复 Agent
    
    根据扫描结果生成修复方案和代码。
    
    使用示例:
        fix_agent = FixAgent()
        result = fix_agent.execute(message)
    """
    
    def __init__(self):
        """初始化 FixAgent"""
        super().__init__(
            AgentConfig(
                name="FixAgent",
                description="代码修复 Agent - 根据问题清单生成重构方案和修复代码"
            )
        )
        self.scanner = ProjectScanner()
    
    def _execute_impl(self, message: AgentMessage) -> FixReport:
        """执行代码修复"""
        content = message.content
        
        # 解析输入
        project_path = content.get('project_path')
        scan_result = content.get('scan_result')
        
        if not project_path:
            raise ValueError("project_path is required")
        if not scan_result:
            raise ValueError("scan_result is required")
        
        logger.info(f"Generating fixes for {len(scan_result.get('issues', []))} issues")
        
        # 读取原始代码
        files_content = self._read_files_content(project_path, scan_result)
        
        # 按文件分组问题
        file_issues = self._group_issues_by_file(scan_result.get('issues', []))
        
        # 生成修复方案
        all_fixes = []
        
        for file_path, issues in file_issues.items():
            fixes = self._generate_fixes_for_file(
                project_path,
                file_path,
                issues,
                files_content.get(file_path, '')
            )
            all_fixes.extend(fixes)
        
        # 生成报告
        report = FixReport(
            total_issues=len(scan_result.get('issues', [])),
            fixed_count=len(all_fixes),
            skipped_count=len(scan_result.get('issues', [])) - len(all_fixes),
            suggestions=all_fixes,
            summary=self._generate_summary(all_fixes)
        )
        
        logger.info(f"Generated {len(all_fixes)} fix suggestions")
        return report
    
    def _read_files_content(self, project_path: str, scan_result: Dict) -> Dict[str, str]:
        """读取相关文件的内容"""
        files_content = {}
        project_info = self.scanner.scan(project_path, include_content=True)
        
        file_map = {f.relative_path: f for f in project_info.files}
        
        for issue in scan_result.get('issues', []):
            file_path = issue.get('file', '')
            if file_path and file_path not in files_content:
                if file_path in file_map:
                    files_content[file_path] = file_map[file_path].content
                else:
                    # 尝试读取文件
                    try:
                        full_path = Path(project_path) / file_path
                        with open(full_path, 'r', encoding='utf-8') as f:
                            files_content[file_path] = f.read()
                    except Exception as e:
                        logger.warning(f"Failed to read file {file_path}: {e}")
        
        return files_content
    
    def _group_issues_by_file(self, issues: List[Dict]) -> Dict[str, List[Dict]]:
        """按文件分组问题"""
        file_issues = {}
        
        for issue in issues:
            file_path = issue.get('file', '')
            if not file_path:
                continue
            
            if file_path not in file_issues:
                file_issues[file_path] = []
            file_issues[file_path].append(issue)
        
        return file_issues
    
    def _generate_fixes_for_file(self, project_path: str, file_path: str, 
                                 issues: List[Dict], code_content: str) -> List[FixSuggestion]:
        """为单个文件生成修复方案"""
        if not code_content:
            return []
        
        # 构建问题列表
        issues_list = []
        for i, issue in enumerate(issues):
            issues_list.append(f"""
问题 {i+1}:
- 严重级别: {issue.get('severity', 'medium')}
- 类别: {issue.get('category', 'style')}
- 描述: {issue.get('description', '')}
- 建议: {issue.get('suggestion', '')}
- 代码片段: {issue.get('code_snippet', '')}
            """)
        
        issues_text = '\n'.join(issues_list)
        
        # 调用 API
        prompt = FIX_PROMPT_TEMPLATE.format(
            project_path=project_path,
            language=self._detect_language(file_path),
            issues_list=issues_text,
            code_content=code_content
        )
        
        messages = [
            {"role": "system", "content": "你是一个专业的代码重构专家。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_api(messages)
            fixes = self._parse_fixes_from_response(response)
            return fixes
        except Exception as e:
            logger.error(f"Failed to generate fixes for {file_path}: {e}")
            return []
    
    def _detect_language(self, file_path: str) -> str:
        """检测文件语言"""
        ext = Path(file_path).suffix.lower()
        lang_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.java': 'Java',
            '.go': 'Go',
            '.rs': 'Rust',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.cs': 'C#'
        }
        return lang_map.get(ext, 'Unknown')
    
    def _parse_fixes_from_response(self, response: str) -> List[FixSuggestion]:
        """从 API 响应中解析修复方案"""
        fixes = []
        
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{.*"fixes".*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
            else:
                data = json.loads(response)
            
            for fix_data in data.get('fixes', []):
                fix = FixSuggestion(
                    issue_id=fix_data.get('issue_id', 0),
                    file=fix_data.get('file', ''),
                    original_code=fix_data.get('original_code', ''),
                    fixed_code=fix_data.get('fixed_code', ''),
                    description=fix_data.get('description', ''),
                    justification=fix_data.get('justification', '')
                )
                fixes.append(fix)
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
        
        return fixes
    
    def _generate_summary(self, fixes: List[FixSuggestion]) -> str:
        """生成修复总结"""
        if not fixes:
            return "未生成任何修复方案"
        
        summary = f"共生成 {len(fixes)} 个修复方案:\n"
        
        by_file = {}
        for fix in fixes:
            if fix.file not in by_file:
                by_file[fix.file] = []
            by_file[fix.file].append(fix)
        
        for file_path, file_fixes in by_file.items():
            summary += f"\n📄 {file_path}: {len(file_fixes)} 处修复\n"
        
        return summary
    
    def apply_fixes(self, project_path: str, report: FixReport, 
                   approved_indices: Optional[List[int]] = None) -> Dict[str, str]:
        """
        应用修复方案
        
        Args:
            project_path: 项目路径
            report: 修复报告
            approved_indices: 批准应用的修复索引，None 表示全部应用
        
        Returns:
            已修改的文件字典
        """
        modified_files = {}
        
        for i, suggestion in enumerate(report.suggestions):
            if approved_indices is not None and i not in approved_indices:
                continue
            
            try:
                file_path = Path(project_path) / suggestion.file
                
                # 读取文件内容
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 替换代码
                if suggestion.original_code in content:
                    new_content = content.replace(
                        suggestion.original_code,
                        suggestion.fixed_code
                    )
                    
                    # 写入文件
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    
                    modified_files[suggestion.file] = suggestion.file
                    logger.info(f"Applied fix to {suggestion.file}")
                else:
                    logger.warning(f"Original code not found in {suggestion.file}")
                    
            except Exception as e:
                logger.error(f"Failed to apply fix to {suggestion.file}: {e}")
        
        return modified_files
    
    def export_fixes(self, report: FixReport, filepath: str):
        """导出修复方案到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Fix report exported to {filepath}")