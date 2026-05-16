# -*- coding: utf-8 -*-
"""
配置管理模块 - 管理 MiMo 代码质量保障工具的所有配置

支持从以下来源加载配置:
1. .env 文件 (环境变量)
2. config.yaml (用户自定义配置)
3. 默认值

配置项:
- API 配置 (API Key, Base URL, 模型参数)
- 请求配置 (超时, 重试次数)
- 缓存配置 (缓存目录, 是否启用)
- 日志配置 (日志等级, 日志文件)
- 项目配置 (代码规则, 测试框架, 重构目标)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml
from dotenv import load_dotenv

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class APIConfig:
    """API 配置"""
    api_key: str = ""
    base_url: str = "https://api.mimo.com/v1"
    model_name: str = "mimo-pro"
    temperature: float = 0.7
    max_tokens: int = 2048
    context_window: int = 128000


@dataclass
class RequestConfig:
    """请求配置"""
    timeout: int = 120
    max_retries: int = 3


@dataclass
class CacheConfig:
    """缓存配置"""
    cache_dir: str = ".mimo_cache"
    enable_cache: bool = True


@dataclass
class LogConfig:
    """日志配置"""
    log_level: str = "INFO"
    log_file: str = "mimo.log"


@dataclass
class CodeRule:
    """代码规则"""
    max_line_length: int = 120
    allowed_imports: List[str] = field(default_factory=list)
    forbidden_functions: List[str] = field(default_factory=lambda: ["eval", "exec"])
    require_type_hints: bool = False
    require_docstrings: bool = False


@dataclass
class ProjectConfig:
    """项目配置"""
    test_framework: str = "pytest"
    refactor_targets: List[str] = field(default_factory=lambda: [
        "dead_code", "duplicate_code", "naming_issues"
    ])
    exclude_patterns: List[str] = field(default_factory=lambda: [
        "__pycache__", "*.pyc", ".git", "node_modules", "venv", ".venv"
    ])
    code_rules: CodeRule = field(default_factory=CodeRule)


@dataclass
class Config:
    """完整配置"""
    api: APIConfig = field(default_factory=APIConfig)
    request: RequestConfig = field(default_factory=RequestConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    log: LogConfig = field(default_factory=LogConfig)
    project: ProjectConfig = field(default_factory=ProjectConfig)


class ConfigManager:
    """
    配置管理器 - 统一管理所有配置加载和保存
    
    使用示例:
        config_manager = ConfigManager()
        config = config_manager.load_config()
        api_key = config.api.api_key
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 自定义配置文件路径，默认查找项目根目录的 config.yaml
        """
        self.config_path = config_path or "config.yaml"
        self.config = Config()
    
    def load_config(self) -> Config:
        """
        加载配置
        
        按优先级加载:
        1. .env 文件中的环境变量
        2. config.yaml 中的用户配置
        3. 默认值
        
        Returns:
            配置对象
        """
        # 加载 .env 文件
        self._load_env_config()
        
        # 加载 config.yaml
        self._load_yaml_config()
        
        # 确保缓存目录存在
        self._ensure_cache_dir()
        
        logger.info("Configuration loaded successfully")
        return self.config
    
    def _load_env_config(self):
        """从 .env 文件加载环境变量配置"""
        # 查找 .env 文件
        env_path = Path(".env")
        if env_path.exists():
            load_dotenv(env_path)
            logger.debug("Loaded .env file")
        
        # API 配置
        self.config.api.api_key = os.getenv("MIMO_API_KEY", "")
        self.config.api.base_url = os.getenv("MIMO_BASE_URL", "https://api.mimo.com/v1")
        self.config.api.model_name = os.getenv("MODEL_NAME", "mimo-pro")
        
        # 模型参数
        try:
            self.config.api.temperature = float(os.getenv("TEMPERATURE", "0.7"))
        except ValueError:
            self.config.api.temperature = 0.7
        
        try:
            self.config.api.max_tokens = int(os.getenv("MAX_TOKENS", "2048"))
        except ValueError:
            self.config.api.max_tokens = 2048
        
        try:
            self.config.api.context_window = int(os.getenv("CONTEXT_WINDOW", "128000"))
        except ValueError:
            self.config.api.context_window = 128000
        
        # 请求配置
        try:
            self.config.request.timeout = int(os.getenv("REQUEST_TIMEOUT", "120"))
        except ValueError:
            self.config.request.timeout = 120
        
        try:
            self.config.request.max_retries = int(os.getenv("MAX_RETRIES", "3"))
        except ValueError:
            self.config.request.max_retries = 3
        
        # 缓存配置
        self.config.cache.cache_dir = os.getenv("CACHE_DIR", ".mimo_cache")
        self.config.cache.enable_cache = os.getenv("ENABLE_CACHE", "true").lower() == "true"
        
        # 日志配置
        self.config.log.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.config.log.log_file = os.getenv("LOG_FILE", "mimo.log")
    
    def _load_yaml_config(self):
        """从 YAML 文件加载用户配置"""
        config_path = Path(self.config_path)
        
        if not config_path.exists():
            logger.debug(f"Config file {self.config_path} not found, using defaults")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f) or {}
            
            # 测试框架配置
            if 'test_framework' in yaml_config:
                self.config.project.test_framework = yaml_config['test_framework']
            
            # 重构目标配置
            if 'refactor_targets' in yaml_config:
                self.config.project.refactor_targets = yaml_config['refactor_targets']
            
            # 排除模式配置
            if 'exclude_patterns' in yaml_config:
                self.config.project.exclude_patterns = yaml_config['exclude_patterns']
            
            # 代码规则配置
            if 'code_rules' in yaml_config:
                rules = yaml_config['code_rules']
                
                if 'max_line_length' in rules:
                    self.config.project.code_rules.max_line_length = rules['max_line_length']
                
                if 'allowed_imports' in rules:
                    self.config.project.code_rules.allowed_imports = rules['allowed_imports']
                
                if 'forbidden_functions' in rules:
                    self.config.project.code_rules.forbidden_functions = rules['forbidden_functions']
                
                if 'require_type_hints' in rules:
                    self.config.project.code_rules.require_type_hints = rules['require_type_hints']
                
                if 'require_docstrings' in rules:
                    self.config.project.code_rules.require_docstrings = rules['require_docstrings']
            
            logger.debug(f"Loaded config from {self.config_path}")
            
        except Exception as e:
            logger.warning(f"Failed to load config from {self.config_path}: {e}")
    
    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        cache_dir = Path(self.config.cache.cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
    
    def save_config(self, config_path: Optional[str] = None):
        """
        保存当前配置到 YAML 文件
        
        Args:
            config_path: 保存路径
        """
        save_path = config_path or self.config_path
        
        try:
            config_data = {
                'test_framework': self.config.project.test_framework,
                'refactor_targets': self.config.project.refactor_targets,
                'exclude_patterns': self.config.project.exclude_patterns,
                'code_rules': {
                    'max_line_length': self.config.project.code_rules.max_line_length,
                    'allowed_imports': self.config.project.code_rules.allowed_imports,
                    'forbidden_functions': self.config.project.code_rules.forbidden_functions,
                    'require_type_hints': self.config.project.code_rules.require_type_hints,
                    'require_docstrings': self.config.project.code_rules.require_docstrings,
                }
            }
            
            with open(save_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"Configuration saved to {save_path}")
            
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise
    
    def update_api_key(self, api_key: str):
        """更新 API Key"""
        self.config.api.api_key = api_key
        logger.info("API key updated")
    
    def update_model_params(self, temperature: float = None, max_tokens: int = None):
        """更新模型参数"""
        if temperature is not None:
            self.config.api.temperature = temperature
        if max_tokens is not None:
            self.config.api.max_tokens = max_tokens
        logger.info("Model parameters updated")
    
    def get_project_config(self) -> Dict[str, Any]:
        """获取项目配置的字典形式"""
        return {
            'test_framework': self.config.project.test_framework,
            'refactor_targets': self.config.project.refactor_targets,
            'exclude_patterns': self.config.project.exclude_patterns,
            'code_rules': {
                'max_line_length': self.config.project.code_rules.max_line_length,
                'allowed_imports': self.config.project.code_rules.allowed_imports,
                'forbidden_functions': self.config.project.code_rules.forbidden_functions,
                'require_type_hints': self.config.project.code_rules.require_type_hints,
                'require_docstrings': self.config.project.code_rules.require_docstrings,
            }
        }
    
    def validate_config(self) -> List[str]:
        """
        验证配置是否正确
        
        Returns:
            错误列表，空列表表示配置正确
        """
        errors = []
        
        if not self.config.api.api_key:
            errors.append("API key is required")
        
        if self.config.api.temperature < 0 or self.config.api.temperature > 2:
            errors.append("Temperature must be between 0 and 2")
        
        if self.config.api.max_tokens < 1:
            errors.append("Max tokens must be positive")
        
        if self.config.request.timeout < 1:
            errors.append("Request timeout must be positive")
        
        if self.config.request.max_retries < 0:
            errors.append("Max retries cannot be negative")
        
        return errors


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load_config()
    return _config_manager


def reload_config(config_path: Optional[str] = None) -> Config:
    """重新加载配置"""
    global _config_manager
    _config_manager = ConfigManager(config_path)
    return _config_manager.load_config()