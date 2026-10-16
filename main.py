# main.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""多设备重启自动化测试脚本 - 主入口"""

import datetime
import queue
import threading
import time
from queue import Queue

from config import (
    DEVICES_CONFIG, BASE_OUTPUT_DIR, LOG_SERIAL_DATA, REBOOT_COUNT,
    MAX_BOOT_TIMEOUT_SECONDS, MAX_TIMEOUT_REBOOT_PER_TEST, SLOW_BOOT_THRESHOLD,
)
from utils import (
    create_device_folders, ensure_dir_exists, calc_success_rate, ensure_utf8_console,
    validate_devices_config,
)
from core import run_single_device_test
from reports import generate_summary_report, generate_html_report_from_excel

# 必须放在任何 print 之前：
# Windows 中文环境下，输出一旦被重定向/走管道（IDE 输出面板、写日志文件），
# Python 的编码会退回系统 GBK，而日志里有 ✅ ⚠️ 这类符号，会直接
# UnicodeEncodeError 崩在第一条日志上。这里统一切成 UTF-8。
ensure_utf8_console()


def _collect_ready_results(results_queue, all_results):
    """取出工作线程已经写好的结果，返回本次新取到的数量。"""
    collected = 0
    while True:
        try:
            all_results.append(results_queue.get_nowait())
            collected += 1
        except queue.Empty:
            return collected


def _print_remaining_logs(log_queue):
    """在线程全部退出后，输出队列里还没显示的最后几行日志。"""
    while True:
        try:
            print(log_queue.get_nowait(), flush=True)
        except queue.Empty:
            return


def _generate_final_reports(all_results, device_folders, timestamp, interrupted=False):
    """生成本批次的文本汇总和 HTML 报告。

    正常结束与用户按 Ctrl+C 停止时都要走这里。中断时每台设备线程会先
    保存已完成的 Excel，再由本函数汇总；因此报告展示的是“已完成部分”，
    而不是把未执行的次数误算为失败。
    """
    if not all_results:
        print("\n[WARN] 没有收到任何设备结果，无法生成汇总报告。")
        return

    report_kind = "中断后的部分测试" if interrupted else "完整测试"
    print(f"\n正在生成{report_kind}报告...")

    # ========== 统计 ===========
    print("\n=============================================")
    print("           测试统计结果")
    print("=============================================")

    summary_report, total_pass, total_fail, total_error, total_slow_boot, _ = \
        generate_summary_report(all_results, timestamp, interrupted=interrupted)

    total_timeout_reboot = 0
    for device_data in all_results:
        device_name = device_data["device_name"]
        if device_data["error"]:
            print(f"\n{device_name}: ERROR - {device_data['error']}")
        else:
            print(f"\n{device_name}: PASS={device_data['pass_count']}, "
                  f"FAIL={device_data['fail_count']}, ERROR={device_data.get('error_count', 0)}, "
                  f"实际执行={device_data.get('total_executed', 0)}/{REBOOT_COUNT}")
            if device_data.get("slow_boot_count", 0) > 0:
                print(f"  慢启动: {device_data['slow_boot_count']} 次（>{SLOW_BOOT_THRESHOLD}秒）")
            if device_data.get("timeout_reboot_count", 0) > 0:
                print(f"  超时补发 reboot: {device_data['timeout_reboot_count']} 次")
        total_timeout_reboot += device_data.get("timeout_reboot_count", 0)

    total_tests = total_pass + total_fail + total_error
    success_rate = calc_success_rate(total_pass, total_fail, total_error)

    print("\n=============================================")
    print(f"汇总: 执行轮次 {total_tests} 次")
    print(f"      PASS: {total_pass} 次")
    print(f"      FAIL: {total_fail} 次")
    if total_error > 0:
        print(f"      ERROR: {total_error} 次（未完成有效测试，不计入成功率）")
    if total_slow_boot > 0:
        print(f"      慢启动: {total_slow_boot} 次（>{SLOW_BOOT_THRESHOLD}秒）")
    if total_timeout_reboot > 0:
        print(f"      超时补发 reboot: {total_timeout_reboot} 次")
    print(f"      总体成功率: {success_rate:.2f}%  （= PASS / (PASS + FAIL)）")
    print("=============================================")
    print(f"\n汇总报告: {summary_report}")
    print("\n各设备详细结果请查看对应的子文件夹")

    # ========== 生成 HTML 报告 ==========
    try:
        print("\n正在生成汇总HTML报告...")
        current_excel_files = {
            info["sn"]: info["excel_file"] for info in device_folders.values()
        }
        source_label = f"SN_*_{timestamp}"
        if interrupted:
            source_label += "（用户中断，部分结果）"
        generate_html_report_from_excel(
            excel_files=current_excel_files,
            source_label=source_label,
            output_filename=(
                f"测试报告_{timestamp}_已中断.html" if interrupted
                else f"测试报告_{timestamp}.html"
            ),
        )
    except Exception as e:
        print(f"[WARN] HTML 报告生成失败（不影响测试结果）: {e}")


