# core/test_runner.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""测试执行器 - 负责单设备测试逻辑

结果分类约定（三类，含义不同，不要混）：
  PASS  —— 两个启动关键词均检测到
  FAIL  —— 串口正常，但设备在等待上限内没有启动（真·启动失败）
  ERROR —— 串口/脚本层面出问题导致这次没测成（如串口断链、重连失败），不计入成功率
"""

import datetime
import time
import traceback

import pandas as pd

from config import (
    SUCCESS_KEYWORD, SUCCESS_KEYWORD2, REBOOT_COUNT, WAIT_AFTER_BOOT,
    CMD_WAIT_SEC, LOG_SERIAL_DATA, AUTO_RECOVER,
    MAX_BOOT_TIMEOUT_SECONDS, MAX_TIMEOUT_REBOOT_PER_TEST, SLOW_BOOT_THRESHOLD,
)
from core.serial_manager import (
    setup_serial, send_serial_cmd, send_reboot,
    check_serial_health, reconnect_serial, wait_for_boot_complete,
)
from utils import truncate_log, calc_success_rate

# Excel 列顺序（同时被 HTML 报告读取，勿随意改名）
RESULT_COLUMNS = [
    "设备名称", "重启序号", "测试开始时间", "重启结果", "重启时长(秒)",
    "超时重启次数", "执行日志(摘要)", "失败原因", "失败时间",
]


def _make_row(device_name, index, start_str, result, duration,
              timeout_reboot_count, log_excerpt, reason, fail_time):
    """构造一条结果记录，保证列一致"""
    return {
        "设备名称": device_name,
        "重启序号": index,
        "测试开始时间": start_str,
        "重启结果": result,
        "重启时长(秒)": round(duration, 2),
        "超时重启次数": timeout_reboot_count,
        "执行日志(摘要)": truncate_log(log_excerpt, 500),
        "失败原因": reason,
        "失败时间": fail_time,
    }


class _DeviceTestContext:
    """单个设备一次完整测试的上下文（把状态收在一起，避免几十个局部变量互相串）"""

    def __init__(self, device_config, log_queue, device_folders, stop_event=None):
        self.device_name = device_config["name"]
        self.port = device_config["port"]
        self.baudrate = device_config["baudrate"]
        self.user_id = device_config.get("user_id", "")
        self.license_id = device_config.get("license_id", "")
        self.sn = device_config.get("sn", "")

        self.folder_info = device_folders.get(self.device_name, {})
        self.device_folder = self.folder_info.get("folder", "")
        self.log_file = self.folder_info.get("log_file", "")
        self.serial_log_file = self.folder_info.get("serial_log_file", "")

        self.log_queue = log_queue
        self.stop_event = stop_event
        self.log_fp = None
        self.serial_log_fp = None
        self.ser = None

        self.results = []
        self.pass_cnt = 0
        self.fail_cnt = 0
        self.error_cnt = 0
        self.slow_boot_times = []
        self.timeout_reboot_counts = []
        self.fatal_error = None

    # ---------------- 日志 ----------------
    def write_log(self, message):
        self.log_queue.put(message)
        if self.log_fp:
            self.log_fp.write(message + "\n")
            self.log_fp.flush()

    def log_serial(self, text, tag=""):
        """写入串口原始日志文件"""
        if not (self.serial_log_fp and text):
            return
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        prefix = f"[{tag}] " if tag else ""
        self.serial_log_fp.write(f"[{ts}] {prefix}{text}\n")
        self.serial_log_fp.flush()

    # ---------------- 句柄 ----------------
    def open_files(self):
        self.log_fp = open(self.log_file, 'w', encoding='utf-8')
        self.log_fp.write(f"设备SN: {self.sn}\n")
        self.log_fp.write(f"测试开始时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_fp.write("=" * 80 + "\n\n")

        if LOG_SERIAL_DATA:
            self.serial_log_fp = open(self.serial_log_file, 'w', encoding='utf-8')
            self.serial_log_fp.write(f"设备SN: {self.sn}\n")
            self.serial_log_fp.write(f"串口: {self.port}, 波特率: {self.baudrate}\n")
            self.serial_log_fp.write(f"测试开始时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.serial_log_fp.write("=" * 80 + "\n\n")

    def close_handles(self):
        """集中释放句柄，放在 finally 里执行。

        串口句柄一旦泄漏，Windows 会一直占用该 COM 口，
        下一次运行会直接打不开串口（Access denied）。
        """
        for fp in (self.serial_log_fp, self.log_fp):
            if fp:
                try:
                    fp.close()
                except Exception:
                    pass
        self.serial_log_fp = None
        self.log_fp = None
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    # ---------------- 记录一条结果 ----------------
    def record(self, index, start_str, result, duration, tb_cnt, excerpt, reason, fail_time=''):
        self.results.append(_make_row(
            self.device_name, index, start_str, result, duration,
            tb_cnt, excerpt, reason, fail_time))
        if result == "PASS":
            self.pass_cnt += 1
        elif result == "FAIL":
            self.fail_cnt += 1
        elif result == "ERROR":
            self.error_cnt += 1


def run_single_device_test(device_config, results_queue, log_queue, device_folders, stop_event=None):
    """单个设备的测试线程"""
    ctx = _DeviceTestContext(device_config, log_queue, device_folders, stop_event)
    name = ctx.device_name

    try:
        ctx.open_files()

        ctx.write_log(f"[{name}] ========== 开始测试 ==========")
        ctx.write_log(f"[{name}] 串口: {ctx.port}, 波特率: {ctx.baudrate}")
        ctx.write_log(f"[{name}] 总次数: {REBOOT_COUNT} | 检测关键词后等待: {WAIT_AFTER_BOOT} 秒")
        ctx.write_log(f"[{name}] 成功关键词1: \"{SUCCESS_KEYWORD}\"，关键词2: \"{SUCCESS_KEYWORD2}\"（需同时检测）")
        ctx.write_log(f"[{name}] USER_ID: {ctx.user_id}, LICENSE_ID: {ctx.license_id}, SN: {ctx.sn}")
        ctx.write_log(f"[{name}] 结果保存目录: {ctx.device_folder}")
        ctx.write_log(f"[{name}] 单次等待上限: {MAX_BOOT_TIMEOUT_SECONDS} 秒，"
                      f"最多补发 {MAX_TIMEOUT_REBOOT_PER_TEST} 次 reboot")
        ctx.write_log(f"[{name}] 自动恢复: {'开启' if AUTO_RECOVER else '关闭'}")
        if LOG_SERIAL_DATA:
            ctx.write_log(f"[{name}] [OK] 串口原始数据日志已开启: {ctx.serial_log_file}")

        ctx.ser, error = setup_serial(ctx.port, ctx.baudrate, name)
        if not ctx.ser:
            # 注意：这里不能直接 return，否则后面的落盘和结果投递会被跳过，
            # 主线程会把本设备判定为"线程异常丢失结果"。
            ctx.fatal_error = f"串口打开失败: {error}"
            ctx.write_log(f"[{name}] [ERROR] 无法打开串口: {error}")
        else:
            ctx.write_log(f"[{name}] [OK] 串口打开成功")
            _run_reboot_loop(ctx)

    except Exception as e:
        # 兜底：任何未预料的异常都不能让线程静默死掉
        ctx.fatal_error = f"测试线程异常: {e}"
        ctx.write_log(f"[{name}] [ERROR] 测试线程异常: {e}")
        traceback.print_exc()
    finally:
        # 报告阶段也会写执行日志；必须在关闭文件句柄之前执行。
        try:
            _persist_and_report(ctx, results_queue)
        finally:
            ctx.close_handles()


def _run_reboot_loop(ctx):
    """主测试循环"""
    name = ctx.device_name
    consecutive_failures = 0

    for i in range(1, REBOOT_COUNT + 1):
        if ctx.stop_event and ctx.stop_event.is_set():
            ctx.fatal_error = "用户中断测试"
            ctx.write_log(f"[{name}] [WARN] 收到停止请求，不再开始新的重启轮次")
            break

        ctx.write_log(f"\n[{name}] ----- 第 {i} 次重启测试 -----")
        test_start_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if ctx.serial_log_fp:
            ctx.serial_log_fp.write(f"\n{'=' * 80}\n")
            ctx.serial_log_fp.write(f"第 {i} 次重启测试开始: {test_start_str}\n")
            ctx.serial_log_fp.write(f"{'=' * 80}\n\n")
            ctx.serial_log_fp.flush()

        # ---- 串口健康检查与恢复 ----
        if not check_serial_health(ctx.ser, name):
            ctx.write_log(f"[{name}] [WARN] 串口健康检查失败")

            if not AUTO_RECOVER:
                ctx.record(i, test_start_str, "ERROR", 0, 0, "",
                           "串口异常，且自动恢复已关闭", test_start_str)
                ctx.write_log(f"[{name}] [ERROR] 自动恢复已关闭，终止测试")
                ctx.fatal_error = "串口异常且未开启自动恢复"
                break

            ctx.write_log(f"[{name}] [WARN] 尝试重连串口...")
            new_ser, ok = reconnect_serial(
                ctx.port, ctx.baudrate, name, old_ser=ctx.ser, stop_event=ctx.stop_event)
            ctx.ser = new_ser
            if ctx.stop_event and ctx.stop_event.is_set():
                ctx.fatal_error = "用户中断测试"
                ctx.write_log(f"[{name}] [WARN] 串口重连期间收到停止请求")
                break
            if not ok:
                ctx.record(i, test_start_str, "ERROR", 0, 0, "",
                           "串口重连失败", test_start_str)
                ctx.write_log(f"[{name}] [ERROR] 串口重连失败，跳过本次测试")
                consecutive_failures += 1
                continue
            ctx.write_log(f"[{name}] [INFO] 串口已重连，继续测试")

        # ---- 停止录像 + 重命名目录 ----
        ctx.write_log(f"[{name}] [INFO] 执行停止录像 + 重命名目录")
        old_path = f"/mnt/mmc01/sdrec/{ctx.user_id}-{ctx.license_id}"
        new_path = f"/mnt/mmc01/sdrec/meari-{ctx.sn}"
        if not send_serial_cmd(
                ctx.ser, "kill $(cat /tmp/ppsapp.pid)", CMD_WAIT_SEC, name, ctx.stop_event):
            ctx.write_log(f"[{name}] [WARN] 停止录像命令发送失败，继续重启流程")
        if ctx.stop_event and ctx.stop_event.is_set():
            ctx.fatal_error = "用户中断测试"
            ctx.write_log(f"[{name}] [WARN] 准备重启前收到停止请求")
            break
        if not send_serial_cmd(
                ctx.ser, f"mv {old_path} {new_path}", CMD_WAIT_SEC, name, ctx.stop_event):
            ctx.write_log(f"[{name}] [WARN] 重命名目录命令发送失败，继续重启流程")
        if ctx.stop_event and ctx.stop_event.is_set():
            ctx.fatal_error = "用户中断测试"
            ctx.write_log(f"[{name}] [WARN] 准备重启前收到停止请求")
            break

        # ---- 清空缓冲，然后重启 ----
        # 顺序很关键：必须放在 mv 等命令之后、reboot 之前。
        # 放太早会把命令回显和等待期间的日志算进"本次启动"的文本里。
        try:
            ctx.ser.reset_input_buffer()
        except Exception as e:
            ctx.write_log(f"[{name}] [WARN] 清空串口缓冲失败: {e}")

        if not send_reboot(ctx.ser, name, ctx.stop_event):
            if ctx.stop_event and ctx.stop_event.is_set():
                ctx.fatal_error = "用户中断测试"
                ctx.write_log(f"[{name}] [WARN] 发送 reboot 前收到停止请求")
                break
            ctx.record(i, test_start_str, "ERROR", 0, 0, "",
                       "reboot 命令发送失败（串口写异常）", test_start_str)
            ctx.write_log(f"[{name}] [ERROR] reboot 命令发送失败，跳过本次测试")
            continue

        ctx.write_log(f"[{name}] [CMD] 已发送 reboot 命令")
        ctx.log_serial(">>> reboot")

        # ---- 等待启动 ----
        ctx.write_log(f"[{name}] 等待设备启动（上限 {MAX_BOOT_TIMEOUT_SECONDS} 秒，超时自动补发 reboot）...")
        br = wait_for_boot_complete(
            ctx.ser, SUCCESS_KEYWORD, ctx.serial_log_fp, name, ctx.stop_event)
        ctx.timeout_reboot_counts.append(br.timeout_reboot_count)

        duration, tb_cnt = br.duration, br.timeout_reboot_count

        if br.error:
            # 串口层面出错：这次没测成，不计入成功率
            ctx.record(i, test_start_str, "ERROR", duration, tb_cnt, br.full_log,
                       br.error, test_start_str)
            ctx.write_log(f"[{name}] [ERROR] {br.error}")
        elif br.success:
            ctx.record(i, test_start_str, "PASS", duration, tb_cnt, br.full_log, "")
            consecutive_failures = 0
            if duration > SLOW_BOOT_THRESHOLD:
                ctx.slow_boot_times.append(duration)
                ctx.write_log(f"[{name}] [PASS⚠️] 设备启动成功，但耗时较长: {duration} 秒")
            else:
                ctx.write_log(f"[{name}] [PASS✓] 设备启动成功，耗时 {duration} 秒")
        else:
            ctx.record(i, test_start_str, "FAIL", duration, tb_cnt, br.full_log,
                       f"未检测到启动关键词（已等待 {duration:.0f} 秒）", test_start_str)
            consecutive_failures += 1
            ctx.write_log(f"[{name}] [FAIL] 启动异常，已等待 {duration:.0f} 秒")
            if consecutive_failures >= 3:
                ctx.write_log(f"[{name}] [WARN⚠️] 连续 {consecutive_failures} 次启动失败，请检查设备状态！")

        if tb_cnt > 0:
            ctx.write_log(f"[{name}] [INFO] 本次启动经历了 {tb_cnt} 次超时补发 reboot")

        ctx.write_log(f"[{name}] [INFO] 等待 {WAIT_AFTER_BOOT} 秒后开始下一次重启...")
        if ctx.stop_event and ctx.stop_event.wait(WAIT_AFTER_BOOT):
            ctx.fatal_error = "用户中断测试"
            ctx.write_log(f"[{name}] [WARN] 等待下一轮期间收到停止请求")
            break


def _persist_and_report(ctx, results_queue):
    """落盘 Excel + 摘要，并务必把结果投递给主线程"""
    name = ctx.device_name
    ctx.write_log(f"[{name}] ========== 测试完成 ==========")

    if ctx.serial_log_file:
        ctx.write_log(f"[{name}] [OK] 串口原始数据日志已保存至: {ctx.serial_log_file}")

    if ctx.slow_boot_times:
        avg_slow = sum(ctx.slow_boot_times) / len(ctx.slow_boot_times)
        ctx.write_log(f"[{name}] [STATS] 慢启动统计: 共 {len(ctx.slow_boot_times)} 次"
                      f"（>{SLOW_BOOT_THRESHOLD}秒），平均耗时 {avg_slow:.1f} 秒")
    if ctx.timeout_reboot_counts and sum(ctx.timeout_reboot_counts) > 0:
        ctx.write_log(f"[{name}] [STATS] 超时补发 reboot 统计: 共 {sum(ctx.timeout_reboot_counts)} 次"
                      f"（单次等待超过 {MAX_BOOT_TIMEOUT_SECONDS} 秒）")

    total_executed = len(ctx.results)
    success_rate = calc_success_rate(ctx.pass_cnt, ctx.fail_cnt, ctx.error_cnt)

    try:
        # 显式给出列：results 为空时也不会因为"没有列"而抛 KeyError
        df = pd.DataFrame(ctx.results, columns=RESULT_COLUMNS)
        df.to_excel(ctx.folder_info["excel_file"], index=False, engine='openpyxl')
        ctx.write_log(f"[{name}] [OK] Excel报告已保存至: {ctx.folder_info['excel_file']}")
    except Exception as e:
        ctx.write_log(f"[{name}] [ERROR] Excel 保存失败: {e}")
        if not ctx.fatal_error:
            ctx.fatal_error = f"Excel 保存失败: {e}"

    try:
        with open(ctx.folder_info["summary_file"], 'w', encoding='utf-8') as sf:
            sf.write(f"设备SN: {ctx.sn}\n")
            sf.write(f"测试时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            sf.write("=" * 80 + "\n\n")
            sf.write("测试结果统计:\n")
            sf.write(f"  计划次数: {REBOOT_COUNT}\n")
            sf.write(f"  实际执行: {total_executed}\n")
            sf.write(f"  PASS: {ctx.pass_cnt}\n")
            sf.write(f"  FAIL: {ctx.fail_cnt}\n")
            sf.write(f"  ERROR: {ctx.error_cnt}\n")
            sf.write(f"  成功率: {success_rate:.2f}%  （= PASS / (PASS + FAIL)）\n\n")

            if ctx.slow_boot_times:
                sf.write(f"慢启动统计（>{SLOW_BOOT_THRESHOLD}秒）:\n")
                sf.write(f"  次数: {len(ctx.slow_boot_times)}\n")
                sf.write(f"  平均耗时: {sum(ctx.slow_boot_times) / len(ctx.slow_boot_times):.1f} 秒\n")
                sf.write(f"  最慢耗时: {max(ctx.slow_boot_times):.1f} 秒\n\n")

            if sum(ctx.timeout_reboot_counts) > 0:
                sf.write(f"超时补发 reboot 统计（单次等待 >{MAX_BOOT_TIMEOUT_SECONDS}秒）:\n")
                sf.write(f"  次数: {sum(ctx.timeout_reboot_counts)} 次\n\n")

            if ctx.fatal_error:
                sf.write(f"提前结束原因: {ctx.fatal_error}\n\n")

            sf.write("详细记录:\n")
            for r in ctx.results:
                sf.write(f"  第{r['重启序号']}次 - {r['重启结果']} - 耗时: {r['重启时长(秒)']}秒")
                if r['超时重启次数'] > 0:
                    sf.write(f" - 超时补发 reboot: {r['超时重启次数']}次")
                if r['失败原因']:
                    sf.write(f" - 原因: {r['失败原因']}")
                sf.write("\n")
        ctx.write_log(f"[{name}] [OK] 设备摘要已保存至: {ctx.folder_info['summary_file']}")
    except Exception as e:
        ctx.write_log(f"[{name}] [ERROR] 摘要保存失败: {e}")

    # 必须执行：不投递结果，主线程会一直等下去
    results_queue.put({
        "device_name": name,
        "results": ctx.results,
        "error": ctx.fatal_error,
        "folder_info": ctx.folder_info,
        "pass_count": ctx.pass_cnt,
        "fail_count": ctx.fail_cnt,
        "error_count": ctx.error_cnt,
        "total_executed": total_executed,
        "success_rate": success_rate,
        "slow_boot_count": len(ctx.slow_boot_times),
        "slow_boot_times": ctx.slow_boot_times,
        "timeout_reboot_count": sum(ctx.timeout_reboot_counts),
        "timeout_reboot_counts": ctx.timeout_reboot_counts,
    })
