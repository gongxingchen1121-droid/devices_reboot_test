# devices_reboot_test

用于经由 Windows 串口执行多设备重启稳定性测试，并生成 Excel、文本和 HTML 报告。

- `main.py`：主入口；设备清单在本机 `config/devices.py`，仓库中只保留 `config/devices.example.py`，运行参数在 `config/settings.py`。
- `core/`：串口通信与单设备测试流程；修改时保持 PASS、FAIL、ERROR 的统计口径一致。
- `reports/`、`templates/`：文本/HTML 报告与模板；输出位于 `设备测试结果报告/`，不得覆盖历史结果。
- 安装依赖：`pip install -r requirements.txt`。
- 重新生成交付 Word 文档和流程图：`pip install -r tools/requirements-docs.txt`，再运行 `python tools/build_delivery_docs.py`；文件保存在 `非代码资料/交付文档/`。
- 基础验证：`python -m compileall -q .`；真机串口测试仅在设备和端口已确认时执行。
- 版本迭代：从 `main` 建分支并提交 PR，用户确认后合并；发布前更新 `CHANGELOG.md`，通过相关验证后再创建 `v主版本.次版本.修订号` 标签；`.github/workflows/verify.yml` 在提交与拉取请求时执行 Windows/Python 3.13 语法及示例配置导入检查。
- 所有日志和报告均使用 UTF-8；真实设备凭据只保存在被 Git 忽略的本机 `config/devices.py`，不要写入仓库或篡改现有测试结果。
