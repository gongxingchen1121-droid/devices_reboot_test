# reports/__init__.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""报告生成模块

- report_generator.py  txt 汇总报告
- html_report.py       HTML 报告
"""

from .report_generator import generate_summary_report      # noqa: F401
from .html_report import generate_html_report_from_excel   # noqa: F401
