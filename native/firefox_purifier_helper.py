"""Capture and replay through Firefox's repository, signature checker and installer."""

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from firefox_purifier_driver import browser, native

INSTALL = """
const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
function publicAddon(addon){
 if(addon.type!=='extension'||!addon.isCompatible||
    ![AddonManager.SIGNEDSTATE_SIGNED,AddonManager.SIGNEDSTATE_PRIVILEGED].includes(addon.signedState))
  throw Error('A compatible Mozilla-signed WebExtension is required');
 return {id:addon.id,version:addon.version,type:addon.type,
         signedState:addon.signedState,compatible:addon.isCompatible};
}
async function installed(install){
 await install.install();
 const addon=await AddonManager.getAddonByID(install.addon.id);
 const metadata=publicAddon(addon);
 if(!addon.isActive)throw Error('Native Firefox did not activate '+addon.id);
 const file=addon.getResourceURI('').QueryInterface(Ci.nsIJARURI)
   .JARFile.QueryInterface(Ci.nsIFileURL).file.path;
 return {metadata,file};
}
"""


def main():
    root, request_file, response_file = map(Path, sys.argv[1:])
    request = json.loads(request_file.read_text())
    root.mkdir(parents=True, exist_ok=True)
    capture = request["action"] == "capture"
    with browser(
        root, os.environ["FIREFOX_PURIFIER_ORIGINAL"], network=capture
    ) as driver:
        version = native(driver, "return Services.appinfo.version;")
        if version != "159.0":
            raise ValueError("This Firefox provider requires Firefox 159.0")
        if capture:
            records = native(
                driver,
                INSTALL
                + """
const {AddonRepository}=ChromeUtils.importESModule('resource://gre/modules/addons/AddonRepository.sys.mjs');
const wanted=args[0];
if(!wanted.length)return [];
const catalog=await AddonRepository.getAddonsByIDs(wanted);
const results=[];
for(const id of wanted){
 const record=catalog.find(addon=>addon.id===id);
 if(!record?.sourceURI)throw Error('Native Firefox catalog entry missing: '+id);
 const install=await AddonManager.getInstallForURL(record.sourceURI.spec);
 const result=await installed(install);
 if(result.metadata.id!==id||result.metadata.version!==record.version)
  throw Error('Native catalog/install identity mismatch');
 results.push({...result,repository:record.toJSON(),url:record.sourceURI.spec});
}
return results;
""",
                request["extensions"],
            )
            result = {"entries": [], "metadata": {}, "repository": {}}
            for record in records:
                metadata = record["metadata"]
                identity = metadata["id"]
                data = Path(record["file"]).read_bytes()
                result["entries"].append(
                    {
                        "id": identity,
                        "path": identity + ".xpi",
                        "url": record["url"],
                        "bytesSha256": hashlib.sha256(data).hexdigest(),
                    }
                )
                result["metadata"][identity] = metadata
                result["repository"][identity] = record["repository"]
        else:
            records = native(
                driver,
                INSTALL
                + """
const results=[];
for(const entry of args[0].entries){
 const file=Cc['@mozilla.org/file/local;1'].createInstance(Ci.nsIFile);
 file.initWithPath(args[0].archives[entry.path]);
 const install=await AddonManager.getInstallForFile(file);
 const result=await installed(install);
 if(result.metadata.id!==entry.id)throw Error('Native installation ID mismatch');
 results.push(result);
}
return results;
""",
                request,
            )
            output = Path(request["output"])
            (output / "extensions").mkdir(parents=True, exist_ok=True)
            selected = {}
            entries = {entry["id"]: entry for entry in request["entries"]}
            for record in records:
                identity = record["metadata"]["id"]
                if record["metadata"] != request["metadata"][identity]:
                    raise ValueError("Native Firefox metadata differs from the lock")
                archive = request["archives"][entries[identity]["path"]]
                if Path(record["file"]).read_bytes() != Path(archive).read_bytes():
                    raise ValueError("Native Firefox installer changed the XPI bytes")
                relative = "extensions/" + identity + ".xpi"
                shutil.copyfile(record["file"], output / relative)
                selected[identity] = {"path": relative, "native": record["metadata"]}
            (output / "manifest.json").write_text(
                json.dumps({"selected": selected}, sort_keys=True)
            )
            result = {"installed": sorted(selected)}
    response_file.write_text(json.dumps(result))


if __name__ == "__main__":
    main()
