# -*- coding: utf-8 -*-
"""
多 Agent 协作模块 - 包含四个核心 Agent 实现

Agent 列表:
- BaseAgent: 基础 Agent 类
- ScanAgent: 代码扫描 Agent
- FixAgent: 代码修复 Agent
- TestAgent: 测试生成 Agent
- VerifyAgent: 测试验证 Agent

使用示例:
    from agents import ScanAgent, FixAgent, TestAgent, VerifyAgent
    
    scan_agent = ScanAgent()
    scan_result = scan_agent.scan("/path/to/project")
    
    fix_agent = FixAgent()
    fix_result = fix_agent.fix(scan_result)
    
    test_agent = TestAgent()
    test_result = test_agent.generate(fix_result)
    
    verify_agent = VerifyAgent()
    verify_result = verify_agent.verify(test_result)
"""

from agents.base_agent import BaseAgent, AgentMessage, AgentResult
from agents.scan_agent import ScanAgent
from agents.fix_agent import FixAgent
from agents.test_agent import TestAgent
from agents.verify_agent import VerifyAgent

__all__ = [
    'BaseAgent',
    'AgentMessage',
    'AgentResult',
    'ScanAgent',
    'FixAgent',
    'TestAgent',
    'VerifyAgent'
]