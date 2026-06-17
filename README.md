# 工单自动填写助手

一个基于 Flask + Playwright + Claude AI 的监控设备工单自动化填写系统。

## 核心功能

**AI 智能解析**：粘贴设备信息文本，调用 Claude AI 自动识别并提取企业名称、经纬度、VPN IP、NVR账号密码、通道号、映射端口等字段，无需手动对应。

**验证码截图接口**：自动驱动浏览器打开平台登录页，截取验证码图片并回传前端展示，用户直接在界面输入验证码即可登录，无需切换窗口。

**自动填表提交**：登录成功后，批量读取解析好的订单数据，逐条自动打开工单提交页面、填入所有字段、选择场所类型并点击保存。

**Web 管理界面**：提供 Dashboard（任务状态总览）和 Fill（手动触发填写）页面，通过浏览器操作整个流程。

## 技术栈

- **Flask** — Web 服务
- **Playwright** — 浏览器自动化（登录、截图、填表）
- **Claude API (claude-haiku)** — AI 文本解析，提取结构化字段

## 安装

```bash
pip install flask playwright anthropic
playwright install chromium
```

## 配置

创建或编辑 `config.json`：

```json
{
  "claude_api_key": "your-anthropic-api-key"
}
```

## 启动

```bash
python app.py
```

浏览器访问 `http://localhost:5000`

## 支持字段

自动解析并填写以下工单字段：企业名称、所属街道、签约路数、经度、纬度、设备品牌、映射端口、VPN用户侧IP、通道号、NVR账号、NVR密码、预警接收人。

## 项目结构

```
├── app.py                # 主应用：路由、AI解析接口、验证码截图、自动填表
├── auto_fill_order.py    # Playwright 填表逻辑
├── parse_order_data.py   # 订单文本解析（CSV/制表符分隔）
├── config.json           # API Key 配置
├── templates/            # 前端页面
└── static/               # 静态资源
```
