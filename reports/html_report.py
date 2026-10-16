# reports/html_report.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTML 报告生成器

职责划分：
  * 本文件 = 取值 + 拼装（不含任何面向读者的文案）
  * config/report_config.py = 报告里所有文字
  * templates/report_template.html = 报告的结构与样式

想改报告里写什么 -> 改 report_config.py
想改报告长什么样 -> 改 report_template.html
"""

import datetime
import html
import os
import re
from collections import defaultdict
from string import Template

import pandas as pd

from config import (
    BASE_OUTPUT_DIR, PROJECT_ROOT, DEVICE_SNS,
    SUCCESS_KEYWORD, SUCCESS_KEYWORD2,
    MAX_BOOT_TIMEOUT_SECONDS, SLOW_BOOT_THRESHOLD,
    REPORT_TITLE, REPORT_SUBTITLE, TEST_DATE, REPORT_SUBTITLE_LINE,
    REPORT_OUTPUT_FILENAME, FIRMWARE_INFO,
    SECTION_OVERVIEW, SECTION_SUMMARY, SECTION_DEVICES,
    SECTION_FAILURES, SECTION_CONCLUSION, SECTION_ATTACHMENTS,
    LABEL_FIRMWARE, LABEL_TEST_TYPE, LABEL_DEVICE_COUNT, LABEL_TEST_PER_DEVICE,
    LABEL_TOTAL_TESTS, LABEL_TIMEOUT, LABEL_KEYWORDS,
    UNIT_DEVICE, UNIT_TIMES, UNIT_SECONDS_PER_TEST, TEMPLATE_KEYWORDS,
    CARD_LABEL_TOTAL, CARD_LABEL_PASS, CARD_LABEL_FAIL, CARD_LABEL_RATE,
    DEVICE_TABLE_COLUMNS, FAILURE_TABLE_COLUMNS,
    CONCLUSION_LEVELS, CONCLUSION_SUMMARY, CONCLUSION_SUMMARY_NO_ERROR,
    CONCLUSION_HEADING, ADVICE_HEADING,
    ADVICE_SLOW_BOOT, ADVICE_MANY_FAILURES, ADVICE_TIMEOUT_REBOOT,
    ADVICE_SERIAL_ERROR, FIXED_ADVICE,
    ATTACHMENTS, ERROR_NOTICE_TEMPLATE, DATA_SOURCE_NOTE_TEMPLATE,
    REPORT_FOOTER_TEMPLATE,
    MSG_NO_DATA, MSG_DEVICE_OK, MSG_DEVICE_FILE_MISSING, MSG_DEVICE_READ_FAIL,
)
from utils import calc_success_rate, cn_number, safe_format, ensure_utf8_console

TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "templates", "report_template.html")

# 结果文件夹命名：SN_<序列号>_<年月日>_<时分秒>
_FOLDER_RE = re.compile(r"^SN_(?P<sn>.+)_(?P<ts>\d{8}_\d{6})$")

# 状态徽章样式类，按 CONCLUSION_LEVELS 的先后顺序对应（高->低）
_TIER_CLASSES = ["status-excellent", "status-good", "status-fair", "status-poor"]


# --------------------------------------------------------------------------
# 一、找到要用的测试数据
# --------------------------------------------------------------------------
def _scan_batches(base_dir):
    """扫描输出目录，按"测试批次"归组

    返回 {批次时间戳: {sn: xlsx路径}}
    """
    batches = defaultdict(dict)
    if not os.path.isdir(base_dir):
        return batches

    for entry in os.listdir(base_dir):
        folder = os.path.join(base_dir, entry)
        if not os.path.isdir(folder):
            continue
        m = _FOLDER_RE.match(entry)
        if not m:
            continue
        sn = m.group("sn")
        xlsx = os.path.join(folder, f"reboot_test_{sn}.xlsx")
        if os.path.isfile(xlsx):
            batches[m.group("ts")][sn] = xlsx
    return batches


def _pick_data(sns):
    """挑选本次报告使用的数据

    优先取"同一批次里所有设备都齐全"的最新一次测试，
    这样报告内部数据是同一次运行的，不会把不同天的结果混在一起。
    找不到完整批次时，退化为"每台设备各自取最近一次"，并记录来源说明。
    """
    batches = _scan_batches(BASE_OUTPUT_DIR)
    timestamps = sorted(batches.keys(), reverse=True)

    # 1) 优先：最新的完整批次
    for ts in timestamps:
        if all(sn in batches[ts] for sn in sns):
            return ts, {sn: batches[ts][sn] for sn in sns}, "batch"

    # 2) 退化：每台设备各自取最近一次有结果的批次
    latest = {}
    for sn in sns:
        for ts in timestamps:
            if sn in batches[ts]:
                latest[sn] = batches[ts][sn]
                break
    return None, latest, "mixed"


# --------------------------------------------------------------------------
# 二、读设备数据
# --------------------------------------------------------------------------
def _read_fatal_error(excel_file, sn):
    """读取设备摘要中的设备级错误（这类错误不会产生重启明细行）。"""
    summary_file = os.path.join(os.path.dirname(excel_file), f"summary_{sn}.txt")
    try:
        with open(summary_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("提前结束原因:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def _read_device(sn, excel_file):
    """读一台设备的 Excel，算出报告需要的全部指标"""
    df = pd.read_excel(excel_file)

    result_col = df["重启结果"] if "重启结果" in df.columns else pd.Series(dtype=str)
    pass_count = int((result_col == "PASS").sum())
    fail_count = int((result_col == "FAIL").sum())
    error_count = int((result_col == "ERROR").sum())
    total = len(df)
    fatal_error = _read_fatal_error(excel_file, sn)
    # 串口打开失败等设备级错误没有重启明细行，原先会被 HTML 静默忽略。
    if total == 0 and fatal_error:
        error_count = 1

    # 只统计真正启动成功那几轮的耗时，混入超时窗口的样本会失真
    durations = df.loc[result_col == "PASS", "重启时长(秒)"].dropna() \
        if "重启时长(秒)" in df.columns else pd.Series(dtype=float)

    if "超时重启次数" in df.columns:
        timeout_total = int(pd.to_numeric(df["超时重启次数"], errors="coerce").fillna(0).sum())
    else:
        timeout_total = 0

    device_name = str(df["设备名称"].iloc[0]) if "设备名称" in df.columns and total else f"设备-{sn}"

    failures = []
    failure_rows = df.loc[result_col == "FAIL"] if "重启结果" in df.columns else pd.DataFrame()
    for _, row in failure_rows.iterrows():
        failures.append({
            "device_name": device_name,
            "index": row.get("重启序号", "-"),
            "start_time": row.get("测试开始时间", "-"),
            "reason": row.get("失败原因", "-"),
            "fail_time": row.get("失败时间", "-"),
        })

    return {
        "name": device_name,
        "sn": sn,
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "error": error_count,
        "fatal_error": fatal_error,
        "timeout": timeout_total,
        "success_rate": calc_success_rate(pass_count, fail_count, error_count),
        "avg_duration": round(durations.mean(), 2) if len(durations) else 0,
        "max_duration": round(durations.max(), 2) if len(durations) else 0,
        "min_duration": round(durations.min(), 2) if len(durations) else 0,
        "slow_boot_count": int((durations > SLOW_BOOT_THRESHOLD).sum()) if len(durations) else 0,
        "failures": failures,
    }


def _make_fatal_device_data(sn, fatal_error):
    """为未成功生成 Excel 的设备保留一条设备级 ERROR。"""
    return {
        "name": f"设备-{sn}",
        "sn": sn,
        "total": 0,
        "pass": 0,
        "fail": 0,
        "error": 1,
        "fatal_error": fatal_error,
        "timeout": 0,
        "success_rate": 0.0,
        "avg_duration": 0,
        "max_duration": 0,
        "min_duration": 0,
        "slow_boot_count": 0,
        "failures": [],
    }


# --------------------------------------------------------------------------
# 三、分级与建议
# --------------------------------------------------------------------------
def _pick_level(rate):
    """按成功率匹配结论等级，返回 (等级下标, 等级配置)"""
    for i, level in enumerate(CONCLUSION_LEVELS):
        if rate >= level["threshold"]:
            return i, level
    if CONCLUSION_LEVELS:
        return len(CONCLUSION_LEVELS) - 1, CONCLUSION_LEVELS[-1]
    return 0, {"label": "", "color": "#333", "advice": ""}


def _tier_class(level_index):
    return _TIER_CLASSES[min(level_index, len(_TIER_CLASSES) - 1)]


def _build_advices(devices_data, overall_rate, totals):
    """生成建议措施列表"""
    advices = []

    _, level = _pick_level(overall_rate)
    if level.get("advice"):
        advices.append(level["advice"])

    if ADVICE_SLOW_BOOT.get("enable"):
        # 按"慢启动次数"判定，而不是按设备平均耗时。
        # 用平均会漏报：一台 8 次里有 1 次 95 秒、其余 40 秒的设备，均值才 59 秒，
        # 但那次 95 秒确实是一次真实的慢启动，必须报出来。
        slow_devices = [d for d in devices_data if d["slow_boot_count"] > 0]
        if slow_devices:
            advices.append(safe_format(
                ADVICE_SLOW_BOOT["template"],
                count=totals["slow_boot"],
                threshold=SLOW_BOOT_THRESHOLD,
                devices=len(slow_devices)))

    if ADVICE_MANY_FAILURES.get("enable"):
        trigger = ADVICE_MANY_FAILURES.get("trigger_fail_over", 3)
        for d in devices_data:
            if d["fail"] > trigger:
                advices.append(safe_format(
                    ADVICE_MANY_FAILURES["template"],
                    name=d["name"], sn=d["sn"], fail=d["fail"]))

    if ADVICE_TIMEOUT_REBOOT.get("enable") and totals["timeout"] > 0:
        advices.append(safe_format(
            ADVICE_TIMEOUT_REBOOT["template"],
            count=totals["timeout"], timeout=MAX_BOOT_TIMEOUT_SECONDS))

    if ADVICE_SERIAL_ERROR.get("enable") and totals["error"] > 0:
        advices.append(safe_format(
            ADVICE_SERIAL_ERROR["template"], count=totals["error"]))

    advices.extend(FIXED_ADVICE)
    return advices


# --------------------------------------------------------------------------
# 四、拼 HTML 片段
# --------------------------------------------------------------------------
def _esc(value):
    return html.escape(str(value if value is not None else ""))


def _render_headers(columns):
    return "\n".join(f"                    <th>{_esc(c['label'])}</th>" for c in columns)


def _device_cells(d):
    """一台设备 -> {列key: HTML单元格}"""
    level_index, level = _pick_level(d["success_rate"])
    max_cell = _esc(d["max_duration"])
    if d["max_duration"] > SLOW_BOOT_THRESHOLD:
        max_cell = f'<span class="num-timeout">{_esc(d["max_duration"])}</span>'

    timeout_cell = (f'<span class="num-timeout">{d["timeout"]}</span>'
                    if d["timeout"] else "0")

    return {
        "name": _esc(d["name"]),
        "sn": _esc(d["sn"]),
        "total": d["total"],
        "pass": f'<span class="num-pass">{d["pass"]}</span>',
        "fail": f'<span class="num-fail">{d["fail"]}</span>',
        "error": f'<span class="num-error">{d["error"]}</span>',
        "timeout": timeout_cell,
        "avg_duration": _esc(d["avg_duration"]),
        "max_duration": max_cell,
        "min_duration": _esc(d["min_duration"]),
        "status": (f'<span class="status-badge {_tier_class(level_index)}">'
                   f'{_esc(level.get("label", ""))}</span>'),
    }


def _render_device_rows(devices_data):
    rows = []
    for d in devices_data:
        cells = _device_cells(d)
        tds = "\n".join(
            f"                    <td>{cells.get(c['key'], '')}</td>"
            for c in DEVICE_TABLE_COLUMNS
        )
        rows.append(f"                <tr>\n{tds}\n                </tr>")
    return "\n".join(rows)


def _render_failure_rows(all_failures):
    key_map = {
        "device_name": lambda f: _esc(f["device_name"]),
        "index": lambda f: f"第{_esc(f['index'])}次",
        "start_time": lambda f: _esc(f["start_time"]),
        "reason": lambda f: f'<span class="num-fail">{_esc(f["reason"])}</span>',
        "fail_time": lambda f: _esc(f["fail_time"]),
    }
    rows = []
    for f in all_failures:
        tds = "\n".join(
            f"                    <td>{key_map.get(c['key'], lambda _: '')(f)}</td>"
            for c in FAILURE_TABLE_COLUMNS
        )
        rows.append(f"                <tr>\n{tds}\n                </tr>")
    return "\n".join(rows)


def _build_failure_section(sec_no, all_failures):
    """有失败记录才返回 HTML，否则返回空串（章节号会自动前移，不会跳号）"""
    if not all_failures:
        return ""
    return f"""        <h2>{sec_no}、{_esc(SECTION_FAILURES)}</h2>
        <table>
            <thead>
                <tr>
{_render_headers(FAILURE_TABLE_COLUMNS)}
                </tr>
            </thead>
            <tbody>
{_render_failure_rows(all_failures)}
            </tbody>
        </table>
