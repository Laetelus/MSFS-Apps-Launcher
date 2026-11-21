"""Add / check / remove this launcher's entry in MSFS's exe.xml.

exe.xml is the file MSFS reads at startup to know which add-on programs to run.
Everything here goes through a real XML parser (never string editing), keeps the
user's other entries and comments untouched, and is careful about failure:

    - the original file is backed up ONCE (exe.xml.MSFSLauncher.bak) before the first change
    - the new content is parsed again before it is written
    - after writing, the file is read back and checked
    - if anything goes wrong the file is put back exactly as it was (held in memory)
    - a file that is already broken is never modified

Windows only, standard library only.
"""
import codecs
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ADDON_NAME = "MSFS App Launcher"
ROOT_TAG = "SimBase.Document"
ADDON_TAG = "Launch.Addon"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ExeXmlError(Exception):
    """An error with a message that is fine to show to the user.
    damaged=True: exe.xml has a syntax error that add() (the Fix button) can work around."""
    damaged = False


# ---------------------------------------------------------------- locations

def installs():
    """MSFS data folders that exist on this PC (one entry per installation).

    exe.xml always lives in the sim's data folder, whatever drive the sim itself
    is installed on:
        Microsoft Store / Xbox app / Game Pass: %LOCALAPPDATA%\\Packages\\<package>\\LocalCache
        Steam:                                  %APPDATA%\\<Microsoft Flight Simulator [2024]>
    """
    local = os.environ.get("LOCALAPPDATA")
    roaming = os.environ.get("APPDATA")
    store = "Microsoft Store / Xbox"
    candidates = []
    # (id, sim, store, data folder, sim executable, URI that starts the sim)
    if local:
        pk = Path(local) / "Packages"
        candidates += [
            ("2024-store", "MSFS 2024", store, pk / "Microsoft.Limitless_8wekyb3d8bbwe" / "LocalCache",
             "FlightSimulator2024.exe", r"shell:AppsFolder\Microsoft.Limitless_8wekyb3d8bbwe!App"),
            ("2020-store", "MSFS 2020", store, pk / "Microsoft.FlightSimulator_8wekyb3d8bbwe" / "LocalCache",
             "FlightSimulator.exe", r"shell:AppsFolder\Microsoft.FlightSimulator_8wekyb3d8bbwe!App"),
        ]
    if roaming:
        candidates += [
            ("2024-steam", "MSFS 2024", "Steam", Path(roaming) / "Microsoft Flight Simulator 2024",
             "FlightSimulator2024.exe", "steam://rungameid/2537590"),
            ("2020-steam", "MSFS 2020", "Steam", Path(roaming) / "Microsoft Flight Simulator",
             "FlightSimulator.exe", "steam://rungameid/1250410"),
        ]
    return [{"id": i, "sim": sim, "store": st, "folder": folder, "exe": exe, "launch": uri}
            for i, sim, st, folder, exe, uri in candidates if folder.is_dir()]


def install_for_exe(exe_name):
    """The installation that runs this sim executable, or None.
    With both a Store and a Steam copy, prefer the one whose exe.xml starts this launcher."""
    matches = [i for i in installs() if i["exe"].lower() == (exe_name or "").lower()]
    for install in matches:
        try:
            if inspect(install["folder"]).get("state") == "ok":
                return install
        except Exception:
            pass
    return matches[0] if matches else None


def start_sim(install):
    """Start the sim through the Store app or Steam (does not wait for it)."""
    try:
        os.startfile(install["launch"])
    except OSError as exc:
        raise ExeXmlError(f"Could not start {install['sim']} ({install['store']}): {exc}") from exc


def exe_xml_path(folder):
    return Path(folder) / "exe.xml"


