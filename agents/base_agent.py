# -*- coding: utf-8 -*-
"""
基础 Agent 类 - 所有 Agent 的基类

提供基础功能:
1. 消息传递机制
2. Agent 状态管理
3. 日志记录
4. 错误处理

使用示例:
    from agents.base_agent import BaseAgent, AgentMessage
    
    class MyAgent(BaseAgent):
        def execute(self, message: AgentMessage) -> AgentResult:
            return AgentResult(success=True, data={"result": "done"})
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from mimo_api import get_mimo_api, MiMoAPI
from config import get_config_manager
from logger import get_logger
from cache import get_cache_manager

logger = get_logger(__name__)


class AgentStatus(Enum):
    """Agent 状态"""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    WAITING = "waiting"


class MessageType(Enum):
    """消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    PROGRESS = "progress"
    APPROVAL = "approval"
    REJECTION = "rejection"


@dataclass
class AgentMessage:
    """Agent 消息"""
    type: MessageType
    sender: str
    receiver: str
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type.value,
            'sender': self.sender,
            'receiver': self.receiver,
            'content': self.content,
            'metadata': self.metadata,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        return cls(
            type=MessageType(data['type']),
            sender=data['sender'],
            receiver=data['receiver'],
            content=data['content'],
            metadata=data.get('metadata', {}),
            timestamp=data.get('timestamp', datetime.now().isoformat())
        )


