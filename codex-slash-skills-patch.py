#!/usr/bin/env python3
"""
Restore "/" slash-menu skill invocation in Codex Desktop (ChatGPT.app) on macOS.

Target tested version: 26.1117.31558 (arm64 macOS).
Zero third-party Python dependencies required.
"""

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BLOCK_SIZE = 4 * 1024 * 1024
FUSE_SENTINEL = b"dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX"
FUSE_ASAR_INTEGRITY_INDEX = 4
DEFAULT_BACKUP_DIR = Path.home() / ".codex-slash-patch" / "backups"

ENTITLEMENTS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.app-sandbox</key>
  <false/>
  <key>com.apple.security.automation.apple-events</key>
  <true/>
  <key>com.apple.security.cs.allow-jit</key>
  <true/>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
  <true/>
  <key>com.apple.security.cs.disable-library-validation</key>
  <true/>
  <key>com.apple.security.device.audio-input</key>
  <true/>
  <key>com.apple.security.device.camera</key>
  <true/>
  <key>com.apple.security.files.user-selected.read-write</key>
  <true/>
  <key>com.apple.security.network.client</key>
  <true/>
  <key>com.apple.security.personal-information.calendars</key>
  <true/>
</dict>
</plist>
"""

MARKER_CODEX = "function id_slash_skills("
MARKER_WORK = 'triggers:["/","@"],requiresEmptyComposer:!1,Icon:{assets:{16:n2.S,20:n3.Z}}'
MARKER_BROWSER = 'searchAliases:[e.name],triggers:["/","@","$"],requiresEmptyComposer:!1'


def default_app_path() -> Path:
    for candidate in (Path("/Applications/ChatGPT.app"), Path("/Applications/Codex.app")):
        if candidate.exists():
            return candidate
    return Path("/Applications/ChatGPT.app")


def read_app_version(app_path: Path) -> str:
    plist_path = app_path / "Contents/Info.plist"
    if not plist_path.exists():
        return "unknown"
    with open(plist_path, "rb") as f:
        pl = plistlib.load(f)
    return str(pl.get("CFBundleShortVersionString", "unknown"))


def compute_integrity(data: bytes) -> dict:
    full_hash = hashlib.sha256(data).hexdigest()
    blocks = [
        hashlib.sha256(data[off : off + BLOCK_SIZE]).hexdigest()
        for off in range(0, len(data), BLOCK_SIZE)
    ]
    if not blocks:
        blocks.append(hashlib.sha256(b"").hexdigest())
    return {
        "algorithm": "SHA256",
        "hash": full_hash,
        "blockSize": BLOCK_SIZE,
        "blocks": blocks,
    }


def read_asar_index(asar_path: Path):
    with open(asar_path, "rb") as f:
        _, u1, _, u3 = struct.unpack("<IIII", f.read(16))
        header_bytes = f.read(u3)
        base = 8 + u1
        f.seek(0, os.SEEK_END)
        total_size = f.tell()
    tree = json.loads(header_bytes.decode("utf-8"))
    return tree, header_bytes, base, total_size - base


def read_asar_entry(asar_path: Path, base: int, meta: dict) -> bytes:
    with open(asar_path, "rb") as f:
        f.seek(base + int(meta["offset"]))
        return f.read(meta["size"])


def find_target_chunks(asar_path: Path, base: int, assets: dict) -> dict:
    targets = {"codex": None, "work": None, "browser": None}
    with open(asar_path, "rb") as f:
        for name, meta in assets.items():
            if not name.endswith(".js") or "offset" not in meta:
                continue
            f.seek(base + int(meta["offset"]))
            blob = f.read(meta["size"])
            if targets["codex"] is None and b"composer.planSkillSlashCommand.title" in blob:
                targets["codex"] = name
            if (
                targets["work"] is None
                and b"composer.atMentionList.skills" in blob
                and b"insertSkillMentionAtSelection" in blob
            ):
                targets["work"] = name
            if (
                targets["browser"] is None
                and b"browserSkills.commandGroup" in blob
                and b"browser-skill-" in blob
            ):
                targets["browser"] = name
            if all(targets.values()):
                break
    return targets


def patch_codex_composer(src: str) -> tuple[str, bool]:
    if MARKER_CODEX in src:
        return src, False
    old = (
        'function id(e){let t,n,l=(0,a.c)(11),{composerMode:r,conversationId:i,hostId:s,'
        'isPlanModeActive:c,onEnablePlanMode:u,providePlanCommand:m,roots:p}=e,'
        'h=(0,d.Ul)(r7.g)&&s===nK.fI&&"cloud"!==r;l[0]!==h?(t={enabled:h},l[0]=h,l[1]=t):t=l[1];'
        'let{skills:f,isError:g,isLoading:v}=(0,ie.a)(p,s,t);'
        'return l[2]!==h||l[3]!==i||l[4]!==g||l[5]!==v||l[6]!==c||l[7]!==u||l[8]!==m||l[9]!==f?'
        '(n=m?(0,o.jsx)(ir,{conversationId:i,isSkillLoading:!c&&h&&v,onEnablePlanMode:u,'
        'skill:!h||c||g||v?void 0:f.find(ic)}):null,l[2]=h,l[3]=i,l[4]=g,l[5]=v,l[6]=c,l[7]=u,'
        'l[8]=m,l[9]=f,l[10]=n):n=l[10],n}function ic(e){return e.enabled&&(0,r9.HS)(e)}'
    )
    if src.count(old) != 1:
        raise RuntimeError(
            f"Unsupported Codex composer chunk structure (expected 1 match, got {src.count(old)}). "
            "Your app version may differ from 26.1117.31558."
        )
    new = (
        'function id(e){let t,n,l=(0,a.c)(11),{composerMode:r,conversationId:i,hostId:s,'
        'isPlanModeActive:c,onEnablePlanMode:u,providePlanCommand:m,roots:p}=e,'
        'h=(0,d.Ul)(r7.g)&&s===nK.fI&&"cloud"!==r;l[0]!==h?(t={enabled:h},l[0]=h,l[1]=t):t=l[1];'
        'let{skills:f,isError:g,isLoading:v}=(0,ie.a)(p,s,t);'
        'return l[2]!==h||l[3]!==i||l[4]!==g||l[5]!==v||l[6]!==c||l[7]!==u||l[8]!==m||l[9]!==f?'
        '(n=m?(0,o.jsx)(ir,{conversationId:i,isSkillLoading:!c&&h&&v,onEnablePlanMode:u,'
        'skill:!h||c||g||v?void 0:f.find(ic)}):null,l[2]=h,l[3]=i,l[4]=g,l[5]=v,l[6]=c,l[7]=u,'
        'l[8]=m,l[9]=f,l[10]=n):n=l[10],'
        '(0,o.jsxs)(o.Fragment,{children:[n,(0,o.jsx)(id_slash_skills,{roots:p,hostId:s,'
        'conversationId:i,composerMode:r})]})}'
        'function id_slash_skills(e){'
        'let{roots:p,hostId:s,conversationId:i,composerMode:r}=e,'
        'en="cloud"!==r,'
        'opts=h.useMemo(()=>({enabled:en,conversationId:i}),[en,i]),'
        '{skills:sk}=(0,ie.a)(p,s,opts),'
        'ctrl=(0,nl.a$)(),'
        'intl=(0,f.A)(),'
        'icon=h.useMemo(()=>{try{return(0,n("lp74").h)()}catch{return void 0}},[]),'
        'cmds=h.useMemo(()=>{'
        'if(!en||!Array.isArray(sk)||0===sk.length)return[];'
        'let grp=intl.formatMessage({id:"composer.atMentionList.skills",defaultMessage:"Skills"}),'
        'seenPath=new Set,seenName=new Set,out=[];'
        'for(let t of sk){'
        'if(!t||!t.enabled||("isPublic"in t&&!1===t.isPublic)||seenPath.has(t.path))continue;'
        'seenPath.add(t.path);'
        'let sid=seenName.has(t.name)?"skill:"+t.name+":"+t.path:"skill:"+t.name;'
        'seenName.add(t.name);'
        'let desc=t.interface?.shortDescription?.trim()||t.short_description||t.shortDescription||t.description||"";'
        'out.push({id:sid,title:(0,r9.nf)(t),description:desc,searchAliases:[t.name],'
        'triggers:["/"],requiresEmptyComposer:!1,Icon:icon,group:grp,'
        'onSelect:async()=>{ctrl.insertSkillMentionAtSelection(t)},'
        'onSelectFromInlineSlash:async e=>{ctrl.insertMention((0,ia.GZ)(t),e)}})}'
        'return out.sort((e,t)=>e.title.localeCompare(t.title))'
        '},[en,sk,ctrl,intl,icon]),'
        'deps=h.useMemo(()=>[sk,ctrl,intl,p,s,en],[sk,ctrl,intl,p,s,en]);'
        'return(0,lH.KS)(cmds,deps),null}'
        'function ic(e){return e.enabled&&(0,r9.HS)(e)}'
    )
    return src.replace(old, new, 1), True


def patch_work_composer(src: str) -> tuple[str, bool]:
    if MARKER_WORK in src:
        return src, False
    old = (
        't=n5()(n7()(l.filter(ir),io),ia).map(t=>({id:' + chr(96) + 'skill:${t.path}' + chr(96) + ',title:(0,n9.nf)(t),'
        'description:(0,n8.a)(t),triggers:["@"],requiresEmptyComposer:!1,'
        'Icon:{assets:{16:n2.S,20:n3.Z}},group:e,onSelect:async()=>{s.insertSkillMentionAtSelection(t)}}))'
    )
    if src.count(old) != 1:
        raise RuntimeError(
            f"Unsupported Work composer chunk structure (expected 1 match, got {src.count(old)})."
        )
    new = (
        't=n5()(n7()(l.filter(ir),io),ia).map(t=>({id:"skill:"+t.name+":"+t.path,title:(0,n9.nf)(t),'
        'description:(0,n8.a)(t),searchAliases:[t.name],triggers:["/","@"],requiresEmptyComposer:!1,'
        'Icon:{assets:{16:n2.S,20:n3.Z}},group:e,onSelect:async()=>{s.insertSkillMentionAtSelection(t)},'
        'onSelectFromInlineSlash:async e=>{s.insertMention((0,n("YWcr").GZ)(t),e)}}))'
    )
    return src.replace(old, new, 1), True


def patch_browser_skills(src: str) -> tuple[str, bool]:
    if MARKER_BROWSER in src:
        return src, False
    old = (
        'searchAliases:[e.name],triggers:["@","$"],requiresEmptyComposer:!1,'
        'group:J.formatMessage({id:"browserSkills.commandGroup",defaultMessage:"Skills"}),'
        'leftAccessory:(0,a.jsx)(S.f,{skill:e,variant:"menu"}),'
        'onSelect:async()=>{null!=X&&(G.set(w.l,!1),K.insertMentionAtSelection({kind:"browser-skill",'
        'name:(0,k.Fj)(e),...(0,u.$m)(e),path:(0,c.z6)(e.id,X),description:e.description,'
        'iconSmall:(0,I.D)(e,Z)}),K.focus())}'
    )
    if src.count(old) != 1:
        raise RuntimeError(
            f"Unsupported BrowserSkills chunk structure (expected 1 match, got {src.count(old)})."
        )
    new = (
        'searchAliases:[e.name],triggers:["/","@","$"],requiresEmptyComposer:!1,'
        'group:J.formatMessage({id:"browserSkills.commandGroup",defaultMessage:"Skills"}),'
        'leftAccessory:(0,a.jsx)(S.f,{skill:e,variant:"menu"}),'
        'onSelect:async()=>{null!=X&&(G.set(w.l,!1),K.insertMentionAtSelection({kind:"browser-skill",'
        'name:(0,k.Fj)(e),...(0,u.$m)(e),path:(0,c.z6)(e.id,X),description:e.description,'
        'iconSmall:(0,I.D)(e,Z)}),K.focus())},'
        'onSelectFromInlineSlash:async t=>{null!=X&&(G.set(w.l,!1),K.insertMention({kind:"browser-skill",'
        'name:(0,k.Fj)(e),...(0,u.$m)(e),path:(0,c.z6)(e.id,X),description:e.description,'
        'iconSmall:(0,I.D)(e,Z)},t),K.focus())}'
    )
    return src.replace(old, new, 1), True


def find_node_binary() -> str | None:
    for candidate in (shutil.which("node"), "/usr/local/bin/node", "/opt/homebrew/bin/node"):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def resolve_sign_identity(requested: str) -> tuple[str, str]:
    if requested != "auto":
        label = "ad-hoc (-)" if requested == "-" else requested
        return requested, label
    try:
        out = subprocess.check_output(
            ["security", "find-identity", "-v", "-p", "codesigning"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return "-", "ad-hoc (-)"
    matches = re.findall(r'\d+\)\s+([0-9A-F]{40})\s+"([^"]+)"', out)
    for sha1, name in matches:
        if "Apple Development" in name or "Developer ID Application" in name:
            return sha1, f"{name} ({sha1[:8]}...)"
    if matches:
        sha1, name = matches[0]
        return sha1, f"{name} ({sha1[:8]}...)"
    return "-", "ad-hoc (-)"


def clone_app_bundle(src: Path, dst: Path) -> None:
    # Prefer APFS copy-on-write clone (-cR) for speed and zero extra disk usage
    res = subprocess.run(["cp", "-cR", str(src), str(dst)], stderr=subprocess.DEVNULL)
    if res.returncode != 0:
        subprocess.run(["cp", "-R", str(src), str(dst)], check=True)


def find_framework_binary(app_path: Path) -> tuple[Path, Path, Path]:
    fw_dir = app_path / "Contents/Frameworks/Codex Framework.framework"
    matches = sorted((fw_dir / "Versions").glob("*/Codex Framework"))
    if not matches:
        raise RuntimeError(f"Codex Framework binary not found under {fw_dir}")
    fw_bin = matches[0]
    helpers_dir = fw_bin.parent / "Helpers"
    return fw_dir, fw_bin, helpers_dir


def read_fuse_byte(fw_bin: Path) -> str | None:
    data = fw_bin.read_bytes()
    idx = data.find(FUSE_SENTINEL)
    if idx == -1:
        return None
    fuse_off = idx + len(FUSE_SENTINEL) + 2
    return chr(data[fuse_off + FUSE_ASAR_INTEGRITY_INDEX])


def read_codesign_summary(app_path: Path) -> str:
    res = subprocess.run(
        ["codesign", "-dv", str(app_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines = []
    for line in (res.stderr + "\n" + res.stdout).splitlines():
        if line.startswith(("Authority=", "TeamIdentifier=", "Signature=")):
            lines.append(line)
    return ", ".join(lines) if lines else "unknown"


def cmd_status(args) -> int:
    app_path = Path(args.app).expanduser().resolve()
    if not app_path.exists():
        print(f"App not found: {app_path}", file=sys.stderr)
        return 1
    version = read_app_version(app_path)
    asar_path = app_path / "Contents/Resources/app.asar"
    tree, header_bytes, base, _ = read_asar_index(asar_path)
    assets = tree["files"]["webview"]["files"]["assets"]["files"]["async"]["files"]
    targets = find_target_chunks(asar_path, base, assets)
    checks = {}
    for key, marker in (("codex", MARKER_CODEX), ("work", MARKER_WORK), ("browser", MARKER_BROWSER)):
        fname = targets[key]
        if fname is None:
            checks[key] = "not-found"
        else:
            text = read_asar_entry(asar_path, base, assets[fname]).decode("utf-8", "replace")
            checks[key] = f"patched ({fname})" if marker in text else f"unpatched ({fname})"
    _, fw_bin, _ = find_framework_binary(app_path)
    fuse = read_fuse_byte(fw_bin)
    with open(app_path / "Contents/Info.plist", "rb") as f:
        pl = plistlib.load(f)
    plist_hash = pl.get("ElectronAsarIntegrity", {}).get("Resources/app.asar", {}).get("hash")
    actual_hash = hashlib.sha256(header_bytes).hexdigest()
    backup_dir = Path(args.backup_dir).expanduser()
    backups = sorted(p.name for p in backup_dir.glob("ChatGPT-*-orig.app")) if backup_dir.exists() else []

    print(f"App path       : {app_path}")
    print(f"App version    : {version}")
    print(f"Codex composer : {checks['codex']}")
    print(f"Work composer  : {checks['work']}")
    print(f"Browser skills : {checks['browser']}")
    print(f"ASAR header    : {'ok' if plist_hash == actual_hash else 'mismatch'}")
    print(f"ASAR fuse bit  : {fuse} (1=enforced, 0=disabled)")
    print(f"Code signature : {read_codesign_summary(app_path)}")
    print(f"Backups ({backup_dir}): {backups or 'none'}")
    return 0


def patch_staged_bundle(stage_path: Path, sign_request: str, dry_run: bool) -> None:
    asar_path = stage_path / "Contents/Resources/app.asar"
    plist_path = stage_path / "Contents/Info.plist"
    fw_dir, fw_bin, helpers_dir = find_framework_binary(stage_path)

    tree, _, old_base, old_payload_size = read_asar_index(asar_path)
    assets = tree["files"]["webview"]["files"]["assets"]["files"]["async"]["files"]
    targets = find_target_chunks(asar_path, old_base, assets)
    missing = [k for k, v in targets.items() if v is None]
    if missing:
        raise RuntimeError(f"Could not locate required webview chunks: {missing}")

    patch_specs = [
        ("codex", targets["codex"], patch_codex_composer),
        ("work", targets["work"], patch_work_composer),
        ("browser", targets["browser"], patch_browser_skills),
    ]

    node_bin = find_node_binary()
    appended_blobs = []
    cur_offset = old_payload_size
    any_changed = False

    with tempfile.TemporaryDirectory() as tmpdir:
        for label, fname, fn in patch_specs:
            meta = assets[fname]
            orig_bytes = read_asar_entry(asar_path, old_base, meta)
            patched_text, changed = fn(orig_bytes.decode("utf-8"))
            patched_bytes = patched_text.encode("utf-8")
            if node_bin:
                tmp_js = Path(tmpdir) / f"{fname}.mjs"
                tmp_js.write_bytes(patched_bytes)
                subprocess.run([node_bin, "--check", str(tmp_js)], check=True)
            status = "patched" if changed else "already patched"
            print(f"  [{label}] {fname}: {status} ({len(orig_bytes)} -> {len(patched_bytes)} bytes)")
            if changed:
                any_changed = True
                meta["size"] = len(patched_bytes)
                meta["offset"] = str(cur_offset)
                meta["integrity"] = compute_integrity(patched_bytes)
                cur_offset += len(patched_bytes)
                appended_blobs.append(patched_bytes)

        if dry_run:
            print("Dry-run succeeded. No files were modified.")
            return

        if not any_changed:
            print("All target chunks are already patched.")
            return

        new_header_bytes = json.dumps(tree, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        new_u3 = len(new_header_bytes)
        pad_len = (4 - (new_u3 % 4)) % 4
        new_u2 = 4 + new_u3 + pad_len
        new_u1 = 4 + new_u2
        new_header_hash = hashlib.sha256(new_header_bytes).hexdigest()

        tmp_asar = asar_path.with_suffix(".asar.tmp")
        with open(tmp_asar, "wb") as out_f, open(asar_path, "rb") as in_f:
            out_f.write(struct.pack("<IIII", 4, new_u1, new_u2, new_u3))
            out_f.write(new_header_bytes)
            out_f.write(b"\x00" * pad_len)
            in_f.seek(old_base)
            shutil.copyfileobj(in_f, out_f, length=8 * 1024 * 1024)
            for blob in appended_blobs:
                out_f.write(blob)
        os.replace(tmp_asar, asar_path)
        print(f"  Repacked app.asar (header SHA-256: {new_header_hash})")

        with open(plist_path, "rb") as f:
            pl = plistlib.load(f)
        if "ElectronAsarIntegrity" in pl and "Resources/app.asar" in pl["ElectronAsarIntegrity"]:
            pl["ElectronAsarIntegrity"]["Resources/app.asar"]["hash"] = new_header_hash
            with open(plist_path, "wb") as f:
                plistlib.dump(pl, f, fmt=plistlib.FMT_XML)
            print("  Updated Info.plist ElectronAsarIntegrity hash")

        fw_data = bytearray(fw_bin.read_bytes())
        idx = fw_data.find(FUSE_SENTINEL)
        if idx == -1:
            raise RuntimeError("Electron fuse sentinel not found in Codex Framework")
        fuse_off = idx + len(FUSE_SENTINEL) + 2
        fw_data[fuse_off + FUSE_ASAR_INTEGRITY_INDEX] = ord("0")
        fw_bin.write_bytes(fw_data)
        print("  Updated Electron ASAR integrity fuse in Codex Framework")

        ent_file = Path(tmpdir) / "entitlements.plist"
        ent_file.write_text(ENTITLEMENTS_XML, encoding="utf-8")
        cert, cert_label = resolve_sign_identity(sign_request)
        print(f"  Signing bundle with: {cert_label}")
        for helper in sorted(helpers_dir.glob("*.app")):
            subprocess.run(
                ["codesign", "--force", "--sign", cert, "--entitlements", str(ent_file), str(helper)],
                check=True,
                stderr=subprocess.DEVNULL,
            )
        subprocess.run(["codesign", "--force", "--sign", cert, str(fw_bin)], check=True, stderr=subprocess.DEVNULL)
        subprocess.run(["codesign", "--force", "--sign", cert, str(fw_dir)], check=True, stderr=subprocess.DEVNULL)
        subprocess.run(
            ["codesign", "--force", "--sign", cert, "--entitlements", str(ent_file), str(stage_path)],
            check=True,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(["codesign", "--verify", "--verbose=2", str(stage_path)], check=True, stderr=subprocess.DEVNULL)
        print("  Code signature verification passed")


def cmd_apply(args) -> int:
    app_path = Path(args.app).expanduser().resolve()
    if not app_path.exists():
        print(f"App not found: {app_path}", file=sys.stderr)
        return 1
    version = read_app_version(app_path)
    print(f"Target app: {app_path} (version {version})")

    if args.dry_run:
        patch_staged_bundle(app_path, args.sign, dry_run=True)
        return 0

    backup_dir = Path(args.backup_dir).expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"ChatGPT-{version}-orig.app"

    # Save original untouched backup once per version
    asar_path = app_path / "Contents/Resources/app.asar"
    tree, _, base, _ = read_asar_index(asar_path)
    assets = tree["files"]["webview"]["files"]["assets"]["files"]["async"]["files"]
    targets = find_target_chunks(asar_path, base, assets)
    already_patched = (
        targets["codex"] is not None
        and MARKER_CODEX in read_asar_entry(asar_path, base, assets[targets["codex"]]).decode("utf-8", "replace")
    )
    if already_patched:
        print("This app bundle is already patched. Nothing to do.")
        return 0

    if not backup_path.exists():
        print(f"Creating backup: {backup_path}")
        clone_app_bundle(app_path, backup_path)
    else:
        print(f"Keeping existing backup: {backup_path}")

    stamp = int(time.time())
    stage_path = app_path.parent / f".{app_path.stem}-slash-staging-{stamp}.app"
    displaced_path = Path(tempfile.gettempdir()) / f"{app_path.stem}-replaced-{version}-{stamp}.app"
    try:
        print(f"Staging bundle at: {stage_path}")
        clone_app_bundle(app_path, stage_path)
        patch_staged_bundle(stage_path, args.sign, dry_run=False)
        # Atomic directory swap so a currently running instance keeps its open inodes
        os.rename(app_path, displaced_path)
        try:
            os.rename(stage_path, app_path)
        except Exception:
            os.rename(displaced_path, app_path)
            raise
    except Exception:
        if stage_path.exists():
            shutil.rmtree(stage_path, ignore_errors=True)
        raise

    print("")
    print("Done! Quit ChatGPT/Codex completely (Cmd+Q) and reopen it to use '/' for skills.")
    print(f"Original backup saved at: {backup_path}")
    return 0


def cmd_restore(args) -> int:
    app_path = Path(args.app).expanduser().resolve()
    backup_dir = Path(args.backup_dir).expanduser().resolve()
    if args.backup:
        backup_path = Path(args.backup).expanduser().resolve()
    else:
        version = read_app_version(app_path)
        candidate = backup_dir / f"ChatGPT-{version}-orig.app"
        if candidate.exists():
            backup_path = candidate
        else:
            backups = sorted(backup_dir.glob("ChatGPT-*-orig.app")) if backup_dir.exists() else []
            if not backups:
                print(f"No backups found in {backup_dir}", file=sys.stderr)
                return 1
            backup_path = backups[-1]

    if not backup_path.exists():
        print(f"Backup not found: {backup_path}", file=sys.stderr)
        return 1

    stamp = int(time.time())
    stage_path = app_path.parent / f".{app_path.stem}-restore-staging-{stamp}.app"
    displaced_path = Path(tempfile.gettempdir()) / f"{app_path.stem}-patched-{stamp}.app"
    print(f"Restoring from: {backup_path}")
    clone_app_bundle(backup_path, stage_path)
    if app_path.exists():
        os.rename(app_path, displaced_path)
    try:
        os.rename(stage_path, app_path)
    except Exception:
        if displaced_path.exists() and not app_path.exists():
            os.rename(displaced_path, app_path)
        raise
    subprocess.run(["codesign", "--verify", "--verbose=2", str(app_path)], check=True, stderr=subprocess.DEVNULL)
    print(f"Restored {app_path} successfully. Quit (Cmd+Q) and reopen the app.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore '/' slash-menu skill invocation in Codex Desktop (macOS)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_apply = sub.add_parser("apply", help="Back up and patch Codex Desktop")
    p_apply.add_argument("--app", default=str(default_app_path()), help="Path to ChatGPT.app / Codex.app")
    p_apply.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR), help="Directory for original app backups")
    p_apply.add_argument("--sign", default="auto", help="Code signing identity: auto, -, or certificate name/SHA-1")
    p_apply.add_argument("--dry-run", action="store_true", help="Verify target chunks and syntax without writing files")
    p_apply.set_defaults(func=cmd_apply)

    p_status = sub.add_parser("status", help="Inspect current patch and signature status")
    p_status.add_argument("--app", default=str(default_app_path()), help="Path to ChatGPT.app / Codex.app")
    p_status.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR), help="Directory for original app backups")
    p_status.set_defaults(func=cmd_status)

    p_restore = sub.add_parser("restore", help="Restore the original unpatched app from backup")
    p_restore.add_argument("--app", default=str(default_app_path()), help="Path to ChatGPT.app / Codex.app")
    p_restore.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR), help="Directory for original app backups")
    p_restore.add_argument("--backup", default=None, help="Explicit path to a backup .app bundle")
    p_restore.set_defaults(func=cmd_restore)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
