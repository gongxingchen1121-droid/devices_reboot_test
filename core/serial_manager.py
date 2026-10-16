# core/serial_manager.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""串口管理器 - 负责串口通信相关操作

本模块的约定：
  * 所有可能阻塞的调用都必须有超时（读 timeout + 写 write_timeout），绝不无限等待；
  * 串口异常一律向上返回明确的 error 描述，由上层决定记为 ERROR 还是 FAIL；
  * 所有日志都带设备名前缀，多设备并行时才能分清是哪台设备。
"""

import codecs
import datetime
import time
from typing import NamedTuple, Optional

import serial

from config import (
    CHECK_INTERVAL, RETRY_INTERVAL, MAX_RETRY, LOG_SERIAL_DATA,
    SUCCESS_KEYWORD2, MAX_BOOT_TIMEOUT_SECONDS, MAX_TIMEOUT_REBOOT_PER_TEST,
    POST_COLLECT_SECONDS, POST_BOOT_IDLE_GAP,
    SERIAL_READ_TIMEOUT, SERIAL_WRITE_TIMEOUT,
)
from utils import clean_illegal_chars, write_log_safe

# 关键词匹配的滑动窗口长度（字节->字符）。
# 关键词最长不过几十字符，4096 足够，不必保留整段启动日志做 in 判断。
_KEYWORD_WINDOW = 4096

# 返回给上层保存的启动日志上限，防止单次启动刷出几 MB 文本拖慢报告
_FULL_LOG_LIMIT = 200000


class BootResult(NamedTuple):
    """单次启动等待的结果

    error 非空表示串口层面出了问题（例如串口被拔掉），
    这种情况应记为 ERROR，而不是 FAIL —— 两者含义完全不同。
    """
    success: bool
    duration: float
    full_log: str
    timeout_reboot_count: int
    error: Optional[str] = None


def setup_serial(port, baudrate, device_name=""):
    """打开串口

    必须同时设置读超时和写超时：只设 timeout 的话，设备重启瞬间
    write 在 Windows 驱动缓冲写满时可能永久阻塞，直接把线程挂死。
    """
    try:
        ser = serial.Serial(
            port, baudrate,
            timeout=SERIAL_READ_TIMEOUT,
            write_timeout=SERIAL_WRITE_TIMEOUT,
        )
        return ser, True
    except Exception as e:
        return None, str(e)


def send_serial_cmd(ser, cmd, wait_sec, device_name="", stop_event=None):
    """发送串口命令，返回是否发送成功（失败不抛异常，由调用方决定后续动作）"""
    if stop_event and stop_event.is_set():
        return False
    try:
        ser.write((cmd + "\n").encode("utf-8"))
        ser.flush()
        if stop_event:
            stop_event.wait(wait_sec)
        else:
            time.sleep(wait_sec)
        return True
    except serial.SerialTimeoutException:
        write_log_safe(f"[{device_name}] [WARN] 写串口超时: {cmd}")
        return False
    except serial.SerialException as e:
        write_log_safe(f"[{device_name}] [WARN] 写串口异常: {e}（命令: {cmd}）")
        return False
    except Exception as e:
        write_log_safe(f"[{device_name}] [WARN] 发送命令失败: {e}（命令: {cmd}）")
        return False


def send_reboot(ser, device_name="", stop_event=None):
    """发送重启命令，返回是否成功"""
    if stop_event and stop_event.is_set():
        return False
    try:
        ser.write(b'reboot\n')
        ser.flush()
        return True
    except serial.SerialTimeoutException:
        write_log_safe(f"[{device_name}] [ERROR] 发送 reboot 命令写超时")
        return False
    except serial.SerialException as e:
        write_log_safe(f"[{device_name}] [ERROR] 发送 reboot 命令失败: {e}")
        return False
    except Exception as e:
        write_log_safe(f"[{device_name}] [ERROR] 发送 reboot 命令失败: {e}")
        return False


def check_serial_health(ser, device_name=""):
    """检查串口健康状态"""
    try:
        if not ser or not ser.is_open:
            return False
        ser.write(b'\n')
        ser.flush()
        time.sleep(0.1)
        ser.reset_input_buffer()
        return True
    except (serial.SerialException, OSError) as e:
        write_log_safe(f"[{device_name}] [WARN] 串口健康检查失败: {e}")
        return False
    except Exception as e:
        write_log_safe(f"[{device_name}] [WARN] 串口健康检查异常: {e}")
        return False


def reconnect_serial(port, baudrate, device_name="", old_ser=None, max_retry=MAX_RETRY,
                     stop_event=None):
    """重新连接串口

    关键：必须先把旧句柄关掉再开新口。
    旧 Serial 对象若只被丢弃引用、等 GC 回收，在 Windows 上这期间
    同一个 COM 口会被判定为"已被占用"，导致重连反而必然失败。
    """
    if old_ser is not None:
        try:
            old_ser.close()
        except Exception:
            pass
        old_ser = None

    for attempt in range(1, max_retry + 1):
        if stop_event and stop_event.is_set():
            write_log_safe(f"[{device_name}] [INFO] 收到停止请求，取消串口重连")
            return None, False
        try:
            write_log_safe(f"[{device_name}] [RETRY] 尝试第 {attempt}/{max_retry} 次重连串口...")
            if stop_event and stop_event.wait(RETRY_INTERVAL):
                write_log_safe(f"[{device_name}] [INFO] 收到停止请求，取消串口重连")
                return None, False
            if not stop_event:
                time.sleep(RETRY_INTERVAL)
            ser = serial.Serial(
                port, baudrate,
                timeout=SERIAL_READ_TIMEOUT,
                write_timeout=SERIAL_WRITE_TIMEOUT,
            )
            write_log_safe(f"[{device_name}] [OK] 串口重连成功")
            return ser, True
        except Exception as e:
            write_log_safe(f"[{device_name}] [WARN] 第 {attempt} 次重连失败: {e}")

    write_log_safe(f"[{device_name}] [ERROR] 串口重连失败，已达最大重试次数")
    return None, False


def _write_serial_log(serial_log_fp, timestamp, lines, tag=""):
    """把一行行串口输出写入原始日志文件"""
    if not (serial_log_fp and LOG_SERIAL_DATA):
        return
    for line in lines:
        clean_line = clean_illegal_chars(line)
        if clean_line.strip():
            prefix = f"[{tag}] " if tag else ""
            serial_log_fp.write(f"[{timestamp}] {prefix}{clean_line}\n")


# ====================【修复 #1 2026-10-15】串口日志按分包写盘导致一行被切成两半 ====================
# 修法：新增行缓冲写入器，不完整的行留缓冲等后半截，结束时补写残余。
# 作用：serial_log_*.txt 里每一行都是完整原文，可按行检索/提单。
def _make_line_writer(serial_log_fp):
    """构造"按完整行写盘"的写入器，返回 (write, flush_remainder)

    修复的问题：原来是每个 read 分块各自 splitlines() 写盘。
    串口数据是分包到达的，一行的两半落在两次读里就被写成两行、
    行首还会丢一截 —— 历史日志里能找到同一行两种形态的实证：
        正常  [17:12:24.893] [0m[32m[00:00:09.669 INFO media_5xx.c:998] main video stream fps [20]
        切断  [17:12:24.995] 09.669 INFO media_5xx.c:998] main video stream fps [20]
    现在把不完整的行留在缓冲里，等它的后半截到了再拼成一行写出去。

    flush_remainder() 在监听结束时调用，把没有换行结尾的最后一行补写出来。
    """
    state = {"buf": ""}

    def write(text, tag=""):
        if not (serial_log_fp and LOG_SERIAL_DATA and text):
            return
        buf = state["buf"] + text
        lines = buf.splitlines()
        if buf.endswith(("\n", "\r")):
            complete, state["buf"] = lines, ""
        else:
            # 最后一行没有换行符 = 很可能被分包切断了，留到下一次拼
            complete, state["buf"] = lines[:-1], lines[-1]
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        _write_serial_log(serial_log_fp, ts, complete, tag=tag)
        serial_log_fp.flush()

    def flush_remainder():
        if serial_log_fp and LOG_SERIAL_DATA and state["buf"]:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            _write_serial_log(serial_log_fp, ts, [state["buf"]])
            state["buf"] = ""
            serial_log_fp.flush()

    return write, flush_remainder


def wait_for_boot_complete(ser, keyword, serial_log_fp=None, device_name="", stop_event=None):
    """监听串口，直到同时检测到两个启动关键词。

    超过 MAX_BOOT_TIMEOUT_SECONDS 仍未启动则自动补发 reboot 并重新计时。

    返回 BootResult。
    """
    start_time = time.monotonic()
    timeout_reboot_count = 0
    keyword1_found = False
    keyword2_found = False

    # 增量解码器：避免每轮把整段历史缓冲重新 decode 一遍（O(n²)）
    decoder = codecs.getincrementaldecoder('utf-8')('ignore')
    # 串口日志按完整行写盘（修复分包切断）
    write_serial, flush_serial = _make_line_writer(serial_log_fp)
    text_parts = []          # 已解码文本片段，最终拼一次
    tail = ''                # 滑动窗口，只用于关键词匹配
    last_heartbeat = -1      # 局部变量：不能再用函数属性，否则多个设备线程会互相覆盖

    def reset_window():
        """超时重启后，重置一块新的启动监听窗口"""
        nonlocal decoder, text_parts, tail, last_heartbeat
        nonlocal keyword1_found, keyword2_found, start_time
        decoder = codecs.getincrementaldecoder('utf-8')('ignore')
        text_parts = []
        tail = ''
        last_heartbeat = -1
        keyword1_found = False
        keyword2_found = False
        start_time = time.monotonic()

    write_log_safe(f"[{device_name}] [INFO] 开始监听串口，等待同时出现关键词 "
                   f"'{keyword}' 和 '{SUCCESS_KEYWORD2}'")
    write_log_safe(f"[{device_name}] [INFO] 单次等待上限 {MAX_BOOT_TIMEOUT_SECONDS} 秒，"
                   f"超时将自动补发 reboot")

    def last_duration():
        # 累计真实耗时：已完成的各段超时窗口 + 当前窗口已耗时。
        # 每段窗口实际等了 MAX_BOOT_TIMEOUT_SECONDS 才触发超时，所以按整数累计。
        return (time.monotonic() - start_time) + timeout_reboot_count * MAX_BOOT_TIMEOUT_SECONDS

    def finish(success, error=None, duration=None):
        # 【修复 #1】监听结束时把行缓冲里没有换行结尾的最后一行补写出来
        # duration 显式传入时以传入值为准：
        # 启动成功后还要补采集 5 秒日志，那 5 秒不能算进"启动耗时"。
        flush_serial()   # 把缓冲里没有换行结尾的最后一行补写出来
        full_log = ''.join(text_parts)
        if len(full_log) > _FULL_LOG_LIMIT:
            full_log = full_log[:_FULL_LOG_LIMIT] + "...(已截断)"
        return BootResult(
            success=success,
            duration=round(last_duration() if duration is None else duration, 2),
            full_log=full_log,
            timeout_reboot_count=timeout_reboot_count,
            error=error,
        )

    try:
        while True:
            if stop_event and stop_event.is_set():
                write_log_safe(f"[{device_name}] [WARN] 收到停止请求，结束本次启动监听")
                return finish(False, error="用户中断测试")

            elapsed = time.monotonic() - start_time

            # ---------- 超时：补发 reboot，重新开一个监听窗口 ----------
            if elapsed >= MAX_BOOT_TIMEOUT_SECONDS:
                # 补发次数封顶：否则设备一直起不来时这里会无限循环，
                # 整个测试永远跑不完（主线程会一直等下去）。
                if timeout_reboot_count >= MAX_TIMEOUT_REBOOT_PER_TEST:
                    write_log_safe(
                        f"[{device_name}] [FAIL] 已补发 {timeout_reboot_count} 次 reboot 仍未启动，"
                        f"判定本次启动失败（上限 {MAX_TIMEOUT_REBOOT_PER_TEST} 次）")
                    return finish(False)

                timeout_reboot_count += 1
                write_log_safe(f"[{device_name}] [WARN] 已等待 {int(elapsed)} 秒未启动，"
                               f"发送第 {timeout_reboot_count}/{MAX_TIMEOUT_REBOOT_PER_TEST} 次补发 reboot...")

                if not ser.is_open:
                    return finish(False, error="串口已关闭（超时补发 reboot 时检测到）")

                if not send_reboot(ser, device_name):
                    return finish(False, error="超时补发 reboot 命令发送失败")

                if serial_log_fp:
                    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    serial_log_fp.write(f"[{ts}] >>> [TIMEOUT_REBOOT] reboot\n")
                    serial_log_fp.flush()

                reset_window()
                continue

            # ---------- 心跳日志 ----------
            # CHECK_INTERVAL 允许配成 0（表示关闭心跳），所以必须先判断 > 0，
            # 否则 int(elapsed) % 0 会抛 ZeroDivisionError，把整轮监听打断成 ERROR。
            if CHECK_INTERVAL > 0 and int(elapsed) % CHECK_INTERVAL == 0 \
                    and int(elapsed) > 0 and int(elapsed) != last_heartbeat:
                write_log_safe(f"[{device_name}] [INFO] 已等待 {int(elapsed)} 秒，继续监听...")
                last_heartbeat = int(elapsed)

            # ---------- 串口状态 ----------
            if not ser.is_open:
                return finish(False, error="串口意外关闭")

            # ---------- 读取数据 ----------
            if ser.in_waiting:
                try:
                    chunk = ser.read(ser.in_waiting)
                except serial.SerialException as e:
                    if serial_log_fp:
                        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        serial_log_fp.write(f"[{ts}] [ERROR] 串口读取异常: {e}\n")
                        serial_log_fp.flush()
                    return finish(False, error=f"串口读取异常: {e}")

                if chunk:
                    # 单次解码：同一份数据既写日志又做关键词匹配
                    # （原来是 decode 两次 —— 'ignore' 一份写日志、增量解码器一份做匹配）
                    text = decoder.decode(chunk)
                    if text:
                        write_serial(text)
                        text_parts.append(text)
                        tail = (tail + text)[-_KEYWORD_WINDOW:]

                        if keyword in tail and not keyword1_found:
                            keyword1_found = True
                            write_log_safe(f"[{device_name}] [OK] 检测到关键词1 '{keyword}'")

                        if SUCCESS_KEYWORD2 in tail and not keyword2_found:
                            keyword2_found = True
                            write_log_safe(f"[{device_name}] [OK] 检测到关键词2 '{SUCCESS_KEYWORD2}'")

                        if keyword1_found and keyword2_found:
                            total_duration = last_duration()
                            write_log_safe(f"[{device_name}] [OK] 两个关键词均已检测到，"
                                           f"设备启动成功，耗时 {round(total_duration, 2)} 秒")
                            if timeout_reboot_count > 0:
                                write_log_safe(f"[{device_name}] [INFO] 本次启动共经历 "
                                               f"{timeout_reboot_count} 次超时补发 reboot")

                            _collect_post_boot(ser, serial_log_fp, text_parts, decoder,
                                               device_name, write_serial)
                            return finish(True, duration=total_duration)

            time.sleep(0.05)

    except KeyboardInterrupt:
        write_log_safe(f"\n[{device_name}] [WARN] 用户手动中断测试")
        return finish(False, error="用户手动中断")

    except Exception as e:
        write_log_safe(f"[{device_name}] [ERROR] wait_for_boot_complete 异常: {e}")
        return finish(False, error=f"监听过程异常: {e}")


def _collect_post_boot(ser, serial_log_fp, text_parts, decoder, device_name, write_serial=None):
    """启动成功后额外采集一段日志

    退出条件取"静默超时"而不是"死等满时长"，为了两者兼顾：
      * 旧实现的条件里带了 `and ser.in_waiting`，日志一出现空档就立刻退出，
        实测 4500 字节的突发只收到 2000 字节，POST 日志是残缺的；
      * 但改成"固定等满 5 秒"也不对 —— 实测每次启动白等 5.04 秒，
        50 轮下来整轮多花约 4 分钟，纯属浪费。
    现在：有新数据就续期，静默超过 POST_BOOT_IDLE_GAP 即收工，
    并以 POST_COLLECT_SECONDS 作为硬上限兜底。实测 0.82 秒即可收全同样内容。

    注意这里不能加"必须已经收到过数据"才允许退出的条件：
    设备启动后一条日志也不吐时，那种写法反倒会白等满 5 秒。
    """
    hard_deadline = time.monotonic() + POST_COLLECT_SECONDS
    idle_deadline = time.monotonic() + POST_BOOT_IDLE_GAP

    while time.monotonic() < hard_deadline:
        n = ser.in_waiting
        if not n:
            if time.monotonic() >= idle_deadline:
                break
            time.sleep(0.02)
            continue

        try:
            extra_chunk = ser.read(n)
        except serial.SerialException as e:
            write_log_safe(f"[{device_name}] [WARN] 补充采集时串口异常: {e}")
            return
        if not extra_chunk:
            continue

        idle_deadline = time.monotonic() + POST_BOOT_IDLE_GAP

        extra_text = decoder.decode(extra_chunk)
        if extra_text:
            text_parts.append(extra_text)
            if write_serial:
                write_serial(extra_text, tag="POST")
