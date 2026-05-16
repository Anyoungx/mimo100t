# -*- coding: utf-8 -*-
"""
日志模块 - 为 MiMo 代码质量保障工具提供统一的日志记录功能

提供两种日志输出方式:
1. 控制台输出 (带颜色)
2. 文件输出 (支持日志轮转)

使用示例:
    from logger import get_logger
    logger = get_logger(__name__)
    logger.info("This is an info message")
    logger.error("This is an error message")
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from rich.logging import RichHandler
from rich.console import Console

# 全局日志等级配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "mimo.log")

# Rich 控制台实例
console = Console()


def setup_logging(
    log_level: str = LOG_LEVEL,
    log_file: Optional[str] = LOG_FILE,
    enable_console: bool = True,
    enable_file: bool = True
) -> logging.Logger:
    """
    配置日志系统
    
    Args:
        log_level: 日志等级 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径
        enable_console: 是否启用控制台输出
        enable_file: 是否启用文件输出
    
    Returns:
        配置好的根日志器
    """
    # 创建根日志器
    root_logger = logging.getLogger("mimo")
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # 避免重复配置
    if root_logger.handlers:
        return root_logger
    
    # 日志格式
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_formatter = logging.Formatter(
        '%(message)s'
    )
    
    # 控制台处理器 (使用 Rich)
    if enable_console:
        console_handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            show_time=True,
            show_path=False,
            markup=True
        )
        console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # 文件处理器
    if enable_file and log_file:
        try:
            # 确保日志目录存在
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 使用日志轮转
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Failed to setup file logging: {e}")
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的日志器
    
    Args:
        name: 日志器名称 (通常使用 __name__)
    
    Returns:
        日志器实例
    """
    logger = logging.getLogger(f"mimo.{name}")
    
    # 如果还没有配置过根日志器，先配置
    root_logger = logging.getLogger("mimo")
    if not root_logger.handlers:
        setup_logging()
    
    return logger


class LogCapture:
    """
    日志捕获器 - 用于捕获特定代码块的日志输出
    
    使用示例:
        with LogCapture() as capture:
            logger.info("test message")
        print(capture.get_logs())
    """
    
    def __init__(self, logger_name: str = "mimo"):
        self.logger_name = logger_name
        self.logs = []
        self.handler = None
    
    def __enter__(self):
        """进入上下文管理器"""
        self.handler = LogHandler(self.logs)
        logger = logging.getLogger(self.logger_name)
        self.handler.setLevel(logging.DEBUG)
        logger.addHandler(self.handler)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器"""
        logger = logging.getLogger(self.logger_name)
        logger.removeHandler(self.handler)
        return False
    
    def get_logs(self) -> list:
        """获取捕获的日志"""
        return self.logs.copy()
    
    def clear(self):
        """清空捕获的日志"""
        self.logs.clear()


class LogHandler(logging.Handler):
    """自定义日志处理器 - 用于捕获日志"""
    
    def __init__(self, logs_container: list):
        super().__init__()
        self.logs_container = logs_container
    
    def emit(self, record: logging.LogRecord):
        """记录日志"""
        try:
            msg = self.format(record)
            self.logs_container.append({
                'level': record.levelname,
                'message': msg,
                'timestamp': datetime.fromtimestamp(record.created)
            })
        except Exception:
            self.handleError(record)


def log_function_call(func):
    """
    装饰器 - 记录函数调用信息
    
    使用示例:
        @log_function_call
        def my_function():
            pass
    """
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} completed successfully")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} failed with error: {e}")
            raise
    return wrapper


def log_execution_time(func):
    """
    装饰器 - 记录函数执行时间
    
    使用示例:
        @log_execution_time
        def slow_function():
            import time
            time.sleep(1)
    """
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = datetime.now()
        logger.debug(f"Starting {func.__name__}")
        try:
            result = func(*args, **kwargs)
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"{func.__name__} completed in {elapsed:.2f}s")
            return result
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"{func.__name__} failed after {elapsed:.2f}s: {e}")
            raise
    return wrapper