@dataclass
class AgentResult:
    """Agent 执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'data': self.data,
            'error': self.error,
            'metadata': self.metadata,
            'execution_time': self.execution_time
        }


@dataclass
class AgentConfig:
    """Agent 配置"""
    name: str
    description: str
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    enable_streaming: bool = False
    cache_enabled: bool = True


class BaseAgent(ABC):
    """
    基础 Agent 类
    
    提供 Agent 的基础功能，子类需要实现 execute 方法。
    
    使用示例:
        class MyAgent(BaseAgent):
            def __init__(self):
                super().__init__(
                    AgentConfig(
                        name="MyAgent",
                        description="My custom agent"
                    )
                )
            
            def execute(self, message: AgentMessage) -> AgentResult:
                return AgentResult(success=True, data={"result": "done"})
    """
    
    def __init__(self, config: AgentConfig):
        """
        初始化 Agent
        
        Args:
            config: Agent 配置
        """
        self.config = config
        self.status = AgentStatus.IDLE
        self.api = get_mimo_api()
        self.cache = get_cache_manager()
        self.message_history: List[AgentMessage] = []
        self._callbacks: Dict[str, List[callable]] = {
            'progress': [],
            'complete': [],
            'error': []
        }
    
    @property
    def name(self) -> str:
        """获取 Agent 名称"""
        return self.config.name
    
    @property
    def description(self) -> str:
        """获取 Agent 描述"""
        return self.config.description
    
    def set_status(self, status: AgentStatus):
        """设置 Agent 状态"""
        self.status = status
        logger.debug(f"{self.name} status changed to {status.value}")
    
    def send_message(self, receiver: str, content: Any, 
                    message_type: MessageType = MessageType.REQUEST,
                    metadata: Optional[Dict[str, Any]] = None) -> AgentMessage:
        """
        发送消息给其他 Agent
        
        Args:
            receiver: 接收者名称
            content: 消息内容
            message_type: 消息类型
            metadata: 元数据
        
        Returns:
            发送的消息对象
        """
        message = AgentMessage(
            type=message_type,
            sender=self.name,
            receiver=receiver,
            content=content,
            metadata=metadata or {}
        )
        self.message_history.append(message)
        logger.debug(f"Message sent from {self.name} to {receiver}")
        return message
    
    def receive_message(self, message: AgentMessage):
        """
        接收来自其他 Agent 的消息
        
        Args:
            message: 消息对象
        """
        self.message_history.append(message)
        logger.debug(f"Message received from {message.sender}")
    
    def register_callback(self, event: str, callback: callable):
        """
        注册回调函数
        
        Args:
            event: 事件名称 (progress, complete, error)
            callback: 回调函数
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _trigger_callback(self, event: str, *args, **kwargs):
        """触发回调函数"""
        if event in self._callbacks:
            for callback in self._callbacks[event]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"Callback error in {event}: {e}")
    
    def _call_api(self, messages: List[Dict[str, str]], 
                  stream: bool = False,
                  on_chunk: Optional[callable] = None) -> str:
        """
        调用 MiMo API
        
        Args:
            messages: 消息列表
            stream: 是否流式输出
            on_chunk: 流式输出回调
        
        Returns:
            API 响应内容
        """
        try:
            if stream:
                chunks = []
                for chunk in self.api.chat.completions.create_streaming(
                    messages=messages,
                    model=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    on_chunk=on_chunk
                ):
                    chunks.append(chunk)
                return ''.join(chunks)
            else:
                response = self.api.chat.completions.create(
                    messages=messages,
                    model=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens
                )
                return response.content
        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise
    
    def _save_to_cache(self, key: str, data: Any):
        """保存数据到缓存"""
        if self.config.cache_enabled:
            self.cache.set(self.name, key, data)
    
    def _load_from_cache(self, key: str, max_age: int = 3600) -> Optional[Any]:
        """从缓存加载数据"""
        if self.config.cache_enabled:
            return self.cache.get(self.name, key, max_age)
        return None
    
    def execute(self, message: AgentMessage) -> AgentResult:
        """
        执行 Agent 逻辑（需要子类实现）
        
        Args:
            message: 输入消息
        
        Returns:
            执行结果
        """
        self.set_status(AgentStatus.RUNNING)
        start_time = time.time()
        
        try:
            result = self._execute_impl(message)
            execution_time = time.time() - start_time
            
            self.set_status(AgentStatus.SUCCESS)
            self._trigger_callback('complete', result)
            
            return AgentResult(
                success=True,
                data=result,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"{self.name} execution failed: {str(e)}"
            logger.error(error_msg)
            
            self.set_status(AgentStatus.FAILED)
            self._trigger_callback('error', e)
            
            return AgentResult(
                success=False,
                error=error_msg,
                execution_time=execution_time
            )
    
    @abstractmethod
    def _execute_impl(self, message: AgentMessage) -> Any:
        """
        实际执行逻辑（由子类实现）
        
        Args:
            message: 输入消息
        
        Returns:
            执行结果
        """
        pass
    
    def get_history(self, limit: int = 50) -> List[AgentMessage]:
        """获取消息历史"""
        return self.message_history[-limit:]
    
    def clear_history(self):
        """清空消息历史"""
        self.message_history.clear()


class AgentPipeline:
    """
    Agent 管道 - 串联多个 Agent 执行
    
    使用示例:
        pipeline = AgentPipeline()
        pipeline.add_agent(scan_agent)
        pipeline.add_agent(fix_agent)
        pipeline.add_agent(test_agent)
        pipeline.add_agent(verify_agent)
        
        result = pipeline.run(initial_message)
    """
    
    def __init__(self):
        """初始化 Agent 管道"""
        self.agents: List[BaseAgent] = []
        self.results: List[AgentResult] = []
    
    def add_agent(self, agent: BaseAgent):
        """添加 Agent 到管道"""
        self.agents.append(agent)
        logger.info(f"Added agent to pipeline: {agent.name}")
    
    def run(self, initial_message: AgentMessage) -> AgentResult:
        """
        执行管道
        
        Args:
            initial_message: 初始消息
        
        Returns:
            最终执行结果
        """
        current_message = initial_message
        self.results.clear()
        
        for agent in self.agents:
            logger.info(f"Executing agent: {agent.name}")
            
            result = agent.execute(current_message)
            self.results.append(result)
            
            if not result.success:
                logger.error(f"Pipeline failed at {agent.name}")
                return result
            
            # 将结果包装成下一阶段的输入消息
            current_message = AgentMessage(
                type=MessageType.REQUEST,
                sender=agent.name,
                receiver="next",
                content=result.data,
                metadata=result.metadata
            )
        
        logger.info("Pipeline completed successfully")
        return self.results[-1] if self.results else AgentResult(success=False, error="No results")
    
    def get_intermediate_results(self) -> List[AgentResult]:
        """获取中间结果"""
        return self.results.copy()


class AgentPool:
    """
    Agent 池 - 并行运行多个 Agent
    
    使用示例:
        pool = AgentPool()
        pool.add_agent(scan_agent_1)
        pool.add_agent(scan_agent_2)
        
        results = pool.run_all(initial_messages)
    """
    
    def __init__(self, max_workers: int = 4):
        """
        初始化 Agent 池
        
        Args:
            max_workers: 最大并行数
        """
        self.agents: List[BaseAgent] = []
        self.max_workers = max_workers
    
    def add_agent(self, agent: BaseAgent):
        """添加 Agent 到池"""
        self.agents.append(agent)
    
    def run_all(self, messages: List[AgentMessage]) -> List[AgentResult]:
        """
        并行执行所有 Agent
        
        Args:
            messages: 输入消息列表
        
        Returns:
            执行结果列表
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(agent.execute, msg): agent 
                for agent, msg in zip(self.agents, messages)
            }
            
            for future in as_completed(futures):
                agent = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append(AgentResult(
                        success=False,
                        error=f"{agent.name} failed: {str(e)}"
                    ))
        
        return results