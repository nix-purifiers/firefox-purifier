"""Check native immutable locations, bundled extensions and writable settings."""

import json

browser = globals()["driver"]
project = globals()["project"]
count = json.loads((project / "counter.json").read_text())
identity = "addon@darkreader.org"
browser.set_context("chrome")
state = browser.execute_async_script("""
const done=arguments[0];
(async()=>{
 const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
 const {XPIInternal}=ChromeUtils.importESModule('resource://gre/modules/addons/XPIProvider.sys.mjs');
 const addon=await AddonManager.getAddonByID('addon@darkreader.org');
 const location=XPIInternal.XPIStates.getLocation('app-profile');
 return {active:addon.isActive,signed:addon.signedState===AddonManager.SIGNEDSTATE_SIGNED,
  source:addon.getResourceURI('').spec,locked:location.locked,
  upgrades:!!(addon.permissions&AddonManager.PERM_CAN_UPGRADE),
  uninstall:!!(addon.permissions&AddonManager.PERM_CAN_UNINSTALL),
  updates:Services.policies.getExtensionSettings(addon.id).updates_disabled,
  builtin:(await AddonManager.getAllAddons()).filter(a=>a.isBuiltin).map(a=>a.id),
  previous:Services.prefs.getBoolPref('browser.tabs.warnOnClose',false),
  uuid:JSON.parse(Services.prefs.getStringPref('extensions.webextensions.uuids'))[addon.id]};
})().then(done,error=>done({error:String(error)}));
""")
assert state["active"] and state["signed"] and state["locked"], state
assert state["source"].startswith("jar:file:///nix/store/"), state
assert not state["upgrades"] and not state["uninstall"] and state["updates"], state
assert "formautofill@mozilla.org" in state["builtin"], state
if count > 1:
    assert state["previous"] == bool((count - 1) % 2)
browser.execute_script(
    "Services.prefs.setBoolPref('browser.tabs.warnOnClose',arguments[0]);",
    bool(count % 2),
)
browser.set_context("content")
browser.get("moz-extension://" + state["uuid"] + "/ui/popup/index.html")
previous = browser.execute_async_script(
    "const done=arguments[0];browser.storage.local.get('purifierProbe').then(done);"
)
assert previous == ({} if count == 1 else {"purifierProbe": count - 1}), previous
stored = browser.execute_async_script(
    "const value=arguments[0],done=arguments[1];browser.storage.local.set({purifierProbe:value}).then(()=>browser.storage.local.get('purifierProbe')).then(done);",
    count,
)
assert stored == {"purifierProbe": count}
