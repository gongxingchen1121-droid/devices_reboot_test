# config/__init__.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""配置汇总入口

- settings.py      运行参数（次数、超时、串口、目录）
- devices.py       被测设备清单（端口、SN、user_id、license_id）
- report_config.py 报告文案（你要改的文字都在这里）
"""

from .settings import *        # noqa: F401,F403
from .devices import *         # noqa: F401,F403
from .report_config import *   # noqa: F401,F403

# 设备 SN 列表从设备清单自动派生，
# 避免"devices.py 改了、报告配置忘了改"导致报告读不到数据。
DEVICE_SNS = [d["sn"] for d in DEVICES_CONFIG]
