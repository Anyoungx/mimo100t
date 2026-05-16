# -*- coding: utf-8 -*-
"""
项目扫描模块 - 扫描和分析本地项目结构

功能:
1. 本地 Git 仓库扫描 - 文件列表、目录结构
2. 远程仓库克隆 - 支持 GitHub 仓库地址
3. 依赖配置解析 - requirements.txt, package.json, etc.
4. 配置文件解析 - config.yaml, .env.example, etc.
5. 代码文件内容读取

使用示例:
    scanner = ProjectScanner()
    project = scanner.scan("/path/to/project")
    print(project.files)
    
    # 从 GitHub 克隆
    scanner.clone("https://github.com/username/repo")
"""

import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from git import Repo, GitCommandError

from config import get_config_manager
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class CodeFile:
    """代码文件"""
    path: str
    relative_path: str
    language: str
    lines: int
    size: int
    content: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'path': self.relative_path,
            'language': self.language,
            'lines': self.lines,
            'size': self.size
        }


@dataclass
class DependencyInfo:
    """依赖信息"""
    name: str
    version: str
    type: str  # "pip", "npm", etc.
    
    def to_dict(self) -> Dict[str, str]:
        return {
            'name': self.name,
            'version': self.version,
            'type': self.type
        }


@dataclass
class ProjectConfig:
    """项目配置"""
    path: str
    name: str
    language: str
    framework: Optional[str] = None
    build_system: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'path': self.path,
            'name': self.name,
            'language': self.language,
            'framework': self.framework,
            'build_system': self.build_system
        }


