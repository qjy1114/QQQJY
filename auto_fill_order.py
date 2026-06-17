import argparse
import csv
import io
import json
from pathlib import Path
from typing import Dict, List

from playwright.sync_api import Playwright, sync_playwright

ALL_FIELDS = [
    "区县",
    "企业名称",
    "网格名称",
    "所属街道",
    "客户经理",
    "签约情况",
    "签约路数",
    "客户侧网络配置完成",
    "经度",
    "纬度",
    "设备品牌",
    "映射端口",
    "VPN用户侧IP",
    "通道号",
    "NVR账号",
    "NVR密码",
    "4+X项AI能力",
    "预警接收人",
    "相关交付信息",
]

SELECTED_FIELDS = [
    "企业名称",
    "所属街道",
    "签约路数",
    "经度",
    "纬度",
    "设备品牌",
    "映射端口",
    "VPN用户侧IP",
    "通道号",
    "NVR账号",
    "NVR密码",
    "预警接收人",
]


def infer_delimiter(line: str) -> str:
    if "\t" in line:
        return "\t"
    if "," in line:
        return ","
    if "  " in line:
        return " "
    return " "


def split_row(line: str) -> List[str]:
    line = line.strip()
    if not line:
        return []
    delimiter = infer_delimiter(line)
    reader = csv.reader([line], delimiter=delimiter)
    cells = [item.strip() for item in next(reader)]
    if len(cells) == 1 and delimiter == " ":
        cells = [item for item in line.split() if item]
    return cells


def normalize_cells(cells: List[str], line: str) -> List[str]:
    if len(cells) == len(ALL_FIELDS):
        return cells
    if len(cells) > len(ALL_FIELDS):
        return cells[: len(ALL_FIELDS) - 1] + [" ".join(cells[len(ALL_FIELDS) - 1 :])]
    if len(cells) == len(ALL_FIELDS) - 1:
        return cells + [""]
    raise ValueError(
        f"这一行的字段数量不够：{len(cells)}，预期至少 {len(ALL_FIELDS) - 1}。请检查分隔符或数据格式。\n行内容：{line}"
    )


def parse_rows(text: str) -> List[Dict[str, str]]:
    rows = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        cells = split_row(line)
        if not cells:
            continue
        cells = normalize_cells(cells, line)
        row = {field: cells[idx].strip() for idx, field in enumerate(ALL_FIELDS)}
        row["__line_no__"] = line_no
        rows.append(row)
    return rows


def fill_order_form(page, row: Dict[str, str], place_type: str = "其他工矿企业") -> None:
    page.fill('#form_item_name', row["企业名称"])
    page.fill('#form_item_address', row["企业名称"])
    page.fill('input[codefield="longitude"]', row["经度"])
    page.fill('input[codefield="latitude"]', row["纬度"])
    page.fill('input[codefield="deviceNum"]', row["签约路数"])
    page.fill('#form_item_ip', row["VPN用户侧IP"])

    page.click('div.ant-select-selector')
    page.wait_for_timeout(300)
    option = page.locator('div.ant-select-item-option-content', has_text=place_type).first()
    if option.count() == 0:
        raise RuntimeError(f'未找到场所类型选项：{place_type}')
    option.click()
    page.wait_for_timeout(300)

    save_button = page.locator('button', has_text='保存').first()
    if save_button.count() == 0:
        save_button = page.locator('button', has_text='保 存').first()
    if save_button.count() == 0:
        raise RuntimeError('未找到保存按钮')
    save_button.click()
    page.wait_for_timeout(1500)


def run(playwright: Playwright, data_rows: List[Dict[str, str]], login_url: str, target_url: str,
        username: str, password: str, captcha: str) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    page.goto(login_url)
    page.fill('input[placeholder="请输入您的用户名"]', username)
    page.fill('input[placeholder="请输入密码"]', password)
    page.fill('input[placeholder="验证码"]', captcha)
    page.click('button:has-text("登 录")')
    page.wait_for_load_state('networkidle')

    for row in data_rows:
        page.goto(target_url)
        page.wait_for_load_state('networkidle')
        fill_order_form(page, row)
        print(f"已处理行 {row['__line_no__']}：{row['企业名称']}")

    browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='自动填写订单提交页面。')
    parser.add_argument('--file', help='输入数据文件路径', type=str, required=True)
    parser.add_argument('--login-url', help='登录地址', default='http://36.212.5.102:30869/#/login?redirect=/order/order/submit')
    parser.add_argument('--target-url', help='订单提交地址', default='http://36.212.5.102:30869/#/order/order/submit')
    parser.add_argument('--username', help='登录用户名', required=True)
    parser.add_argument('--password', help='登录密码', required=True)
    parser.add_argument('--captcha', help='登录验证码', required=True)
    parser.add_argument('--place-type', help='场所类型', default='其他工矿企业')
    parser.add_argument('--attach', help='连接到已启动的 Chromium via CDP（避免新登录）', action='store_true')
    parser.add_argument('--cdp-url', help='CDP 端点地址，默认 http://127.0.0.1:9222', default='http://127.0.0.1:9222')
    args = parser.parse_args()

    raw_text = Path(args.file).read_text(encoding='utf-8')
    rows = parse_rows(raw_text)
    if not rows:
        raise RuntimeError('未解析到任何数据行')

    # 如果用户要求 attach，则尝试连接到已启动并开启 remote-debugging 的 Chromium 实例
    if args.attach:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(args.cdp_url)
            # 尝试找到已有 tab，否则在该浏览器实例中新开 tab
            page = None
            for ctx in browser.contexts:
                for pg in ctx.pages:
                    try:
                        if args.target_url.split('#')[-1] in pg.url or args.target_url in pg.url:
                            page = pg
                            break
                    except Exception:
                        continue
                if page:
                    break

            if not page:
                page = browser.new_page()

            results = []
            for row in rows:
                try:
                    page.goto(args.target_url)
                    page.wait_for_load_state('networkidle')
                    # 直接填写
                    page.fill('#form_item_name', row['企业名称'])
                    page.fill('#form_item_address', row['企业名称'])
                    page.fill('input[codefield="longitude"]', row['经度'])
                    page.fill('input[codefield="latitude"]', row['纬度'])
                    page.fill('input[codefield="deviceNum"]', row['签约路数'])
                    page.fill('#form_item_ip', row['VPN用户侧IP'])
                    page.click('div.ant-select-selector')
                    try:
                        page.wait_for_selector('div.ant-select-item-option-content', timeout=3000)
                        opt = page.locator('div.ant-select-item-option-content', has_text=args.place_type).first()
                        if opt.count() > 0:
                            opt.click()
                    except Exception:
                        pass

                    save_btn = page.locator('button', has_text='保存').first()
                    if save_btn.count() == 0:
                        save_btn = page.locator('button', has_text='保 存').first()
                    if save_btn.count() > 0:
                        save_btn.click()
                        page.wait_for_timeout(1200)
                        results.append({'line': row['__line_no__'], 'enterprise': row['企业名称'], 'success': True})
                    else:
                        results.append({'line': row['__line_no__'], 'enterprise': row['企业名称'], 'success': False, 'error': '未找到保存按钮'})
                except Exception as exc:
                    results.append({'line': row['__line_no__'], 'enterprise': row['企业名称'], 'success': False, 'error': str(exc)})

            print(json.dumps({'results': results}, ensure_ascii=False, indent=2))
            return

    # 默认行为：playwright 启动浏览器并登录一次处理所有记录
    with sync_playwright() as playwright:
        run(playwright, rows, args.login_url, args.target_url, args.username, args.password, args.captcha)


if __name__ == '__main__':
    main()
