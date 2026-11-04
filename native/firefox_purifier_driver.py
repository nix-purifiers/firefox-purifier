"""Launch native Firefox and call its original privileged add-on interfaces."""

import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from firefox_purifier_session import private_environment
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service


@contextmanager
def browser(root, sdk, *, environment=None, profile=None, network=True):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    env, _bus = private_environment(
        root, os.environ.copy(), os.environ["FIREFOX_PURIFIER_FONTS"]
    )
    for key in [
        "FIREFOX_PURIFIER_ENVIRONMENT",
        "FIREFOX_PURIFIER_STARTUP",
        "MOZ_APP_DATA",
        "MOZILLA_FIVE_HOME",
    ]:
        env.pop(key, None)
    env.update(
        DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(root / "no-session-bus"),
        MOZ_ENABLE_WAYLAND="0",
        MOZ_DBUS_REMOTE="0",
    )
    if environment is not None:
        env["FIREFOX_PURIFIER_ENVIRONMENT"] = str(Path(environment).resolve())
        env["FIREFOX_PURIFIER_STARTUP"] = str(root / "startup.json")
    profile = Path(profile or root / "profile").resolve()
    profile.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.binary_location = str(Path(sdk) / "bin/firefox")
    for argument in ["--headless", "--no-remote", "--profile", str(profile)]:
        options.add_argument(argument)
    options.accept_insecure_certs = False
    # RemoteAgent otherwise replaces Firefox's AMO endpoint with a test URL.
    options.set_preference("remote.prefs.recommended", False)
    options.set_preference("browser.shell.checkDefaultBrowser", False)
    proxy = urlsplit(os.environ.get("HTTPS_PROXY", os.environ.get("HTTP_PROXY", "")))
    options.set_preference("network.proxy.type", 1 if network and proxy.hostname else 0)
    if network and proxy.hostname:
        for scheme in ["http", "ssl"]:
            options.set_preference("network.proxy." + scheme, proxy.hostname)
            options.set_preference(
                "network.proxy." + scheme + "_port", proxy.port or 80
            )
        options.set_preference("network.proxy.no_proxies_on", "localhost,127.0.0.1")
    for variable in ["NO_PROXY", "no_proxy"]:
        os.environ[variable] = os.environ.get(variable, "") + ",localhost,127.0.0.1"
    service = Service(
        executable_path=os.environ["FIREFOX_PURIFIER_GECKODRIVER"],
        service_args=["--allow-system-access"],
        env=env,
        log_output=str(root / "geckodriver.log"),
    )
    with webdriver.Firefox(options=options, service=service) as driver:
        driver.set_script_timeout(180)
        yield driver


def native(driver, script, *arguments):
    driver.set_context("chrome")
    result = driver.execute_async_script(
        "const args=Array.from(arguments),done=args.pop();"
        "(async()=>{" + script + "})().then(value=>done({ok:true,value}),"
        "error=>done({ok:false,error:String(error),stack:error.stack}));",
        *arguments,
    )
    if not result["ok"]:
        raise ValueError(result.get("stack") or result["error"])
    return result["value"]
