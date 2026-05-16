#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiMo Code Quality Assurance Tool - 主程序入口

基于小米 MiMo API 的多 Agent 协作式代码质量保障工具

使用示例:
    # 交互式模式
    python main.py
    
    # 命令行模式
    python main.py scan --path /path/to/project
    python main.py fix --path /path/to/project --scan-results scan_results.json
    python main.py run --path /path/to/project
"""

import argparse
import sys
from pathlib import Path

from agents import ScanAgent, FixAgent, TestAgent, VerifyAgent
from agents.base_agent import AgentMessage, MessageType, AgentPipeline
from cli import MiMoCLI
from config import get_config_manager, reload_config
from logger import get_logger, setup_logging
from project_scanner import ProjectScanner
from reports import ReportGenerator


def setup_arguments() -> argparse.ArgumentParser:
    """设置命令行参数"""
    parser = argparse.ArgumentParser(
        description="MiMo 代码质量保障工具 - 多 Agent 协作式代码质量分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py                      # 交互式模式
  python main.py scan --path /path    # 扫描项目
  python main.py fix --path /path      # 修复问题
  python main.py run --path /path     # 完整流程
        """
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        help='配置文件路径'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='日志级别'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # 扫描命令
    scan_parser = subparsers.add_parser('scan', help='扫描代码')
    scan_parser.add_argument('--path', '-p', required=True, help='项目路径')
    scan_parser.add_argument('--output', '-o', help='输出文件路径')
    
    # 修复命令
    fix_parser = subparsers.add_parser('fix', help='修复问题')
    fix_parser.add_argument('--path', '-p', required=True, help='项目路径')
    fix_parser.add_argument('--scan-results', '-s', required=True, help='扫描结果文件')
    fix_parser.add_argument('--output', '-o', help='输出文件路径')
    fix_parser.add_argument('--apply', '-a', action='store_true', help='自动应用修复')
    
    # 测试命令
    test_parser = subparsers.add_parser('test', help='生成测试')
    test_parser.add_argument('--path', '-p', required=True, help='项目路径')
    test_parser.add_argument('--fix-results', '-f', help='修复结果文件')
    test_parser.add_argument('--output', '-o', help='输出目录')
    test_parser.add_argument('--write', '-w', action='store_true', help='写入测试文件')
    
    # 验证命令
    verify_parser = subparsers.add_parser('verify', help='验证测试')
    verify_parser.add_argument('--path', '-p', required=True, help='项目路径')
    verify_parser.add_argument('--test-files', '-t', nargs='+', help='测试文件')
    verify_parser.add_argument('--output', '-o', help='输出文件路径')
    
    # 完整运行命令
    run_parser = subparsers.add_parser('run', help='完整流程')
    run_parser.add_argument('--path', '-p', required=True, help='项目路径')
    run_parser.add_argument('--output-dir', '-o', help='输出目录')
    run_parser.add_argument('--format', choices=['md', 'html', 'json'], default='md', help='报告格式')
    run_parser.add_argument('--no-apply', action='store_true', help='不自动应用修复')
    
    # 克隆命令
    clone_parser = subparsers.add_parser('clone', help='克隆仓库')
    clone_parser.add_argument('url', help='GitHub 仓库 URL')
    clone_parser.add_argument('--path', '-p', help='目标路径')
    clone_parser.add_argument('--branch', '-b', help='分支')
    
    return parser


def handle_scan(args):
    """处理扫描命令"""
    logger = get_logger('main')
    logger.info(f"Scanning project: {args.path}")
    
    scanner = ProjectScanner()
    agent = ScanAgent()
    
    message = AgentMessage(
        type=MessageType.REQUEST,
        sender="cli",
        receiver="ScanAgent",
        content={"project_path": args.path}
    )
    
    result = agent.execute(message)
    
    if result.success:
        report = result.data
        logger.info(f"Scan completed: {report.total_issues} issues found")
        
        if args.output:
            agent.export_report(report, args.output)
            logger.info(f"Report exported to {args.output}")
        
        # 打印摘要
        print(f"\n扫描完成!")
        print(f"  文件数: {report.total_files}")
        print(f"  问题数: {report.total_issues}")
        for severity, count in report.issues_by_severity.items():
            print(f"  {severity}: {count}")
        
        return report
    else:
        logger.error(f"Scan failed: {result.error}")
        print(f"[Error] {result.error}")
        return None


