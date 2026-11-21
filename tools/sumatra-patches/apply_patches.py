#!/usr/bin/env python3
"""Idempotent exact-text patches for the Linux SumatraPDF build.

The same script is used by the local preflight in sumatra-menu.sh and by the
GitHub Actions workflow, so "would it apply?" and "what CI applies" cannot
drift apart.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Replacement:
    path: str
    old: str
    new: str


@dataclass(frozen=True)
class Patch:
    name: str
    marker_path: str
    marker: str
    replacements: tuple[Replacement, ...] = field(default_factory=tuple)


PATCHES: tuple[Patch, ...] = (
    Patch(
        name="linux-x86-64-v2",
        marker_path="cmd/helper/ng-targets.ts",
        marker="const tessX86DefinesLinux",
        replacements=(
            Replacement(
                "cmd/helper/ng-targets.ts",
                """// tesseract picks a SIMD kernel at run time (cpuid); these say which were built
const tessX86Defines = ["HAVE_AVX", "HAVE_AVX2", "HAVE_SSE4_1", "HAVE_FMA"];
// each kernel file needs its instruction set enabled by the compiler
""",
                """// tesseract picks a SIMD kernel at run time (cpuid); these say which were built
const tessX86Defines = ["HAVE_AVX", "HAVE_AVX2", "HAVE_SSE4_1", "HAVE_FMA"];
// Linux stays at x86-64-v2: newer glibc rejects the v3 ELF property emitted
// by the AVX/AVX2/FMA kernels on v2-only CPUs.
const tessX86DefinesLinux = ["HAVE_SSE4_1"];
// each kernel file needs its instruction set enabled by the compiler
""",
            ),
            Replacement(
                "cmd/helper/ng-targets.ts",
                """const tessX86Kernelsx86: PlatformExtra = { defines: tessX86Defines };
// an arm64 mac has no x86 kernels; NEON is picked up from __ARM_NEON
""",
                """const tessX86KernelsSse = tessX86Kernels.filter((k) => k.flags.includes("-msse4.1"));
