{
  lib,
  runCommand,
  writeText,
  makeWrapper,
  nativePython,
  geckodriver,
  original,
  sdk,
  fontConfig,
  nix,
  gh,
  cacert,
  nixpkgsSrc,
  purifierSrc,
}:
let
  integration = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      (lib.fileset.fileFilter (file: file.hasExt "py") ../firefox_purifier)
      (lib.fileset.fileFilter (file: file.hasExt "py" || file.hasExt "cfg") ../native)
      (lib.fileset.fileFilter (file: file.hasExt "nix") ./.)
    ];
  };
  bootstrap = writeText "firefox-purifier-main.py" "import os,runpy,sys; sys.path.insert(0, ${builtins.toJSON integration}); sys.argv[0]=os.environ['FIREFOX_PURIFIER_COMMAND']; runpy.run_module('firefox_purifier.main',run_name='__main__')";
  realize = writeText "firefox-purifier-realize.nix" ''
    { lockPath, projectPath, target ? "environment" }:
    let
      pkgs = import (builtins.storePath "${nixpkgsSrc}") {};
      scope = import ${integration}/nix/scope.nix {
        inherit pkgs;
        nixpkgsSrc = builtins.storePath "${nixpkgsSrc}";
        purifierSrc = builtins.storePath "${purifierSrc}";
      };
      lockFile = builtins.toPath lockPath;
      src = if target == "environment" then builtins.toPath projectPath else builtins.path {
        path = builtins.toPath projectPath;
        name = "firefox-project";
        filter = path: type: !(builtins.elem (baseNameOf path) [ ".git" ".firefox-purifier" "__pycache__" "result" "output" ]);
      };
      build = scope.buildFirefoxProject { inherit src lockFile; };
    in if target == "environment" then scope.environment { lock = scope.readLock { inherit src lockFile; }; }
       else if target == "project" then build.packages.project
       else if target == "release" then build.release
       else throw "Unknown FIREFOX purifier target"
  '';
in
runCommand "firefox-purifier" { nativeBuildInputs = [ makeWrapper ]; } ''
  mkdir -p "$out/bin"
  for name in firefox-purifier firefox; do
    makeWrapper ${nativePython}/bin/python "$out/bin/$name" \
      --add-flags ${bootstrap} \
      --set FIREFOX_PURIFIER_COMMAND "$name" \
      --set FIREFOX_PURIFIER_NATIVE ${integration}/native \
      --set FIREFOX_PURIFIER_ORIGINAL ${original} \
      --set FIREFOX_PURIFIER_PYTHON ${nativePython}/bin/python3 \
      --set FIREFOX_PURIFIER_GECKODRIVER ${geckodriver}/bin/geckodriver \
      --set FIREFOX_PURIFIER_SDK ${sdk} \
      --set FIREFOX_PURIFIER_FONTS ${fontConfig} \
      --set FIREFOX_PURIFIER_REALIZE ${realize} \
      --set-default FIREFOX_PURIFIER_GH ${gh}/bin/gh \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set-default NIX_SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --prefix PATH : ${
        lib.makeBinPath [
          nix
          gh
        ]
      }
  done
''
