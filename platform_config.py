# 仅校验配置和产物写入，开启时不连接串口
CHECK_ONLY = True

# 被测设备 SN 列表，从平台设备选择器填充
DEVICE_LIST = []

# 执行机上受保护的设备配置 JSON 路径，结构见 README
DEVICE_CONFIG_FILE = ""

# 每台设备的重启次数
REBOOT_COUNT = 1

# 首次启动和每次补发后的等待上限（秒）
MAX_BOOT_TIMEOUT_SECONDS = 120

# 单轮最多补发 reboot 次数
MAX_TIMEOUT_REBOOT_PER_TEST = 3

# 慢启动阈值（秒）
SLOW_BOOT_THRESHOLD = 60

# 启动成功关键词
SUCCESS_KEYWORD = "iot online"

# 第二关键词，空字符串表示只匹配第一关键词
SUCCESS_KEYWORD2 = ""
