"""Run native GUI jobs with private desktop services and pinned fonts."""

import os
import secrets
import signal
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def private_environment(root, base, fonts):
    root = Path(root).resolve()
    env = base.copy()
    for key in [
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "WAYLAND_SOCKET",
        "DBUS_SESSION_BUS_ADDRESS",
        "DBUS_STARTER_ADDRESS",
        "DBUS_STARTER_BUS_TYPE",
        "SESSION_MANAGER",
        "AT_SPI_BUS_ADDRESS",
        "GTK_MODULES",
        "GTK3_MODULES",
        "GTK_PATH",
        "QT_QPA_PLATFORMTHEME",
        "XDG_ACTIVATION_TOKEN",
        "DESKTOP_STARTUP_ID",
        "NODE_OPTIONS",
        "NODE_PATH",
        "ELECTRON_RUN_AS_NODE",
    ]:
        env.pop(key, None)
    for key, name in [
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ]:
        directory = root / name
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        env[key] = str(directory)
    env.update(
        FONTCONFIG_FILE=str(fonts),
        GDK_BACKEND="x11",
        GTK_USE_PORTAL="0",
        NO_AT_BRIDGE="1",
        LIBGL_ALWAYS_SOFTWARE="1",
        GSETTINGS_BACKEND="memory",
        DBUS_SYSTEM_BUS_ADDRESS="unix:path=" + str(root / "no-system-bus"),
        ELECTRON_OZONE_PLATFORM_HINT="x11",
    )
    bus = ET.Element("busconfig")
    ET.SubElement(bus, "type").text = "session"
    ET.SubElement(bus, "listen").text = (
        "unix:abstract=firefox-purifier-" + secrets.token_hex(12)
    )
    ET.SubElement(bus, "auth").text = "EXTERNAL"
    policy = ET.SubElement(bus, "policy", context="default")
    for attr in ["own", "send_destination", "receive_sender"]:
        ET.SubElement(policy, "allow", {attr: "*"})
    file = root / "bus.conf"
    ET.ElementTree(bus).write(file, encoding="UTF-8", xml_declaration=True)
    return env, file


def session(arguments, env, bus, xvfb, dbus, *, cwd=None):
    args = [
        str(Path(xvfb) / "bin/xvfb-run"),
        "-a",
        str(Path(dbus) / "bin/dbus-run-session"),
        "--dbus-daemon=" + str(Path(dbus) / "bin/dbus-daemon"),
        "--config-file=" + str(bus),
        "--",
        *map(str, arguments),
    ]
    process = subprocess.Popen(args, env=env, cwd=cwd, start_new_session=True)
    try:
        return process.wait()
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
