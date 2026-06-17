# QQQJY - 订单自动填写工具

基于 Flask + Playwright + Claude AI 的订单自动化填写 Web 应用。

## 功能

- 登录目标平台并保持会话
- 解析订单数据，自动识别字段
- 调用 Claude AI 辅助填写订单
- 支持任务管理与状态跟踪
- 提供 Web 界面（Dashboard / Fill 页面）

## 环境要求

- Python 3.9+
- [Playwright](https://playwright.dev/python/)
- Anthropic Claude API Key

## 安装

```bash
pip install flask playwright anthropic
playwright install chromium
```

## 配置

在项目根目录创建或编辑 `config.json`：

```json
{
  "claude_api_key": "your-anthropic-api-key"
}
```

也可以通过环境变量设置：

```bash
set ANTHROPIC_API_KEY=your-api-key
```

## 运行

```bash
python app.py
```

浏览器访问 `http://localhost:5000`

## 项目结构

```
├── app.py                # 主应用，路由与业务逻辑
├── auto_fill_order.py    # 自动填写订单核心逻辑
├── parse_order_data.py   # 订单数据解析
├── config.json           # 配置文件（API Key 等）
├── templates/            # HTML 模板
└── static/               # 静态资源
```
