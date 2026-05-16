# -*- coding: utf-8 -*-
"""
Web 前端模块 - 提供基于 Flask 的 Web 界面

功能:
1. Web 界面交互
2. 项目选择和配置
3. 任务执行和进度展示
4. 报告预览和下载

运行方式:
    python web_app.py
    访问 http://localhost:5000
"""

import os
import threading
import time
from pathlib import Path
from typing import Optional

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

from agents import ScanAgent, FixAgent, TestAgent, VerifyAgent
from agents.base_agent import AgentMessage, MessageType
from config import get_config_manager
from logger import get_logger
from project_scanner import ProjectScanner
from reports import ReportGenerator

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['REPORTS_FOLDER'] = 'reports'

# 确保目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['REPORTS_FOLDER'], exist_ok=True)

logger = get_logger('web_app')


class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        self.current_task = None
        self.task_status = "idle"  # idle, running, completed, failed
        self.task_progress = 0
        self.task_result = None
        self.task_error = None
        
        # Agent 实例
        self.scan_agent = ScanAgent()
        self.fix_agent = FixAgent()
        self.test_agent = TestAgent()
        self.verify_agent = VerifyAgent()
        self.scanner = ProjectScanner()
        self.report_generator = ReportGenerator()
        
        # 结果存储
        self.scan_result = None
        self.fix_result = None
        self.test_result = None
        self.verify_result = None
        self.current_project = None
    
    def run_scan(self, project_path: str):
        """执行扫描"""
        self.current_task = "scan"
        self.task_status = "running"
        self.task_progress = 0
        
        try:
            message = AgentMessage(
                type=MessageType.REQUEST,
                sender="web",
                receiver="ScanAgent",
                content={"project_path": project_path}
            )
            
            result = self.scan_agent.execute(message)
            self.task_progress = 100
            
            if result.success:
                self.scan_result = result.data
                self.task_status = "completed"
                self.task_result = result.data.to_dict()
            else:
                self.task_status = "failed"
                self.task_error = result.error
                
        except Exception as e:
            self.task_status = "failed"
            self.task_error = str(e)
    
    def run_fix(self, project_path: str):
        """执行修复"""
        if not self.scan_result:
            self.task_status = "failed"
            self.task_error = "请先执行扫描"
            return
        
        self.current_task = "fix"
        self.task_status = "running"
        self.task_progress = 0
        
        try:
            message = AgentMessage(
                type=MessageType.REQUEST,
                sender="web",
                receiver="FixAgent",
                content={
                    "project_path": project_path,
                    "scan_result": self.scan_result.to_dict()
                }
            )
            
            result = self.fix_agent.execute(message)
            self.task_progress = 100
            
            if result.success:
                self.fix_result = result.data
                self.task_status = "completed"
                self.task_result = result.data.to_dict()
            else:
                self.task_status = "failed"
                self.task_error = result.error
                
        except Exception as e:
            self.task_status = "failed"
            self.task_error = str(e)
    
    def run_test(self, project_path: str):
        """执行测试生成"""
        self.current_task = "test"
        self.task_status = "running"
        self.task_progress = 0
        
        try:
            message = AgentMessage(
                type=MessageType.REQUEST,
                sender="web",
                receiver="TestAgent",
                content={
                    "project_path": project_path,
                    "fix_result": self.fix_result.to_dict() if self.fix_result else None
                }
            )
            
            result = self.test_agent.execute(message)
            self.task_progress = 100
            
            if result.success:
                self.test_result = result.data
                self.task_status = "completed"
                self.task_result = result.data.to_dict()
            else:
                self.task_status = "failed"
                self.task_error = result.error
                
        except Exception as e:
            self.task_status = "failed"
            self.task_error = str(e)
    
    def run_verify(self, project_path: str):
        """执行验证"""
        if not self.test_result:
            self.task_status = "failed"
            self.task_error = "请先生成测试"
            return
        
        self.current_task = "verify"
        self.task_status = "running"
        self.task_progress = 0
        
        try:
            message = AgentMessage(
                type=MessageType.REQUEST,
                sender="web",
                receiver="VerifyAgent",
                content={
                    "project_path": project_path,
                    "test_files": [t.file for t in self.test_result.tests]
                }
            )
            
            result = self.verify_agent.execute(message)
            self.task_progress = 100
            
            if result.success:
                self.verify_result = result.data
                self.task_status = "completed"
                self.task_result = result.data.to_dict()
            else:
                self.task_status = "failed"
                self.task_error = result.error
                
        except Exception as e:
            self.task_status = "failed"
            self.task_error = str(e)
    
    def run_all(self, project_path: str):
        """执行完整流程"""
        self.current_task = "all"
        self.task_status = "running"
        self.current_project = project_path
        
        try:
            # 1. 扫描
            self.task_progress = 10
            message = AgentMessage(
                type=MessageType.REQUEST,
                sender="web",
                receiver="ScanAgent",
                content={"project_path": project_path}
            )
            result = self.scan_agent.execute(message)
            
            if not result.success:
                self.task_status = "failed"
                self.task_error = f"扫描失败: {result.error}"
                return
            
            self.scan_result = result.data
            
            # 2. 修复
            self.task_progress = 30
            message = AgentMessage(
                type=MessageType.REQUEST,
                sender="web",
                receiver="FixAgent",
                content={
                    "project_path": project_path,
                    "scan_result": self.scan_result.to_dict()
                }
            )
            result = self.fix_agent.execute(message)
            
            if result.success:
                self.fix_result = result.data
            
            # 3. 测试
            self.task_progress = 60
            message = AgentMessage(
                type=MessageType.REQUEST,
                sender="web",
                receiver="TestAgent",
                content={
                    "project_path": project_path,
                    "fix_result": self.fix_result.to_dict() if self.fix_result else None
                }
            )
            result = self.test_agent.execute(message)
            
            if result.success:
                self.test_result = result.data
            
            # 4. 验证
            self.task_progress = 90
            message = AgentMessage(
                type=MessageType.REQUEST,
                sender="web",
                receiver="VerifyAgent",
                content={
                    "project_path": project_path,
                    "test_files": [t.file for t in self.test_result.tests] if self.test_result else []
                }
            )
            result = self.verify_agent.execute(message)
            
            if result.success:
                self.verify_result = result.data
            
            self.task_progress = 100
            self.task_status = "completed"
            
        except Exception as e:
            self.task_status = "failed"
            self.task_error = str(e)
    
    def get_status(self):
        """获取状态"""
        return {
            "task": self.current_task,
            "status": self.task_status,
            "progress": self.task_progress,
            "error": self.task_error,
            "result": self.task_result
        }
    
    def generate_report(self, format: str = "md"):
        """生成报告"""
        scan_dict = self.scan_result.to_dict() if self.scan_result else None
        fix_dict = self.fix_result.to_dict() if self.fix_result else None
        test_dict = self.test_result.to_dict() if self.test_result else None
        verify_dict = self.verify_result.to_dict() if self.verify_result else None
        
        project_name = Path(self.current_project).name if self.current_project else "Project"
        
        report = self.report_generator.generate_summary_report(
            scan_result=scan_dict,
            fix_result=fix_dict,
            test_result=test_dict,
            verify_result=verify_dict,
            project_name=project_name,
            project_path=self.current_project or ""
        )
        
        output_dir = Path(app.config['REPORTS_FOLDER'])
        output_dir.mkdir(exist_ok=True)
        
        if format == "html":
            filepath = output_dir / f"{project_name}_report.html"
            self.report_generator.export_html(report, str(filepath))
        elif format == "json":
            filepath = output_dir / f"{project_name}_report.json"
            self.report_generator.export_json(report, str(filepath))
        else:
            filepath = output_dir / f"{project_name}_report.md"
            self.report_generator.export_markdown(report, str(filepath))
        
        return filepath
    
    def clone_repo(self, url: str):
        """克隆仓库"""
        try:
            target_dir = self.scanner.clone(url)
            self.current_project = target_dir
            return target_dir
        except Exception as e:
            raise Exception(f"克隆失败: {str(e)}")


