{
  lib,
  runCommand,
  writeText,
  fetchurl,
  fetchgit,
  python3,
  nativePython,
  original,
  makeSdk,
  purifier,
  sdk,
  fontConfig,
  geckodriver,
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  archives = purifier.tree (
    {
      name = "firefox-extension-archives";
      entries = checked.entries;
      inherit
        runCommand
        writeText
        fetchurl
        fetchgit
        python3
        ;
    }
    // fetchers
  );
  lockedSdk = makeSdk (map (entry: entry.id) checked.entries);
  request = writeText "firefox-native-install.json" (
    builtins.toJSON {
      action = "install";
      entries = checked.entries;
      metadata = checked.data.native.metadata;
      archives = builtins.listToAttrs (
        map (entry: {
          name = entry.path;
          value = "${archives}/${entry.path}";
        }) checked.entries
      );
    }
  );
  driver = lib.fileset.toSource {
    root = ../native;
    fileset = lib.fileset.unions [
      ../native/firefox_purifier_helper.py
      ../native/firefox_purifier_driver.py
      ../native/firefox_purifier_session.py
    ];
  };
  manifest = writeText "firefox-lock.json" (builtins.toJSON checked.data);
in
assert lib.assertMsg (
  checked.data.sdk == sdk
) "Firefox SDK changed; run firefox-purifier lock --update";
runCommand "firefox-locked-extensions" { } ''
  mkdir -p "$out/empty"
  export FIREFOX_PURIFIER_ORIGINAL=${original} FIREFOX_PURIFIER_FONTS=${fontConfig}
  export FIREFOX_PURIFIER_GECKODRIVER=${geckodriver}/bin/geckodriver
  ${python3}/bin/python3 -c 'import json,sys;from pathlib import Path;v=json.loads(Path(sys.argv[1]).read_text());v["output"]=sys.argv[2];Path(sys.argv[3]).write_text(json.dumps(v))' ${request} "$out" "$TMPDIR/request.json"
  ${nativePython}/bin/python3 ${driver}/firefox_purifier_helper.py "$TMPDIR/session" "$TMPDIR/request.json" "$TMPDIR/response.json" > "$TMPDIR/helper.log" 2>&1 || { cat "$TMPDIR/helper.log"; exit 1; }
  ln -s ${archives} "$out/archives"
  ln -s ${lockedSdk} "$out/sdk"
  ln -s ${manifest} "$out/lock.json"
''
