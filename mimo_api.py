# -*- coding: utf-8 -*-
"""
MiMo API 封装模块 - 封装小米 MiMo API 的所有请求

功能:
1. 统一请求函数，支持流式输出
2. 错误处理（超时、密钥错误、额度不足）
3. Token 消耗统计
4. 请求重试机制

使用示例:
    api = MiMoAPI()
    response = api.chat.completions.create(
        messages=[{"role": "user", "content": "Hello"}]
    )
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional
from collections import defaultdict

import requests

from config import get_config_manager
from logger import get_logger

logger = get_logger(__name__)


class MiMoAPIError(Exception):
    """MiMo API 基础异常"""
    pass


class AuthenticationError(MiMoAPIError):
    """认证失败 - API Key 无效"""
    pass


class RateLimitError(MiMoAPIError):
    """请求频率限制"""
    pass


class QuotaExceededError(MiMoAPIError):
    """API 额度不足"""
    pass


class TimeoutError(MiMoAPIError):
    """请求超时"""
    pass


class InvalidRequestError(MiMoAPIError):
    """无效请求"""
    pass


@dataclass
class TokenUsage:
    """Token 使用统计"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    def add(self, input_tokens: int, output_tokens: int):
        """累加 Token 使用"""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens


@dataclass
class APIResponse:
    """API 响应"""
    content: str
    usage: TokenUsage
    model: str
    finish_reason: str
    raw_response: Dict[str, Any]


@dataclass
class TokenStats:
    """Token 统计报告"""
    total_input: int = 0
    total_output: int = 0
    total_tokens: int = 0
    request_count: int = 0
    cost_per_million_input: float = 0.5  # 默认价格
    cost_per_million_output: float = 1.5
    estimated_cost: float = 0.0
    
    def calculate_cost(self):
        """计算预估费用"""
        input_cost = (self.total_input / 1_000_000) * self.cost_per_million_input
        output_cost = (self.total_output / 1_000_000) * self.cost_per_million_output
        self.estimated_cost = input_cost + output_cost
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'total_input_tokens': self.total_input,
            'total_output_tokens': self.total_output,
            'total_tokens': self.total_tokens,
            'request_count': self.request_count,
            'estimated_cost_usd': round(self.estimated_cost, 4)
        }


