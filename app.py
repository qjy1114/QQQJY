from flask import Flask, jsonify, redirect, render_template, request
from pathlib import Path
import json
import os
import time
import urllib.parse
import traceback

from parse_order_data import parse_rows, select_fields
from playwright.sync_api import sync_playwright

DATA_FILE = Path(__file__).with_name("tasks.json")
CONFIG_FILE = Path(__file__).with_name("config.json")


def _load_api_key():
    """Load Claude API key and base URL from env or config file."""
    key = os.environ.get('ANTHROPIC_AUTH_TOKEN', '') or os.environ.get('ANTHROPIC_API_KEY', '')
    base_url = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com')
    if key:
        return key, base_url
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            key = cfg.get('claude_api_key', '') or cfg.get('ANTHROPIC_API_KEY', '')
            base_url = cfg.get('anthropic_base_url', base_url)
            if key:
                return key, base_url
        except Exception:
            pass
    return '', base_url
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# ---------------------------------------------------------------------------
#  Platform Session State
# ---------------------------------------------------------------------------

PLATFORM_SESSION = {
    "playwright": None,
    "browser": None,
    "context": None,
    "page": None,
    "logged_in": False,
    "username": None,
    "base_url": "http://36.212.5.102:30869",
    "auth_headers": None,
    "auth_headers_ts": 0,
}

AUTH_HEADER_CACHE_TTL = 1800  # 30 minutes


def load_tasks():
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_tasks(tasks):
    DATA_FILE.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


@app.route("/")
def index():
    return redirect('/login')


@app.route("/fill")
def fill_page():
    if not PLATFORM_SESSION['logged_in']:
        return redirect('/login')
    return render_template('fill.html')


@app.route('/dashboard')
def dashboard_page():
    if not PLATFORM_SESSION['logged_in']:
        return redirect('/login')
    return render_template('dashboard.html')


@app.route('/logout')
def logout_page():
    _reset_platform_session()
    return redirect('/login')


# ---------------------------------------------------------------------------
#  Browser lifecycle management
# ---------------------------------------------------------------------------

def _cleanup_browser():
    """Safely close all browser resources."""
    for key in ["page", "context", "browser"]:
        obj = PLATFORM_SESSION.get(key)
        if obj:
            try:
                if key == "page" and not obj.is_closed():
                    obj.close()
                elif key == "context":
                    obj.close()
                elif key == "browser" and obj.is_connected():
                    obj.close()
            except Exception:
                pass
        PLATFORM_SESSION[key] = None


def get_platform_playwright():
    """Get or create the Playwright instance."""
    if PLATFORM_SESSION["playwright"] is None:
        PLATFORM_SESSION["playwright"] = sync_playwright().start()
    return PLATFORM_SESSION["playwright"]


def get_platform_page():
    """Get or create a browser page pointed at the platform.

    Initialises browser -> context -> page lazily.
    If the existing browser has crashed / been closed, re-creates it.
    """
    playwright = get_platform_playwright()

    # ---- browser ----
    browser = PLATFORM_SESSION.get("browser")
    if browser is None or not browser.is_connected():
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        PLATFORM_SESSION["browser"] = None
        PLATFORM_SESSION["context"] = None
        PLATFORM_SESSION["page"] = None

        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=ChromeWhatsNewUI",
                "--window-size=1920,1080",
                "--disable-dev-shm-usage",
            ],
        )
        PLATFORM_SESSION["browser"] = browser

    # ---- context ----
    context = PLATFORM_SESSION.get("context")
    if context is None:
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            )
        except Exception:
            # Browser might have died; retry once
            _cleanup_browser()
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--window-size=1920,1080",
                ],
            )
            PLATFORM_SESSION["browser"] = browser
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            )
        PLATFORM_SESSION["context"] = context

    # ---- page ----
    page = PLATFORM_SESSION.get("page")
    if page is None or page.is_closed():
        try:
            page = context.new_page()
        except Exception:
            _cleanup_browser()
            return get_platform_page()
        PLATFORM_SESSION["page"] = page

    return page


def _reset_platform_session():
    """Reset login state but keep browser alive for reuse."""
    PLATFORM_SESSION["logged_in"] = False
    PLATFORM_SESSION["username"] = None
    PLATFORM_SESSION["auth_headers"] = None
    PLATFORM_SESSION["auth_headers_ts"] = 0


def install_platform_header_capture(page):
    """Inject JS to intercept XHR/fetch headers for API calls (kept for future use)."""
    try:
        page.add_init_script(
            '''() => {
                if (window.__captureApiHeadersPatched) {
                    return;
                }
                window.__captureApiHeadersPatched = true;
                window.__capturedApiHeaders = [];
                const originalOpen = XMLHttpRequest.prototype.open;
                const originalSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
                XMLHttpRequest.prototype.open = function (method, url, ...args) {
                    this.__xhrUrl = url;
                    return originalOpen.call(this, method, url, ...args);
                };
                XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
                    if (this.__xhrUrl && this.__xhrUrl.includes('/api/')) {
                        window.__capturedApiHeaders.push({ url: this.__xhrUrl, name, value });
                    }
                    return originalSetRequestHeader.call(this, name, value);
                };
                const originalFetch = window.fetch;
                window.fetch = function (input, init = {}) {
                    const url = typeof input === 'string' ? input : input.url;
                    if (url && url.includes('/api/')) {
                        const headers = init.headers || {};
                        if (headers instanceof Headers) {
                            for (const [name, value] of headers.entries()) {
                                window.__capturedApiHeaders.push({ url, name, value });
                            }
                        } else if (Array.isArray(headers)) {
                            headers.forEach(([name, value]) => {
                                window.__capturedApiHeaders.push({ url, name, value });
                            });
                        } else {
                            for (const name in headers) {
                                if (headers.hasOwnProperty(name)) {
                                    window.__capturedApiHeaders.push({ url, name, value: headers[name] });
                                }
                            }
                        }
                    }
                    return originalFetch.call(this, input, init);
                };
            }'''
        )
    except Exception:
        pass