const tessX86KernelsNonSse = tessX86Kernels.filter((k) => !k.flags.includes("-msse4.1"));
const tessX86Kernelsx86: PlatformExtra = { defines: tessX86Defines };
const tessX86KernelsLinux: PlatformExtra = {
  defines: tessX86DefinesLinux,
  exclude: tessX86KernelsNonSse.map((k) => k.glob),
};
// an arm64 mac has no x86 kernels; NEON is picked up from __ARM_NEON
""",
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
            Replacement(
                "src/ng/CommandPalette.cpp",
                """    if (wnd->tw) {
        ToolWindowClose(wnd->tw);
        wnd->tw = nullptr;
    } else if (win && win->gpuiWin && wnd->editQuery) {
""",
                """    if (wnd->tw) {
        // ng: closing the palette's tool window must hand activation and
        // keyboard focus back to the main window. Other tool windows do this
        // already; without it gpui keeps sending keys to the destroyed popup
        // and the document stops responding after Escape / Enter.
        bool wasActive = ToolWindowIsActive(wnd->tw);
        if (wasActive && IsMainWindowValidAndNotClosing(win)) {
            AppShellActivateWindow(win);
        }
        ToolWindowClose(wnd->tw);
        wnd->tw = nullptr;
        if (wasActive && IsMainWindowValidAndNotClosing(win)) {
            AppShellFocusFrame(win);
        }
    } else if (win && win->gpuiWin && wnd->editQuery) {
""",
            ),
            Replacement(
                "src/ng/CommandPalette.cpp",
                """    if (!ToolWindowsAvailable()) {
        return;
    }
    ToolWindowDesc desc;
""",
                """    if (!ToolWindowsAvailable()) {
        return;
    }
#if !OS_WIN
    // Linux (xwayland-satellite): a separate toplevel for the palette leaves
    // keyboard focus with the destroyed popup after Esc / Enter, so the
    // document stops taking keys. Keep the palette as an in-frame overlay.
    return;
#endif
    ToolWindowDesc desc;
""",
            ),
        ),
    ),
    Patch(
        name="keymap-after-settings-reload",
        marker_path="ext/gpui/gpui.cpp",
        marker="void KeymapUnbindAction",
        replacements=(
            Replacement(
                "ext/gpui/gpui.cpp",
                """void KeymapClear() {
    VecClear(gBindings);
    VecClear(gPreds);
    gNPending = 0;
    gGeneration++;
    if (!gGeneration) {
        gGeneration = 1;
    }
}

void KeymapBind(const KeyBinding* bindings, int n) {
""",
                """void KeymapClear() {
    VecClear(gBindings);
    VecClear(gPreds);
    gNPending = 0;
    gGeneration++;
    if (!gGeneration) {
        gGeneration = 1;
    }
}

void KeymapUnbindAction(uint32_t action) {
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

void KeymapBind(const KeyBinding* bindings, int n) {
""",
            ),
            Replacement(
                "ext/gpui/gpui.h",
                """void KeymapBind(const KeyBinding* bindings, int n);
void KeymapClear();
""",
                """void KeymapBind(const KeyBinding* bindings, int n);
// remove all key bindings for one action, so a caller can rebuild them
void KeymapUnbindAction(uint32_t action);
void KeymapClear();
""",
            ),
            Replacement(
                "src/ng/gui/AppShell.cpp",
                """static void BindKeys() {
    int n = 0;
""",
                """static void BindKeys() {
    // idempotent: accelerator tables are rebuilt when settings reload
    gp::KeymapUnbindAction(ActSumatraCmd());
    int n = 0;
""",
            ),
            Replacement(
                "src/ng/gui/AppShell.cpp",
                """    logf("BindKeys: %d shortcuts bound\\n", nBind);
}

// --- menu bar ---------------------------------------------------------------
""",
                """    logf("BindKeys: %d shortcuts bound\\n", nBind);
}

// called after settings reload, when LoadSettings() rebuilds accelerators
void AppShellBindKeys() {
    BindKeys();
}

// --- menu bar ---------------------------------------------------------------
""",
            ),
            Replacement(
                "src/ng/gui/AppShell.h",
                """void AppShellSetApp(gpui::App*);
// runs the event loop until the last window closes
""",
                """void AppShellSetApp(gpui::App*);
// rebind Sumatra commands after settings reload rebuilds the accelerator table
void AppShellBindKeys();
// runs the event loop until the last window closes
""",
            ),
            Replacement(
                "src/shared/AppSettings.cpp",
                """#include "gui/UIModels.h"

#if defined(SUMATRA_NG)
#endif
""",
                """#include "gui/UIModels.h"

#if defined(SUMATRA_NG)
#include "gui/AppShell.h"
#endif
""",
            ),
            Replacement(
                "src/shared/AppSettings.cpp",
                """#if defined(SUMATRA_NG)
    ReRegisterGlobalHotkeys();
#endif
""",
                """#if defined(SUMATRA_NG)
    ReRegisterGlobalHotkeys();
    // LoadSettings() rebuilt the accelerator table; keep gpui's keymap in sync
    // so custom shortcuts in the Shortcuts section still work.
    AppShellBindKeys();
#endif
""",
            ),
        ),
    ),
    Patch(
        name="x11-wm-class",
        marker_path="ext/gpui/gpui.cpp",
        marker="XSetClassHint(gDpy, pw->xwin, &classHint)",
        replacements=(
            Replacement(
                "ext/gpui/gpui.cpp",
                """    XSetWMProtocols(gDpy, pw->xwin, &aWmDeleteWindow, 1);

    Atom xdndVersion = 5;
""",
                """    XSetWMProtocols(gDpy, pw->xwin, &aWmDeleteWindow, 1);
#if GPUI_OS_LINUX
    {
        // Set the X class hint in the app, so every toplevel gets the right
        // App ID / icon in Wayland compositors without an xdotool .desktop hack.
        XClassHint classHint = {};
        classHint.res_name = (char*)"SumatraPDF";
        classHint.res_class = (char*)"SumatraPDF";
        XSetClassHint(gDpy, pw->xwin, &classHint);
    }
#endif

    Atom xdndVersion = 5;
""",
            ),
        ),
    ),
    Patch(
        name="toolwindow-close-restores-focus",
        marker_path="src/ng/gui/ToolWindow.cpp",
        marker="ToolWindowFocus",
        replacements=(
            Replacement(
                "src/ng/gui/ToolWindow.cpp",
                """static void DestroyNow(ToolWindow* tw) {
    if (!IsLive(tw)) {
        return;
    }
    if (tw->gw) {
        // OnGpuiWindowClosed forgets it
        gp::AppQuit(tw->gw);
    }
    if (IsLive(tw)) {
        Forget(tw);
    }
}
""",
                """// Hand focus back once the popup is actually gone. Doing this inside
// DestroyNow, before AppQuit, is racy on X11: releasing the modal keyboard
// grab and destroying the X window can override the earlier focus change,
// leaving the keyboard going nowhere until the window is clicked.
static void RestoreOwnerFocus(MainWindow* win) {
    if (IsMainWindowValidAndNotClosing(win)) {
        AppShellActivateWindow(win);
        AppShellFocusFrame(win);
    }
}

static void DestroyNow(ToolWindow* tw) {
    if (!IsLive(tw)) {
        return;
    }
    MainWindow* owner = tw->owner;
    if (tw->gw) {
        // OnGpuiWindowClosed forgets it
        gp::AppQuit(tw->gw);
    }
    if (IsLive(tw)) {
        Forget(tw);
    }
    // Deferred so the X teardown has completed before XSetInputFocus.
    uitask::Post(MkFunc0(RestoreOwnerFocus, owner), "ToolWindowFocus");
}
""",
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
                """void WindowModalRelease(Window* dlg) {
    Window* parent = dlg ? dlg->modalParent : nullptr;
    if (!parent) {
        return;
    }
    dlg->modalParent = nullptr;

    if (!WindowIsEnabled(parent) || !parent->plat) {
        return;
    }

    bool wasActive = dlg->plat && WindowIsActive(dlg);
    PlatWindowSetModal(dlg, parent, false);
    if (wasActive) {
        WindowActivateInApp(parent);
    }
}
""",
                """void WindowModalRelease(Window* dlg) {
    Window* parent = dlg ? dlg->modalParent : nullptr;
    // Always give up the X11 keyboard/pointer grab, even if modalParent was
    // never set (or was already cleared). Otherwise closing a modal dialog
    // with Escape can leave the keyboard grabbed and the whole app frozen.
    if (dlg) {
        PlatWindowSetModal(dlg, parent, false);
    }
    if (!parent) {
        return;
    }
    dlg->modalParent = nullptr;

    if (!WindowIsEnabled(parent) || !parent->plat) {
        return;
    }

    bool wasActive = dlg->plat && WindowIsActive(dlg);
    if (wasActive) {
        WindowActivateInApp(parent);
    }
}
""",
            ),
        ),
    ),
    Patch(
        name="tab-shortcut-before-focus-cycle",
        marker_path="src/ng/gui/AppShell.cpp",
        marker="gp::WindowResolveKeyAction(cx->win, VK_TAB",
        replacements=(
            Replacement(
                "src/ng/gui/AppShell.cpp",
                """    if (ev->vk == VK_TAB && !ev->ctrl && !ev->alt && !self->overlayUp) {
        bool inTabOrder = AppShellIsFrameFocused(win) || IsToolbarPageBoxFocused(win) ||
                          SidebarPanelHasFocus(win, SidebarSlot::Top) ||
                          SidebarPanelHasFocus(win, SidebarSlot::Middle) ||
                          SidebarPanelHasFocus(win, SidebarSlot::Bottom);
        if (inTabOrder) {
""",
                """    if (ev->vk == VK_TAB && !ev->ctrl && !ev->alt && !self->overlayUp) {
        // A user shortcut bound to Tab (CmdToggleBookmarks here) must win over
        // the built-in focus cycle. Let gpui dispatch a key the keymap claims.
        bool tabBound = gp::WindowResolveKeyAction(cx->win, VK_TAB, ev->shift, ev->ctrl,
                                                   ev->alt, ev->platform, ev->function,
                                                   nullptr, nullptr) != 0;
        bool inTabOrder = !tabBound &&
                          (AppShellIsFrameFocused(win) || IsToolbarPageBoxFocused(win) ||
                           SidebarPanelHasFocus(win, SidebarSlot::Top) ||
                           SidebarPanelHasFocus(win, SidebarSlot::Middle) ||
                           SidebarPanelHasFocus(win, SidebarSlot::Bottom));
        if (inTabOrder) {
""",
            ),
        ),
    ),
    Patch(
        name="findnext-while-findbar-focused",
        marker_path="src/ng/FindWindow.cpp",
        marker="F4 find next while the find bar is focused",
        replacements=(
            Replacement(
                "src/ng/FindWindow.cpp",
                """bool FindWindowOnKeyDown(MainWindow* win, int vk, bool ctrl, bool shift, bool alt) {
    if (!IsFindWindowVisible(win)) {
""",
                """bool FindWindowOnKeyDown(MainWindow* win, int vk, bool ctrl, bool shift, bool alt) {
    // F4 find next while the find bar is focused
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
    if (!IsFindWindowVisible(win)) {
""",
            ),
        ),
    ),
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"ERROR: missing source file: {path}")


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
            count = text.count(repl.old)
            if count != 1:
                error = f"expected one match in {repl.path}, found {count}"
                break
            changed[path] = text.replace(repl.old, repl.new, 1)
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
