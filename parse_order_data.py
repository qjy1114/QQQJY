import argparse
import csv
import io
import json
from typing import List, Dict

# 原始数据字段顺序
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

# 需要提取的字段
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
    """尝试按制表符优先，若无则按逗号或连续空格分隔。"""
    line = line.strip()
    if not line:
        return []

    delimiter = infer_delimiter(line)
    reader = csv.reader([line], delimiter=delimiter)
    cells = [item.strip() for item in next(reader)]

    # 如果只有一个单元格，说明 csv 分隔失败，尝试简单空白拆分
    if len(cells) == 1 and delimiter == " ":
        cells = [item for item in line.split() if item]

    return cells


def normalize_cells(cells: List[str], line: str) -> List[str]:
    if len(cells) == len(ALL_FIELDS):
        return cells

    if len(cells) > len(ALL_FIELDS):
        # 如果超出字段数量，则把多余部分合并到最后一个字段中
        return cells[: len(ALL_FIELDS) - 1] + [" ".join(cells[len(ALL_FIELDS) - 1 :])]

    if len(cells) == len(ALL_FIELDS) - 1:
        # 只有最后一个可选字段没有提供，则补空
        return cells + [""]

    if len(cells) < len(ALL_FIELDS) - 1:
        raise ValueError(
            f"这一行的字段数量不够：{len(cells)}，预期至少 {len(ALL_FIELDS) - 1}（缺少可选的“相关交付信息”字段也可以）。请检查分隔符或数据格式。\n行内容：{line}"
        )

    return cells


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


def select_fields(parsed_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    result = []
    for row in parsed_rows:
        selected = {field: row.get(field, "") for field in SELECTED_FIELDS}
        result.append(selected)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="解析粘贴数据，并输出指定字段。支持多行输入。"
    )
    parser.add_argument(
        "--file",
        help="从文件读取原始数据，每一行代表一条记录。",
        type=str,
    )
    parser.add_argument(
        "--json",
        help="以 JSON 输出结果（默认）。",
        action="store_true",
    )
    parser.add_argument(
        "--csv",
        help="以 CSV 输出结果。",
        action="store_true",
    )
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            raw_text = f.read()
    else:
        print("请粘贴原始数据，输入完成后按 Ctrl+D (Unix) 或 Ctrl+Z 回车 (Windows)：")
        raw_text = io.TextIOWrapper(io.BufferedReader(io.FileIO(0, mode="r", closefd=False)), encoding="utf-8").read()

    parsed = parse_rows(raw_text)
    selected = select_fields(parsed)

    if args.csv:
        writer = csv.DictWriter(
            io.StringIO(), fieldnames=SELECTED_FIELDS, extrasaction="ignore"
        )
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=SELECTED_FIELDS)
        writer.writeheader()
        writer.writerows(selected)
        print(output.getvalue().strip())
        return

    print(json.dumps(selected, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
