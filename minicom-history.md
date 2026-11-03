# Minicom and Serial Terminals, Then and Now

*Written 2026-11-02. Facts are from memory and not checked against sources, so treat dates as approximate.*

## What minicom is

Minicom is a full-screen, menu-driven serial terminal for Unix and Linux. Miquel van Smoorenburg started it around 1991, and it is still maintained today. Its own man page calls it "somewhat a clone of the MS-DOS Telix communication program." That is why it felt familiar to DOS users moving to Linux.

Van Smoorenburg also wrote Linux's `sysvinit`. Later maintainers included Jukka Lahtinen and Adam Lackorzynski. The project now lives on Debian's Salsa GitLab and is packaged by every major distro.

Signature features:

- **Ctrl-A command prefix**: `Ctrl-A Z` opens help and `Ctrl-A X` quits. See [minicom-ctrl-a.md](minicom-ctrl-a.md).
- **`minicom -s` setup screen**: sets the port, baud rate, 8N1 framing and modem strings, and saves them to `minirc.dfl`.
- **Dialing directory**: stores numbers along with the modem's init, dial and hangup AT strings.
- **External file transfers**: uses `sz`/`rz` (later the `lrzsz` package) for ZMODEM, YMODEM and XMODEM, plus Kermit.
- **`runscript`**: a small scripting language for automating BBS and shell-account logins.
- **VT102/ANSI emulation with color**: essential for BBS ANSI art.

## 1990s alternatives

In the modem era, each platform had its own favorites. Most were built for dialing BBSes and shell accounts.

| Platform | Program | Notes |
| --- | --- | --- |
| Unix | `cu` | From UUCP in late-1970s Unix. Minimal; exit with `~.` |
| Unix (BSD) | `tip` | BSD's equivalent. Uses `~` escapes; hosts go in `/etc/remote` |
| Unix and many others | C-Kermit | From Columbia University (Frank da Cruz). Its own transfer protocol and strong scripting |
| Unix (X11) | Seyon | Graphical terminal for X |
| Unix | ECU, Pcomm, xc | Full-screen tools; Pcomm was a Procomm clone |
| DOS | Telix | The program minicom was modeled on |
| DOS | Procomm / Procomm Plus | From Datastorm; hugely popular |
| DOS | Qmodem, Telemate, Crosstalk | Common in the BBS era |
| DOS | MS-DOS Kermit | Columbia's DOS port |
| Windows | Terminal.exe | Built into Windows 3.x |
| Windows | HyperTerminal | From Hilgraeve; bundled with Windows from Windows 95 |
| Mac | ZTerm | Much-loved shareware |
| Mac | MicroPhone, White Knight | Scriptable commercial options |
| Amiga | JR-Comm, NComm, Term | |
| Atari ST | Flash, Freeze Dried Terminal | |

## Alternatives today

Modems are mostly gone. These tools now act as serial consoles for Raspberry Pis, routers, switches and microcontrollers. The usual connection is a USB-serial adapter (FTDI, CP2102 or CH340) at 115200 baud.

| Kind | Tool | Why people pick it |
| --- | --- | --- |
| Terminal | minicom | Still in every distro; familiar menus |
| Terminal | picocom | Minimal and starts instantly |
| Terminal | tio | Reconnects automatically on unplug; timestamps, logging and Lua scripting |
| Terminal | `screen` | Usually already installed. Its Ctrl-A prefix clashes with minicom's |
| Terminal | pyserial miniterm | Works anywhere Python is installed |
| Terminal | `cu`, C-Kermit | Both still around. Kermit became open source after Columbia ended the project in 2011 |
| Terminal | microcom | Comes with BusyBox, so it's common on embedded systems |
| GUI, Windows | PuTTY, Tera Term, RealTerm, MobaXterm, SecureCRT | PuTTY and Tera Term are the common free choices |
| GUI, Linux | CuteCom, GTKTerm, moserial | Simple desktop serial windows |
| GUI, cross-platform | CoolTerm, Serial.app (macOS) | Polished hex and logging views |
| Developer tools | Arduino serial monitor, PlatformIO `pio device monitor`, VS Code serial extensions | Built into the embedded workflow |

## Quick start: open a serial console

Replace `/dev/ttyUSB0` with your device, such as `/dev/ttyACM0` on Linux or `/dev/tty.usbserial-*` on macOS.

```sh
minicom -D /dev/ttyUSB0 -b 115200        # quit: Ctrl-A X
picocom -b 115200 /dev/ttyUSB0           # quit: Ctrl-A Ctrl-X
tio -b 115200 /dev/ttyUSB0               # quit: Ctrl-T Q
screen /dev/ttyUSB0 115200               # quit: Ctrl-A K (or Ctrl-A \)
python -m serial.tools.miniterm /dev/ttyUSB0 115200   # quit: Ctrl-]
cu -l /dev/ttyUSB0 -s 115200             # quit: ~.
```

If you get "Permission denied", add yourself to the serial group, then log out and back in. The group is `dialout` on Debian and Ubuntu, or `uucp` on Arch:

```sh
sudo usermod -aG dialout $USER
```
