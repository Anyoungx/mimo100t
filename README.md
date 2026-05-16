# MiMo Code Quality Assurance Tool

基于小米 MiMo API 的多 Agent 协作式代码质量保障工具，通过 ScanAgent、FixAgent、TestAgent、VerifyAgent 四个核心 Agent 协作，自动完成代码扫描、问题修复、测试生成和质量验证。

## 功能特性

- 🤖 **多 Agent 协作**: ScanAgent 分析代码 → FixAgent 修复问题 → TestAgent 生成测试 → VerifyAgent 验证质量
- 🔍 **智能代码扫描**: 自动识别技术债、规范问题、安全隐患
- 🔧 **自动代码修复**: 生成可立即使用的修复方案
- 🧪 **测试自动生成**: 适配 pytest/jest 等主流测试框架
- 📊 **质量报告导出**: 支持 Markdown/HTML 格式报告
- 💾 **本地缓存**: 保存历史任务和生成的文件
- 🎨 **美观 CLI**: 基于 Rich 的交互式命令行界面

## 安装

### 环境要求

- Python 3.10+
- Git

### 安装步骤

```bash
# 克隆项目
git clone <repository-url>
cd mimo100t

# 创建虚拟环境 (推荐)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 MiMo API Key
```

## 配置

在 `.env` 文件中配置以下参数：

```env
MIMO_API_KEY=your_api_key_here
MIMO_BASE_URL=https://api.mimo.com/v1
MODEL_NAME=mimo-pro
TEMPERATURE=0.7
MAX_TOKENS=2048
```

## 使用方法

### 交互式模式

```bash
python main.py
```

### 命令行模式

```bash
# 扫描项目
python main.py scan --path /path/to/project

# 修复问题
python main.py fix --path /path/to/project --scan-results scan_results.json

# 生成测试
python main.py test --path /path/to/project --fixed-files ./fixed/

# 验证质量
python main.py verify --path /path/to/project

# 完整流程
python main.py run --path /path/to/project
```

### Web 界面模式

```bash
# 安装 Flask 依赖
pip install -r requirements.txt

# 启动 Web 服务
python web_app.py

# 访问 http://localhost:5000
```

### 从 GitHub 克隆

```bash
python main.py clone https://github.com/username/repo
```

## 项目结构

```
mimo100t/
├── main.py              # 主程序入口
├── mimo_api.py          # MiMo API 封装
├── project_scanner.py   # 项目扫描模块
├── config.py            # 配置管理
├── logger.py            # 日志模块
├── cache.py             # 缓存管理
├── reports.py           # 报告生成
├── cli.py               # 命令行交互
├── agents/              # Agent 模块
│   ├── __init__.py
│   ├── base_agent.py    # Agent 基类
│   ├── scan_agent.py    # 代码扫描
│   ├── fix_agent.py     # 代码修复
│   ├── test_agent.py    # 测试生成
│   └── verify_agent.py  # 质量验证
├── prompts/             # 提示词模板
│   └── __init__.py
└── requirements.txt
```

## Agent 工作流程

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  ScanAgent  │───>│   FixAgent  │───>│  TestAgent  │───>│ VerifyAgent │
│             │    │             │    │             │    │             │
│ 扫描代码    │    │ 生成修复方案│    │ 生成测试用例│    │ 验证测试结果│
│ 识别问题    │    │ 提供修复代码│    │ 适配框架    │    │ 覆盖率检查  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │                  │
       v                  v                  v                  v
   问题清单         重构方案+代码        测试用例         验证报告
```

## 自定义配置

在项目根目录创建 `config.yaml` 来自定义规则：

```yaml
code_rules:
  max_line_length: 120
  allowed_imports:
    - requests
    - typing
  forbidden_functions:
    - eval
    - exec

test_framework: pytest

refactor_targets:
  - dead_code
  - duplicate_code
  - naming_issues
```

## 输出报告

工具会生成以下报告：

- `scan_report.md` - 代码扫描报告
- `fix_report.md` - 修复方案报告
- `test_report.md` - 测试生成报告
- `verify_report.md` - 质量验证报告
- `summary_report.md` - 完整质量报告

## Token 消耗

工具会统计并记录每次 API 调用的 Token 消耗：

- 输入 Token 数
- 输出 Token 数
- 总消耗
- 预估费用

## 故障排除

### API Key 无效
```
Error: Invalid API Key. Please check your .env file.
```
解决：确认 `.env` 文件中的 `MIMO_API_KEY` 正确

### 额度不足
```
Error: API quota exceeded.
```
解决：联系 MiMo 提升额度或等待配额重置

### Git 仓库克隆失败
```
Error: Failed to clone repository.
```
解决：检查网络连接和 GitHub 仓库地址

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License