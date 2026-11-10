{
  lib,
  purifier,
  runCommand,
  python3,
  nativePython,
  geckodriver,
  environment,
  readLock,
  fontConfig,
  gnutar,
  gzip,
}:
{
  src,
  lockFile ? src + "/firefox-purifier.lock.json",
  script ? "build.py",
  fetchers ? { },
  doCheck ? false,
  checkCommand ? "",
  resourceRoots ? { },
  resourceDependencies ? [ ],
}:
let
  lock = readLock { inherit src lockFile; };
  profile = environment { inherit lock fetchers; };
  driver = lib.fileset.toSource {
    root = ../native;
    fileset = lib.fileset.unions [
      ../native/firefox_purifier_run_project.py
      ../native/firefox_purifier_session.py
      ../native/firefox_purifier_driver.py
    ];
  };
  projectSource = lib.cleanSourceWith {
    inherit src;
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        ".git"
        ".firefox-purifier"
        "__pycache__"
        "result"
        "output"
      ]);
  };
  builtProject = runCommand "firefox-project" { } ''
    export FIREFOX_PURIFIER_ENVIRONMENT=${profile}
    export FIREFOX_PURIFIER_FONTS=${fontConfig}
    export FIREFOX_PURIFIER_GECKODRIVER=${geckodriver}/bin/geckodriver
    export FIREFOX_PURIFIER_OUTPUT="$out" FIREFOX_PURIFIER_STATE="$TMPDIR/firefox-run"
    mkdir -p "$out"
    cp -r ${projectSource} project
    chmod -R u+w project
    cd project
    export FIREFOX_PURIFIER_PROJECT="$PWD" FIREFOX_PURIFIER_SCRIPT="$PWD/"${lib.escapeShellArg script}
    ${nativePython}/bin/python ${driver}/firefox_purifier_run_project.py "$PWD" "$FIREFOX_PURIFIER_SCRIPT" "$FIREFOX_PURIFIER_STATE" ${profile} "$out"
    ${lib.optionalString doCheck checkCommand}
  '';
  projections = lib.optionalAttrs (resourceRoots != { }) (
    purifier.resourceProjections {
      producer = builtProject;
      roots = resourceRoots;
      dependencies = resourceDependencies;
      inherit runCommand python3;
    }
  );
  project = builtProject // {
    inherit projections;
  };
  release =
    runCommand "firefox-project-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        mkdir -p "$out"
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -cf - -C ${project} . | gzip -n > "$out/firefox-project.tar.gz"
      '';
in
{
  packages = {
    default = project;
    inherit project;
    environment = profile;
  };
  tests = project;
  inherit release projections;
  fetches = lock.entries;
}
