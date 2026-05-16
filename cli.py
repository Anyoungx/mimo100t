# -*- coding: utf-8 -*-
"""
命令行交互模块 - 使用 Rich 实现美观的命令行界面

功能:
1. 项目选择和配置设置
2. 任务进度展示
3. 实时日志输出
4. 用户干预流程

使用示例:
    from cli import MiMoCLI
    
    cli = MiMoCLI()
    cli.run_interactive()
"""

import os
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.tree import Tree

from agents import ScanAgent, FixAgent, TestAgent, VerifyAgent
from agents.base_agent import AgentMessage, MessageType, AgentPipeline
from config import get_config_manager
from logger import get_logger, setup_logging
from project_scanner import ProjectScanner
from reports import ReportGenerator

logger = get_logger(__name__)


class MiMoCLI:
    """
    MiMo 命令行界面
    
    使用 Rich 库实现美观的交互式命令行界面。
    
    使用示例:
        cli = MiMoCLI()
        cli.run_interactive()
    """
    
    def __init__(self):
        """初始化 CLI"""
        self.console = Console()
        self.config = get_config_manager()
        self.config.load_config()
        self.scanner = ProjectScanner()
        
        # 初始化 Agent
        self.scan_agent = ScanAgent()
        self.fix_agent = FixAgent()
        self.test_agent = TestAgent()
        self.verify_agent = VerifyAgent()
        
        # 当前项目
        self.current_project: Optional[str] = None
        
        # 任务结果
        self.scan_result = None
        self.fix_result = None
        self.test_result = None
        self.verify_result = None
    
    def run_interactive(self):
        """运行交互式模式"""
        self._print_banner()
        
        # 检查配置
        if not self._check_config():
            return
        
        # 主循环
        while True:
            self._print_main_menu()
            choice = Prompt.ask(
                "[bold cyan]请选择操作[/bold cyan]",
                choices=['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
                default='0'
            )
            
            if choice == '0':
                self._print_exit()
                break
            elif choice == '1':
                self._handle_scan()
            elif choice == '2':
                self._handle_fix()
            elif choice == '3':
                self._handle_test()
            elif choice == '4':
                self._handle_verify()
            elif choice == '5':
                self._handle_run_all()
            elif choice == '6':
                self._handle_clone()
            elif choice == '7':
                self._handle_config()
            elif choice == '8':
                self._handle_history()
            elif choice == '9':
                self._handle_export()
    
    def _print_banner(self):
        """打印横幅"""
        banner = """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║     ███╗   ███╗ ██████╗ ██████╗ ███████╗███████╗███████╗    ║
║     ████╗ ████║██╔═══██╗██╔══██╗██╔════╝██╔════╝██╔════╝    ║
║     ██╔████╔██║██║   ██║██████╔╝███████╗█████╗  ███████╗    ║
║     ██║╚██╔╝██║██║   ██║██╔══██╗╚════██║██╔══╝  ╚════██║    ║
║     ██║ ╚═╔█╝╚██████╔╝██████╔╝███████║███████╗███████║    ║
║     ╚═╝   ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚══════╝    ║
║                                                           ║
║          多 Agent 协作式代码质量保障工具                   ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
        """
        self.console.print(banner, style="cyan")
    
    def _print_main_menu(self):
        """打印主菜单"""
        table = Table(title="📋 主菜单", show_header=False, box=None)
        table.add_column("选项", style="cyan", width=4)
        table.add_column("功能", style="white")
        table.add_column("说明", style="dim")
        
        table.add_row("1", "🔍 扫描项目", "扫描代码，识别问题")
        table.add_row("2", "🔧 修复问题", "生成修复方案")
        table.add_row("3", "🧪 生成测试", "自动生成测试用例")
        table.add_row("4", "✅ 验证测试", "执行测试并收集结果")
        table.add_row("5", "🚀 一键运行", "执行完整流程")
        table.add_row("6", "📥 克隆仓库", "从 GitHub 克隆项目")
        table.add_row("7", "⚙️  配置设置", "修改配置参数")
        table.add_row("8", "📜 历史记录", "查看任务历史")
        table.add_row("9", "📤 导出报告", "导出质量报告")
        table.add_row("0", "🚪 退出程序", "退出 MiMo")
        
        self.console.print(table)
    
    def _print_exit(self):
        """打印退出信息"""
        self.console.print("\n[bold green]感谢使用 MiMo！[/bold green]\n", justify="center")
    
    def _check_config(self) -> bool:
        """检查配置是否正确"""
        errors = self.config.validate_config()
        
        if errors:
            self.console.print("\n[bold red]配置错误:[/bold red]")
            for error in errors:
                self.console.print(f"  • {error}")
            
            if Confirm.ask("是否现在配置?"):
                self._handle_config()
            else:
                return False
        
        return True
    
    def _select_project(self) -> Optional[str]:
        """选择项目"""
        self.console.print("\n[bold cyan]📂 选择项目[/bold cyan]")
        
        # 检查当前目录
        current_dir = Path.cwd()
        if (current_dir / "requirements.txt").exists() or (current_dir / "package.json").exists():
            use_current = Confirm.ask(f"使用当前目录 [{current_dir}]?", default=True)
            if use_current:
                return str(current_dir)
        
        # 输入路径
        path = Prompt.ask("请输入项目路径")
        
        if not Path(path).exists():
            self.console.print(f"[red]路径不存在: {path}[/red]")
            return None
        
        self.current_project = path
        return path
    
    def _handle_scan(self):
        """处理扫描任务"""
        project_path = self.current_project or self._select_project()
        if not project_path:
            return
        
        self.console.print(f"\n[bold cyan]🔍 正在扫描项目: {project_path}[/bold cyan]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console
        ) as progress:
            task = progress.add_task("扫描中...", total=100)
            
            message = AgentMessage(
                type=MessageType.REQUEST,
                sender="cli",
                receiver="ScanAgent",
                content={"project_path": project_path}
            )
            
            result = self.scan_agent.execute(message)
            progress.update(task, completed=100)
            
            if result.success:
                self.scan_result = result.data
                self._display_scan_result()
            else:
                self.console.print(f"[red]扫描失败: {result.error}[/red]")
    
    def _handle_fix(self):
        """处理修复任务"""
        if not self.scan_result:
            self.console.print("[yellow]请先执行扫描[/yellow]")
            return
        
        self.console.print("\n[bold cyan]🔧 正在生成修复方案...[/bold cyan]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("生成修复中...", total=None)
            
            message = AgentMessage(
                type=MessageType.REQUEST,
                sender="cli",
                receiver="FixAgent",
                content={
                    "project_path": self.scan_result.project_path,
                    "scan_result": self.scan_result.to_dict()
                }
            )
            
            result = self.fix_agent.execute(message)
            progress.update(task, completed=100)
            
            if result.success:
                self.fix_result = result.data
                self._display_fix_result()
            else:
                self.console.print(f"[red]修复失败: {result.error}[/red]")
    
    def _handle_test(self):
        """处理测试生成任务"""
        project_path = self.current_project or self._select_project()
        if not project_path:
            return
        
        self.console.print("\n[bold cyan]🧪 正在生成测试用例...[/bold cyan]")
        
        message = AgentMessage(
            type=MessageType.REQUEST,
            sender="cli",
            receiver="TestAgent",
            content={
                "project_path": project_path,
                "fix_result": self.fix_result.to_dict() if self.fix_result else None
            }
        )
        
        result = self.test_agent.execute(message)
        
        if result.success:
            self.test_result = result.data
            self._display_test_result()
        else:
            self.console.print(f"[red]测试生成失败: {result.error}[/red]")
    
    def _handle_verify(self):
        """处理验证任务"""
        if not self.test_result:
            self.console.print("[yellow]请先生成测试[/yellow]")
            return
        
        project_path = self.current_project or self._select_project()
        if not project_path:
            return
        
        self.console.print("\n[bold cyan]✅ 正在验证测试...[/bold cyan]")
        
        message = AgentMessage(
            type=MessageType.REQUEST,
            sender="cli",
            receiver="VerifyAgent",
            content={
                "project_path": project_path,
                "test_files": [t.file for t in self.test_result.tests]
            }
        )
        
        result = self.verify_agent.execute(message)
        
        if result.success:
            self.verify_result = result.data
            self._display_verify_result()
        else:
            self.console.print(f"[red]验证失败: {result.error}[/red]")
    
    def _handle_run_all(self):
        """处理一键运行"""
        project_path = self.current_project or self._select_project()
        if not project_path:
            return
        
        self.console.print("\n[bold green]🚀 开始执行完整流程...[/bold green]\n")
        
        # 创建管道
        pipeline = AgentPipeline()
        pipeline.add_agent(self.scan_agent)
        pipeline.add_agent(self.fix_agent)
        pipeline.add_agent(self.test_agent)
        pipeline.add_agent(self.verify_agent)
        
        # 执行扫描
        self.console.print("[cyan]步骤 1/4: 扫描代码...[/cyan]")
        scan_msg = AgentMessage(
            type=MessageType.REQUEST,
            sender="cli",
            receiver="ScanAgent",
            content={"project_path": project_path}
        )
        scan_result = self.scan_agent.execute(scan_msg)
        
        if not scan_result.success:
            self.console.print(f"[red]扫描失败: {scan_result.error}[/red]")
            return
        
        self.scan_result = scan_result.data
        self.console.print("[green]✓ 扫描完成[/green]\n")
        
        # 执行修复
        self.console.print("[cyan]步骤 2/4: 生成修复...[/cyan]")
        fix_msg = AgentMessage(
            type=MessageType.REQUEST,
            sender="cli",
            receiver="FixAgent",
            content={
                "project_path": project_path,
                "scan_result": self.scan_result.to_dict()
            }
        )
        fix_result = self.fix_agent.execute(fix_msg)
        
        if fix_result.success:
            self.fix_result = fix_result.data
            self.console.print("[green]✓ 修复完成[/green]\n")
        
        # 生成测试
        self.console.print("[cyan]步骤 3/4: 生成测试...[/cyan]")
        test_msg = AgentMessage(
            type=MessageType.REQUEST,
            sender="cli",
            receiver="TestAgent",
            content={
                "project_path": project_path,
                "fix_result": self.fix_result.to_dict() if self.fix_result else None
            }
        )
        test_result = self.test_agent.execute(test_msg)
        
        if test_result.success:
            self.test_result = test_result.data
            self.console.print("[green]✓ 测试生成完成[/green]\n")
        
        # 验证测试
        self.console.print("[cyan]步骤 4/4: 验证测试...[/cyan]")
        verify_msg = AgentMessage(
            type=MessageType.REQUEST,
            sender="cli",
            receiver="VerifyAgent",
            content={
                "project_path": project_path,
                "test_files": [t.file for t in self.test_result.tests]
            }
        )
        verify_result = self.verify_agent.execute(verify_msg)
        
        if verify_result.success:
            self.verify_result = verify_result.data
            self.console.print("[green]✓ 验证完成[/green]\n")
        
        # 生成报告
        self._print_summary()
    
    def _handle_clone(self):
        """处理克隆任务"""
        repo_url = Prompt.ask("\n[bold cyan]请输入 GitHub 仓库地址[/bold cyan]")
        
        self.console.print(f"\n[cyan]正在克隆仓库: {repo_url}[/cyan]")
        
        try:
            target_dir = self.scanner.clone(repo_url)
            self.current_project = target_dir
            self.console.print(f"[green]✓ 克隆成功: {target_dir}[/green]")
        except Exception as e:
            self.console.print(f"[red]克隆失败: {e}[/red]")
    
    def _handle_config(self):
        """处理配置"""
        table = Table(title="当前配置", show_header=True)
        table.add_column("配置项", style="cyan")
        table.add_column("值", style="white")
        
        api_config = self.config.config.api
        table.add_row("API Key", f"{api_config.api_key[:10]}..." if api_config.api_key else "未设置")
        table.add_row("Base URL", api_config.base_url)
        table.add_row("Model", api_config.model_name)
        table.add_row("Temperature", str(api_config.temperature))
        table.add_row("Max Tokens", str(api_config.max_tokens))
        
        self.console.print(table)
        
        if Confirm.ask("是否修改配置?"):
            new_key = Prompt.ask("API Key (留空保持不变)")
            if new_key:
                self.config.update_api_key(new_key)
            
            self.console.print("[green]配置已更新[/green]")
    
    def _handle_history(self):
        """处理历史记录"""
        from cache import get_task_history
        
        history = get_task_history()
        tasks = history.get_tasks(limit=10)
        
        if not tasks:
            self.console.print("[yellow]暂无历史记录[/yellow]")
            return
        
        table = Table(title="任务历史", show_header=True)
        table.add_column("ID", style="cyan", width=4)
        table.add_column("类型", style="white")
        table.add_column("项目", style="white")
        table.add_column("状态", style="white")
        table.add_column("时间", style="dim")
        
        for task in tasks:
            table.add_row(
                str(task['id']),
                task['type'],
                task['project_path'],
                task['status'],
                task['created_at'][:19]
            )
        
        self.console.print(table)
    
    def _handle_export(self):
        """处理导出"""
        generator = ReportGenerator()
        
        scan_dict = self.scan_result.to_dict() if self.scan_result else None
        fix_dict = self.fix_result.to_dict() if self.fix_result else None
        test_dict = self.test_result.to_dict() if self.test_result else None
        verify_dict = self.verify_result.to_dict() if self.verify_result else None
        
        project_name = Path(self.current_project).name if self.current_project else "Project"
        
        report = generator.generate_summary_report(
            scan_result=scan_dict,
            fix_result=fix_dict,
            test_result=test_dict,
            verify_result=verify_dict,
            project_name=project_name,
            project_path=self.current_project or ""
        )
        
        self.console.print("\n[bold cyan]选择导出格式:[/bold cyan]")
        self.console.print("1. Markdown (.md)")
        self.console.print("2. HTML (.html)")
        self.console.print("3. JSON (.json)")
        
        choice = Prompt.ask("请选择", choices=['1', '2', '3'], default='1')
        output_dir = Path("reports")
        output_dir.mkdir(exist_ok=True)
        
        if choice == '1':
            filepath = output_dir / f"{project_name}_report.md"
            generator.export_markdown(report, str(filepath))
        elif choice == '2':
            filepath = output_dir / f"{project_name}_report.html"
            generator.export_html(report, str(filepath))
        else:
            filepath = output_dir / f"{project_name}_report.json"
            generator.export_json(report, str(filepath))
        
        self.console.print(f"[green]✓ 报告已导出: {filepath}[/green]")
    
    def _display_scan_result(self):
        """显示扫描结果"""
        if not self.scan_result:
            return
        
        table = Table(title="扫描结果", show_header=False)
        table.add_column("指标", style="cyan")
        table.add_column("数值", style="white")
        
        table.add_row("扫描文件数", str(self.scan_result.total_files))
        table.add_row("发现问题数", str(self.scan_result.total_issues))
        
        for severity, count in self.scan_result.issues_by_severity.items():
            table.add_row(f"{severity} 问题", str(count))
        
        self.console.print(table)
    
    def _display_fix_result(self):
        """显示修复结果"""
        if not self.fix_result:
            return
        
        self.console.print(f"\n[green]✓ 生成了 {self.fix_result.fixed_count} 个修复方案[/green]")
    
    def _display_test_result(self):
        """显示测试结果"""
        if not self.test_result:
            return
        
        self.console.print(f"\n[green]✓ 生成了 {self.test_result.total_tests} 个测试用例[/green]")
    
    def _display_verify_result(self):
        """显示验证结果"""
        if not self.verify_result:
            return
        
        table = Table(title="验证结果", show_header=False)
        table.add_column("指标", style="cyan")
        table.add_column("数值", style="white")
        
        table.add_row("总测试数", str(self.verify_result.total_tests))
        table.add_row("通过", str(self.verify_result.passed))
        table.add_row("失败", str(self.verify_result.failed))
        table.add_row("通过率", f"{self.verify_result.pass_rate:.1f}%")
        
        if self.verify_result.coverage:
            table.add_row("覆盖率", f"{self.verify_result.coverage.line_percent:.1f}%")
        
        self.console.print(table)
    
    def _print_summary(self):
        """打印总结"""
        self.console.print("\n")
        self.console.print(Panel.fit(
            "[bold green]执行完成！[/bold green]\n\n"
            f"发现问题: {self.scan_result.total_issues if self.scan_result else 0}\n"
            f"修复方案: {self.fix_result.fixed_count if self.fix_result else 0}\n"
            f"测试用例: {self.test_result.total_tests if self.test_result else 0}\n"
            f"测试通过: {self.verify_result.passed if self.verify_result else 0}",
            title="执行总结"
        ))