#!/usr/bin/env python3
"""Idempotent patches for the Linux SumatraPDF build.

Most changes are exact-text replacements, but insertions use a single-line
anchor plus nearby context so an upstream comment inserted next to the target
does not break the patch. The same script is used by the local preflight in
sumatra-menu.sh and by the GitHub Actions workflow, so "would it apply?" and
"what CI applies" cannot drift apart.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Replacement:
    """Exact old -> new text replacement. Use for real code changes."""

    path: str
    old: str
    new: str


@dataclass(frozen=True)
class Insert:
    """Insert text at a single-line anchor, checked against nearby context.

    Unlike an exact multi-line Replacement, comments inserted next to the
    anchor do not break this. `before` / `after` strings only have to appear
    somewhere within `window` lines of the anchor, not directly adjacent.
    They also disambiguate anchors that occur multiple times in a file.
    """

    path: str
    anchor: str
    text: str
    where: str = "after"  # "before" or "after" the anchor line
    before: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    window: int = 12


@dataclass(frozen=True)
class Patch:
    name: str
    marker_path: str
    marker: str
    replacements: tuple[Replacement | Insert, ...] = field(default_factory=tuple)


PATCHES: tuple[Patch, ...] = (
    Patch(
        name="linux-x86-64-v2",
        marker_path="cmd/helper/ng-targets.ts",
        marker="const tessX86DefinesLinux",
        replacements=(
            Insert(
                "cmd/helper/ng-targets.ts",
                anchor='const tessX86Defines = ["HAVE_AVX", "HAVE_AVX2", "HAVE_SSE4_1", "HAVE_FMA"];',
                text="""// Linux stays at x86-64-v2: newer glibc rejects the v3 ELF property emitted
// by the AVX/AVX2/FMA kernels on v2-only CPUs.
const tessX86DefinesLinux = ["HAVE_SSE4_1"];
""",
                before=("// tesseract picks a SIMD kernel at run time (cpuid); these say which were built",),
                after=("// each kernel file needs its instruction set enabled by the compiler",),
            ),
            Insert(
                "cmd/helper/ng-targets.ts",
                anchor="const tessX86Kernelsx86: PlatformExtra = { defines: tessX86Defines };",
                text="""const tessX86KernelsSse = tessX86Kernels.filter((k) => k.flags.includes("-msse4.1"));
const tessX86KernelsNonSse = tessX86Kernels.filter((k) => !k.flags.includes("-msse4.1"));
""",
                where="before",
                after=("// an arm64 mac has no x86 kernels; NEON is picked up from __ARM_NEON",),
            ),
            Insert(
                "cmd/helper/ng-targets.ts",
                anchor="const tessX86Kernelsx86: PlatformExtra = { defines: tessX86Defines };",
                text="""const tessX86KernelsLinux: PlatformExtra = {
  defines: tessX86DefinesLinux,
  exclude: tessX86KernelsNonSse.map((k) => k.glob),
};
""",
                after=("// an arm64 mac has no x86 kernels; NEON is picked up from __ARM_NEON",),
            ),
            Replacement(
                "cmd/helper/ng-targets.ts",
                """      linux: tessX86Kernelsx86,
      mac: tessMac,
    },
    perSource: tessX86Kernels.map((k) => ({ ...k, platforms: ["linux", "mac"] as Platform[] })),
""",
                """      linux: tessX86KernelsLinux,
      mac: tessMac,
    },
    perSource: [
      ...tessX86Kernels.map((k) => ({ ...k, platforms: ["mac"] as Platform[] })),
      ...tessX86KernelsSse.map((k) => ({ ...k, platforms: ["linux"] as Platform[] })),
    ],
""",
            ),
        ),
    ),
    Patch(
        name="linux-force-baseline-flags",
        marker_path="cmd/helper/ng-compile.ts",
        marker="keep ELF ISA property at x86-64 baseline",
        replacements=(
            Replacement(
                "cmd/helper/ng-compile.ts",
                """  if (tc.plat === "linux") flags.push("-g");
""",
                """  // keep ELF ISA property at x86-64 baseline, even when the runner's
  // toolchain defaults to a newer x86-64 level
  if (tc.plat === "linux") flags.push("-g", "-march=x86-64");
""",
            ),
        ),
    ),
    Patch(
        name="palette-linux-inframe",
        marker_path="src/ng/CommandPalette.cpp",
        marker="Linux (xwayland-satellite)",
        replacements=(
            Insert(
                "src/ng/CommandPalette.cpp",
                anchor="    if (wnd->tw) {",
                text="""        // ng: closing the palette's tool window must hand activation and
        // keyboard focus back to the main window. Other tool windows do this
        // already; without it gpui keeps sending keys to the destroyed popup
        // and the document stops responding after Escape / Enter.
        bool wasActive = ToolWindowIsActive(wnd->tw);
        if (wasActive && IsMainWindowValidAndNotClosing(win)) {
            AppShellActivateWindow(win);
        }
