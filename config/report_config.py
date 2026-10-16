# config/report_config.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ============================================================================
#                        报 告 文 案 配 置
# ----------------------------------------------------------------------------
#  改报告里的文字，只改这个文件，不用碰任何 Python 逻辑，也不会影响报告样式。
#
#  规则：
#    1) 只改引号 "" 里面的中文内容；
#    2) 不要改动等号左边的键名、括号、逗号；
#    3) 花括号 {xxx} 是自动填充的数据占位符，可以调整它们在句子里的位置，
#       但如果整个删掉，那一项数据就不会出现在报告里了；
#    4) 改完保存，重新运行 main.py，报告文字就会同步更新。
#
#  报告章节的"一、二、三…"序号由脚本自动计算，这里只写标题名，不要带序号。
# ============================================================================

# ==================== 一、报告基本信息 ====================

# 报告大标题
REPORT_TITLE = "【基线|双目|中性品牌】T33ZL-6.2.0版本-开启efuse设备重启自动化测试报告"

# 报告副标题（显示在标题下方，也会填入"测试类型"一行）
REPORT_SUBTITLE = "开启efuse设备重启自动化测试"

# 测试日期。留空 = 自动使用报告生成当天；也可手填，例如 "2026年07月15日"
TEST_DATE = ""

# 副标题栏的排版模板，{subtitle} 和 {test_date} 是自动填充
REPORT_SUBTITLE_LINE = "{subtitle} | 测试日期：{test_date}"

# 生成好的报告文件名（保存在 设备测试结果报告/ 目录下）
REPORT_OUTPUT_FILENAME = "测试报告.html"


# ==================== 二、测试固件信息 ====================
# 用列表写，列表里的顺序 = 报告里的显示顺序。每一条占一行。
FIRMWARE_INFO = [
    "Build Date:2026-06-29-19:31:19-CST Version:6.2.0 C42AB",
    "SDK_version:15223-2.1.1:2026-06-17 15:06:07 CST",
    "media_version:6.1.14.68346e0a7 feature_6.0.x_",
    "git log:2026-06-29, dev_by_t33zl_ipc, 777f6c1eb, P by zhengzhiyi",
]


# ==================== 三、章节标题 ====================
# 序号自动生成。若当次测试没有失败记录，"失败原因分析"这一节会整节隐藏，
# 后面章节的序号会自动前移，不会出现跳号。
SECTION_OVERVIEW = "测试概况"
SECTION_SUMMARY = "测试结果汇总"
SECTION_DEVICES = "各设备详细数据"
SECTION_FAILURES = "失败原因分析"
SECTION_CONCLUSION = "测试结论与建议"
SECTION_ATTACHMENTS = "附件清单"


# ==================== 四、"测试概况"表格的行标签 ====================
LABEL_FIRMWARE = "测试固件"
LABEL_TEST_TYPE = "测试类型"
LABEL_DEVICE_COUNT = "测试设备数"
LABEL_TEST_PER_DEVICE = "单设备测试次数"
LABEL_TOTAL_TESTS = "总测试次数"
LABEL_TIMEOUT = "超时等待时间"
LABEL_KEYWORDS = "启动检测关键词"

# 单位
UNIT_DEVICE = "台"
UNIT_TIMES = "次"
UNIT_SECONDS_PER_TEST = "秒/次"
# 关键词一行的排版模板，{kw1} {kw2} 自动填充
TEMPLATE_KEYWORDS = "\"{kw1}\" 和 \"{kw2}\"（需同时检测）"


# ==================== 五、"测试结果汇总"四张大卡片的标题 ====================
CARD_LABEL_TOTAL = "总测试次数"
CARD_LABEL_PASS = "成功次数"
CARD_LABEL_FAIL = "失败次数"
CARD_LABEL_RATE = "总体成功率"


# ==================== 六、设备明细表 / 失败明细表的表头 ====================
# 想改表头文字：只改 "label"。想删掉某一列：把整个 { ... } 那一段删掉即可。
# "key" 是程序取值用的内部名，不要改。
DEVICE_TABLE_COLUMNS = [
    {"key": "name",          "label": "设备名称"},
    {"key": "sn",            "label": "序列号(SN)"},
    {"key": "total",         "label": "测试次数"},
    {"key": "pass",          "label": "成功"},
    {"key": "fail",          "label": "失败"},
    {"key": "error",         "label": "错误"},
    {"key": "timeout",       "label": "超时补发reboot次数"},
    {"key": "avg_duration",  "label": "平均耗时(秒)"},
    {"key": "max_duration",  "label": "最大耗时(秒)"},
    {"key": "min_duration",  "label": "最小耗时(秒)"},
    {"key": "status",        "label": "状态"},
]

FAILURE_TABLE_COLUMNS = [
    {"key": "device_name", "label": "设备名称"},
    {"key": "index",       "label": "重启序号"},
    {"key": "start_time",  "label": "测试开始时间"},
    {"key": "reason",      "label": "失败原因"},
    {"key": "fail_time",   "label": "失败时间"},
]


