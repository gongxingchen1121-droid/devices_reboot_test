# device_reboot_test

通过 Windows 串口执行多设备重启稳定性测试，生成 Excel、文本和 HTML 报告。

## 准备

1. 安装依赖：`pip install -r requirements.txt`。
2. 将 `config/devices.example.py` 复制为 `config/devices.py`，填写设备端口、序列号及所需授权信息。`config/devices.py` 不会提交到 Git；请勿将真实设备凭据写入示例文件。
3. 按需调整 `config/settings.py` 中的测试次数和超时设置。

确认设备和串口后，运行 `python main.py`。测试结果保存在 `设备测试结果报告/`，该目录不会提交到 Git。

若需重新生成交付 Word 文档，先运行 `pip install -r tools/requirements-docs.txt`，再运行 `python tools/build_delivery_docs.py`。

基础语法检查：`python -m compileall -q .`。真机串口测试仅在设备和端口已确认时执行。

## 测试管理平台

- Git 工程的变量文件选择 `platform_config.py`，工具入口填写 `platform_run.py`。节点直接运行 `python platform_run.py`。
- 保持 `CHECK_ONLY = True` 可校验配置和产物写入，报告在 `reports/reboot-*/配置校验.txt`。默认校验无需设备，且不会打开串口。
- 真机执行时，将 `CHECK_ONLY` 设为 `False`，选择 `DEVICE_LIST`，在 `DEVICE_CONFIG_FILE` 填写节点上受保护的 JSON 文件路径。JSON 顶层为数组，每个对象使用 `name`、`port`、`baudrate`、`user_id`、`license_id`、`sn` 字段，结构与 `config/devices.example.py` 中的设备字典相同。该文件由节点管理员保管，平台变量只需要文件路径和所选设备 SN。
- 产物在 `reports/reboot-*/`。通过时退出码为 0，配置、重启或报告异常时返回非零。平台运行关闭原始串口日志采集，设备授权字段留在节点。
