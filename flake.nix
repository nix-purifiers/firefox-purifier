{
  description = "firefox with locked, Nix-resolved add-ons";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      overlay = final: prev: {
        firefox-purifier = import ./nix/scope.nix {
          pkgs = final;
          nixpkgsSrc = nixpkgs;
          purifierSrc = purifier;
        };
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      packages = forAll (
        system:
        let
          p = (pkgsFor system).firefox-purifier;
        in
        {
          default = p.cli;
          firefox = p.original;
          gui-test-env =
            let
              pkgs = pkgsFor system;
            in
            pkgs.runCommand "firefox-test-environment" { } ''
              mkdir -p "$out/bin"
              ln -s ${
                pkgs.python3.withPackages (python: [
                  python.selenium
                  python.lz4
                ])
              }/bin/python3 "$out/bin/python3"
              ln -s ${pkgs.geckodriver}/bin/geckodriver "$out/bin/geckodriver"
              ln -s ${p.fontConfig} "$out/fonts.conf"
            '';
        }
      );
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/firefox-purifier";
        };
      });
      lib.firefox-purifier.readLock = import ./nix/read-lock.nix { lib = nixpkgs.lib; };
      checks = forAll (
        system:
        let
          p = (pkgsFor system).firefox-purifier;
          build = p.buildFirefoxProject {
            src = ./examples/minimal;
            doCheck = true;
            checkCommand = ''test -s "$out/page.png"'';
          };
        in
        {
          cli = p.cli;
          sdk = p.makeSdk (map (entry: entry.id) (p.readLock { src = ./examples/minimal; }).entries);
          inherit (build.packages) environment project;
          release = build.release;
        }
      );
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
    };
}
