# config/settings.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""测试运行参数配置

修改说明见各分组注释。
注意：本文件全部变量都会被 `from config import *` 导出，命名请勿与 devices.py 冲突。
"""

import os

# ================== 路径配置 ==================
# 项目根目录（config/ 的上一级）。
# 所有输出路径都以它为基准，不再依赖"当前工作目录"，
# 避免从其他目录、IDE 或绝对路径运行时，测试结果和报告读写到两个不同位置。
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ================== 测试配置 ==================
SUCCESS_KEYWORD = 'iot status: 2'  # 本类设备的启动成功关键词
SUCCESS_KEYWORD2 = None           # 可选；设为字符串时需同时检测到两个关键词
REBOOT_COUNT = 20                 # 每台设备的重启测试次数
WAIT_AFTER_BOOT = 2               # 一次测试结束后的间隔（秒）
CMD_WAIT_SEC = 2                  # 发送停止录像/重命名命令后的等待时间（秒）
LOG_SERIAL_DATA = True            # 是否记录串口原始数据日志

# ================== 超时与判定阈值 ==================
# 以下三处是"报告里会写出来的数字"，全部由这里单一来源，改这里即可
MAX_BOOT_TIMEOUT_SECONDS = 120    # 单次启动等待上限（秒），超时自动补发 reboot 并重新计时
MAX_TIMEOUT_REBOOT_PER_TEST = 3   # 单次测试最多补发几次 reboot；补满仍不启动就判该次 FAIL。
                                  # 必设：不设上限的话，设备一直起不来会无限循环补发，
                                  # 整个测试永远结束不了。最坏耗时 = (上限+1) × 单次上限。
POST_COLLECT_SECONDS = 5          # 启动成功后补采集日志的"硬上限"（秒），到点必停
POST_BOOT_IDLE_GAP = 0.5          # 补采集期间"静默"超过这个时长就提前收工（秒）。
                                  # 既收全启动后那段连续日志，又不用死等满 5 秒。
                                  # 设得比 POST_COLLECT_SECONDS 大，即退化为"固定等满"。
SLOW_BOOT_THRESHOLD = 60          # 60 秒内正常；超过 60 秒但未超时则计入慢启动统计

# ================== 串口配置 ==================
SERIAL_READ_TIMEOUT = 1           # 串口读超时（秒）
SERIAL_WRITE_TIMEOUT = 1          # 串口写超时（秒）；必须设置，否则 write 可能永久阻塞挂死线程
CHECK_INTERVAL = 5                # 等待启动期间，心跳日志的打印间隔（秒）；设为 0 表示关闭心跳
RETRY_INTERVAL = 5                # 串口重连间隔（秒）
MAX_RETRY = 3                     # 串口重连最大尝试次数
AUTO_RECOVER = True               # 串口异常时是否自动重连

# ================== 目录配置 ==================
BASE_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "设备测试结果报告")   # 测试结果输出根目录（绝对路径）