def _target():
    """What exe.xml must start.

    Packaged build: this exe itself, with --service.
    Source files:   python(w).exe running src/launcher.py (the python is found when adding).
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return {"frozen": True, "file": exe, "args": "--service"}
    script = Path(__file__).resolve().parent / "launcher.py"
    return {"frozen": False, "file": script, "args": f'"{script}"'}


def _norm(text):
    return str(text).replace("/", "\\").casefold()


def find_python():
    """A pythonw.exe that can run launcher.py (which needs the SimConnect package).

    Looks next to the Python running this GUI first, then on PATH, then the 'py' launcher.
    Each candidate is tested, so a bare Python (for example an embedded one) is skipped.
    """
    candidates = [Path(sys.executable).with_name("pythonw.exe")]
    found = shutil.which("pythonw")
    if found:
        candidates.append(Path(found))
    try:
        out = subprocess.run(["py", "-3", "-c", "import sys;print(sys.executable)"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=NO_WINDOW).stdout.strip()
        if out:
            candidates.append(Path(out).with_name("pythonw.exe"))
    except Exception:
        pass

    tried = set()
    for pyw in candidates:
        key = os.path.normcase(str(pyw))
        if key in tried or not pyw.is_file():
            continue
        tried.add(key)
        python = pyw.with_name("python.exe")
        if not python.is_file():
            continue
        try:
            ok = subprocess.run([str(python), "-c", "import SimConnect"], capture_output=True,
                                timeout=20, creationflags=NO_WINDOW).returncode == 0
        except Exception:
            ok = False
        if ok:
            return pyw
    raise ExeXmlError("No Python with the SimConnect package was found, so the launcher "
                      "could not be added. Install it with:  pip install SimConnect")


# ---------------------------------------------------------------- reading

def _parse(raw):
    """Parse exe.xml bytes. Comments and processing instructions are kept."""
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    try:
        root = ET.fromstring(raw, parser=parser)
    except ET.ParseError as exc:
        line, col = getattr(exc, "position", (0, 0))
        err = ExeXmlError(f"exe.xml has a syntax error (line {line}, column {col}): {exc}")
        err.damaged = True
        raise err from None
    if root.tag != ROOT_TAG:
        raise ExeXmlError(f"exe.xml is not a MSFS launch file (expected <{ROOT_TAG}>, found <{root.tag}>).")
    return root


def _load(path):
    """Returns (root, uses_crlf, has_bom)."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ExeXmlError(_os_message(exc, path, "read")) from None
    return _parse(raw), b"\r\n" in raw, raw.startswith(codecs.BOM_UTF8)


def _child_text(el, tag):
    c = el.find(tag)
    return (c.text or "").strip() if c is not None else ""


def _is_exact(el, target):
    """True when this entry starts exactly what we would add."""
    cmd = _norm(_child_text(el, "CommandLine"))
    if target["frozen"]:
        return _norm(_child_text(el, "Path")) == _norm(target["file"]) and "--service" in cmd
    return _norm(target["file"]) in cmd


def _find_ours(root, target):
    """Our entries in the file: [(element, exact)].  exact=True when it starts our launcher;
    exact=False when it only has our name (for example it points to a moved copy, or to the
    other kind of install: source files vs. packaged exe)."""
    found = []
    for el in root.findall(ADDON_TAG):
        if _is_exact(el, target):
            found.append((el, True))
        elif _child_text(el, "Name").casefold() == ADDON_NAME.casefold():
            found.append((el, False))
    return found


def _is_writable(path, folder):
    return os.access(path, os.W_OK) if path.exists() else os.access(folder, os.W_OK)


def inspect(folder):
    """Describe the state of exe.xml in `folder` for the UI.

    state:   "ok"    entry present and valid
             "none"  entry not added (or exe.xml not created yet)
             "error" something is wrong (see message)
    actions: what the user can do: "add", "fix", "remove" (empty when the file can't be changed)
    """
    path = exe_xml_path(folder)
    target = _target()
    res = {"path": str(path), "state": "none", "message": "Not added yet.", "actions": ["add"]}

    if not path.exists():
        res["message"] = "Not added yet (exe.xml doesn't exist; it will be created)."
    else:
        try:
            root, _, _ = _load(path)
        except ExeXmlError as exc:
            if exc.damaged:   # Fix keeps every readable entry and rebuilds the rest
                res.update(state="error", actions=["fix"],
                           message=f"{exc} Fix keeps every readable entry.")
                if not _is_writable(path, Path(folder)):
                    res["actions"] = []
                return res
            return {**res, "state": "error", "actions": [], "message": str(exc)}
        ours = _find_ours(root, target)
        if ours:
            el, exact = ours[0]
            prog = _child_text(el, "Path")
            problem = None
            if not exact:
                other = f"{prog} {_child_text(el, 'CommandLine')}".strip()
                problem = f"Points to a different launcher: {other or '(empty)'}"
            elif _child_text(el, "Disabled").lower() == "true":
                problem = "The entry is disabled in exe.xml."
            elif not prog or not Path(prog).is_file():
                problem = f"The program it starts was not found: {prog or '(empty)'}"
            elif not target["file"].is_file():
                problem = f"{target['file'].name} was not found at {target['file']}"
            if problem:
                res.update(state="error", message=problem, actions=["fix", "remove"])
            else:
                res.update(state="ok", message="Connected. MSFS will start the launcher.", actions=["remove"])

    if res["actions"] and not _is_writable(path, Path(folder)):
        res["actions"] = []
        res["message"] += " (exe.xml is read-only, so it can't be changed from here.)"
        if res["state"] == "none":
            res["state"] = "error"
    return res


