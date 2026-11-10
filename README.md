# firefox-purifier

Use Firefox with locked, Nix-resolved WebExtensions.

## Quickstart

```sh
nix shell 'github:nix-purifiers/firefox-purifier'
```

Create `firefox-purifier.json` with Mozilla add-on IDs:

```json
{
  "extensions": ["addon@darkreader.org"]
}
```

Resolve the selection and open Firefox:

```sh
firefox-purifier lock --update
firefox https://example.org
```

Commit the selection and `firefox-purifier.lock.json`. Locked launches use a
persistent project profile under `.firefox-purifier/profile`. Firefox's profile
selection flags remain available, including profiles supplied by Selenium.
An occupied profile is refused instead of forwarding to a running browser.

Extension code is read directly from an immutable Nix location. Browser history,
preferences and extension storage remain writable. Native installation, updates
and temporary extension replacement are disabled while the lock applies.
Firefox's bundled extensions are retained; ordinary browsing remains available.

Without a lockfile, the wrapper prints a warning and starts ordinary Firefox.
Changed selections or SDKs require an explicit lock update.

## Updating

```sh
firefox-purifier lock --update
```

Capture uses Firefox's original Mozilla Add-ons repository client, downloader,
signature checker and installer. Nix retains those exact XPI bytes and replays
native installation before the lock is replaced. The provider accepts compatible
Mozilla-signed WebExtensions from the native catalog.

## Scripted projects

```sh
cd examples/minimal
firefox-purifier run build.py
```

The example serves the project source locally, lets the real Dark Reader
extension transform it and exports Firefox's native screenshot. Project scripts
receive `driver` (a Selenium Firefox driver), `project` and `output` globals.
They run with a separate persistent profile under `.firefox-purifier/run`.
Existing Selenium workflows can also select the supplied `firefox` binary.

## Nix builds

`firefox-purifier build` builds the scripted project in the Nix sandbox.
`firefox-purifier bundle` archives its outputs. External Nix definitions can use
`pkgs.firefox-purifier.buildFirefoxProject` from the overlay, with `src`,
`lockFile` and `script` (default `build.py`).

## Support

The current provider targets Firefox 159.0 on x86_64 Linux. It configures the
original native add-on manager with a read-only installation location and keeps
signature enforcement enabled. Startup metadata is revalidated through the
native parser so mutable caches cannot redirect extension code.

The scope is WebExtensions. Native messaging programs and downloaded components
such as DRM modules require separate providers. Application overrides (`-app`)
are unsupported.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).

## Public output resources

Select generated project output files explicitly:

```nix
project = pkgs.firefox-purifier.buildFirefoxProject {
  src = ./.;
  resourceRoots."public/file" = "generated-file";
};
```

`project.projections.resources` exposes the selected file directory and its
catalog; `project.projections.web.documentRoot` is the HTTP serving root,
and `project.projections.java-resources.classPath` is the resource JAR.
The same projections are attached to `project.packages.project`.
`resourceDependencies` accepts additional typed resource views. Empty
`resourceRoots` preserves existing output behavior.

Paths are relative to the native project output. Selection copies actual
export bytes. Unselected siblings stay outside the exported tree, and proof
metadata stays outside HTTP and JAR payloads. A selected directory includes
its contents, so select only
public generated files or directories. Missing files, traversal, and resource
collisions fail.

Checks run two genuine native producer inputs, compare every selected byte
with native files, serve them over HTTP, and load the JAR through an isolated
Java class loader with exact origin and hash checks. They exclude a real
private sibling and reject a genuine changed producer's JAR against the
original byte contract. Native producers, resource views, and consumers are
rebuilt directly.