""",
                after=("        ToolWindowClose(wnd->tw);", "        wnd->tw = nullptr;"),
            ),
            Insert(
                "src/ng/CommandPalette.cpp",
                anchor="    } else if (win && win->gpuiWin && wnd->editQuery) {",
                text="""        if (wasActive && IsMainWindowValidAndNotClosing(win)) {
            AppShellFocusFrame(win);
        }
""",
                where="before",
                before=("        wnd->tw = nullptr;",),
                after=("        InputBlurWhereFocused(wnd->editQuery, win->gpuiWin);",),
            ),
            Insert(
                "src/ng/CommandPalette.cpp",
                anchor="    ToolWindowDesc desc;",
                text="""#if !OS_WIN
    // Linux (xwayland-satellite): a separate toplevel for the palette leaves
    // keyboard focus with the destroyed popup after Esc / Enter, so the
    // document stops taking keys. Keep the palette as an in-frame overlay.
    return;
#endif
""",
                where="before",
                before=("    if (!ToolWindowsAvailable()) {",),
            ),
        ),
    ),
    Patch(
        name="keymap-after-settings-reload",
        marker_path="ext/gpui/gpui.cpp",
        marker="void KeymapUnbindAction",
        replacements=(
            Insert(
                "ext/gpui/gpui.cpp",
                anchor="void KeymapBind(const KeyBinding* bindings, int n) {",
                text="""void KeymapUnbindAction(uint32_t action) {
    for (int i = len(gBindings) - 1; i >= 0; i--) {
        if (gBindings[i].action == action) {
            VecRemoveAt(gBindings, i);
        }
    }
    gGeneration++;
    if (!gGeneration) {
        gGeneration = 1;
    }
}

""",
                where="before",
                before=("gGeneration = 1;",),
            ),
            Insert(
                "ext/gpui/gpui.h",
                anchor="void KeymapBind(const KeyBinding* bindings, int n);",
                text="""// remove all key bindings for one action, so a caller can rebuild them
void KeymapUnbindAction(uint32_t action);
""",
                after=("void KeymapClear();",),
            ),
            Insert(
                "src/ng/gui/AppShell.cpp",
                anchor="    int n = 0;",
                text="""    // idempotent: accelerator tables are rebuilt when settings reload
    gp::KeymapUnbindAction(ActSumatraCmd());
""",
                where="before",
                after=("    const AccelStroke* strokes = GetAcceleratorStrokes(n);",),
                window=8,
            ),
            Insert(
                "src/ng/gui/AppShell.cpp",
                anchor="// --- menu bar ---------------------------------------------------------------",
                text="""// called after settings reload, when LoadSettings() rebuilds accelerators
void AppShellBindKeys() {
    BindKeys();
}

""",
                where="before",
                before=("    logf(\"BindKeys: %d shortcuts bound\\n\", nBind);",),
            ),
            Insert(
                "src/ng/gui/AppShell.h",
                anchor="void AppShellSettingChanged();",
                text="""// rebind Sumatra commands after settings reload rebuilds the accelerator table
void AppShellBindKeys();
""",
                before=("// a system setting changed (orig's WM_SETTINGCHANGE)",),
                after=("gpui::component::PopupMenu* AppShellMenuPopup",),
            ),
            Insert(
                "src/shared/AppSettings.cpp",
                anchor="#include \"Settings.h\"",
                text="""#if defined(SUMATRA_NG)
#include "gui/AppShell.h"
#endif

""",
                where="before",
                before=("#include \"gui/UIModels.h\"",),
                after=("#include \"Commands.h\"",),
                window=8,
            ),
            Insert(
                "src/shared/AppSettings.cpp",
                anchor="    ReRegisterGlobalHotkeys();",
                text="""    // LoadSettings() rebuilt the accelerator table; keep gpui's keymap in sync
    // so custom shortcuts in the Shortcuts section still work.
    AppShellBindKeys();