# ---------------------------------------------------------------- writing

def _os_message(exc, path, verb):
    if isinstance(exc, PermissionError):
        return (f"Windows denied access while trying to {verb} {path}. Make sure the file isn't "
                "read-only and isn't open in another program.")
    return f"Could not {verb} {path}: {exc}"


def _indent_unit(root):
    m = re.search(r"\n([ \t]+)$", root.text or "")
    return m.group(1) if m else "    "


def _format(el, ind):
    """Indent a new element (and its children) like the rest of the file."""
    el.text = "\n" + ind * 2
    kids = list(el)
    for k in kids:
        k.tail = "\n" + ind * 2
    if kids:
        kids[-1].tail = "\n" + ind


def _new_entry(program, args, ind):
    el = ET.Element(ADDON_TAG)
    for tag, value in (("Name", ADDON_NAME), ("Disabled", "False"), ("ManualLoad", "False"),
                       ("Path", str(program)), ("CommandLine", args)):
        ET.SubElement(el, tag).text = value
    _format(el, ind)
    return el


def _append(root, el, ind):
    """Insert `el` right after the last </Launch.Addon>, aligned with the other entries.
    The closing </SimBase.Document> tag is never touched. Without any entry yet, the new
    one goes after the last child (or into an empty root)."""
    kids = list(root)
    addons = [k for k in kids if k.tag == ADDON_TAG]
    last = addons[-1] if addons else (kids[-1] if kids else None)
    if last is None:
        root.text = "\n" + ind
        el.tail = "\n"
        root.append(el)
        return
    el.tail = last.tail if (last.tail or "").strip() == "" and last.tail else "\n"
    last.tail = "\n" + ind          # line break + indent between the two entries
    root.insert(kids.index(last) + 1, el)


def _new_document(ind="    "):
    root = ET.Element(ROOT_TAG, {"Type": "Launch", "version": "1,0"})
    root.text = "\n" + ind
    descr = ET.SubElement(root, "Descr")
    descr.text, descr.tail = "Launch File", "\n" + ind
    name = ET.SubElement(root, "Filename")
    name.text, name.tail = "EXE.xml", "\n"
    return root


def _serialize(root, crlf, bom):
    text = '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    data = text.encode("utf-8")
    return codecs.BOM_UTF8 + data if bom else data


def _backup(path):
    """Keep ONE backup of exe.xml as it was before this launcher first changed it.
    It is created once and never overwritten. Returns the path only when it was just
    created (so the user is told once), otherwise None."""
    dest = path.with_name(f"{path.name}.MSFSLauncher.bak")
    if dest.exists():
        return None
    try:
        shutil.copy2(path, dest)
    except OSError as exc:
        raise ExeXmlError(_os_message(exc, path, "back up") + " Nothing was changed.") from None
    return dest


def _commit(path, data, original, verify):
    """Write `data`, read it back and run `verify(root)`. On any problem the file is put back
    to `original` (its bytes, held in memory; None = the file did not exist)."""
    _parse(data)                                   # never write something that doesn't parse
    try:
        path.write_bytes(data)
        problem = verify(_parse(path.read_bytes()))
    except (OSError, ExeXmlError) as exc:
        problem = str(exc)
    if problem:
        try:
            if original is not None:
                path.write_bytes(original)
            else:
                path.unlink(missing_ok=True)
        except OSError as exc:
            raise ExeXmlError(f"The change failed ({problem}) and the original file could not be "
                              f"restored automatically ({exc}).") from None
        raise ExeXmlError(f"The change did not work ({problem}). The original exe.xml was restored.")