# ==================== 七、测试结论与建议 ====================
# 按成功率从高到低排列，第一个满足「成功率 >= threshold」的等级生效。
# 可以自由增删等级、调整 threshold、改 label（显示文字）、改 color（徽章颜色）、改 advice（建议）。
CONCLUSION_LEVELS = [
    {
        "threshold": 95,
        "label": "优秀",
        "color": "#28a745",
        "advice": "✅ 测试通过：设备重启稳定性表现优秀，建议继续保持监控",
    },
    {
        "threshold": 90,
        "label": "良好",
        "color": "#ffc107",
        "advice": "⚠️ 测试良好：成功率达到 90% 以上，建议关注少数失败案例",
    },
    {
        "threshold": 80,
        "label": "一般",
        "color": "#fd7e14",
        "advice": "⚠️ 需要优化：成功率低于 90%，建议分析失败原因并优化启动流程",
    },
    {
        "threshold": 0,
        "label": "需改进",
        "color": "#dc3545",
        "advice": "❌ 需要改进：成功率低于 80%，建议重点排查设备启动流程",
    },
]

# 结论段落模板。
# {total}=总测试次数 {pass_count}=成功数 {fail}=失败数 {error}=错误数 {rate}=成功率(%)。
# 无错误时用下面第二条（不出现"错误 0 次"这种别扭说法）。
CONCLUSION_SUMMARY = "本次测试共执行 {total} 次重启操作，成功 {pass_count} 次，失败 {fail} 次，错误 {error} 次，成功率达到 {rate}%。"
CONCLUSION_SUMMARY_NO_ERROR = "本次测试共执行 {total} 次重启操作，成功 {pass_count} 次，失败 {fail} 次，成功率达到 {rate}%。"

# 结论小标题
CONCLUSION_HEADING = "测试结论："
ADVICE_HEADING = "建议措施："


# ==================== 八、附加建议（按条件自动追加） ====================
# 把 enable 改成 False 即可关闭某条。
# 可用占位符见每条后面的注释。

# 存在慢启动时追加
ADVICE_SLOW_BOOT = {
    "enable": True,
    "template": "⏱️ 慢启动警告：共检测到 {count} 次启动耗时超过 {threshold} 秒（涉及 {devices} 台设备），建议核对启动流程",
    # {count}=慢启动次数 {threshold}=慢启动阈值(秒) {devices}=涉及的设备台数
}

# 单台设备失败次数较多时追加
ADVICE_MANY_FAILURES = {
    "enable": True,
    "template": "🔴 设备 {name}（SN: {sn}）失败 {fail} 次，建议检查该设备硬件状态",
    # {name}=设备名 {sn}=序列号 {fail}=失败次数
    "trigger_fail_over": 3,   # 失败次数超过该值才追加
}

# 出现启动超时（自动补发 reboot）时追加
ADVICE_TIMEOUT_REBOOT = {
    "enable": True,
    "template": "🔁 检测到 {count} 次启动超时（单次等待超过 {timeout} 秒后已自动补发 reboot），建议排查系统启动阶段是否存在卡死",
    # {count}=超时重启总次数 {timeout}=单次等待上限(秒)
}

# 出现串口 ERROR 时追加
ADVICE_SERIAL_ERROR = {
    "enable": True,
    "template": "🔌 有 {count} 次测试因串口异常被记为 ERROR（未计入成功率），建议检查串口线与 USB 转串口稳定性",
    # {count}=ERROR 次数
}

# 固定追加的建议（每次都会出现），不需要就留空列表 []
FIXED_ADVICE = [
    "日志分析：对于失败原因，建议研发根据测试提供的串口日志，定位具体问题",
]


# ==================== 九、附件清单 ====================
ATTACHMENTS = [
    "各设备 Excel 详细报告（reboot_test_<SN>.xlsx）",
    "各设备完整执行日志（log_<SN>.txt）",
    "各设备串口原始数据日志（serial_log_<SN>.txt）",
    "各设备测试摘要（summary_<SN>.txt）",
    "多设备汇总报告（汇总报告_<时间戳>.txt）",
]


# ==================== 十、提示与页脚文案 ====================
# ERROR 提示条（当有串口类错误时显示），{count} 自动填充
ERROR_NOTICE_TEMPLATE = "⚠️ 注意：共有 {count} 次测试出现 ERROR 状态（如串口重连失败），未计入成功/失败统计。"

# 数据来源说明（显示在报告开头，告诉你这份报告的数据取自哪些批次）
# {source} 会自动填入实际的批次目录
DATA_SOURCE_NOTE_TEMPLATE = "数据来源：{source}"

# 页脚
REPORT_FOOTER_TEMPLATE = "报告生成时间：{generate_time}"

# 找不到任何测试数据时的提示（控制台输出）
MSG_NO_DATA = "❌ 没有找到任何测试数据，未生成报告"
MSG_DEVICE_OK = "✅ 已读取设备 {sn}：共 {total} 次测试，成功 {pass_count}，失败 {fail}，错误 {error}"
MSG_DEVICE_FILE_MISSING = "⚠️ 未找到设备 {sn} 的 Excel 文件"
MSG_DEVICE_READ_FAIL = "⚠️ 读取设备 {sn} 的 Excel 文件失败：{error}"