""",
                before=("    UpdateFixedPageScrollbarsVisibility();",),
                after=("    if (!str::EqI(thumbnailsType, gSettings->thumbnailsType)) {",),
                window=16,
            ),
        ),
    ),
    Patch(
        name="x11-wm-class",
        marker_path="ext/gpui/gpui.cpp",
        marker="XSetClassHint(gDpy, pw->xwin, &classHint)",
        replacements=(
            Insert(
                "ext/gpui/gpui.cpp",
                anchor="    XSetWMProtocols(gDpy, pw->xwin, &aWmDeleteWindow, 1);",
                text="""#if GPUI_OS_LINUX
    {
        // Set the X class hint in the app, so every toplevel gets the right
        // App ID / icon in Wayland compositors without an xdotool .desktop hack.
        XClassHint classHint = {};
        classHint.res_name = (char*)"SumatraPDF";
        classHint.res_class = (char*)"SumatraPDF";
        XSetClassHint(gDpy, pw->xwin, &classHint);
    }
#endif
""",
                after=("    Atom xdndVersion = 5;",),
            ),
        ),
    ),
    Patch(
        name="toolwindow-close-restores-focus",
        marker_path="src/ng/gui/ToolWindow.cpp",
        marker="ToolWindowFocus",
        replacements=(
            Insert(
                "src/ng/gui/ToolWindow.cpp",
                anchor="static void DestroyNow(ToolWindow* tw) {",
                text="""// Hand focus back once the popup is actually gone. Doing this inside
// DestroyNow, before AppQuit, is racy on X11: releasing the modal keyboard
// grab and destroying the X window can override the earlier focus change,
// leaving the keyboard going nowhere until the window is clicked.
static void RestoreOwnerFocus(MainWindow* win) {
    if (IsMainWindowValidAndNotClosing(win)) {
        AppShellActivateWindow(win);
        AppShellFocusFrame(win);
    }
}

""",
                where="before",
            ),
            Insert(
                "src/ng/gui/ToolWindow.cpp",
                anchor="        gp::WindowActivateInApp(ownerGw);",
                text="""        // On X11 WindowActivateInApp() no-ops when the destroyed window left
        // focus nowhere. Restore it after the teardown has completed.
        uitask::Post(MkFunc0(RestoreOwnerFocus, owner), "ToolWindowFocus");
""",
                before=("    if (wasActive && ownerGw && IsMainWindowValidAndNotClosing(owner)) {",),
            ),
        ),
    ),
    Patch(
        name="gpui-modal-close-ungrab",
        marker_path="ext/gpui/gpui.cpp",
        marker="Always give up the X11 keyboard/pointer grab",
        replacements=(
            Replacement(
                "ext/gpui/gpui.cpp",
                "    PlatWindowSetModal(dlg, parent, false);\n",
                "",
            ),
            Insert(
                "ext/gpui/gpui.cpp",
                anchor="    Window* parent = dlg ? dlg->modalParent : nullptr;",
                text="""    // Always give up the X11 keyboard/pointer grab, even if modalParent was
    // never set (or was already cleared). Otherwise closing a modal dialog
    // with Escape can leave the keyboard grabbed and the whole app frozen.
    if (dlg) {
        PlatWindowSetModal(dlg, parent, false);
    }
""",
                after=("    if (!parent) {",),
            ),
        ),
    ),
    Patch(
        name="tab-shortcut-before-focus-cycle",
        marker_path="src/ng/gui/AppShell.cpp",
        marker="gp::WindowResolveKeyAction(cx->win, VK_TAB",
        replacements=(
            Insert(
                "src/ng/gui/AppShell.cpp",
                anchor="    if (ev->vk == VK_TAB && !ev->ctrl && !ev->alt && !self->overlayUp) {",
                text="""        // A user shortcut bound to Tab (CmdToggleBookmarks here) must win over
        // the built-in focus cycle. Let gpui dispatch a key the keymap claims.
        bool tabBound = gp::WindowResolveKeyAction(cx->win, VK_TAB, ev->shift, ev->ctrl,
                                                   ev->alt, ev->platform, ev->function,
                                                   nullptr, nullptr) != 0;
""",
                after=("        bool inTabOrder = AppShellIsFrameFocused(win) || IsToolbarPageBoxFocused(win) ||",),
            ),
            Replacement(
                "src/ng/gui/AppShell.cpp",
                """        bool inTabOrder = AppShellIsFrameFocused(win) || IsToolbarPageBoxFocused(win) ||
                          SidebarPanelHasFocus(win, SidebarSlot::Top) ||
                          SidebarPanelHasFocus(win, SidebarSlot::Middle) ||
                          SidebarPanelHasFocus(win, SidebarSlot::Bottom);
""",
                """        bool inTabOrder = !tabBound &&
                          (AppShellIsFrameFocused(win) || IsToolbarPageBoxFocused(win) ||
                           SidebarPanelHasFocus(win, SidebarSlot::Top) ||
                           SidebarPanelHasFocus(win, SidebarSlot::Middle) ||
                           SidebarPanelHasFocus(win, SidebarSlot::Bottom));