class ChatCompletions:
    """
    Chat Completions API 客户端
    
    使用示例:
        api = MiMoAPI()
        response = api.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a code reviewer."},
                {"role": "user", "content": "Review this code..."}
            ],
            temperature=0.7
        )
    """
    
    def __init__(self, api: 'MiMoAPI'):
        self.api = api
    
    def create(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> APIResponse:
        """
        创建聊天补全请求
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出 Token 数
            stream: 是否启用流式输出
            **kwargs: 其他参数
        
        Returns:
            API 响应对象
        """
        return self.api._make_request(
            endpoint="/chat/completions",
            data={
                "messages": messages,
                "model": model or self.api.config.api.model_name,
                "temperature": temperature or self.api.config.api.temperature,
                "max_tokens": max_tokens or self.api.config.api.max_tokens,
                "stream": stream,
                **kwargs
            }
        )
    
    def create_streaming(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> Iterator[str]:
        """
        创建流式聊天补全请求
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大输出 Token 数
            on_chunk: 每个数据块的回调函数
        
        Yields:
            生成的文本片段
        """
        response = self.api._make_streaming_request(
            endpoint="/chat/completions",
            data={
                "messages": messages,
                "model": model or self.api.config.api.model_name,
                "temperature": temperature or self.api.config.api.temperature,
                "max_tokens": max_tokens or self.api.config.api.max_tokens,
                "stream": True
            }
        )
        
        full_content = ""
        for chunk in response:
            if on_chunk:
                on_chunk(chunk)
            full_content += chunk
            yield chunk


class MiMoAPI:
    """
    MiMo API 客户端
    
    使用示例:
        api = MiMoAPI()
        api.configure(api_key="your_key")
        
        # 非流式请求
        response = api.chat.completions.create(
            messages=[{"role": "user", "content": "Hello"}]
        )
        print(response.content)
        
        # 流式请求
        for chunk in api.chat.completions.create_streaming(
            messages=[{"role": "user", "content": "Hello"}]
        ):
            print(chunk, end="")
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化 MiMo API 客户端
        
        Args:
            api_key: API Key，如果不提供则从配置读取
            base_url: API 基础 URL
        """
        self.config = get_config_manager()
        self.config.load_config()
        
        # 配置覆盖
        if api_key:
            self.config.update_api_key(api_key)
        if base_url:
            self.config.config.api.base_url = base_url
        
        # Chat Completions API
        self.chat = ChatCompletions(self)
        
        # Token 统计
        self.token_stats = TokenStats()
        self._request_history: List[Dict[str, Any]] = []
    
    def configure(self, api_key: str = None, base_url: str = None,
                  temperature: float = None, max_tokens: int = None):
        """
        配置 API 参数
        
        Args:
            api_key: API Key
            base_url: 基础 URL
            temperature: 温度参数
            max_tokens: 最大 Token 数
        """
        if api_key:
            self.config.update_api_key(api_key)
        if base_url:
            self.config.config.api.base_url = base_url
        if temperature is not None or max_tokens is not None:
            self.config.update_model_params(temperature, max_tokens)
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.config.api.api_key}"
        }
    
    def _make_request(
        self,
        endpoint: str,
        data: Dict[str, Any],
        retry_count: int = 0
    ) -> APIResponse:
        """
        发送 API 请求
        
        Args:
            endpoint: API 端点
            data: 请求数据
            retry_count: 当前重试次数
        
        Returns:
            API 响应对象
        
        Raises:
            AuthenticationError: 认证失败
            RateLimitError: 请求频率限制
            QuotaExceededError: 额度不足
            TimeoutError: 请求超时
        """
        url = f"{self.config.config.api.base_url}{endpoint}"
        
        try:
            logger.debug(f"Making request to {endpoint}")
            
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=data,
                timeout=self.config.config.request.timeout
            )
            
            # 处理响应状态码
            if response.status_code == 401:
                raise AuthenticationError("Invalid API Key. Please check your .env file.")
            elif response.status_code == 403:
                raise AuthenticationError("Access forbidden. Check your API permissions.")
            elif response.status_code == 429:
                if retry_count < self.config.config.request.max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(f"Rate limited. Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    return self._make_request(endpoint, data, retry_count + 1)
                raise RateLimitError("API rate limit exceeded after retries.")
            elif response.status_code == 402:
                raise QuotaExceededError("API quota exceeded. Please check your plan limits.")
            elif response.status_code == 400:
                error_detail = response.json().get('error', {}).get('message', 'Bad request')
                raise InvalidRequestError(f"Invalid request: {error_detail}")
            
            response.raise_for_status()
            
            result = response.json()
            
            # 提取 Token 使用量
            usage = result.get('usage', {})
            input_tokens = usage.get('prompt_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0)
            
            # 更新统计
            self.token_stats.total_input += input_tokens
            self.token_stats.total_output += output_tokens
            self.token_stats.request_count += 1
            self.token_stats.calculate_cost()
            
            # 记录历史
            self._request_history.append({
                'timestamp': datetime.now().isoformat(),
                'endpoint': endpoint,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'model': result.get('model', '')
            })
            
            return APIResponse(
                content=result['choices'][0]['message']['content'],
                usage=TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens
                ),
                model=result.get('model', ''),
                finish_reason=result['choices'][0]['finish_reason'],
                raw_response=result
            )
            
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Request timeout after {self.config.config.request.timeout}s")
        except requests.exceptions.ConnectionError as e:
            raise MiMoAPIError(f"Connection error: {e}")
        except requests.exceptions.RequestException as e:
            raise MiMoAPIError(f"Request failed: {e}")
    
    def _make_streaming_request(
        self,
        endpoint: str,
        data: Dict[str, Any]
    ) -> Iterator[str]:
        """
        发送流式 API 请求
        
        Args:
            endpoint: API 端点
            data: 请求数据
        
        Yields:
            生成的文本片段
        """
        url = f"{self.config.config.api.base_url}{endpoint}"
        
        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=data,
                timeout=self.config.config.request.timeout,
                stream=True
            )
            
            if response.status_code == 401:
                raise AuthenticationError("Invalid API Key.")
            elif response.status_code == 429:
                raise RateLimitError("API rate limit exceeded.")
            elif response.status_code == 402:
                raise QuotaExceededError("API quota exceeded.")
            
            response.raise_for_status()
            
            # 处理 SSE 流
            for line in response.iter_lines():
                if not line:
                    continue
                
                line = line.decode('utf-8')
                
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str == '[DONE]':
                        break
                    
                    try:
                        chunk_data = json.loads(data_str)
                        content = chunk_data.get('choices', [{}])[0].get('delta', {}).get('content', '')
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
            
        except requests.exceptions.Timeout:
            raise TimeoutError("Request timeout during streaming")
        except Exception as e:
            raise MiMoAPIError(f"Streaming request failed: {e}")
    
    def get_token_stats(self) -> TokenStats:
        """获取 Token 统计"""
        return self.token_stats
    
    def get_request_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取请求历史"""
        return self._request_history[-limit:]
    
    def export_stats(self, filepath: str = "token_stats.json"):
        """
        导出 Token 统计到文件
        
        Args:
            filepath: 导出文件路径
        """
        stats = self.token_stats.to_dict()
        stats['history'] = self._request_history
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Token stats exported to {filepath}")


# 全局 API 实例
_mimo_api: Optional[MiMoAPI] = None


def get_mimo_api() -> MiMoAPI:
    """获取全局 MiMo API 实例"""
    global _mimo_api
    if _mimo_api is None:
        _mimo_api = MiMoAPI()
    return _mimo_api


def reset_mimo_api():
    """重置全局 MiMo API 实例"""
    global _mimo_api
    _mimo_api = None