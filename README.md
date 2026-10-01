# tdesktop-wayland-notifications

> [!NOTE]
> This patch was written by an LLM (Claude), directed and tested by a human.

A patch for Telegram Desktop that makes its own notification popups work on Wayland, the way they do on Windows and X11.

Upstream forces system notifications on Wayland because apps can't position their own windows there ([tdesktop#28820](https://github.com/telegramdesktop/tdesktop/issues/28820)). Forcing custom notifications through the experimental settings puts them in the middle of the screen.

- **Popups appear in your chosen corner**, on the monitor Telegram is on, stay clear of panels, and never steal focus.
- **Popups wait for you.** If you're away when a message arrives, the popup stays until you next move the mouse or press a key. Idle inhibitors from games and video players are ignored.
- **The "Use native notifications" setting comes back** on Wayland.

Tested on KDE Plasma 6 (Wayland). Other compositors with `zwlr_layer_shell_v1` (Hyprland, Sway, …) should work. GNOME has no layer-shell, so it falls back to system notifications as before.

## Install (Arch)

```bash
git clone https://github.com/iridium/tdesktop-wayland-notifications
cd tdesktop-wayland-notifications
makepkg -si
```

This replaces the `telegram-desktop` package. It's Arch's own PKGBUILD with the patch applied, so it builds Telegram and tdlib from source.

Then in Telegram: Settings → Notifications, turn off **Use native notifications**. If you'd previously enabled **Force non-native notifications availability** under Settings → Advanced → Experimental settings, it's no longer needed.

On other distros, apply the patch to the release tarball and build as usual. You'll need `layer-shell-qt` and `wayland-client` development files:

```bash
patch -Np1 -d tdesktop-7.2.9-full -i wayland-notifications.patch
```

## How it works

- Each popup becomes a `wlr-layer-shell` surface via [layer-shell-qt](https://invent.kde.org/plasma/layer-shell-qt), anchored to the nearest screen corner, with margins computed from where Telegram would have placed it. It never takes keyboard focus, except after you click Reply on it.
- Idle detection uses `ext-idle-notify-v1`'s input idle notification (v2), which also makes Telegram's online/away status more accurate on Wayland. Previously only X11 and GNOME were supported.
- Popups skip `setWindowOpacity()` on Wayland, which Qt doesn't support there and only logs warnings for. Your compositor's open/close animation is used instead of Telegram's fade.

Layer-shell support is optional at build time. Without `layer-shell-qt`, Telegram builds and behaves like upstream.

## Limitations

- No fade in or out, since Wayland doesn't let Qt set window opacity. Your compositor's own animation is used instead.
- A popup already on screen stays on its monitor if you move Telegram. The next one follows.
- While idle detection is active, Telegram knows when you last used the mouse or keyboard to within about a second.

## Updating

A daily GitHub Action follows Arch's `telegram-desktop` package. When Arch moves to a new release, it checks that the patch still applies and commits the version bump, or opens an issue if the patch needs rebasing. It doesn't compile Telegram, so a bump that applies cleanly could still fail to build.

To update after a bump:

```bash
git pull
makepkg -si
```

## License

GPL-3.0-or-later with the OpenSSL exception, same as Telegram Desktop.