""",
            ),
        ),
    ),
    Patch(
        name="findnext-while-findbar-focused",
        marker_path="src/ng/FindWindow.cpp",
        marker="F4 find next while the find bar is focused",
        replacements=(
            Insert(
                "src/ng/FindWindow.cpp",
                anchor="bool FindWindowOnKeyDown(MainWindow* win, int vk, bool ctrl, bool shift, bool alt) {",
                text="""    // F4 find next while the find bar is focused
    // The search edit swallows F4 in both find UIs, so forward the command the
    // user actually bound to it in settings. The compact bar is not a
    // FindWindow, so the floating-window path below never sees it either.
    if (vk == VK_F4 && !ctrl && !alt) {
        int cmd = AcceleratorCmd(VK_F4, false, shift, false, false);
        if (cmd != 0) {
            ExecuteCmd(win, cmd);
            return true;
        }
    }
""",
                after=("    if (!IsFindWindowVisible(win)) {",),
            ),
        ),
    ),
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"ERROR: missing source file: {path}")


def apply_insert(text: str, ins: Insert) -> tuple[str, str]:
    """Return (new_text, error). Empty error means success."""
    if ins.text in text:
        return text, ""
    if ins.where not in ("before", "after"):
        return text, f"invalid where={ins.where!r} in {ins.path}"

    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if ins.anchor in line]
    if not hits:
        return text, f"missing anchor {ins.anchor!r} in {ins.path}"

    # An anchor may appear more than once (e.g. `#if defined(SUMATRA_NG)`).
    # Nearby context selects the right occurrence, but does not have to be
    # directly adjacent: upstream comments can be inserted around the anchor.
    window = max(1, ins.window)
    candidates = []
    for i in hits:
        before_window = "".join(lines[max(0, i - window) : i])
        after_window = "".join(lines[i + 1 : i + 1 + window])
        if all(ctx in before_window for ctx in ins.before) and all(
            ctx in after_window for ctx in ins.after
        ):
            candidates.append(i)
    if len(candidates) != 1:
        suffix = " (add before/after context)" if len(hits) > 1 and not (ins.before or ins.after) else ""
        return (
            text,
            f"expected one anchor {ins.anchor!r} with nearby context in {ins.path}, "
            f"found {len(candidates)} of {len(hits)}{suffix}",
        )
    i = candidates[0]

    chunk = ins.text if ins.text.endswith("\n") else ins.text + "\n"
    at = i if ins.where == "before" else i + 1
    lines.insert(at, chunk)
    return "".join(lines), ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("."), help="source checkout root")
    ap.add_argument("--check", action="store_true", help="only check; do not write files")
    ap.add_argument("--apply", action="store_true", help="write patched files")
    ap.add_argument("--list", action="store_true", help="list patches and exit")
    ap.add_argument("--list-files", action="store_true", help="list source files needed for patches")
    args = ap.parse_args()

    if args.list:
        for patch in PATCHES:
            print(patch.name)
        return 0
    if args.list_files:
        paths: list[str] = []
        for patch in PATCHES:
            for path in (patch.marker_path, *(r.path for r in patch.replacements)):
                if path not in paths:
                    paths.append(path)
        print("\n".join(paths))
        return 0
    if args.check == args.apply:
        raise SystemExit("choose exactly one of --check or --apply")

    root: Path = args.root.resolve()
    failures: list[str] = []

    for patch in PATCHES:
        marker_path = root / patch.marker_path
        if marker_path.is_file() and patch.marker in read_text(marker_path):
            print(f"PATCH {patch.name}: SKIP (already applied)")
            continue

        changed: dict[Path, str] = {}
        error = ""
        for repl in patch.replacements:
            path = root / repl.path
            text = changed.get(path)
            if text is None:
                text = read_text(path)
            if isinstance(repl, Insert):
                text, error = apply_insert(text, repl)
            else:
                count = text.count(repl.old)
                if count != 1:
                    error = f"expected one match in {repl.path}, found {count}"
                else:
                    text = text.replace(repl.old, repl.new, 1)
                    error = ""
            if error:
                break
            changed[path] = text
        if error:
            print(f"PATCH {patch.name}: FAIL ({error})")
            failures.append(patch.name)
            continue
        if not args.check:
            for path, text in changed.items():
                path.write_text(text, encoding="utf-8")
        print(f"PATCH {patch.name}: {'OK' if args.check else 'APPLIED'}")

    if failures:
        print(f"ERROR: {len(failures)} patch(es) failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
