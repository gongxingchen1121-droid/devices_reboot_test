# device_reboot_test

用于经由 Windows 串口执行多设备重启稳定性测试，并生成 Excel、文本和 HTML 报告。

- `main.py`：主入口；设备清单在本机 `config/devices.py`，仓库中只保留 `config/devices.example.py`，运行参数在 `config/settings.py`。
- `core/`：串口通信与单设备测试流程；修改时保持 PASS、FAIL、ERROR 的统计口径一致。
- `reboot_reports/`、`templates/`：文本/HTML 报告代码与模板。本地结果写入 `设备测试结果报告/`，平台产物写入 `reports/`。
- 平台入口 `python platform_run.py`，变量文件为 `platform_config.py`，预设仅校验配置和产物写入。
- 安装依赖：`pip install -r requirements.txt`。
- 重新生成交付 Word 文档和流程图：`pip install -r tools/requirements-docs.txt`，再运行 `python tools/build_delivery_docs.py`；文件保存在 `非代码资料/交付文档/`。
- 基础验证：`python -m compileall -q .`；真机串口测试仅在设备和端口已确认时执行。
- 所有日志和报告均使用 UTF-8；真实设备凭据保存在 Git 忽略的本机设备配置或执行机受保护配置中。
