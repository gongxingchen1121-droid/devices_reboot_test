# devices_reboot_test

通过 Windows 串口执行多设备重启稳定性测试，生成 Excel、文本和 HTML 报告。

## 准备

1. 安装依赖：`pip install -r requirements.txt`。
2. 将 `config/devices.example.py` 复制为 `config/devices.py`，填写设备端口、序列号及所需授权信息。`config/devices.py` 不会提交到 Git；请勿将真实设备凭据写入示例文件。
3. 按需调整 `config/settings.py` 中的测试次数和超时设置。

确认设备和串口后，运行 `python main.py`。测试结果保存在 `设备测试结果报告/`，该目录不会提交到 Git。

若需重新生成交付 Word 文档，先运行 `pip install -r tools/requirements-docs.txt`，再运行 `python tools/build_delivery_docs.py`。

基础语法检查：`python -m compileall -q .`。真机串口测试仅在设备和端口已确认时执行。

## 版本迭代

- 发布版本使用 `v主版本.次版本.修订号` 标签；当前基线版本为 `v2.0.0`。
- 每次发布前更新 [CHANGELOG.md](CHANGELOG.md)，写明用户可见的变化、修复和兼容性影响。
- 提交和拉取请求会在 Windows 上运行 Python 3.13 语法检查，并用示例设备配置检查模块导入；这些检查不代替真机测试。
- 发布前核对提交内容，不将 `config/devices.py`、测试结果或历史备份加入仓库。