# 全局任务管理器
task_manager = TaskManager()


@app.route('/')
def index():
    """首页"""
    return render_template('index.html')


@app.route('/api/status')
def api_status():
    """获取状态"""
    return jsonify(task_manager.get_status())


@app.route('/api/reset')
def api_reset():
    """重置状态"""
    task_manager.task_status = "idle"
    task_manager.current_task = None
    task_manager.task_progress = 0
    task_manager.task_result = None
    task_manager.task_error = None
    return jsonify({"status": "reset"})


@app.route('/api/scan', methods=['POST'])
def api_scan():
    """执行扫描"""
    data = request.get_json()
    project_path = data.get('project_path')
    
    if not project_path or not Path(project_path).exists():
        return jsonify({"error": "项目路径无效"}), 400
    
    task_manager.current_project = project_path
    
    # 后台执行
    thread = threading.Thread(target=task_manager.run_scan, args=(project_path,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})


@app.route('/api/fix', methods=['POST'])
def api_fix():
    """执行修复"""
    data = request.get_json()
    project_path = data.get('project_path')
    
    if not project_path:
        return jsonify({"error": "项目路径无效"}), 400
    
    # 后台执行
    thread = threading.Thread(target=task_manager.run_fix, args=(project_path,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})


@app.route('/api/test', methods=['POST'])
def api_test():
    """执行测试"""
    data = request.get_json()
    project_path = data.get('project_path')
    
    if not project_path:
        return jsonify({"error": "项目路径无效"}), 400
    
    # 后台执行
    thread = threading.Thread(target=task_manager.run_test, args=(project_path,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})


@app.route('/api/verify', methods=['POST'])
def api_verify():
    """执行验证"""
    data = request.get_json()
    project_path = data.get('project_path')
    
    if not project_path:
        return jsonify({"error": "项目路径无效"}), 400
    
    # 后台执行
    thread = threading.Thread(target=task_manager.run_verify, args=(project_path,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})


@app.route('/api/run', methods=['POST'])
def api_run():
    """执行完整流程"""
    data = request.get_json()
    project_path = data.get('project_path')
    
    if not project_path:
        return jsonify({"error": "项目路径无效"}), 400
    
    task_manager.current_project = project_path
    
    # 后台执行
    thread = threading.Thread(target=task_manager.run_all, args=(project_path,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})


@app.route('/api/clone', methods=['POST'])
def api_clone():
    """克隆仓库"""
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "请提供仓库 URL"}), 400
    
    try:
        target_dir = task_manager.clone_repo(url)
        return jsonify({"status": "success", "path": target_dir})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/report', methods=['POST'])
def api_report():
    """生成报告"""
    data = request.get_json()
    format = data.get('format', 'md')
    
    try:
        filepath = task_manager.generate_report(format)
        return jsonify({"status": "success", "path": str(filepath)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/download/<path:filename>')
def api_download(filename):
    """下载报告"""
    filepath = Path(app.config['REPORTS_FOLDER']) / filename
    if filepath.exists():
        return send_file(filepath)
    return jsonify({"error": "文件不存在"}), 404


if __name__ == '__main__':
    print("=" * 50)
    print("MiMo 代码质量保障工具 - Web 界面")
    print("=" * 50)
    print("启动中...")
    print("请访问: http://localhost:5000")
    print("按 Ctrl+C 停止服务")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)