"""


# --------------------------------------------------------------------------
# 五、主流程
# --------------------------------------------------------------------------
def generate_html_report_from_excel(excel_files=None, source_label=None, output_filename=None):
    """从各设备 Excel 汇总生成 HTML 报告。

    ``excel_files`` 不为空时严格使用传入的本次运行文件，绝不回退到历史批次。
    ``output_filename`` 可指定本次报告的文件名，避免覆盖以前批次的 HTML 报告。
    直接单独运行本模块时，保留按历史目录查找最近结果的兼容行为。
    """

    if not DEVICE_SNS:
        print(MSG_NO_DATA)
        return None

    if excel_files is None:
        batch_ts, files, mode = _pick_data(DEVICE_SNS)
    else:
        batch_ts, files, mode = None, dict(excel_files), "current"

    devices_data = []
    for sn in DEVICE_SNS:
        excel_file = files.get(sn)
        if not excel_file:
            print(safe_format(MSG_DEVICE_FILE_MISSING, sn=sn))
            continue
        if not os.path.isfile(excel_file):
            fatal_error = _read_fatal_error(excel_file, sn)
            if fatal_error:
                d = _make_fatal_device_data(sn, fatal_error)
                devices_data.append(d)
                print(safe_format(MSG_DEVICE_OK, sn=sn, total=d["total"],
                                  pass_count=d["pass"], fail=d["fail"], error=d["error"]))
            else:
                print(safe_format(MSG_DEVICE_FILE_MISSING, sn=sn))
            continue
        try:
            d = _read_device(sn, excel_file)
            devices_data.append(d)
            print(safe_format(MSG_DEVICE_OK, sn=sn, total=d["total"],
                              pass_count=d["pass"], fail=d["fail"], error=d["error"]))
        except Exception as e:
            print(safe_format(MSG_DEVICE_READ_FAIL, sn=sn, error=e))

    if not devices_data:
        print(MSG_NO_DATA)
        return None

    # ---- 汇总 ----
    totals = {
        "total": sum(d["total"] for d in devices_data),
        "pass": sum(d["pass"] for d in devices_data),
        "fail": sum(d["fail"] for d in devices_data),
        "error": sum(d["error"] for d in devices_data),
        "timeout": sum(d["timeout"] for d in devices_data),
        "slow_boot": sum(d["slow_boot_count"] for d in devices_data),
    }
    overall_rate = calc_success_rate(totals["pass"], totals["fail"], totals["error"])

    level_index, level = _pick_level(overall_rate)
    conclusion_color = level.get("color", "#333")

    all_failures = []
    for d in devices_data:
        all_failures.extend(d["failures"])

    # ---- 章节编号（自动连续，无失败记录时后面章节自动前移） ----
    idx = 1
    sec_overview = cn_number(idx); idx += 1
    sec_summary = cn_number(idx); idx += 1
    sec_devices = cn_number(idx); idx += 1
    sec_failures = cn_number(idx)
    if all_failures:
        idx += 1
    sec_conclusion = cn_number(idx); idx += 1
    sec_attachments = cn_number(idx)

    # ---- 概况表数值 ----
    per_device = {d["total"] for d in devices_data}
    if len(per_device) == 1:
        test_per_device_value = f"{per_device.pop()} {UNIT_TIMES}"
    else:
        test_per_device_value = f"{min(per_device)}~{max(per_device)} {UNIT_TIMES}"

    test_date = TEST_DATE or datetime.datetime.now().strftime("%Y年%m月%d日")

    if mode == "current":
        source_folders = source_label or "本次测试结果"
    elif mode == "batch" and batch_ts:
        source_folders = f"SN_*_{batch_ts}"
    else:
        source_folders = "各设备最近一次结果"

    # ---- 组装占位符 ----
    subs = {
        "REPORT_TITLE": _esc(REPORT_TITLE),
        "SUBTITLE_LINE": safe_format(REPORT_SUBTITLE_LINE,
                                     subtitle=_esc(REPORT_SUBTITLE),
                                     test_date=_esc(test_date)),
        "DATA_SOURCE_NOTE": safe_format(DATA_SOURCE_NOTE_TEMPLATE, source=source_folders),

        "SEC_OVERVIEW": sec_overview,
        "SEC_SUMMARY": sec_summary,
        "SEC_DEVICES": sec_devices,
        "SEC_CONCLUSION": sec_conclusion,
        "SEC_ATTACHMENTS": sec_attachments,

        "TITLE_OVERVIEW": _esc(SECTION_OVERVIEW),
        "TITLE_SUMMARY": _esc(SECTION_SUMMARY),
        "TITLE_DEVICES": _esc(SECTION_DEVICES),
        "TITLE_CONCLUSION": _esc(SECTION_CONCLUSION),
        "TITLE_ATTACHMENTS": _esc(SECTION_ATTACHMENTS),

        "LABEL_FIRMWARE": _esc(LABEL_FIRMWARE),
        "FIRMWARE_VALUE": "<br>".join(_esc(x) for x in FIRMWARE_INFO),
        "LABEL_TEST_TYPE": _esc(LABEL_TEST_TYPE),
        "TEST_TYPE_VALUE": _esc(REPORT_SUBTITLE),
        "LABEL_DEVICE_COUNT": _esc(LABEL_DEVICE_COUNT),
        "DEVICE_COUNT_VALUE": f"{len(devices_data)} {UNIT_DEVICE}",
        "LABEL_TEST_PER_DEVICE": _esc(LABEL_TEST_PER_DEVICE),
        "TEST_PER_DEVICE_VALUE": test_per_device_value,
        "LABEL_TOTAL_TESTS": _esc(LABEL_TOTAL_TESTS),
        "TOTAL_TESTS_VALUE": f"{totals['total']} {UNIT_TIMES}",
        "LABEL_TIMEOUT": _esc(LABEL_TIMEOUT),
        "TIMEOUT_VALUE": f"{MAX_BOOT_TIMEOUT_SECONDS} {UNIT_SECONDS_PER_TEST}",
        "LABEL_KEYWORDS": _esc(LABEL_KEYWORDS),
        "KEYWORDS_VALUE": safe_format(TEMPLATE_KEYWORDS,
                                      kw1=_esc(SUCCESS_KEYWORD),
                                      kw2=_esc(SUCCESS_KEYWORD2)),

        "CARD_TOTAL_LABEL": _esc(CARD_LABEL_TOTAL),
        "CARD_TOTAL_VALUE": totals["total"],
        "CARD_PASS_LABEL": _esc(CARD_LABEL_PASS),
        "CARD_PASS_VALUE": totals["pass"],
        "CARD_FAIL_LABEL": _esc(CARD_LABEL_FAIL),
        "CARD_FAIL_VALUE": totals["fail"],
        "CARD_RATE_LABEL": _esc(CARD_LABEL_RATE),
        "CARD_RATE_VALUE": f"{overall_rate:.2f}%",

        "ERROR_NOTICE": (
            f'        <div class="notice">'
            f'{safe_format(ERROR_NOTICE_TEMPLATE, count=totals["error"])}'
            f'</div>'
        ) if totals["error"] > 0 else "",

        "DEVICE_HEADERS": _render_headers(DEVICE_TABLE_COLUMNS),
        "DEVICE_ROWS": _render_device_rows(devices_data),
        "FAILURE_SECTION": _build_failure_section(sec_failures, all_failures),

        "CONCLUSION_HEADING": _esc(CONCLUSION_HEADING),
        "CONCLUSION_STATUS": _esc(level.get("label", "")),
        "CONCLUSION_COLOR": conclusion_color,
        "CONCLUSION_SUMMARY": safe_format(
            CONCLUSION_SUMMARY if totals["error"] > 0 else CONCLUSION_SUMMARY_NO_ERROR,
            total=totals["total"], pass_count=totals["pass"], fail=totals["fail"],
            error=totals["error"], rate=f"{overall_rate:.2f}"),
        "ADVICE_HEADING": _esc(ADVICE_HEADING),
        "ADVICES": "\n".join(f"                <li>{a}</li>"
                             for a in _build_advices(devices_data, overall_rate, totals)),

        "ATTACHMENTS": "\n".join(f"            <li>{_esc(a)}</li>" for a in ATTACHMENTS),
        "FOOTER": safe_format(REPORT_FOOTER_TEMPLATE,
                              generate_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    }

    # ---- 渲染 ----
    template_text = _load_template()
    html_content = Template(template_text).safe_substitute(subs)

    os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(BASE_OUTPUT_DIR, output_filename or REPORT_OUTPUT_FILENAME)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✅ HTML报告已生成：{output_path}")
    return output_path


def _load_template():
    if not os.path.isfile(TEMPLATE_PATH):
        raise FileNotFoundError(
            f"报告模板不存在: {TEMPLATE_PATH}\n"
            f"请确认 templates/report_template.html 是否存在")
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        return f.read()


if __name__ == "__main__":
    ensure_utf8_console()
    generate_html_report_from_excel()
