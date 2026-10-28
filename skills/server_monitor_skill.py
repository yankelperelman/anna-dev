# skills/server_monitor_skill.py
"""Cross-platform server monitoring skill: load, RAM, disk, uptime."""
import os
import time
import logging
import psutil
from typing import Any

logger = logging.getLogger("anna.server_monitor")

# Which filesystem to report. Override with ANNA_MONITOR_DISK_PATH if needed.
# On Windows, "/" usually means the current drive (e.g. C:\).
DISK_PATH = os.getenv("ANNA_MONITOR_DISK_PATH", "/")

FUNCTION_DECLARATIONS = [
    {
        "name": "get_server_stats",
        "description": "Get the current server state: CPU load, free RAM, disk space and uptime.",
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

def _get_stats_logic() -> str:
    lines = []

    # 1. CPU load (psutil emulates getloadavg on Windows)
    try:
        load1, load5, load15 = psutil.getloadavg()
        cores = psutil.cpu_count(logical=True) or 1
        lines.append(
            f"CPU load average: {load1:.2f} (1 min), "
            f"{load5:.2f} (5 min), {load15:.2f} (15 min); cores: {cores}."
        )
    except Exception:
        logger.warning("Load average unavailable", exc_info=True)
        lines.append("Could not read CPU load.")

    # 2. Memory (RAM)
    try:
        mem = psutil.virtual_memory()
        mem_total = mem.total // (2**20)  # MB
        mem_avail = mem.available // (2**20) # MB
        lines.append(f"RAM: {mem_avail} MB available out of {mem_total} MB.")
    except Exception:
        logger.warning("Memory info unavailable", exc_info=True)
        lines.append("Could not read memory info.")

    # 3. Disk space
    try:
        disk = psutil.disk_usage(DISK_PATH)
        total_gb = disk.total // (2**30)
        free_gb = disk.free // (2**30)
        free_mb = (disk.free % (2**30)) // (2**20)
        lines.append(
            f"Disk ({DISK_PATH}): {free_gb} GB {free_mb} MB free of {total_gb} GB "
            f"({disk.percent:.1f}% used)."
        )
    except Exception:
        logger.warning("Disk usage unavailable", exc_info=True)
        lines.append("Could not read disk usage.")

    # 4. Uptime
    try:
        uptime_seconds = time.time() - psutil.boot_time()
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
