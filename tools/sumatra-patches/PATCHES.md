# SumatraPDF Linux patches

These patches are applied by `.github/workflows/build-patched.yml` to a clean
checkout of the fork's `master` branch. The fork itself stays upstream-clean:
the only fork commit adds these files and the workflow.

Upstream now has native Linux single-instance reuse (`ReuseInstance_posix.cpp`,
using `$XDG_RUNTIME_DIR` and peer-cred checks), so the old fixed-socket
`linux-single-instance` patch was removed. Upstream `afda83e8e0` also fixed the
`CrashHandler_posix.cpp` `write()` result warnings, so that one-time patch was
removed too.

Patches:

- `linux-x86-64-v2`: build Tesseract with SSE-only kernels on Linux so the
  binary does not require x86-64-v3.
- `linux-force-baseline-flags`: pin Linux compilation to `-march=x86-64` so a
  runner toolchain cannot add newer ISA properties to the final ELF. CI also
  normalizes the final ELF note to `x86-64-baseline`, because Ubuntu's linker
  stamps v3 even when no object requires it.
- `palette-linux-inframe`: keep the Command Palette in-frame on Linux and hand
  focus back to the document when it closes.
- `keymap-after-settings-reload`: rebuild GPUI key bindings after settings
  reload, so custom `Shortcuts` keep working.
- `x11-wm-class`: set `WM_CLASS=SumatraPDF` on every X11 toplevel, so the app
  icon / App ID works without an `xdotool` desktop-entry hack.
- `toolwindow-close-restores-focus`: upstream now activates the owner of a
  closed active tool window, but on X11 `WindowActivateInApp()` no-ops when the
  destroyed window left focus nowhere. Defer `AppShellActivateWindow()` and
  `AppShellFocusFrame()` to the UI task queue so the modal keyboard grab and X
  window teardown finish first; doing it before `AppQuit` was racy and left
  Escape-closed popups (Document Properties, F9 Change Scrollbar, etc.) with a
  dead keyboard.
- `gpui-modal-close-ungrab`: always release gpui's X11 keyboard/pointer grab in
  `WindowModalRelease`, even when `modalParent` is unset. This is the other
  half of the freeze: if the grab is left active, all keys keep going to the
  destroyed dialog and the app stops responding.
- `tab-shortcut-before-focus-cycle`: if the keymap resolves Tab to a user
  command, let gpui dispatch it before the built-in Tab focus-cycle handler.
- `findnext-while-findbar-focused`: in `FindWindowOnKeyDown()`, forward F4
  through `ExecuteCmd()` using the command looked up from the accelerator
  table, before the search edit swallows the key. Settings stay authoritative:
  remapping F4 to another command (or unbinding it) works in both the compact
  bar and the floating find window. Without this, a custom F4 shortcut is dead
  whenever the search box is open.

`apply_patches.py` is idempotent. It skips fixes that are already upstream and
fails clearly if an expected source context changes. `sumatra-menu.sh fork check`
runs the exact same script against the touched files from upstream `master`
before the fork is updated.

Pure additions use `Insert`: a single-line anchor plus nearby `before` / `after`
context. The context only has to appear within a window of lines around the
anchor, so an upstream comment inserted next to the target no longer breaks the
patch (this happened to `keymap-after-settings-reload` when upstream added a
comment above `AppShellSettingChanged()`). Ambiguous anchors such as
`#if defined(SUMATRA_NG)` also require context to select the right occurrence.
Real code changes still use exact `Replacement`, so an actual upstream behavior
change continues to fail loudly instead of silently double-patching.