def collect_platform_auth_headers(page):
    """Extract authentication headers from the platform page.

    Uses two strategies:
      1) Read tokens from localStorage / sessionStorage (most reliable).
      2) Intercept outgoing API requests as a fallback.
    """
    normalized = {}

    # ---- Strategy 1: localStorage / sessionStorage ----
    try:
        page.goto(f"{PLATFORM_SESSION['base_url']}/#/device/list", wait_until='domcontentloaded')
        page.wait_for_timeout(2000)

        storage_data = page.evaluate('''() => {
            const result = {};
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                result[k] = localStorage.getItem(k);
            }
            for (let i = 0; i < sessionStorage.length; i++) {
                const k = sessionStorage.key(i);
                result['session_' + k] = sessionStorage.getItem(k);
            }
            return result;
        }''')

        # Map storage keys → normalized header names
        for key, value in storage_data.items():
            kl = key.lower()
            if kl == 'authorization':
                normalized['Authorization'] = value
            elif kl in ('token', 'access_token', 'accesstoken', 'jwt', 'jwttoken',
                        'auth_token', 'bearer_token'):
                if not normalized.get('Token'):
                    normalized['Token'] = value
            elif 'tenant' in kl:
                if not normalized.get('TenantId'):
                    normalized['TenantId'] = value
            elif 'application' in kl or 'appid' in kl:
                if not normalized.get('ApplicationId'):
                    normalized['ApplicationId'] = value
            elif kl == 'path':
                normalized['Path'] = value
            elif 'gray' in kl:
                normalized['gray_version'] = value
            elif 'repeat' in kl or 'alarm' in kl:
                normalized['repeatAlarm'] = value

        # Also look for a base64-encoded Authorization string in storage
        if not normalized.get('Authorization'):
            for key, value in storage_data.items():
                if value and len(value) > 20 and (
                    value.startswith('Basic ') or value.startswith('Bearer ') or
                    ':' in value  # clientId:clientSecret pattern
                ):
                    normalized['Authorization'] = 'Basic ' + value if not value.startswith('Basic ') else value
                    break
    except Exception:
        pass

    # ---- Strategy 2: request interception (fills gaps) ----
    collected = {}

    def on_request(request):
        if '/api/' not in request.url and '/gateway/' not in request.url:
            return
        for name, value in request.headers.items():
            kl = name.lower()
            if kl in ['token', 'authorization', 'tenantid', 'applicationid',
                      'path', 'gray_version', 'repeatalarm']:
                if kl not in collected:
                    collected[kl] = value

    page.on('request', on_request)
    try:
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(2000)
    except Exception:
        pass
    finally:
        page.remove_listener('request', on_request)

    # Merge interception results (only fill keys still missing from storage)
    for kl, value in collected.items():
        if kl == 'token' and not normalized.get('Token'):
            normalized['Token'] = value
        elif kl == 'authorization' and not normalized.get('Authorization'):
            normalized['Authorization'] = value
        elif kl == 'tenantid' and not normalized.get('TenantId'):
            normalized['TenantId'] = value
        elif kl == 'applicationid' and not normalized.get('ApplicationId'):
            normalized['ApplicationId'] = value
        elif kl == 'path' and not normalized.get('Path'):
            normalized['Path'] = value
        elif kl == 'gray_version' and not normalized.get('gray_version'):
            normalized['gray_version'] = value
        elif kl == 'repeatalarm' and not normalized.get('repeatAlarm'):
            normalized['repeatAlarm'] = value

    # Fill defaults
    if not normalized.get('Path'):
        normalized['Path'] = '/'
    if not normalized.get('gray_version'):
        normalized['gray_version'] = 'zuihou'
    if not normalized.get('repeatAlarm'):
        normalized['repeatAlarm'] = 'true'

    return normalized


def get_cached_auth_headers(page):
    """Return cached auth headers if still fresh, otherwise re-collect from the platform."""
    now = time.time()
    cached = PLATFORM_SESSION.get("auth_headers")
    if cached and cached.get('Token') and cached.get('Authorization'):
        if (now - PLATFORM_SESSION.get("auth_headers_ts", 0)) < AUTH_HEADER_CACHE_TTL:
            return cached
        # Cache expired, clear it
        PLATFORM_SESSION["auth_headers"] = None

    headers = collect_platform_auth_headers(page)
    if headers.get('Token') and headers.get('Authorization'):
        PLATFORM_SESSION["auth_headers"] = headers
        PLATFORM_SESSION["auth_headers_ts"] = now
    else:
        # Even partial headers might be useful; still cache briefly
        print(f"[WARN] 认证头不完整，只采集到: {list(headers.keys())}")
        PLATFORM_SESSION["auth_headers"] = headers
        PLATFORM_SESSION["auth_headers_ts"] = now
    return headers