def main():
    print("=============================================")
    print("     多设备重启自动化测试脚本")
    print("=============================================")

    config_errors = validate_devices_config(DEVICES_CONFIG)
    if config_errors:
        print("\n[ERROR] 设备配置有问题，已取消本次测试：")
        for error in config_errors:
            print(f"  - {error}")
        print("请修改 config/devices.py 后再重新运行。")
        return

    print(f"\n将同时测试以下 {len(DEVICES_CONFIG)} 台设备:")
    for idx, dev in enumerate(DEVICES_CONFIG, 1):
        print(f"  {idx}. {dev['name']} - 串口: {dev['port']} - SN: {dev['sn']}")
    print("\n⚠️  重要提示：")
    print(f"  - 单次启动等待上限为 {MAX_BOOT_TIMEOUT_SECONDS} 秒，超时后自动补发 reboot 继续等待")
    print(f"  - 单次测试最多补发 {MAX_TIMEOUT_REBOOT_PER_TEST} 次，仍未启动则该次判定为 FAIL")
    print("  - 如需中断测试，请按 Ctrl+C")
    print("  - 请确保所有设备已连接且串口未被占用")

    try:
        input("\n按 Enter 键开始测试...")
    except KeyboardInterrupt:
        print("\n已取消，未开始测试。")
        return

    # 确保输出目录存在
    ensure_dir_exists(BASE_OUTPUT_DIR)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # 创建设备文件夹
    device_folders = create_device_folders(BASE_OUTPUT_DIR, DEVICES_CONFIG, timestamp)

    print(f"\n结果将保存至: {BASE_OUTPUT_DIR}")
    for name, info in device_folders.items():
        print(f"  - {name}: {info['folder']}")
        if LOG_SERIAL_DATA:
            print(f"    ├─ 串口日志: serial_log_{info['sn']}.txt")

    # 创建队列
    results_queue = Queue()
    log_queue = Queue()
    stop_event = threading.Event()

    # 创建并启动测试线程
    threads = []
    for device_config in DEVICES_CONFIG:
        thread = threading.Thread(
            target=run_single_device_test,
            args=(device_config, results_queue, log_queue, device_folders, stop_event),
            name=device_config["name"],
            daemon=False,
        )
        threads.append(thread)
        thread.start()

    # 实时日志输出
    print("\n========== 实时日志输出 ==========\n")
    all_results = []
    completed_count = 0

    try:
        while completed_count < len(DEVICES_CONFIG):
            # 1) 先把日志取出来（timeout 顺便充当轮询节拍）
            try:
                print(log_queue.get(timeout=0.5), flush=True)
            except queue.Empty:
                pass

            # 2) 再把已完成的结果收干净
            completed_count += _collect_ready_results(results_queue, all_results)

            # 3) 只有"所有线程都已退出"才可能是异常丢失结果。
            #    不能按"已退出线程数"判断：正常跑完的设备线程也是已退出状态，
            #    那样会在第一台设备跑完时就把整个测试提前掐断。
            if all(not t.is_alive() for t in threads):
                # 给线程退出后的最后一次投递留一点时间
                deadline = time.time() + 1.0
                while time.time() < deadline:
                    newly_collected = _collect_ready_results(results_queue, all_results)
                    completed_count += newly_collected
                    if not newly_collected:
                        time.sleep(0.05)

                if completed_count < len(DEVICES_CONFIG):
                    delivered = {r.get("device_name") for r in all_results}
                    missing = [t.name for t in threads if t.name not in delivered]
                    print(f"\n[ERROR] 以下测试线程异常退出且未返回结果: {missing}")
                    print(f"[ERROR] 已收到 {completed_count}/{len(DEVICES_CONFIG)} 台设备的结果，终止等待")
                    print("[ERROR] 常见原因：写 Excel 失败 / 结果投递前进程被强杀。请查看上方日志定位")
                break

    except KeyboardInterrupt:
        print("\n⚠️  用户中断测试（Ctrl+C）")
        print("   已通知各设备停止；正在等待线程安全退出...")
        stop_event.set()
        for t in threads:
            t.join()
        print("   所有设备线程已安全退出，串口与日志已关闭。")
        _collect_ready_results(results_queue, all_results)
        _print_remaining_logs(log_queue)
        _generate_final_reports(all_results, device_folders, timestamp, interrupted=True)
        print("   测试已中断。若设备正处于重启过程中，请等待其恢复正常后再操作设备。")
        print("   已生成本次已完成部分的汇总报告和 HTML 报告。")
        return

    # 输出剩余日志
    _print_remaining_logs(log_queue)
    _generate_final_reports(all_results, device_folders, timestamp)


if __name__ == "__main__":
    main()