@dataclass
class ProjectInfo:
    """项目信息"""
    config: ProjectConfig
    files: List[CodeFile] = field(default_factory=list)
    dependencies: List[DependencyInfo] = field(default_factory=list)
    structure: Dict[str, Any] = field(default_factory=dict)
    git_info: Optional[Dict[str, str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'config': self.config.to_dict(),
            'file_count': len(self.files),
            'files': [f.to_dict() for f in self.files],
            'dependencies': [d.to_dict() for d in self.dependencies],
            'structure': self.structure,
            'git_info': self.git_info
        }


# 文件语言映射
LANGUAGE_MAP = {
    '.py': 'Python',
    '.js': 'JavaScript',
    '.ts': 'TypeScript',
    '.jsx': 'React',
    '.tsx': 'React',
    '.java': 'Java',
    '.c': 'C',
    '.cpp': 'C++',
    '.h': 'C/C++ Header',
    '.hpp': 'C++ Header',
    '.cs': 'C#',
    '.go': 'Go',
    '.rs': 'Rust',
    '.rb': 'Ruby',
    '.php': 'PHP',
    '.swift': 'Swift',
    '.kt': 'Kotlin',
    '.scala': 'Scala',
    '.vue': 'Vue',
    '.html': 'HTML',
    '.css': 'CSS',
    '.scss': 'SCSS',
    '.sass': 'Sass',
    '.less': 'Less',
    '.json': 'JSON',
    '.xml': 'XML',
    '.yaml': 'YAML',
    '.yml': 'YAML',
    '.md': 'Markdown',
    '.sql': 'SQL',
    '.sh': 'Shell',
    '.bash': 'Bash',
    '.ps1': 'PowerShell',
    '.r': 'R',
    '.lua': 'Lua',
    '.ex': 'Elixir',
    '.exs': 'Elixir',
    '.erl': 'Erlang',
    '.hs': 'Haskell',
    '.clj': 'Clojure',
    '.fs': 'F#',
    '.dart': 'Dart',
    '.jl': 'Julia'
}

# 代码文件扩展名
CODE_EXTENSIONS = set(LANGUAGE_MAP.keys())

# 测试文件模式
TEST_PATTERNS = [
    r'test_.*\.py$',
    r'.*_test\.py$',
    r'.*\.test\.py$',
    r'.*\.spec\.py$',
    r'test_.*\.js$',
    r'.*\.test\.js$',
    r'.*\.spec\.js$',
    r'.*\.test\.ts$',
    r'.*\.spec\.ts$',
    r'.*\.test\.tsx$',
    r'.*\.spec\.tsx$',
    r'.*\.test\.java$',
    r'.*Test\.java$',
]


class ProjectScanner:
    """
    项目扫描器 - 扫描和分析本地项目
    
    使用示例:
        scanner = ProjectScanner()
        project = scanner.scan("/path/to/project")
        print(project.files)
    """
    
    def __init__(self, exclude_patterns: Optional[List[str]] = None):
        """
        初始化项目扫描器
        
        Args:
            exclude_patterns: 排除的文件/目录模式
        """
        config = get_config_manager()
        config.load_config()
        
        # 默认排除模式
        self.exclude_patterns = exclude_patterns or config.config.project.exclude_patterns
        self._exclude_re = self._compile_exclude_patterns()
    
    def _compile_exclude_patterns(self) -> Set[re.Pattern]:
        """编译排除模式为正则表达式"""
        patterns = set()
        for pattern in self.exclude_patterns:
            # 支持通配符模式
            regex_pattern = pattern.replace('.', r'\.')
            regex_pattern = regex_pattern.replace('*', '.*')
            regex_pattern = regex_pattern.replace('?', '.')
            patterns.add(re.compile(regex_pattern))
        return patterns
    
    def _should_exclude(self, path: str) -> bool:
        """检查路径是否应该被排除"""
        path_parts = Path(path).parts
        for part in path_parts:
            for pattern in self._exclude_re:
                if pattern.match(part):
                    return True
        return False
    
    def scan(self, project_path: str, include_content: bool = False, 
             max_file_size: int = 1024 * 1024) -> ProjectInfo:
        """
        扫描项目
        
        Args:
            project_path: 项目路径
            include_content: 是否包含文件内容
            max_file_size: 最大文件大小（字节）
        
        Returns:
            项目信息对象
        """
        path = Path(project_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Project path does not exist: {project_path}")
        
        logger.info(f"Scanning project: {path}")
        
        # 获取项目配置
        config = self._detect_project_config(path)
        
        # 获取 Git 信息
        git_info = self._get_git_info(path)
        
        # 扫描文件
        files = self._scan_files(path, include_content, max_file_size)
        
        # 获取依赖
        dependencies = self._parse_dependencies(path, config.language)
        
        # 生成目录结构
        structure = self._generate_structure(path, files)
        
        project_info = ProjectInfo(
            config=config,
            files=files,
            dependencies=dependencies,
            structure=structure,
            git_info=git_info
        )
        
        logger.info(f"Scan completed: {len(files)} files found")
        return project_info
    
    def _detect_project_config(self, path: Path) -> ProjectConfig:
        """检测项目配置"""
        name = path.name
        language = "Unknown"
        framework = None
        build_system = None
        
        # 检测语言和框架
        if (path / "requirements.txt").exists():
            language = "Python"
            build_system = "pip"
        elif (path / "package.json").exists():
            language = "JavaScript"
            framework = self._detect_js_framework(path)
            build_system = "npm"
        elif (path / "pom.xml").exists():
            language = "Java"
            framework = "Maven"
            build_system = "Maven"
        elif (path / "build.gradle").exists():
            language = "Java"
            framework = "Gradle"
            build_system = "Gradle"
        elif (path / "go.mod").exists():
            language = "Go"
            build_system = "Go Modules"
        elif (path / "Cargo.toml").exists():
            language = "Rust"
            build_system = "Cargo"
        elif (path / "*.csproj").exists():
            language = "C#"
            build_system = ".NET"
        elif (path / "*.xcodeproj").exists() or (path / "*.xcworkspace").exists():
            language = "Swift/Objective-C"
            build_system = "Xcode"
        elif (path / "Gemfile").exists():
            language = "Ruby"
            build_system = "Bundler"
        
        return ProjectConfig(
            path=str(path),
            name=name,
            language=language,
            framework=framework,
            build_system=build_system
        )
    
    def _detect_js_framework(self, path: Path) -> Optional[str]:
        """检测 JS 框架"""
        package_json = path / "package.json"
        if package_json.exists():
            try:
                import json
                with open(package_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
                    
                    if 'react' in deps:
                        return 'React'
                    elif 'vue' in deps:
                        return 'Vue'
                    elif '@angular/core' in deps:
                        return 'Angular'
                    elif 'next' in deps:
                        return 'Next.js'
                    elif 'nuxt' in deps:
                        return 'Nuxt'
            except:
                pass
        return None
    
    def _get_git_info(self, path: Path) -> Optional[Dict[str, str]]:
        """获取 Git 信息"""
        try:
            repo = Repo(path)
            return {
                'branch': repo.active_branch.name,
                'commit': repo.head.commit.hexsha[:8],
                'is_dirty': repo.is_dirty(),
                'remote_url': self._get_remote_url(repo)
            }
        except Exception as e:
            logger.debug(f"Not a git repository: {e}")
            return None
    
    def _get_remote_url(self, repo: Repo) -> Optional[str]:
        """获取远程仓库 URL"""
        try:
            if 'origin' in repo.remotes:
                return repo.remotes.origin.url
        except:
            pass
        return None
    
    def _scan_files(self, path: Path, include_content: bool = False,
                   max_file_size: int = 1024 * 1024) -> List[CodeFile]:
        """扫描代码文件"""
        files = []
        
        for root, dirs, filenames in os.walk(path):
            root_path = Path(root)
            
            # 排除目录
            dirs[:] = [d for d in dirs if not self._should_exclude(d)]
            
            for filename in filenames:
                file_path = root_path / filename
                
                if self._should_exclude(filename):
                    continue
                
                # 检查是否是代码文件
                ext = file_path.suffix.lower()
                if ext not in CODE_EXTENSIONS:
                    continue
                
                try:
                    # 检查文件大小
                    size = file_path.stat().st_size
                    if size > max_file_size:
                        logger.warning(f"Skipping large file: {file_path} ({size} bytes)")
                        continue
                    
                    # 读取内容
                    content = ""
                    if include_content:
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                        except UnicodeDecodeError:
                            try:
                                with open(file_path, 'r', encoding='latin-1') as f:
                                    content = f.read()
                            except:
                                content = "[Binary or unreadable file]"
                    
                    # 计算行数
                    lines = content.count('\n') + 1 if content else 0
                    
                    code_file = CodeFile(
                        path=str(file_path),
                        relative_path=str(file_path.relative_to(path)),
                        language=LANGUAGE_MAP.get(ext, 'Unknown'),
                        lines=lines,
                        size=size,
                        content=content
                    )
                    files.append(code_file)
                    
                except Exception as e:
                    logger.warning(f"Failed to read file {file_path}: {e}")
        
        return files
    
    def _parse_dependencies(self, path: Path, language: str) -> List[DependencyInfo]:
        """解析依赖文件"""
        dependencies = []
        
        if language == "Python":
            # requirements.txt
            req_file = path / "requirements.txt"
            if req_file.exists():
                try:
                    with open(req_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                # 解析版本
                                match = re.match(r'^([a-zA-Z0-9_-]+)([<>=!~]+)?(.*)$', line)
                                if match:
                                    name, op, version = match.groups()
                                    dependencies.append(DependencyInfo(
                                        name=name,
                                        version=f"{op or ''}{version}".strip() or "any",
                                        type="pip"
                                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse requirements.txt: {e}")
        
        elif language == "JavaScript":
            # package.json
            pkg_file = path / "package.json"
            if pkg_file.exists():
                try:
                    import json
                    with open(pkg_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        all_deps = {}
                        all_deps.update(data.get('dependencies', {}))
                        all_deps.update(data.get('devDependencies', {}))
                        
                        for name, version in all_deps.items():
                            dependencies.append(DependencyInfo(
                                name=name,
                                version=version,
                                type="npm"
                            ))
                except Exception as e:
                    logger.warning(f"Failed to parse package.json: {e}")
        
        return dependencies
    
    def _generate_structure(self, path: Path, files: List[CodeFile]) -> Dict[str, Any]:
        """生成目录结构"""
        structure = {}
        
        for file in files:
            parts = Path(file.relative_path).parts
            current = structure
            
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # 文件
                    if '__files__' not in current:
                        current['__files__'] = []
                    current['__files__'].append({
                        'name': part,
                        'language': file.language,
                        'lines': file.lines
                    })
                else:
                    # 目录
                    if part not in current:
                        current[part] = {}
                    current = current[part]
        
        return structure
    
    def clone(self, repo_url: str, target_dir: Optional[str] = None,
              branch: Optional[str] = None) -> str:
        """
        克隆远程仓库
        
        Args:
            repo_url: GitHub 仓库 URL
            target_dir: 目标目录，None 则使用临时目录
            branch: 分支，None 则克隆默认分支
        
        Returns:
            克隆到的本地路径
        """
        logger.info(f"Cloning repository: {repo_url}")
        
        # 解析 URL
        if not repo_url.startswith(('http://', 'https://', 'git@')):
            # 可能是简化的 GitHub URL
            if '/' in repo_url:
                repo_url = f"https://github.com/{repo_url}"
        
        # 确定目标目录
        if target_dir is None:
            from tempfile import gettempdir
            target_dir = os.path.join(gettempdir(), f"mimo_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        try:
            # 克隆仓库
            repo = Repo.clone_from(
                repo_url,
                target_dir,
                branch=branch,
                depth=1  # 浅克隆
            )
            
            logger.info(f"Repository cloned to: {target_dir}")
            return target_dir
            
        except GitCommandError as e:
            logger.error(f"Failed to clone repository: {e}")
            raise MiMoAPIError(f"Failed to clone repository: {e}")
    
    def read_file(self, file_path: str, max_lines: int = 10000) -> str:
        """
        读取文件内容
        
        Args:
            file_path: 文件路径
            max_lines: 最大行数
        
        Returns:
            文件内容
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line)
                return ''.join(lines)
        except UnicodeDecodeError:
            with open(path, 'r', encoding='latin-1') as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line)
                return ''.join(lines)
    
    def get_files_by_pattern(self, project_path: str, pattern: str) -> List[str]:
        """
        根据模式获取文件列表
        
        Args:
            project_path: 项目路径
            pattern: 文件模式（支持通配符）
        
        Returns:
            匹配的文件路径列表
        """
        path = Path(project_path)
        regex_pattern = pattern.replace('.', r'\.')
        regex_pattern = regex_pattern.replace('*', '.*')
        regex_pattern = f"^{regex_pattern}$"
        
        compiled_pattern = re.compile(regex_pattern)
        matched_files = []
        
        for file in self._scan_files(path, include_content=False):
            if compiled_pattern.match(file.relative_path):
                matched_files.append(file.path)
        
        return matched_files
    
    def get_test_files(self, project_path: str) -> List[str]:
        """
        获取测试文件列表
        
        Args:
            project_path: 项目路径
        
        Returns:
            测试文件路径列表
        """
        test_files = []
        
        for pattern in TEST_PATTERNS:
            compiled_pattern = re.compile(pattern)
            project = self.scan(project_path)
            
            for file in project.files:
                if compiled_pattern.match(file.relative_path):
                    test_files.append(file.path)
        
        return test_files


class MiMoAPIError(Exception):
    """MiMo API 错误"""
    pass