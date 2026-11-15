"""Configure only the new builder-owned renderer profile."""
import os
import configparser
def _parse_ini(text):
    sections = {"": {}}
    order = [""]
    current = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            if current not in sections:
                sections[current] = {}
                order.append(current)
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            sections[current][k.strip()] = v.strip()
    return sections, order

def _write_ini(path, mutate):
    text = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    sections, order = _parse_ini(text)

    def upsert(section, key, value):
        if section not in sections:
            sections[section] = {}
            order.append(section)
        sections[section][key] = str(value)

    def replace_section(section, kv):
        if section not in sections:
            order.append(section)
        sections[section] = dict(kv)

    mutate(upsert, replace_section)

    lines = []
    first = True
    for name in order:
        if name == "" and not sections.get("", {}):
            continue
        if name != "":
            if not first:
                lines.append("")
            lines.append(f"[{name}]")
            first = False
        for k, v in sections[name].items():
            lines.append(f"{k} = {v}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def _patch_dolphin_ini(user_dir, pipe_name, render_size=None, interactive=False):
    path = os.path.join(user_dir, "Config", "Dolphin.ini")
    # Captures are PrintWindow grabs of the render window's client area, so the
    # window size IS the screenshot resolution -- raising it is the only way to
    # get a bigger shot. Keep any override on-screen: an oversized window gets
    # clipped by the desktop and PrintWindow returns the clipped pixels.
    rw, rh = render_size or (1280, 960)
    if interactive:
        original = configparser.ConfigParser(strict=False, interpolation=None)
        original.read(path, encoding="utf-8")
        device = original.get("Core", "SIDevice0", fallback="6").strip()
        if device not in ("6", "12"):
            raise ValueError("Configure a Standard Controller or GameCube Adapter on "
                             "port 1 in Slippi before starting a playable preview.")
        if device == "6":
            pads = configparser.ConfigParser(strict=False, interpolation=None)
            pads.read(os.path.join(user_dir, "Config", "GCPadNew.ini"), encoding="utf-8")
            mapping = pads.get("GCPad1", "Device", fallback="").strip()
            if not mapping or mapping.lower().startswith("pipe/"):
                raise ValueError("Configure your port-1 controller mapping in Slippi "
                                 "before starting a playable preview. An empty or "
                                 "automation-pipe mapping cannot provide your controls.")

    def mutate(upsert, replace_section):
        upsert("Input", "BackgroundInput", "True")       # accept input unfocused
        upsert("Interface", "ConfirmStop", "False")      # no "are you sure" on stop
        upsert("Interface", "PauseOnFocusLost", "False")
        # Copied absolute paths would bypass the GC/ copy and write the user's
        # live memory cards. Empty paths select this run's own User/GC defaults.
        upsert("Core", "MemcardAPath", "")
        upsert("Core", "MemcardBPath", "")
        upsert("Display", "Fullscreen", "False")
        # The owned preview/capture targets a separate render surface. A copied
        # RenderToMain=True would put the game inside Dolphin's settings GUI.
        upsert("Display", "RenderToMain", "False")
        upsert("Display", "RenderWindowAutoSize", "False")
        upsert("Display", "RenderWindowWidth", str(rw))
        upsert("Display", "RenderWindowHeight", str(rh))
        if not interactive:
            upsert("Core", "SIDevice0", "6")  # automated checks use pipe port 1
        upsert("Core", "SIDevice1", "0")
        upsert("Core", "SIDevice2", "0")
        upsert("Core", "SIDevice3", "6" if interactive else "0")

    _write_ini(path, mutate)

    gc_path = os.path.join(user_dir, "Config", "GCPadNew.ini")

    def mutate_gc(upsert, replace_section):
        p = "GCPad4" if interactive else "GCPad1"
        replace_section(p, {})  # wipe inherited keyboard mapping
        upsert(p, "Device", f"Pipe/0/{pipe_name}")
        for btn in ["A", "B", "X", "Y", "Z", "L", "R"]:
            upsert(p, f"Buttons/{btn}", f"Button {btn}")
        upsert(p, "Buttons/Start", "Button START")
        upsert(p, "Buttons/Threshold", "50.0")
        upsert(p, "Main Stick/Up", "Axis MAIN Y +")
        upsert(p, "Main Stick/Down", "Axis MAIN Y -")
        upsert(p, "Main Stick/Left", "Axis MAIN X -")
        upsert(p, "Main Stick/Right", "Axis MAIN X +")
        upsert(p, "Main Stick/Radius", "100.0")
        upsert(p, "D-Pad/Up", "Button D_UP")
        upsert(p, "D-Pad/Down", "Button D_DOWN")
        upsert(p, "D-Pad/Left", "Button D_LEFT")
        upsert(p, "D-Pad/Right", "Button D_RIGHT")
        upsert(p, "C-Stick/Up", "Axis C Y +")
        upsert(p, "C-Stick/Down", "Axis C Y -")
        upsert(p, "C-Stick/Left", "Axis C X -")
        upsert(p, "C-Stick/Right", "Axis C X +")
        upsert(p, "C-Stick/Radius", "100.0")
        upsert(p, "Triggers/L", "Button L")
        upsert(p, "Triggers/R", "Button R")
        upsert(p, "Triggers/L-Analog", "Axis L -+")
        upsert(p, "Triggers/R-Analog", "Axis R -+")
        upsert(p, "Triggers/Threshold", "90.0")
        if not interactive:
            replace_section("GCPad3", {})  # drop inherited port-3 keyboard cursor

    _write_ini(gc_path, mutate_gc)

def _patch_logger_ini(user_dir):
    """Enable Dolphin's OSReport log channel, written to User/Logs/dolphin.log.
    Melee (and m-ex / HSD) print assertions and heap failures through OSReport,
    so a hang that leaves the frame counter frozen usually has its cause here."""
    path = os.path.join(user_dir, "Config", "Logger.ini")
    cfg = configparser.ConfigParser(strict=False, interpolation=None)
    cfg.optionxform = str
    if os.path.exists(path):
        try:
            cfg.read(path, encoding="utf-8")
        except configparser.Error:
            pass
    for sec in ("Options", "Logs"):
        if not cfg.has_section(sec):
            cfg.add_section(sec)
    cfg["Options"]["WriteToFile"] = "True"
    cfg["Options"]["WriteToConsole"] = "False"
    cfg["Options"]["Verbosity"] = "4"
    cfg["Logs"]["OSREPORT"] = "True"
    cfg["Logs"]["OSREPORT_HLE"] = "True"
    with open(path, "w", encoding="utf-8") as f:
        cfg.write(f, space_around_delimiters=True)

def _patch_hotkeys(user_dir):
    """Neutralise the keyboard hotkeys that fire over BackgroundInput=True.

    Because we run with background input on (so the pipe controller works while
    the app -- not Dolphin -- has focus), Dolphin's keyboard hotkeys ALSO fire
    while the user is interacting with our window. The worst offender is plain
    `F` = Toggle Fullscreen (Slippi's default), which yanks the throwaway/embedded
    Dolphin into fullscreen mid-run. We blank that and the other plain-key globals
    a user could hit by accident while typing (Esc=Stop, Tab=speed limit,
    Y=OSD chat, Enter=send chat). State-save F-keys keep their modifiers/Fn keys
    and are left alone. This only touches the throwaway copy; the real config is
    untouched."""
    path = os.path.join(user_dir, "Config", "Hotkeys.ini")

    def mutate(upsert, _replace):
        s = "Hotkeys1"
        for binding in (
            "Toggle Fullscreen",
            "Stop/Hide OSD chat",
            "Toggle OSD chat",
            "Send OSD chat message",
            "Disable Emulation Speed Limit",
        ):
            upsert(s, f"Keys/{binding}", "")

    _write_ini(path, mutate)

def _patch_clean_osd(user_dir):
    """Turn off the emulator OSD overlays for a clean screenshot: Dolphin's FPS
    counter and Slippi's on-screen ping ("Delay: N"). Keys are written lowercase
    to match how Slippi writes GFX.ini (Dolphin reads them case-insensitively)."""
    path = os.path.join(user_dir, "Config", "GFX.ini")

    def mutate(upsert, _replace):
        upsert("Settings", "showfps", "False")
        upsert("Settings", "shownetplayping", "False")
        upsert("Settings", "shownetplaymessages", "False")

    _write_ini(path, mutate)

    # General OSD messages ("Wrote memory card A contents to ...") are a
    # Dolphin.ini Interface setting, not GFX.ini -- they photobomb captures
    # whenever the game touches the memory card near the shot.
    dolphin_ini = os.path.join(user_dir, "Config", "Dolphin.ini")

    def mutate_iface(upsert, _replace):
        upsert("Interface", "OnScreenDisplayMessages", "False")

    _write_ini(dolphin_ini, mutate_iface)

def _patch_gfx_internal_res(user_dir, scale):
    """Render at `scale`x native (1 = 640x528). Rendering ABOVE the window size
    supersamples: Dolphin downsamples to the window, which is what the capture
    grabs, so stage textures come back far cleaner at the same output size."""
    path = os.path.join(user_dir, "Config", "GFX.ini")

    def mutate(upsert, _replace):
        upsert("Settings", "InternalResolution", str(int(scale)))

    _write_ini(path, mutate)
