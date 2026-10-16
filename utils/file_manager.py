# utils/file_manager.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""文件管理工具"""

import os
import datetime


_REQUIRED_DEVICE_FIELDS = ("name", "port", "baudrate", "user_id", "license_id", "sn")


def validate_devices_config(devices_config):
    """检查设备配置，返回可直接显示给用户的错误列表。"""
    errors = []
    if not isinstance(devices_config, list) or not devices_config:
        return ["DEVICES_CONFIG 必须是至少包含一台设备的列表。"]

    seen = {"name": {}, "port": {}, "sn": {}}
    for index, device in enumerate(devices_config, 1):
        if not isinstance(device, dict):
            errors.append(f"第 {index} 台设备的配置必须是字典。")
            continue

        for field in _REQUIRED_DEVICE_FIELDS:
            value = device.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"第 {index} 台设备缺少 {field}。")

        baudrate = device.get("baudrate")
        if not isinstance(baudrate, int) or isinstance(baudrate, bool) or baudrate <= 0:
            errors.append(f"第 {index} 台设备的 baudrate 必须是大于 0 的整数。")

        for field, normalizer in (
            ("name", lambda value: str(value).strip()),
            ("port", lambda value: str(value).strip().upper()),
            ("sn", lambda value: str(value).strip()),
        ):
            value = device.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            key = normalizer(value)
            if key in seen[field]:
                errors.append(
                    f"第 {seen[field][key]} 台和第 {index} 台设备的 {field} 重复: {value}。")
            else:
                seen[field][key] = index

    return errors


def create_device_folders(base_dir, devices_config, timestamp=None):
    """为每台设备创建独立的子文件夹，并使用同一批次的统一时间戳。"""
    device_folders = {}
    timestamp = timestamp or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    for device in devices_config:
        sn = device["sn"]
        device_folder = os.path.join(base_dir, f"SN_{sn}_{timestamp}")
        os.makedirs(device_folder, exist_ok=True)

        device_folders[device["name"]] = {
            "folder": device_folder,
            "sn": sn,
            "log_file": os.path.join(device_folder, f"log_{sn}.txt"),
            "excel_file": os.path.join(device_folder, f"reboot_test_{sn}.xlsx"),
            "summary_file": os.path.join(device_folder, f"summary_{sn}.txt"),
            "serial_log_file": os.path.join(device_folder, f"serial_log_{sn}.txt")
        }

    return device_folders


def ensure_dir_exists(path):
    """确保目录存在，不存在则创建"""
    os.makedirs(path, exist_ok=True)
    return path
