# utils/helpers.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""通用辅助函数"""

import re
import sys

# 控制字符正则（除 Tab / LF / CR 外全部剔除）
_CONTROL_CHARS = ''.join(chr(c) for c in range(0, 0x20) if c not in (0x09, 0x0A, 0x0D))
_CONTROL_RE = re.compile('[%s]' % re.escape(_CONTROL_CHARS))

_CN_NUM = "零一二三四五六七八九"


def ensure_utf8_console():
    """把标准输出/标准错误切到 UTF-8，必须在任何 print 之前调用。

    为什么需要：Windows 中文环境下，只要输出不是直连控制台（被重定向到文件、
    走管道、IDE 的输出面板），Python 就会退回用系统 ANSI 代码页(GBK)。
    而本项目日志里带 ✅ ⚠️ ❌ 这类符号，GBK 编码不了，会直接抛
    UnicodeEncodeError 让脚本在第一行日志处崩掉。这里显式切到 UTF-8，
    并加 errors='replace' 兜底，保证任何环境下都不会因为"打印不出来"而中断测试。

    对直连 Windows 控制台的场景是无害的（Python 本来就按 UTF-8 处理控制台输出）。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            # 流对象不支持 reconfigure（例如已被替换成自定义对象）时忽略，
            # 不能因为这点小事影响主流程
            pass


def clean_illegal_chars(text):
    """清理非法控制字符（写 Excel / HTML 前必须调用）"""
    if not isinstance(text, str):
        return text
    return _CONTROL_RE.sub('', text).replace('\x7f', '')


def truncate_log(log, max_chars=500):
    """截断日志，保留指定长度"""
    if log is None:
        return ""
    if len(log) > max_chars:
        log = log[:max_chars] + "...(截断)"
    return clean_illegal_chars(log)


def write_log_safe(message):
    """安全的日志输出函数（多线程下逐行刷新，避免日志粘连）"""
    print(message, flush=True)


def cn_number(n):
    """阿拉伯数字转中文序号：1 -> 一，12 -> 十二（用于报告章节编号）"""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    if n <= 0:
        return str(n)
    if n < 10:
        return _CN_NUM[n]
    if n < 20:
        return "十" + (_CN_NUM[n % 10] if n % 10 else "")
    if n < 100:
        return _CN_NUM[n // 10] + "十" + (_CN_NUM[n % 10] if n % 10 else "")
    return str(n)


class _SafeDict(dict):
    """format_map 用：缺失的占位符原样保留，不抛异常"""

    def __missing__(self, key):
        return "{" + key + "}"


def safe_format(template, **kwargs):
    """安全字符串模板填充

    报告中所有文案都来自用户可编辑的配置文件，用户可能误删占位符或写错括号。
    这里保证：占位符缺失 -> 原样保留；模板本身语法错误 -> 返回原文，绝不抛异常打断报告生成。
    """
    if not isinstance(template, str):
        return template
    try:
        return template.format_map(_SafeDict(kwargs))
    except Exception:
        return template


def calc_success_rate(pass_cnt, fail_cnt, error_cnt=0):
    """统一的成功率口径：成功率 = 成功 / (成功 + 失败)

    ERROR 表示本轮未能完成有效测试（例如串口或脚本异常），不应被当成
    设备测试失败来拉低成功率；ERROR 数量仍会在报告中单独展示。
    ``error_cnt`` 保留是为了兼容现有调用点。
    """
    total = pass_cnt + fail_cnt
    return (pass_cnt / total * 100) if total else 0.0
