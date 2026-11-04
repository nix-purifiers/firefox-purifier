{ original, lib }:
identities:
let
  driver = lib.fileset.toSource {
    root = ../native;
    fileset = ../native/guard.cfg;
  };
in
original.override {
  extraAutoConfig = ''pref("general.config.sandbox_enabled", false);'';
  extraPrefs = builtins.readFile (driver + "/guard.cfg");
  extraPolicies = {
    ExtensionSettings = {
      "*".installation_mode = "blocked";
    }
    // lib.genAttrs identities (_: {
      installation_mode = "allowed";
      updates_disabled = true;
    });
    DisableSystemAddonUpdate = true;
  };
}