def build_auth_headers(auth_dict):
    """Build the complete headers dict for platform API calls."""
    return {
        'Content-Type': 'application/json;charset=UTF-8',
        'Token': auth_dict.get('Token', ''),
        'TenantId': auth_dict.get('TenantId', ''),
        'ApplicationId': auth_dict.get('ApplicationId', ''),
        'Authorization': auth_dict.get('Authorization', ''),
        'Path': auth_dict.get('Path', '/'),
        'gray_version': str(auth_dict.get('gray_version', 'zuihou')),
        'repeatAlarm': str(auth_dict.get('repeatAlarm', 'true')),
    }


# ---------------------------------------------------------------------------
#  AI-powered device info parser (DeepSeek V4 Flash)
# ---------------------------------------------------------------------------

@app.route("/api/parse_device_info", methods=["POST"])
def api_parse_device_info():
    payload = request.get_json(silent=True) or {}
    raw_text = payload.get('rawText', '').strip()
    if not raw_text:
        return jsonify({'error': 'rawText is required'}), 400

    api_key, base_url = _load_api_key()
    if not api_key:
        return jsonify({'error': '请在 config.json 中设置 claude_api_key'}), 500

    system_prompt = (
        '你是一个文本结构化工具，专门处理监控设备工单录入系统的表单自动填写任务。\n'
        '从用户提供的工单文本中识别并提取以下字段，严格只输出一个合法JSON对象，不输出任何解释或其他内容。\n\n'
        '字段说明：\n'
        '- ip：文本中唯一的IP地址，标注为VPN/IP/地址的均是\n'
        '- port：逗号分隔的纯数字端口，按优先级筛选：\n'
        '    优先级1（海康SDK）：8000-8009范围\n'
        '    优先级2（大华SDK）：37777-37779范围\n'
        '    优先级3（RTSP）：554-559范围\n'
        '    规则：有优先级1就只取优先级1，有优先级2就只取优先级2，依此类推；80/443/8080等无关端口忽略\n'
        '    范围写法如"8001-8005"表示8001,8002,8003,8004,8005五个端口\n'
        '- channel：逗号分隔纯数字，去掉D/Ch前缀。\n'
        '    重要规则：先统计筛选后的port数量N和通道数量M：\n'
        '    若M==N（1:1对应）→ port保持N个，channel填"1"\n'
        '    若M>N（通道多于端口）→ port只保留第1个，channel填所有M个通道\n'
        '    若M<N（端口多于通道）→ port保持N个，channel填"1"\n'
        '- brand："海康"/"大华"/"tp"/"萤石"/"杂牌"\n'
        '- username：登录账号，无则填"admin"\n'
        '- password：登录密码，注意密码后可能没有冒号直接跟密码值\n'
        '- name：单位/企业名称\n'
        '- phone：电话号码，无则填空字符串\n\n'
        '只输出JSON，不输出任何其他内容。'
    )

    try:
        import urllib.request
        import urllib.error

        req_body = json.dumps({
            'model': 'claude-haiku-4-5-20251001',
            'max_tokens': 300,
            'system': system_prompt,
            'messages': [
                {'role': 'user', 'content': raw_text},
            ],
        }).encode('utf-8')

        req = urllib.request.Request(
            f'{base_url.rstrip("/")}/v1/messages',
            data=req_body,
            headers={
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
            },
            method='POST',
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        response_text = data['content'][0]['text'].strip()
        # 去掉 <thinking>...</thinking> 块
        import re
        response_text = re.sub(r'<thinking>.*?</thinking>', '', response_text, flags=re.DOTALL).strip()
        # 去掉 ```json ... ``` 围栏
        if response_text.startswith('```'):
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
        result = json.loads(response_text)
        return jsonify(result)

    except json.JSONDecodeError:
        return jsonify({'error': 'AI 返回格式异常，请重试', 'raw': response_text}), 500
    except urllib.error.HTTPError as err:
        traceback.print_exc()
        return jsonify({'error': f'Claude API 错误 {err.code}'}), 500
    except Exception as err:
        traceback.print_exc()
        return jsonify({'error': f'AI 解析失败: {str(err)}'}), 500


@app.route("/api/parse", methods=["POST"])
def parse_data():
    payload = request.get_json(silent=True) or {}
    raw_text = payload.get('rawText', '').strip()
    if not raw_text:
        return jsonify({'error': 'rawText is required'}), 400
    try:
        rows = parse_rows(raw_text)
        selected = select_fields(rows)
        return jsonify({'rows': selected, 'count': len(selected)})
    except Exception as err:
        return jsonify({'error': str(err)}), 400


# ---------------------------------------------------------------------------
#  Login & Session
# ---------------------------------------------------------------------------

@app.route("/login")
def login_page():
    return render_template('login.html')


@app.route("/api/login", methods=["POST"])
def api_login():
    """Log into the external platform via Playwright.

    Expects JSON body: { username, password, captcha }
    On success stores auth headers for subsequent API calls.
    """
    payload = request.get_json(silent=True) or {}
    username = payload.get("username", "").strip()
    password = payload.get("password", "").strip()
    captcha = payload.get("captcha", "").strip()

    if not username or not password or not captcha:
        return jsonify({"error": "用户名、密码和验证码不能为空"}), 400

    try:
        page = get_platform_page()
        login_url = f"{PLATFORM_SESSION['base_url']}/#/login?redirect=/order/order/submit"

        # Navigate to login page
        page.goto(login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Wait for the login form to be ready
        try:
            page.wait_for_selector('input[placeholder*="用户名"]', timeout=10000)
            page.wait_for_selector('input[placeholder*="密码"]', timeout=5000)
            page.wait_for_selector('input[placeholder*="验证码"]', timeout=5000)
        except Exception:
            return jsonify({"error": "登录页面加载超时，请确认平台地址是否正确"}), 500

        # Fill in credentials
        page.fill('input[placeholder*="用户名"]', username)
        page.fill('input[placeholder*="密码"]', password)
        page.fill('input[placeholder*="验证码"]', captcha)

        # Click login button (try both spacing variants)
        page.click('button:has-text("登 录"), button:has-text("登录")')

        # Wait for navigation away from login page
        login_success = False
        error_text = ""
        try:
            page.wait_for_function(
                '''() => {
                    const url = window.location.href;
                    return !url.includes("/login") && !url.includes("login?");
                }''',
                timeout=15000,
            )
            login_success = True
        except Exception:
            # Check for error messages on the page
            try:
                error_text = page.evaluate('''() => {
                    const selectors = [
                        ".ant-message-error", ".ant-message-notice",
                        ".el-message--error", ".el-message",
                        ".ant-alert-error", ".ant-alert-message",
                        '[class*="error"]', '[class*="message"]',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) return el.textContent || "";
                    }
                    return "";
                }''')
            except Exception:
                pass

        if not login_success:
            if error_text:
                return jsonify({"error": f"登录失败: {error_text.strip()}"}), 400
            return jsonify({
                "error": "登录失败，用户名、密码或验证码不正确",
                "needRefresh": True,
            }), 400

        # Login succeeded -- update session
        PLATFORM_SESSION["logged_in"] = True
        PLATFORM_SESSION["username"] = username

        # Collect auth headers for subsequent API calls
        try:
            ah = collect_platform_auth_headers(page)
            if ah.get("Token") and ah.get("Authorization"):
                PLATFORM_SESSION["auth_headers"] = ah
                PLATFORM_SESSION["auth_headers_ts"] = time.time()
        except Exception:
            pass

        return jsonify({"success": True, "username": username})

    except Exception as err:
        traceback.print_exc()
        return jsonify({"error": f"登录异常: {str(err)}"}), 500


@app.route("/api/login_cdp", methods=["POST"])
def api_login_cdp():
    """Connect to an already-open browser via CDP and reuse its platform session.

    Use this when you've already logged into the platform in a Chrome window
    that was launched with --remote-debugging-port=9222.
    """
    payload = request.get_json(silent=True) or {}
    cdp_url = (payload.get('cdpUrl') or payload.get('cdp_url') or '').strip()
    if not cdp_url:
        cdp_url = 'http://127.0.0.1:9222'

    try:
        playwright = get_platform_playwright()
        browser = playwright.chromium.connect_over_cdp(cdp_url)

        # Find a page already on the platform
        target_page = None
        for context in browser.contexts:
            for page in context.pages:
                try:
                    if PLATFORM_SESSION['base_url'] in (page.url or ''):
                        target_page = page
                        break
                except Exception:
                    continue
            if target_page:
                break

        if not target_page:
            # Fall back to any open page
            for context in browser.contexts:
                if context.pages:
                    target_page = context.pages[0]
                    break

        if not target_page:
            try:
                target_page = browser.new_page()
                target_page.goto(PLATFORM_SESSION['base_url'])
                target_page.wait_for_load_state('networkidle')
            except Exception as e:
                return jsonify({'error': f'无法连接到平台页面: {str(e)}'}), 400

        # Verify the browser already has an active platform session
        login_inputs = target_page.locator('input[placeholder="请输入您的用户名"]').count()
        if login_inputs > 0:
            return jsonify({'error': '浏览器中未检测到已登录的平台会话，请先在浏览器中登录平台'}), 400

        # Collect auth headers from the attached browser
        auth_headers = collect_platform_auth_headers(target_page)
        if not auth_headers.get('Token') or not auth_headers.get('Authorization'):
            return jsonify({'error': '无法从浏览器获取认证信息，请确认平台已登录'}), 401

        # Wire the attached browser into the platform session
        PLATFORM_SESSION['browser'] = browser
        PLATFORM_SESSION['context'] = target_page.context
        PLATFORM_SESSION['page'] = target_page
        PLATFORM_SESSION['logged_in'] = True
        PLATFORM_SESSION['username'] = 'CDP用户'
        PLATFORM_SESSION['auth_headers'] = auth_headers
        PLATFORM_SESSION['auth_headers_ts'] = time.time()

        return jsonify({'success': True, 'username': 'CDP用户', 'cdp': True})
    except Exception as err:
        traceback.print_exc()
        return jsonify({'error': f'CDP连接失败: {str(err)}'}), 500


@app.route("/api/captcha", methods=["GET"])
def api_captcha():
    import base64
    try:
        page = get_platform_page()
        login_url = f"{PLATFORM_SESSION['base_url']}/#/login?redirect=/order/order/submit"

        page.goto(login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # 优先截图验证码元素，与平台显示完全一致
        captcha_selectors = [
            ".captcha-col img",
            ".captcha-img",
            "img.captcha",
            'input[placeholder*="验证码"] ~ img',
        ]
        for sel in captcha_selectors:
            el = page.query_selector(sel)
            if el:
                img_bytes = el.screenshot()
                b64 = base64.b64encode(img_bytes).decode("ascii")
                return jsonify({"src": f"data:image/png;base64,{b64}"})

        # 回退：找验证码输入框旁边的 img 元素并截图
        captcha_input = page.query_selector('input[placeholder*="验证码"]')
        if captcha_input:
            el = captcha_input.evaluate_handle('''input => {
                let el = input.parentElement;
                for (let i = 0; i < 8 && el; i++) {
                    const img = el.querySelector("img");
                    if (img) return img;
                    el = el.parentElement;
                }
                return null;
            }''')
            if el:
                img_bytes = el.as_element().screenshot()
                b64 = base64.b64encode(img_bytes).decode("ascii")
                return jsonify({"src": f"data:image/png;base64,{b64}"})

        return jsonify({"error": "未找到验证码图片，请检查平台登录页面是否正常"}), 500

    except Exception as err:
        traceback.print_exc()
        return jsonify({"error": f"获取验证码失败: {str(err)}"}), 500

@app.route("/api/session_status", methods=["GET"])
def api_session_status():
    return jsonify({
        'logged_in': PLATFORM_SESSION['logged_in'],
        'username': PLATFORM_SESSION['username'],
        'base_url': PLATFORM_SESSION['base_url'],
    })


# ---------------------------------------------------------------------------
#  Helpers: image extraction from platform API responses
# ---------------------------------------------------------------------------

def _looks_like_base64_image(s):
    """Return True if *s* looks like a base64-encoded image (no data: prefix)."""
    if not isinstance(s, str) or len(s) < 64:
        return False
    # Common base64 image patterns — starts with typical image magic bytes in b64
    image_prefixes = [
        '/9j/',   # JPEG
        'iVBOR',  # PNG
        'R0lGOD', # GIF
        'UklGR',  # WEBP
        'Qk',     # BMP (shorter, but we already check len >= 64)
    ]
    for pfx in image_prefixes:
        if s.startswith(pfx):
            return True
    return False


def _make_data_uri(b64_string):
    """Turn a raw base64 string into a proper data: URI."""
    if b64_string.startswith('/9j/'):
        return 'data:image/jpeg;base64,' + b64_string
    if b64_string.startswith('iVBOR'):
        return 'data:image/png;base64,' + b64_string
    if b64_string.startswith('R0lGOD'):
        return 'data:image/gif;base64,' + b64_string
    if b64_string.startswith('UklGR'):
        return 'data:image/webp;base64,' + b64_string
    return 'data:image/png;base64,' + b64_string


def _extract_image_from_response(data):
    """Recursively search the API response for an image (URL or base64).

    Returns a string suitable for an <img src> attribute, or None.
    """
    if data is None:
        return None

    # 1) data is a plain string
    if isinstance(data, str):
        data_stripped = data.strip()
        if not data_stripped:
            return None
        # Already a full data URI
        if data_stripped.startswith('data:image/'):
            return data_stripped
        # Looks like a URL
        if data_stripped.startswith('http://') or data_stripped.startswith('https://'):
            return data_stripped
        # Looks like raw base64 — convert to data URI
        if _looks_like_base64_image(data_stripped):
            return _make_data_uri(data_stripped)
        # Could be a relative URL path
        if data_stripped.startswith('/'):
            return PLATFORM_SESSION['base_url'] + data_stripped
        # Unknown string — assume base64
        if len(data_stripped) > 100:
            return _make_data_uri(data_stripped)
        return None

    # 2) data is a dict — search common keys
    if isinstance(data, dict):
        # Common keys that may hold the image
        image_keys = ['data', 'image', 'imageUrl', 'imageData', 'url',
                      'imgUrl', 'img', 'captureImage', 'snapImage', 'pic']
        for key in image_keys:
            if key in data:
                result = _extract_image_from_response(data[key])
                if result:
                    return result
        # Fallback: scan every string value in the dict
        for key, value in data.items():
            if key in image_keys:
                continue  # already checked
            result = _extract_image_from_response(value)
            if result:
                return result
        return None

    # 3) data is a list — check each element
    if isinstance(data, list):
        for item in data:
            result = _extract_image_from_response(item)
            if result:
                return result
        return None

    return None


def _parse_range(value):
    """Parse a range string like '8001-8004' or '1,4,6,7,10' into a list of strings.

    Examples:
        '8001-8004'          -> ['8001','8002','8003','8004']
        '1,4,6,7,10'         -> ['1','4','6','7','10']
        '8001-8004,8006'     -> ['8001','8002','8003','8004','8006']
        '80'                 -> ['80']
    """
    if not value or not str(value).strip():
        return []
    value = str(value).strip()
    result = []
    for part in value.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                start_s, end_s = part.split('-', 1)
                start = int(start_s.strip())
                end = int(end_s.strip())
                if start <= end:
                    for i in range(start, end + 1):
                        result.append(str(i))
                else:
                    result.append(part)
            except ValueError:
                result.append(part)
        else:
            result.append(part)
    return result

# ---------------------------------------------------------------------------
#  IP/Port connectivity test
# ---------------------------------------------------------------------------

@app.route('/api/check_telnet', methods=['POST'])
def api_check_telnet():
    """Test IP + port connectivity via the platform telnet check API."""
    payload = request.get_json(silent=True) or {}
    ip = payload.get('ip', '').strip()
    port = payload.get('port', '').strip()
    if not ip or not port:
        return jsonify({'error': 'ip and port are required'}), 400
    if not PLATFORM_SESSION.get('logged_in'):
        return jsonify({'error': '请先登录平台'}), 400

    try:
        page = get_platform_page()
        auth_headers = get_cached_auth_headers(page)
        headers = build_auth_headers(auth_headers)

        import hashlib
        device_id = 'D' + hashlib.md5(ip.encode()).hexdigest()[:12]
        result = page.evaluate(
            '''async ({body, headers}) => {
                const response = await fetch('/api/protocol/v1/check/telnet/body', {
                    method: 'POST',
                    credentials: 'include',
                    headers,
                    body: JSON.stringify(body),
                });
                const text = await response.text();
                let data = text;
                try { data = JSON.parse(text); } catch (e) {}
                return { status: response.status, ok: response.ok, data };
            }''',
            {'body': {'deviceId': device_id, 'ip': ip, 'port': port},
             'headers': headers},
        )

        if result.get('ok'):
            resp_data = result.get('data', {})
            reachable = resp_data.get('data') if isinstance(resp_data, dict) else False
            return jsonify({'reachable': bool(reachable), 'msg': resp_data.get('msg', '') if isinstance(resp_data, dict) else ''})
        return jsonify({'reachable': False, 'msg': '检测请求失败'})
    except Exception as err:
        traceback.print_exc()
        return jsonify({'error': str(err)}), 500

# ---------------------------------------------------------------------------
#  Capture Validate
# ---------------------------------------------------------------------------

@app.route('/api/capture_validate', methods=['POST'])
def api_capture_validate():
    payload = request.get_json(silent=True) or {}
    print(f"[DEBUG] 收到请求 payload: {payload}")

    # Determine whether this is a stream capture request
    mode = payload.get('mode', 'direct')
    is_stream = mode == 'stream' or bool(payload.get('stream', '').strip())

    # Build the required-fields list dynamically
    required_fields = ['ip', 'port', 'username', 'password', 'channel', 'captureType']
    if is_stream:
        required_fields.append('stream')

    missing = [field for field in required_fields if not payload.get(field)]
    if missing:
        return jsonify({'error': f"缺少参数：{', '.join(missing)}"}), 400

    if not PLATFORM_SESSION['logged_in']:
        return jsonify({'error': '请先登录平台'}), 400

    try:
        page = get_platform_page()
        # Use cached auth headers (avoids re-navigating every time)
        auth_headers = get_cached_auth_headers(page)

        if not auth_headers.get('Token') or not auth_headers.get('Authorization'):
            missing_parts = []
            if not auth_headers.get('Token'):
                missing_parts.append('Token')
            if not auth_headers.get('Authorization'):
                missing_parts.append('Authorization')
            return jsonify({
                'error': f'无法获取平台认证头（缺少: {", ".join(missing_parts)}），请退出重新登录。',
                'debug_headers': list(auth_headers.keys()),
            }), 401

        headers = build_auth_headers(auth_headers)

        # Build the API request body
        ct = payload.get('captureType', '')
        # Map stream-format keys to platform API captureType values
        # Direct: CAPTURE_SERVICE_xxx_SDK_FILE / CAPTURE_SERVICE_xxx_SDK
        # Stream: all use CAPTURE_SERVICE_HIKVISION_SDK_PREVIEW
        if ct in ('hikvision_stream', 'dahua_stream', 'ezviz_stream', 'generic_stream', 'tp_nvr_stream', 'tp_ipc_stream', 'huawei_stream', 'uniview_stream'):
            ct = 'CAPTURE_SERVICE_HIKVISION_SDK_PREVIEW'

        api_body = {
            'ip': payload['ip'],
            'port': payload['port'],
            'username': payload['username'],
            'password': payload['password'],
            'channel': payload['channel'],
            'captureType': ct,
        }
        if is_stream:
            api_body['stream'] = urllib.parse.unquote(payload['stream'])

        result = page.evaluate(
            '''async ({body, headers}) => {
                const url = '/api/protocol/v1/capture/validate';
                const response = await fetch(url, {
                    method: 'POST',
                    credentials: 'include',
                    headers,
                    body: JSON.stringify(body),
                });
                const text = await response.text();
                let data = text;
                try { data = JSON.parse(text); } catch (e) {}
                return {
                    status: response.status,
                    ok: response.ok,
                    data,
                };
            }''',
            {'body': api_body, 'headers': headers},
        )

        if not result.get('ok'):
            return jsonify({'error': '抓图校验接口调用失败', 'response': result.get('data')}), result.get('status', 500)

        response_data = result.get('data')
        image_src = _extract_image_from_response(response_data)
        return jsonify({
            'success': True,
            'response': response_data,
            'imageUrl': image_src,
        })
    except Exception as err:
        traceback.print_exc()
        return jsonify({'error': str(err)}), 500


# ---------------------------------------------------------------------------
#  Batch Capture Validate
# ---------------------------------------------------------------------------

@app.route('/api/capture_validate_batch', methods=['POST'])
def api_capture_validate_batch():
    """Batch version: port and channel accept range syntax like '8001-8004' or '1,4,6'."""
    payload = request.get_json(silent=True) or {}

    mode = payload.get('mode', 'direct')
    is_stream = mode == 'stream' or bool(payload.get('stream', '').strip())

    # Expand port and channel ranges
    ports = _parse_range(payload.get('port', ''))
    channels = _parse_range(payload.get('channel', ''))

    if not ports:
        return jsonify({'error': 'port 必须提供有效的值或范围'}), 400
    if not channels:
        return jsonify({'error': 'channel 必须提供有效的值或范围'}), 400

    # Validate other required fields
    required_fields = ['ip', 'username', 'password', 'captureType']
    if is_stream:
        required_fields.append('stream')
    missing = [f for f in required_fields if not payload.get(f)]
    if missing:
        return jsonify({'error': f"缺少参数：{', '.join(missing)}"}), 400

    if not PLATFORM_SESSION['logged_in']:
        return jsonify({'error': '请先登录平台'}), 400

    try:
        page = get_platform_page()
        auth_headers = get_cached_auth_headers(page)

        if not auth_headers.get('Token') or not auth_headers.get('Authorization'):
            mp = [h for h in ['Token', 'Authorization'] if not auth_headers.get(h)]
            return jsonify({'error': f'无法获取平台认证头（缺少: {", ".join(mp)}），请退出重新登录。'}), 401

        headers = build_auth_headers(auth_headers)

        results = []

        for port in ports:
            for channel in channels:
                # Map stream-format keys back to platform API captureType values
                batch_ct = payload.get('captureType', '')
                if batch_ct in ('hikvision_stream', 'dahua_stream', 'ezviz_stream', 'generic_stream', 'tp_stream', 'huawei_stream', 'uniview_stream'):
                    batch_ct = 'CAPTURE_SERVICE_HIKVISION_SDK_PREVIEW'

                api_body = {
                    'ip': payload['ip'],
                    'port': port,
                    'username': payload['username'],
                    'password': payload['password'],
                    'channel': channel,
                    'captureType': batch_ct,
                }
                if is_stream:
                    api_body['stream'] = urllib.parse.unquote(payload['stream'])

                try:
                    result = page.evaluate(
                        '''async ({body, headers}) => {
                            const url = '/api/protocol/v1/capture/validate';
                            const response = await fetch(url, {
                                method: 'POST',
                                credentials: 'include',
                                headers,
                                body: JSON.stringify(body),
                            });
                            const text = await response.text();
                            let data = text;
                            try { data = JSON.parse(text); } catch (e) {}
                            return {
                                status: response.status,
                                ok: response.ok,
                                data,
                            };
                        }''',
                        {'body': api_body, 'headers': headers},
                    )

                    image_src = None
                    error_msg = None
                    if result.get('ok'):
                        image_src = _extract_image_from_response(result.get('data'))
                        if not image_src:
                            error_msg = '接口返回成功但未提取到图片'
                    else:
                        resp_data = result.get('data', {})
                        if isinstance(resp_data, dict):
                            error_msg = resp_data.get('msg') or resp_data.get('message') or str(resp_data)
                        else:
                            error_msg = str(resp_data)

                    results.append({
                        'port': port,
                        'channel': channel,
                        'success': result.get('ok', False),
                        'imageUrl': image_src,
                        'error': error_msg,
                        'response': result.get('data') if not result.get('ok') else None,
                    })
                except Exception as inner_err:
                    results.append({
                        'port': port,
                        'channel': channel,
                        'success': False,
                        'imageUrl': None,
                        'error': str(inner_err),
                        'response': None,
                    })

        success_count = sum(1 for r in results if r['success'])
        return jsonify({
            'results': results,
            'total': len(results),
            'successCount': success_count,
        })
    except Exception as err:
        traceback.print_exc()
        return jsonify({'error': str(err)}), 500


# ---------------------------------------------------------------------------
#  Generic API Proxy (with auth headers)
# ---------------------------------------------------------------------------

@app.route('/api/proxy', methods=['POST'])
def api_proxy():
    """Forward a request to the platform API, attaching cached auth headers."""
    if not PLATFORM_SESSION.get('logged_in'):
        return jsonify({'error': '请先登录平台'}), 401

    payload = request.get_json(silent=True) or {}
    path = payload.get('path', '').strip()
    method = payload.get('method', 'GET').upper()
    data = payload.get('data', None)
    if not path:
        return jsonify({'error': 'path is required'}), 400

    try:
        page = get_platform_page()
        auth_headers = get_cached_auth_headers(page)
        api_headers = build_auth_headers(auth_headers)

        resp = page.evaluate(
            '''async ({path, method, payload, extraHeaders}) => {
                const init = {
                    method,
                    headers: {
                        'Content-Type': 'application/json',
                        ...extraHeaders,
                    },
                    credentials: 'include',
                };
                if (payload !== null && payload !== undefined) {
                    init.body = JSON.stringify(payload);
                }
                const response = await fetch(path, init);
                const text = await response.text();
                let body = text;
                try { body = JSON.parse(text); } catch (ex) {}
                return {
                    status: response.status,
                    ok: response.ok,
                    url: response.url,
                    body,
                };
            }''',
            {'path': path, 'method': method, 'payload': data, 'extraHeaders': api_headers},
        )
        return jsonify(resp)
    except Exception as err:
        traceback.print_exc()
        return jsonify({'error': str(err)}), 500


# ---------------------------------------------------------------------------
#  Order Fill
# ---------------------------------------------------------------------------

@app.route("/api/fill", methods=["POST"])
def fill_data():
    payload = request.get_json(silent=True) or {}
    raw_text = payload.get('rawText', '').strip()
    username = payload.get('username', '').strip()
    password = payload.get('password', '').strip()
    captcha = payload.get('captcha', '').strip()
    target_url = payload.get('targetUrl', 'http://36.212.5.102:30869/#/order/order/submit').strip()
    attach = bool(payload.get('attach', False))
    cdp_url = (payload.get('cdpUrl') or payload.get('cdp_url') or '').strip()

    if not raw_text:
        return jsonify({'error': 'rawText is required'}), 400
    if not attach and not cdp_url:
        if not username or not password or captcha == '':
            return jsonify({'error': 'Either attach/cdpUrl or username/password/captcha are required'}), 400

    try:
        rows = parse_rows(raw_text)

        def fill_order_form(page, row):
            page.fill('#form_item_name', row['企业名称'])
            page.fill('#form_item_address', row['企业名称'])
            page.fill('input[codefield="longitude"]', row['经度'])
            page.fill('input[codefield="latitude"]', row['纬度'])
            page.fill('input[codefield="deviceNum"]', row['签约路数'])
            page.fill('#form_item_ip', row['VPN用户侧IP'])
            page.click('div.ant-select-selector')
            page.wait_for_selector('div.ant-select-item-option-content', timeout=5000)
            option = page.locator('div.ant-select-item-option-content', has_text='其他工矿企业').first()
            if option.count() == 0:
                raise RuntimeError('未找到场所类型选项：其他工矿企业')
            option.click()
            page.wait_for_timeout(300)
            save_button = page.locator('button', has_text='保存').first()
            if save_button.count() == 0:
                save_button = page.locator('button', has_text='保 存').first()
            if save_button.count() == 0:
                raise RuntimeError('未找到保存按钮')
            save_button.click()
            page.wait_for_timeout(1500)

        results = []
        playwright = get_platform_playwright()
        if attach or cdp_url:
            cdp_endpoint = cdp_url or 'http://127.0.0.1:9222'
            fill_browser = playwright.chromium.connect_over_cdp(cdp_endpoint)
            fill_context = fill_browser.contexts[0] if fill_browser.contexts else fill_browser.new_context()

            fill_page = None
            for p in fill_context.pages:
                try:
                    if p.url and target_url.split('#')[-1] in p.url:
                        fill_page = p
                        break
                except Exception:
                    continue
            if fill_page is None:
                fill_page = fill_context.new_page()

            for row in rows:
                fill_page.goto(target_url)
                fill_page.wait_for_load_state('networkidle')
                try:
                    fill_order_form(fill_page, row)
                    results.append({'line': row['__line_no__'], 'enterprise': row['企业名称'], 'success': True})
                except Exception as exc:
                    results.append({'line': row['__line_no__'], 'enterprise': row['企业名称'], 'success': False, 'error': str(exc)})
            # Do not close fill_browser — user may still be using it

        else:
            fill_browser = playwright.chromium.launch(headless=True)
            fill_context = fill_browser.new_context()
            fill_page = fill_context.new_page()
            fill_page.goto('http://36.212.5.102:30869/#/login?redirect=/order/order/submit')
            fill_page.fill('input[placeholder="请输入您的用户名"]', username)
            fill_page.fill('input[placeholder="请输入密码"]', password)
            fill_page.fill('input[placeholder="验证码"]', captcha)
            fill_page.click('button:has-text("登 录")')
            fill_page.wait_for_load_state('networkidle')

            for row in rows:
                fill_page.goto(target_url)
                fill_page.wait_for_load_state('networkidle')
                try:
                    fill_order_form(fill_page, row)
                    results.append({'line': row['__line_no__'], 'enterprise': row['企业名称'], 'success': True})
                except Exception as exc:
                    results.append({'line': row['__line_no__'], 'enterprise': row['企业名称'], 'success': False, 'error': str(exc)})
            fill_browser.close()
        return jsonify({'results': results})
    except Exception as err:
        traceback.print_exc()
        return jsonify({'error': str(err)}), 500


# ---------------------------------------------------------------------------
#  Tasks (Kanban board — auxiliary feature)
# ---------------------------------------------------------------------------

@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    return jsonify(load_tasks())


@app.route("/api/tasks", methods=["POST"])
def add_task():
    payload = request.get_json(silent=True)
    if not payload or "title" not in payload or not payload["title"].strip():
        return jsonify({"error": "title is required"}), 400

    tasks = load_tasks()
    new_id = max((task["id"] for task in tasks), default=0) + 1
    task = {
        "id": new_id,
        "title": payload["title"].strip(),
        "done": False,
        "status": payload.get("status", "todo") if payload.get("status") in ["todo", "in-progress", "done"] else "todo",
        "priority": payload.get("priority", "medium") if payload.get("priority") in ["low", "medium", "high"] else "medium",
        "dueDate": payload.get("dueDate", "") or "",
        "description": payload.get("description", "") or "",
    }
    tasks.append(task)
    save_tasks(tasks)
    return jsonify(task), 201


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "invalid payload"}), 400

    tasks = load_tasks()
    for task in tasks:
        if task["id"] == task_id:
            if "title" in payload and payload["title"] is not None:
                task["title"] = payload["title"].strip()
            if "done" in payload:
                task["done"] = bool(payload["done"])
            if "status" in payload and payload["status"] in ["todo", "in-progress", "done"]:
                task["status"] = payload["status"]
                task["done"] = payload["status"] == "done"
            if "priority" in payload and payload["priority"] in ["low", "medium", "high"]:
                task["priority"] = payload["priority"]
            if "dueDate" in payload:
                task["dueDate"] = payload["dueDate"] or ""
            if "description" in payload:
                task["description"] = payload["description"] or ""
            save_tasks(tasks)
            return jsonify(task)

    return jsonify({"error": "task not found"}), 404


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    tasks = load_tasks()
    updated = [task for task in tasks if task["id"] != task_id]
    if len(updated) == len(tasks):
        return jsonify({"error": "task not found"}), 404

    save_tasks(updated)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=False, threaded=False, use_reloader=False, port=5000)
