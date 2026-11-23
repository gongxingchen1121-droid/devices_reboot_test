"""测试管理平台直接运行的入口。"""

import json
import logging
import re
import sys
import tempfile
from pathlib import Path

import platform_config as task

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent
SAFE_DEVICE_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def load_selected_devices():
    if not task.DEVICE_LIST or not task.DEVICE_CONFIG_FILE.strip():
        raise ValueError("真机测试需要选择设备并填写执行机设备配置文件路径。")
    config_path = Path(task.DEVICE_CONFIG_FILE)
    try:
        devices = json.loads((ROOT / config_path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError("执行机设备配置文件无法读取或 JSON 格式有误。") from error
    if not isinstance(devices, list) or any(not isinstance(item, dict) for item in devices):
        raise ValueError("执行机设备配置必须是设备对象列表。")

    selected = []
    for sn in task.DEVICE_LIST:
        matches = [device for device in devices if device.get("sn") == sn]
        if len(matches) != 1:
            raise ValueError("所选设备在执行机配置中缺失或重复。")
        device = matches[0]
        for field in ("sn", "user_id", "license_id"):
            value = device.get(field)
            if not isinstance(value, str) or not SAFE_DEVICE_VALUE.fullmatch(value) or value == "replace-me":
                raise ValueError(f"执行机设备配置的 {field} 格式有误或仍使用占位值。")
        selected.append(device)
    return selected


def configure_task():
    import config
    from config import settings

    if type(task.CHECK_ONLY) is not bool:
        raise ValueError("CHECK_ONLY 必须为布尔值。")
    if (not isinstance(task.DEVICE_LIST, list)
            or any(not isinstance(sn, str) or not SAFE_DEVICE_VALUE.fullmatch(sn) for sn in task.DEVICE_LIST)
            or len(set(task.DEVICE_LIST)) != len(task.DEVICE_LIST)):
        raise ValueError("DEVICE_LIST 必须是去重后的有效设备 SN 列表。")
    if not isinstance(task.DEVICE_CONFIG_FILE, str):
        raise ValueError("DEVICE_CONFIG_FILE 必须为字符串。")

    overrides = {
        "REBOOT_COUNT": task.REBOOT_COUNT,
        "MAX_BOOT_TIMEOUT_SECONDS": task.MAX_BOOT_TIMEOUT_SECONDS,
        "MAX_TIMEOUT_REBOOT_PER_TEST": task.MAX_TIMEOUT_REBOOT_PER_TEST,
        "SLOW_BOOT_THRESHOLD": task.SLOW_BOOT_THRESHOLD,
        "SUCCESS_KEYWORD": task.SUCCESS_KEYWORD,
        "SUCCESS_KEYWORD2": task.SUCCESS_KEYWORD2 if task.SUCCESS_KEYWORD2 != "" else None,
        "LOG_SERIAL_DATA": False,
        "PLATFORM_MODE": True,
    }
    for name, value in overrides.items():
        setattr(settings, name, value)
        setattr(config, name, value)
    errors = settings.validate_runtime_settings()
    if errors:
        raise ValueError(" ".join(errors))
    if not task.CHECK_ONLY or task.DEVICE_LIST or task.DEVICE_CONFIG_FILE.strip():
        from utils import validate_devices_config

        devices = load_selected_devices()
        if validate_devices_config(devices):
            raise ValueError("执行机设备配置缺少必填字段，或设备名称、串口、SN 重复。")
        config.DEVICES_CONFIG = devices
        config.DEVICE_SNS = [device["sn"] for device in devices]

    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    config.BASE_OUTPUT_DIR = tempfile.mkdtemp(prefix="reboot-", dir=reports_dir)
    return Path(config.BASE_OUTPUT_DIR)


def run():
    try:
        output = configure_task()
        from main import main

        if task.CHECK_ONLY:
            (output / "配置校验.txt").write_text(
                f"配置校验通过\n重启次数: {task.REBOOT_COUNT}\n超时秒数: {task.MAX_BOOT_TIMEOUT_SECONDS}\n",
                encoding="utf-8",
            )
            LOGGER.info("配置校验通过，产物位置 %s。", output.relative_to(ROOT))
            return 0
        return main(non_interactive=True)
    except (ValueError, OSError, ImportError) as error:
        LOGGER.error("执行失败：%s", error)
        return 1
    except KeyboardInterrupt:
        LOGGER.error("执行中断。")
        return 130


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(run())