def _salvage(raw, path):
    """Rebuild a syntax-damaged exe.xml: every complete, readable <Launch.Addon> entry is kept
    exactly as written, unreadable pieces are dropped. Returns the parsed root, or raises
    ExeXmlError when too little is left to trust (no <SimBase.Document> tag)."""
    def readable(fragment):
        try:
            ET.fromstring(f"<r>{fragment}</r>")
            return True
        except ET.ParseError:
            return False

    text = raw.decode("utf-8-sig", errors="replace")
    opening = re.search(r"<SimBase\.Document\b[^>]*>", text)
    if not opening:
        raise ExeXmlError(f"exe.xml is too damaged to fix automatically (no <{ROOT_TAG}> tag). "
                          f"Restore it from a backup next to {path.name}.")
    body = re.sub(r"</SimBase\.Document\s*>\s*$", "", text[opening.end():])
    parts, pos = [], 0
    for m in re.finditer(r"<Launch\.Addon\b.*?</Launch\.Addon\s*>", body, re.S):
        between = body[pos:m.start()]
        parts.append(between if readable(between) else "\n    ")
        if readable(m.group(0)):
            parts.append(m.group(0))
        pos = m.end()
    tail = body[pos:]
    parts.append(tail if readable(tail) else "\n")
    return _parse((text[:opening.end()] + "".join(parts).rstrip() + "\n</SimBase.Document>\n").encode("utf-8"))


def add(folder):
    """Add (or repair) our entry. Returns {"message", "backup"}; raises ExeXmlError."""
    path = exe_xml_path(folder)
    target = _target()
    if not target["file"].is_file():
        raise ExeXmlError(f"{target['file'].name} was not found at {target['file']}")
    if not _is_writable(path, Path(folder)):
        raise ExeXmlError(f"{path} is read-only. Clear the read-only attribute and try again.")

    if inspect(folder)["state"] == "ok":
        return {"message": "Already added.", "backup": None}

    program = target["file"] if target["frozen"] else find_python()
    backup = original = None
    damaged = False
    if path.exists():
        original = path.read_bytes()
        try:
            root, crlf, bom = _load(path)
            backup = _backup(path)
        except ExeXmlError as exc:
            if not exc.damaged:
                raise
            # Syntax error: rebuild from what is readable (normal one-time backup applies)
            root = _salvage(original, path)
            crlf, bom = b"\r\n" in original, original.startswith(codecs.BOM_UTF8)
            backup = _backup(path)
            damaged = True
    else:
        root, crlf, bom = _new_document(), True, False
    ind = _indent_unit(root)

    entry = _new_entry(program, target["args"], ind)
    ours = _find_ours(root, target)
    if ours:                                       # repair in place, keeping its position
        kids = list(root)
        first = ours[0][0]
        entry.tail = first.tail
        root[kids.index(first)] = entry
        for extra, _ in ours[1:]:                  # collapse duplicates
            _drop(root, extra)
    else:
        _append(root, entry, ind)

    def verify(r):
        mine = _find_ours(r, target)
        if len(mine) != 1 or not mine[0][1]:
            return "the entry was not found after writing"
        return None

    _commit(path, _serialize(root, crlf, bom), original, verify)
    msg = "Added to exe.xml." if not ours else "Entry repaired."
    if damaged:
        msg = "Fixed the syntax error and " + msg[0].lower() + msg[1:]
    return {"message": msg, "backup": str(backup) if backup else None}


def _drop(root, el):
    """Remove one child, keeping the surrounding whitespace tidy."""
    kids = list(root)
    i = kids.index(el)
    if i > 0:
        kids[i - 1].tail = el.tail
    elif len(kids) == 1:
        root.text = el.tail
    root.remove(el)


def remove(folder):
    """Remove our entry. Returns {"message", "backup"}; raises ExeXmlError."""
    path = exe_xml_path(folder)
    target = _target()
    if not path.exists():
        return {"message": "Nothing to remove (exe.xml doesn't exist).", "backup": None}
    if not _is_writable(path, Path(folder)):
        raise ExeXmlError(f"{path} is read-only. Clear the read-only attribute and try again.")

    root, crlf, bom = _load(path)
    ours = _find_ours(root, target)
    if not ours:
        return {"message": "Nothing to remove, the entry wasn't there.", "backup": None}

    original = path.read_bytes()
    backup = _backup(path)
    for el, _ in ours:
        _drop(root, el)
    _commit(path, _serialize(root, crlf, bom), original,
            lambda r: None if not _find_ours(r, target) else "the entry was still there after writing")
    return {"message": "Removed from exe.xml.", "backup": str(backup) if backup else None}


def open_folder(folder):
    """Open the folder in Explorer, selecting exe.xml when it exists."""
    path = exe_xml_path(folder)
    if path.exists():
        subprocess.Popen(f'explorer /select,"{path}"')   # one string: see gui.open_app_folder
    else:
        os.startfile(str(folder))
