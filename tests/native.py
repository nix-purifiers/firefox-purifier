"""Ordinary Selenium, native profile locks, independent decoding and failed startup."""

import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

source = Path(__file__).resolve().parents[1]
cli, original, resources = (Path(value).resolve() for value in sys.argv[1:])
sys.path.insert(0, str(source / "native"))
from firefox_purifier_driver import browser, native
from firefox_purifier_session import private_environment

fixture = source / "examples/minimal"
os.environ.update(
    FIREFOX_PURIFIER_FONTS=str(resources / "fonts.conf"),
    FIREFOX_PURIFIER_GECKODRIVER=str(resources / "bin/geckodriver"),
    FIREFOX_PURIFIER_PROJECT=str(fixture),
)


def command(*arguments):
    result = subprocess.run(
        [cli / "bin/firefox-purifier", "--project", fixture, *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip())


with tempfile.TemporaryDirectory(prefix="firefox-native-test-") as temporary:
    root = Path(temporary)
    environment = command("prefetch")
    profile = root / "profile"
    with browser(root / "first", cli, profile=profile) as driver:
        result = native(
            driver,
            """
const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
const {XPIInternal}=ChromeUtils.importESModule('resource://gre/modules/addons/XPIProvider.sys.mjs');
const addon=await AddonManager.getAddonByID('addon@darkreader.org');
return {active:addon.isActive,source:addon.getResourceURI('').spec,
 locked:XPIInternal.XPIStates.getLocation('app-profile').locked,
 profile:Services.dirsvc.get('ProfD',Ci.nsIFile).path};
""",
        )
        assert result["active"] and result["locked"], result
        assert result["source"].startswith("jar:file:///nix/store/"), result
        assert result["profile"] == str(profile), result
        lock = profile / ".parentlock"
        inode = lock.lstat().st_ino
        env, _bus = private_environment(
            root / "second", os.environ.copy(), resources / "fonts.conf"
        )
        env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + str(root / "no-session")
        second = subprocess.run(
            [cli / "bin/firefox", "--headless", "--profile", profile, "about:blank"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
        )
        assert second.returncode != 0, second.stdout + second.stderr
        assert lock.lstat().st_ino == inode
        assert native(driver, "return 1;") == 1
    with browser(root / "reopen", cli, profile=profile) as driver:
        assert native(driver, "return 1;") == 1

    built = command("build")
    image = built / "page.png"
    expected = struct.unpack(">II", image.read_bytes()[16:24])
    with browser(root / "consumer", original, network=False) as driver:
        assert native(
            driver,
            "const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');return (await AddonManager.getAddonByID('addon@darkreader.org'))===null;",
        )
        driver.set_context("content")
        driver.get(image.as_uri())
        decoded = driver.execute_script(
            "const i=document.images[0];return [i.naturalWidth,i.naturalHeight];"
        )
        assert tuple(decoded) == expected and all(decoded), decoded

    fake = root / "invalid-environment"
    fake.mkdir()
    (fake / "sdk").symlink_to(environment / "sdk")
    state = root / "invalid-state"
    state.mkdir()
    worker = root / "invalid.py"
    worker.write_text(
        "import sys;sys.path.insert(0,sys.argv[1]);"
        "from firefox_purifier_gui import launch;"
        "raise SystemExit(launch(sys.argv[2],sys.argv[3],['--headless','about:blank']))"
    )
    failed = subprocess.run(
        [sys.executable, worker, source / "native", state, fake],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )
    assert failed.returncode != 0
    assert "Locked Firefox extension directory missing" in failed.stdout + failed.stderr
print(
    "Native wrapper, profile exclusion/reopen, independent PNG decode and failed startup pass"
)