def handle_fix(args):
    """处理修复命令"""
    logger = get_logger('main')
    logger.info(f"Fixing issues for: {args.path}")
    
    import json
    with open(args.scan_results, 'r', encoding='utf-8') as f:
        scan_result = json.load(f)
    
    agent = FixAgent()
    
    message = AgentMessage(
        type=MessageType.REQUEST,
        sender="cli",
        receiver="FixAgent",
        content={
            "project_path": args.path,
            "scan_result": scan_result
        }
    )
    
    result = agent.execute(message)
    
    if result.success:
        report = result.data
        logger.info(f"Fix completed: {report.fixed_count} fixes generated")
        
        if args.output:
            agent.export_fixes(report, args.output)
            logger.info(f"Fix report exported to {args.output}")
        
        if args.apply:
            modified_files = agent.apply_fixes(args.path, report)
            logger.info(f"Applied fixes to {len(modified_files)} files")
        
        print(f"\n修复方案生成完成!")
        print(f"  总问题: {report.total_issues}")
        print(f"  修复数: {report.fixed_count}")
        print(f"  跳过数: {report.skipped_count}")
        
        return report
    else:
        logger.error(f"Fix failed: {result.error}")
        print(f"[Error] {result.error}")
        return None


def handle_test(args):
    """处理测试命令"""
    logger = get_logger('main')
    logger.info(f"Generating tests for: {args.path}")
    
    fix_result = None
    if args.fix_results:
        import json
        with open(args.fix_results, 'r', encoding='utf-8') as f:
            fix_result = json.load(f)
    
    agent = TestAgent()
    
    message = AgentMessage(
        type=MessageType.REQUEST,
        sender="cli",
        receiver="TestAgent",
        content={
            "project_path": args.path,
            "fix_result": fix_result
        }
    )
    
    result = agent.execute(message)
    
    if result.success:
        report = result.data
        logger.info(f"Test generation completed: {report.total_tests} tests")
        
        if args.output:
            agent.export_tests(report, args.output)
            logger.info(f"Test report exported to {args.output}")
        
        if args.write:
            written_files = agent.write_tests(args.path, report)
            logger.info(f"Wrote {len(written_files)} test files")
        
        print(f"\n测试生成完成!")
        print(f"  测试数量: {report.total_tests}")
        print(f"  测试框架: {report.framework}")
        
        return report
    else:
        logger.error(f"Test generation failed: {result.error}")
        print(f"[Error] {result.error}")
        return None


def handle_verify(args):
    """处理验证命令"""
    logger = get_logger('main')
    logger.info(f"Verifying tests for: {args.path}")
    
    agent = VerifyAgent()
    
    message = AgentMessage(
        type=MessageType.REQUEST,
        sender="cli",
        receiver="VerifyAgent",
        content={
            "project_path": args.path,
            "test_files": args.test_files or []
        }
    )
    
    result = agent.execute(message)
    
    if result.success:
        report = result.data
        logger.info(f"Verification completed: {report.passed}/{report.total_tests} passed")
        
        if args.output:
            agent.export_report(report, args.output)
            logger.info(f"Verify report exported to {args.output}")
        
        print(f"\n验证完成!")
        print(f"  总测试: {report.total_tests}")
        print(f"  通过: {report.passed}")
        print(f"  失败: {report.failed}")
        print(f"  跳过: {report.skipped}")
        
        if report.coverage:
            print(f"  覆盖率: {report.coverage.line_percent:.1f}%")
        
        return report
    else:
        logger.error(f"Verification failed: {result.error}")
        print(f"[Error] {result.error}")
        return None


