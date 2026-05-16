# -*- coding: utf-8 -*-
"""
缓存管理模块 - 为 MiMo 代码质量保障工具提供本地缓存功能

支持功能:
1. API 响应缓存 - 避免重复请求相同内容
2. 项目扫描结果缓存 - 加快二次分析速度
3. 生成文件缓存 - 保存历史生成的代码和测试
4. 任务历史记录 - 保存执行过的任务

使用示例:
    cache = CacheManager()
    cache.set("scan_result", project_path, data)
    result = cache.get("scan_result", project_path)
"""

import json
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import get_config_manager
from logger import get_logger

logger = get_logger(__name__)


class CacheManager:
    """
    缓存管理器 - 管理所有本地缓存
    
    使用示例:
        cache = CacheManager()
        cache.set("api_response", key, data)
        data = cache.get("api_response", key)
    """
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录路径，默认使用配置中的缓存目录
        """
        config = get_config_manager()
        self.cache_dir = Path(cache_dir or config.config.cache.cache_dir)
        self.enable_cache = config.config.cache.enable_cache
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        if self.enable_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Cache directory: {self.cache_dir}")
    
    def _get_cache_path(self, category: str, key: str) -> Path:
        """
        获取缓存文件路径
        
        Args:
            category: 缓存类别 (api_response, scan_result, etc.)
            key: 缓存键
        
        Returns:
            缓存文件路径
        """
        # 对 key 进行哈希处理，避免文件名过长
        key_hash = hashlib.md5(key.encode()).hexdigest()[:16]
        category_dir = self.cache_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
        return category_dir / f"{key_hash}.json"
    
    def set(self, category: str, key: str, data: Any, metadata: Optional[Dict] = None):
        """
        保存数据到缓存
        
        Args:
            category: 缓存类别
            key: 缓存键
            data: 要缓存的数据
            metadata: 可选的元数据
        """
        if not self.enable_cache:
            return
        
        try:
            cache_path = self._get_cache_path(category, key)
            
            cache_entry = {
                'key': key,
                'data': data,
                'metadata': metadata or {},
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_entry, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Cached data for {category}/{key[:50]}")
            
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def get(self, category: str, key: str, max_age: Optional[int] = None) -> Optional[Any]:
        """
        从缓存获取数据
        
        Args:
            category: 缓存类别
            key: 缓存键
            max_age: 最大缓存时间（秒），None 表示永不过期
        
        Returns:
            缓存的数据，如果不存在或已过期返回 None
        """
        if not self.enable_cache:
            return None
        
        try:
            cache_path = self._get_cache_path(category, key)
            
            if not cache_path.exists():
                return None
            
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_entry = json.load(f)
            
            # 检查缓存是否过期
            if max_age is not None:
                created_at = datetime.fromisoformat(cache_entry['created_at'])
                age = (datetime.now() - created_at).total_seconds()
                if age > max_age:
                    logger.debug(f"Cache expired for {category}/{key[:50]}")
                    return None
            
            logger.debug(f"Cache hit for {category}/{key[:50]}")
            return cache_entry['data']
            
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return None
    
    def delete(self, category: str, key: str):
        """
        删除缓存
        
        Args:
            category: 缓存类别
            key: 缓存键
        """
        try:
            cache_path = self._get_cache_path(category, key)
            if cache_path.exists():
                cache_path.unlink()
                logger.debug(f"Deleted cache for {category}/{key[:50]}")
        except Exception as e:
            logger.warning(f"Failed to delete cache: {e}")
    
    def clear(self, category: Optional[str] = None):
        """
        清空缓存
        
        Args:
            category: 要清空的缓存类别，None 表示清空所有
        """
        try:
            if category:
                category_dir = self.cache_dir / category
                if category_dir.exists():
                    shutil.rmtree(category_dir)
                    category_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Cleared cache for {category}")
            else:
                if self.cache_dir.exists():
                    shutil.rmtree(self.cache_dir)
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    logger.info("Cleared all cache")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
    
    def list_cache(self, category: str) -> List[Dict[str, Any]]:
        """
        列出指定类别的所有缓存
        
        Args:
            category: 缓存类别
        
        Returns:
            缓存项列表
        """
        cache_list = []
        category_dir = self.cache_dir / category
        
        if not category_dir.exists():
            return cache_list
        
        for cache_file in category_dir.glob("*.json"):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_entry = json.load(f)
                cache_list.append({
                    'key': cache_entry.get('key', ''),
                    'file': str(cache_file),
                    'created_at': cache_entry.get('created_at', ''),
                    'updated_at': cache_entry.get('updated_at', ''),
                    'metadata': cache_entry.get('metadata', {})
                })
            except Exception as e:
                logger.warning(f"Failed to read cache file {cache_file}: {e}")
        
        return sorted(cache_list, key=lambda x: x.get('updated_at', ''), reverse=True)


class TaskHistory:
    """
    任务历史记录 - 保存执行过的任务
    
    使用示例:
        history = TaskHistory()
        history.add_task("scan", project_path, {"files": 10})
        tasks = history.get_tasks("scan")
    """
    
    def __init__(self, cache_dir: Optional[str] = None):
        """初始化任务历史记录"""
        self.history_file = Path(cache_dir or ".mimo_cache") / "task_history.json"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_history(self) -> List[Dict[str, Any]]:
        """加载历史记录"""
        if not self.history_file.exists():
            return []
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load task history: {e}")
            return []
    
    def _save_history(self, history: List[Dict[str, Any]]):
        """保存历史记录"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save task history: {e}")
    
    def add_task(self, task_type: str, project_path: str, params: Dict[str, Any], 
                 results: Optional[Dict[str, Any]] = None, status: str = "completed"):
        """
        添加任务记录
        
        Args:
            task_type: 任务类型 (scan, fix, test, verify)
            project_path: 项目路径
            params: 任务参数
            results: 任务结果
            status: 任务状态 (pending, running, completed, failed)
        """
        history = self._load_history()
        
        task = {
            'id': len(history) + 1,
            'type': task_type,
            'project_path': project_path,
            'params': params,
            'results': results or {},
            'status': status,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        history.insert(0, task)  # 最新记录在前
        
        # 只保留最近 100 条记录
        if len(history) > 100:
            history = history[:100]
        
        self._save_history(history)
        logger.debug(f"Added task record: {task_type}")
    
    def update_task(self, task_id: int, status: str = None, results: Dict[str, Any] = None):
        """
        更新任务记录
        
        Args:
            task_id: 任务 ID
            status: 新状态
            results: 新结果
        """
        history = self._load_history()
        
        for task in history:
            if task['id'] == task_id:
                if status:
                    task['status'] = status
                if results:
                    task['results'].update(results)
                task['updated_at'] = datetime.now().isoformat()
                break
        
        self._save_history(history)
    
    def get_tasks(self, task_type: Optional[str] = None, project_path: Optional[str] = None,
                  limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取任务历史
        
        Args:
            task_type: 任务类型过滤
            project_path: 项目路径过滤
            limit: 返回记录数限制
        
        Returns:
            任务列表
        """
        history = self._load_history()
        
        filtered = history
        if task_type:
            filtered = [t for t in filtered if t['type'] == task_type]
        if project_path:
            filtered = [t for t in filtered if t['project_path'] == project_path]
        
        return filtered[:limit]
    
    def clear_history(self):
        """清空历史记录"""
        self._save_history([])


# 全局缓存管理器实例
_cache_manager: Optional[CacheManager] = None
_task_history: Optional[TaskHistory] = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器实例"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def get_task_history() -> TaskHistory:
    """获取全局任务历史记录实例"""
    global _task_history
    if _task_history is None:
        _task_history = TaskHistory()
    return _task_history