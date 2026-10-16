# core/__init__.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""核心模块

显式导出，不用 `import *`：
星号导入会把 serial / pandas / time 等模块名和一堆配置常量
一起泄漏到 core 命名空间（`core.pd`、`core.serial` 都能访问到），
既容易撞名，也让人误以为 core 是个常量包。
"""

from .serial_manager import (          # noqa: F401
    setup_serial,
    send_serial_cmd,
    send_reboot,
    check_serial_health,
    reconnect_serial,
    wait_for_boot_complete,
    BootResult,
)
from .test_runner import run_single_device_test   # noqa: F401

__all__ = [
    "setup_serial",
    "send_serial_cmd",
    "send_reboot",
    "check_serial_health",
    "reconnect_serial",
    "wait_for_boot_complete",
    "BootResult",
    "run_single_device_test",
]
