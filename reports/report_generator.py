# reports/report_generator.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""控制台/文本汇总报告生成器"""

import datetime
import os

from config import (
    BASE_OUTPUT_DIR, REBOOT_COUNT, MAX_BOOT_TIMEOUT_SECONDS, SLOW_BOOT_THRESHOLD,
)
from utils import calc_success_rate


def generate_summary_report(all_results, timestamp, interrupted=False, planned_reboot_count=None):
    """生成 txt 汇总报告

    返回 (报告路径, PASS总数, FAIL总数, ERROR总数, 慢启动总数, 慢启动耗时列表)
    """
    # 补生成历史批次报告时，当前配置里的次数可能已被用户改过；允许调用方
    # 传入该批次实际的计划次数，防止报告把“原来计划 50 次”误写成“20 次”。
    planned_reboot_count = (REBOOT_COUNT if planned_reboot_count is None
                            else planned_reboot_count)

    total_pass = 0
    total_fail = 0
    total_error = 0
    total_slow_boot = 0
    total_timeout_reboot = 0
    fatal_device_count = 0
    all_slow_times = []

    summary_lines = []
    summary_lines.append("=" * 80)
    summary_lines.append("多设备重启测试汇总报告")
    summary_lines.append(f"测试时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if interrupted:
        summary_lines.append("测试状态: 用户中断，以下统计仅包含停止前已完成的部分结果")
    summary_lines.append("=" * 80)
    summary_lines.append("")
    summary_lines.append(f"启动等待上限: {MAX_BOOT_TIMEOUT_SECONDS} 秒/次（超时后自动补发 reboot 继续等待）")
    summary_lines.append(f"慢启动判定阈值: {SLOW_BOOT_THRESHOLD} 秒")
    summary_lines.append("")

    for device_data in all_results:
        device_name = device_data["device_name"]
        folder_info = device_data.get("folder_info", {})

        # 单台设备整体失败（例如串口打不开）——注意它的逐次记录可能是空的
        if device_data["error"] and not device_data.get("results"):
            # 整台设备在第一轮前就失败（例如串口打不开）不等于执行了一次
            # 重启测试，不能计入“有效执行次数”或成功率分母。
            fatal_device_count += 1
            summary_lines.append(f"{device_name}: ERROR - {device_data['error']}")
            summary_lines.append(f"  结果目录: {folder_info.get('folder', '')}")
            summary_lines.append("")
            continue

        pass_cnt = device_data.get("pass_count", 0)
        fail_cnt = device_data.get("fail_count", 0)
        error_cnt = device_data.get("error_count", 0)
        executed = device_data.get("total_executed", pass_cnt + fail_cnt + error_cnt)
        timeout_cnt = device_data.get("timeout_reboot_count", 0)
        slow_cnt = device_data.get("slow_boot_count", 0)
        slow_times = device_data.get("slow_boot_times", [])

        total_pass += pass_cnt
        total_fail += fail_cnt
        total_error += error_cnt
        total_slow_boot += slow_cnt
        total_timeout_reboot += timeout_cnt
        all_slow_times.extend(slow_times)

        summary_lines.append(f"{device_name} (SN: {folder_info.get('sn', '')})")
        summary_lines.append(f"  结果目录: {folder_info.get('folder', '')}")
        summary_lines.append(f"  执行情况: 计划 {planned_reboot_count} 次，实际执行 {executed} 次")
        summary_lines.append(f"  测试结果: PASS={pass_cnt}, FAIL={fail_cnt}, ERROR={error_cnt}")
        summary_lines.append(f"  成功率: {calc_success_rate(pass_cnt, fail_cnt, error_cnt):.2f}%"
                             f"（= PASS / (PASS + FAIL)）")
        if device_data["error"]:
            summary_lines.append(f"  ⚠️ 提前结束: {device_data['error']}")

        if slow_cnt > 0:
            avg_slow = sum(slow_times) / len(slow_times) if slow_times else 0
            max_slow = max(slow_times) if slow_times else 0
            summary_lines.append(
                f"  慢启动统计: {slow_cnt} 次（>{SLOW_BOOT_THRESHOLD}秒），"
                f"平均 {avg_slow:.1f} 秒，最慢 {max_slow:.1f} 秒")

        if timeout_cnt > 0:
            summary_lines.append(f"  超时补发 reboot: {timeout_cnt} 次")

        summary_lines.append(f"  Excel报告: {folder_info.get('excel_file', '')}")
        summary_lines.append(f"  完整日志: {folder_info.get('log_file', '')}")
        summary_lines.append(f"  串口日志: {folder_info.get('serial_log_file', '')}")
        summary_lines.append(f"  设备摘要: {folder_info.get('summary_file', '')}")
        summary_lines.append("")

    total_executed = total_pass + total_fail + total_error
    overall_rate = calc_success_rate(total_pass, total_fail, total_error)

    summary_lines.append("=" * 80)
    summary_lines.append("汇总统计:")
    summary_lines.append(f"  实际执行总次数: {total_executed}")
    summary_lines.append(f"  PASS总数: {total_pass}")
    summary_lines.append(f"  FAIL总数: {total_fail}")
    if total_error > 0:
        summary_lines.append(f"  ERROR总数: {total_error}（串口/脚本问题导致该次未完成）")
    if fatal_device_count > 0:
        summary_lines.append(f"  设备级错误: {fatal_device_count} 台（未执行重启轮次）")
    if total_slow_boot > 0:
        avg_all_slow = sum(all_slow_times) / len(all_slow_times) if all_slow_times else 0
        max_all_slow = max(all_slow_times) if all_slow_times else 0
        summary_lines.append(f"  慢启动总数: {total_slow_boot} 次（>{SLOW_BOOT_THRESHOLD}秒）")
        summary_lines.append(f"  慢启动平均耗时: {avg_all_slow:.1f} 秒")
        summary_lines.append(f"  慢启动最慢耗时: {max_all_slow:.1f} 秒")
    if total_timeout_reboot > 0:
        summary_lines.append(f"  超时补发 reboot 总数: {total_timeout_reboot} 次"
                             f"（单次等待 >{MAX_BOOT_TIMEOUT_SECONDS}秒）")
    summary_lines.append(f"  总体成功率: {overall_rate:.2f}%（= PASS / (PASS + FAIL)）")
    summary_lines.append("=" * 80)

    summary_report = os.path.join(BASE_OUTPUT_DIR, f"汇总报告_{timestamp}.txt")
    with open(summary_report, 'w', encoding='utf-8') as f:
        f.write('\n'.join(summary_lines))

    return summary_report, total_pass, total_fail, total_error, total_slow_boot, all_slow_times
