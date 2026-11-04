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
