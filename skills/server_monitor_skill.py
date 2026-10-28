# skills/server_monitor_skill.py
"""Read-only server monitoring skill: load, RAM, disk, uptime.

Uses only the Python standard library. Linux is fully supported; on other
systems the unavailable metrics are reported as such.
"""
import os
import shutil
import logging
from typing import Any

logger = logging.getLogger("anna.server_monitor")

# Which filesystem to report. Override with ANNA_MONITOR_DISK_PATH if needed.
DISK_PATH = os.getenv("ANNA_MONITOR_DISK_PATH", "/")

FUNCTION_DECLARATIONS = [
    {
        "name": "get_server_stats",
        "description": "Get the current server state: CPU load (load average), free RAM, disk space and uptime.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    }
]

INSTRUCTION_ADDON = """
Skill: server monitoring. If the user asks about the state of the server, free disk
space, memory or load, use the get_server_stats tool. Keep answers short and to the point.
"""


def _meminfo_mb(meminfo: str, key: str) -> int:
    for line in meminfo.splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1]) // 1024
    raise KeyError(key)


def _get_stats_logic() -> str:
    lines = []

    # 1. Load average (CPU). LA is only meaningful relative to the core count.
    try:
        load1, load5, load15 = os.getloadavg()
        cores = os.cpu_count() or 1
        lines.append(
            f"CPU load average: {load1:.2f} (1 min), "
            f"{load5:.2f} (5 min), {load15:.2f} (15 min); cores: {cores}."
        )
    except Exception:
        logger.warning("Load average unavailable", exc_info=True)
        lines.append("Could not read CPU load.")

    # 2. Memory (RAM)
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = f.read()
        mem_total = _meminfo_mb(meminfo, "MemTotal")
        mem_avail = _meminfo_mb(meminfo, "MemAvailable")
        lines.append(f"RAM: {mem_avail} MB available out of {mem_total} MB.")
    except Exception:
        logger.warning("Memory info unavailable", exc_info=True)
        lines.append("Could not read memory info.")

    # 3. Disk space
    try:
        total, used, free = shutil.disk_usage(DISK_PATH)
        total_gb = total // (2**30)
        free_gb = free // (2**30)
        free_mb = (free % (2**30)) // (2**20)
        used_percent = (used / total) * 100
        lines.append(
            f"Disk ({DISK_PATH}): {free_gb} GB {free_mb} MB free of {total_gb} GB "
            f"({used_percent:.1f}% used)."
        )
    except Exception:
        logger.warning("Disk usage unavailable", exc_info=True)
        lines.append("Could not read disk usage.")

    # 4. Uptime
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.read().split()[0])
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        lines.append(f"Uptime since last reboot: {days} d {hours} h.")
    except Exception:
        logger.warning("Uptime unavailable", exc_info=True)
        lines.append("Could not read uptime.")

    return " ".join(lines)


async def execute(name: str, args: Any) -> str:
    if name == "get_server_stats":
        return _get_stats_logic()
    return f"Unknown tool: {name}"