def handle_run(args):
    """处理完整运行命令"""
    logger = get_logger('main')
    logger.info(f"Running full pipeline for: {args.path}")
    
    output_dir = Path(args.output_dir or "reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    project_name = Path(args.path).name
    
    scan_result = None
    fix_result = None
    test_result = None
    verify_result = None
    
    # 1. 扫描
    print("\n[1/4] 扫描代码...")
    agent = ScanAgent()
    message = AgentMessage(
        type=MessageType.REQUEST,
        sender="cli",
        receiver="ScanAgent",
        content={"project_path": args.path}
    )
    result = agent.execute(message)
    
    if result.success:
        scan_result = result.data
        print(f"      ✓ 发现 {scan_result.total_issues} 个问题")
    else:
        print(f"      ✗ 扫描失败: {result.error}")
        return
    
    # 2. 修复
    print("\n[2/4] 生成修复...")
    agent = FixAgent()
    message = AgentMessage(
        type=MessageType.REQUEST,
        sender="cli",
        receiver="FixAgent",
        content={
            "project_path": args.path,
            "scan_result": scan_result.to_dict()
        }
    )
    result = agent.execute(message)
    
    if result.success:
        fix_result = result.data
        print(f"      ✓ 生成 {fix_result.fixed_count} 个修复方案")
        
        if not args.no_apply:
            modified = agent.apply_fixes(args.path, fix_result)
            print(f"      ✓ 应用 {len(modified)} 个修复")
    else:
        print(f"      ✗ 修复失败: {result.error}")
    
    # 3. 测试
    print("\n[3/4] 生成测试...")
    agent = TestAgent()
    message = AgentMessage(
        type=MessageType.REQUEST,
        sender="cli",
        receiver="TestAgent",
        content={
            "project_path": args.path,
            "fix_result": fix_result.to_dict() if fix_result else None
        }
    )
    result = agent.execute(message)
    
    if result.success:
        test_result = result.data
        print(f"      ✓ 生成 {test_result.total_tests} 个测试用例")
        
        # 写入测试文件
        written = agent.write_tests(args.path, test_result)
        print(f"      ✓ 写入 {len(written)} 个测试文件")
    else:
        print(f"      ✗ 测试生成失败: {result.error}")
    
    # 4. 验证
    print("\n[4/4] 验证测试...")
    agent = VerifyAgent()
    message = AgentMessage(
        type=MessageType.REQUEST,
        sender="cli",
        receiver="VerifyAgent",
        content={
            "project_path": args.path,
            "test_files": [t.file for t in test_result.tests] if test_result else []
        }
    )
    result = agent.execute(message)
    
    if result.success:
        verify_result = result.data
        print(f"      ✓ 通过 {verify_result.passed}/{verify_result.total_tests} 个测试")
    else:
        print(f"      ✗ 验证失败: {result.error}")
    
    # 生成报告
    print("\n生成报告...")
    generator = ReportGenerator()
    
    report = generator.generate_summary_report(
        scan_result=scan_result.to_dict() if scan_result else None,
        fix_result=fix_result.to_dict() if fix_result else None,
        test_result=test_result.to_dict() if test_result else None,
        verify_result=verify_result.to_dict() if verify_result else None,
        project_name=project_name,
        project_path=args.path
    )
    
    if args.format == 'md':
        filepath = output_dir / f"{project_name}_report.md"
        generator.export_markdown(report, str(filepath))
    elif args.format == 'html':
        filepath = output_dir / f"{project_name}_report.html"
        generator.export_html(report, str(filepath))
    else:
        filepath = output_dir / f"{project_name}_report.json"
        generator.export_json(report, str(filepath))
    
    print(f"      ✓ 报告已导出: {filepath}")


def handle_clone(args):
    """处理克隆命令"""
    logger = get_logger('main')
    logger.info(f"Cloning repository: {args.url}")
    
    scanner = ProjectScanner()
    
    try:
        target_dir = scanner.clone(args.url, args.path, args.branch)
        print(f"\n✓ 克隆成功!")
        print(f"  路径: {target_dir}")
    except Exception as e:
        print(f"\n✗ 克隆失败: {e}")


def main():
    """主函数"""
    parser = setup_arguments()
    args = parser.parse_args()
    
    # 加载配置
    if args.config:
        reload_config(args.config)
    
    # 设置日志
    setup_logging(log_level=args.log_level)
    logger = get_logger('main')
    
    logger.info("MiMo Code Quality Assurance Tool started")
    
    # 执行命令
    if args.command is None:
        # 交互式模式
        cli = MiMoCLI()
        cli.run_interactive()
    elif args.command == 'scan':
        handle_scan(args)
    elif args.command == 'fix':
        handle_fix(args)
    elif args.command == 'test':
        handle_test(args)
    elif args.command == 'verify':
        handle_verify(args)
    elif args.command == 'run':
        handle_run(args)
    elif args.command == 'clone':
        handle_clone(args)
    
    logger.info("MiMo Code Quality Assurance Tool finished")


if __name__ == '__main__':
    main()