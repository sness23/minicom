# Minicom Ctrl-A Command Reference

*Written 2026-11-02. This is from memory of the minicom 2.x man page. Run `Ctrl-A Z` in your own build to confirm, because a few letters vary between versions.*

## How the escape key works

Everything you type in minicom goes straight to the serial port, except the **escape key**, which is `Ctrl-A` by default. Press `Ctrl-A`, let go, then press a single letter to run a command. Letters are not case-sensitive.

- **Help**: `Ctrl-A Z` opens the command summary, the one screen worth remembering.
- **Send a literal Ctrl-A** to the remote side: press `Ctrl-A` twice.
- **Change the escape key**: run `minicom -s`, then choose **Screen and keyboard** → **Command key is**. Picking a different key avoids clashes with `screen`, `tmux` or Emacs.
- **Use the Meta/Alt key instead**: start with `minicom -m`, then type `Alt-X` instead of `Ctrl-A X`.

## Command table

### Getting help and leaving

| Keys | Action |
| --- | --- |
| `Ctrl-A Z` | Help screen (command summary) |
| `Ctrl-A X` | Exit and reset the modem (asks first) |
| `Ctrl-A Q` | Quit without resetting the modem, which leaves the line up |
| `Ctrl-A J` | Jump to a shell; type `exit` to return |

### Port and line settings

| Keys | Action |
| --- | --- |
| `Ctrl-A P` | Communication parameters: baud rate, data bits, parity, stop bits (such as 115200 8N1) |
| `Ctrl-A O` | Configure minicom (same menus as `minicom -s`) |
| `Ctrl-A F` | Send a BREAK signal (used for magic SysRq, Cisco ROMMON and similar) |
| `Ctrl-A E` | Toggle local echo |
| `Ctrl-A A` | Toggle adding a linefeed after each received carriage return |
| `Ctrl-A U` | Toggle adding a carriage return after each received linefeed |
| `Ctrl-A W` | Toggle line wrap |
| `Ctrl-A T` | Terminal settings (emulation such as VT102 or ANSI, backspace key) |
| `Ctrl-A I` | Toggle the cursor keys between normal and application mode |

### Modem and dialing

| Keys | Action |
| --- | --- |
| `Ctrl-A D` | Dialing directory |
| `Ctrl-A M` | Send the modem init string |
| `Ctrl-A H` | Hang up |

### Files and transfers

| Keys | Action |
| --- | --- |
| `Ctrl-A S` | Send files (ZMODEM, YMODEM, XMODEM, Kermit, ASCII) |
| `Ctrl-A R` | Receive files |
| `Ctrl-A Y` | Paste a file, sending its contents as typed text |
| `Ctrl-A K` | Run Kermit, then redraw the screen when it finishes |
| `Ctrl-A G` | Run a `runscript` script ("Go") |

### Screen, capture and logging

| Keys | Action |
| --- | --- |
| `Ctrl-A L` | Turn the capture file on or off (logs the session to a file) |
| `Ctrl-A B` | Scrollback buffer (browse with arrow keys, search with `/`, exit with `Esc`) |
| `Ctrl-A C` | Clear the screen |
| `Ctrl-A N` | Toggle a timestamp on each line (newer versions) |

## Common workflows

1. **Quit cleanly**: `Ctrl-A X`, then Enter. On a USB serial console, `Ctrl-A Q` does the same job without touching modem lines.
2. **Fix the baud rate when the output is garbled**: `Ctrl-A P`, then pick the speed letter (for example `I` for 115200) and Enter.
3. **Fix lines that stair-step across the screen**: `Ctrl-A U` adds the missing carriage returns.
4. **Fix lines that overwrite each other**: `Ctrl-A A` adds the missing linefeeds.
5. **Log a boot session**: `Ctrl-A L`, enter a filename, reboot the device, then `Ctrl-A L` again to close the file. You can also start with `minicom -C boot.log`.
6. **Send a file over ZMODEM**: on the remote side run `rz`, then press `Ctrl-A S`, choose `zmodem` and pick the file. Install `lrzsz` locally first.
7. **Paste a config into a router**: `Ctrl-A Y`, then choose the file. Set a character delay in `Ctrl-A O` if the far end drops characters.
8. **Send a BREAK** (for example, to break into a bootloader or press a Linux SysRq key): `Ctrl-A F`.

## Gotchas

- **`screen` and `tmux` conflicts**: running minicom inside GNU `screen` means both want `Ctrl-A`. Press `Ctrl-A A` in screen to pass one through, or change minicom's command key. tmux's default `Ctrl-B` doesn't conflict.
- **X versus Q**: `X` resets the modem and may drop DTR, which can reset some boards (such as an Arduino). `Q` leaves the line alone.
- **No hardware flow control on cheap adapters**: if nothing you type arrives, turn off **Hardware Flow Control** under `Ctrl-A O` → **Serial port setup** (key `F`). This is the most common "minicom is broken" problem.
- **Saved defaults**: after changing settings in `Ctrl-A O`, choose **Save setup as dfl** so they persist in `minirc.dfl`. Named profiles (`minicom -s myboard`, then `minicom myboard`) save into `~/.minirc.myboard` or `/etc/minicom/`.
- **Colors**: start with `minicom -c on` for color, which some distros leave off by default.

## Useful command-line flags

```sh
minicom -s                          # setup menu
minicom -D /dev/ttyUSB0 -b 115200   # device and baud without a profile
minicom -o                          # skip the modem init string
minicom -m                          # Alt/Meta key as the command key
minicom -c on                       # enable color
minicom -w                          # line wrap on at start
minicom -C session.log              # capture to a file from the start
minicom -S script.run               # run a runscript at startup
```
