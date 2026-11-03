#!/usr/bin/env python3
"""NEXUS BBS -- a pretend dial-up BBS behind a pretend Hayes modem.

Creates a pseudo-terminal, links it at ./ttyBBS, and answers like a modem.

    python3 bbs.py                 # 9600 baud feel (default)
    python3 bbs.py --baud 2400     # authentic misery
    python3 bbs.py --baud 0        # no speed limit

Then in another terminal:

    minicom -D ./ttyBBS

and type   ATDT 555-1234   to dial in.
"""
import argparse
import json
import os
import random
import re
import select
import signal
import subprocess
import sys
import termios
import time
import tty
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_FILE = HERE / "bbs_data" / "state.json"
FILES_DIR = HERE / "bbs_files"
UPLOAD_DIR = FILES_DIR / "uploads"


# ---------------------------------------------------------------- ANSI bits
def col(*codes):
    return "\x1b[" + ";".join(str(c) for c in codes) + "m"


RST = col(0)
CLS = "\x1b[2J\x1b[H"
RED, GRN, YEL, BLU, MAG, CYN, WHT = (col(1, n) for n in range(31, 38))
DGRN, DCYN, GRY = col(0, 32), col(0, 36), col(0, 37)
DIM = col(1, 30)

BANNER = [
    r"  _   _ _______  ___   _ ____  ",
    r" | \ | | ____\ \/ / | | / ___| ",
    r" |  \| |  _|  \  /| | | \___ \ ",
    r" | |\  | |___ /  \| |_| |___) |",
    r" |_| \_|_____/_/\_\\___/|____/ ",
]
BANNER_COLORS = [CYN, CYN, BLU, BLU, MAG]


class Hangup(Exception):
    """Carrier lost: caller logged off, sent +++, reset the modem, or vanished."""


# ---------------------------------------------------------------- the wire
class Line:
    """The modem's side of the serial line, with a baud-rate throttle."""

    RESET_PATTERNS = ("AT S7=", "\rATZ", "\rAT&F", "\rATH")

    def __init__(self, fd, slave_fd, baud):
        self.fd, self.slave_fd = fd, slave_fd
        self.cps = baud // 10 if baud else 0
        self.buf = b""
        self.recent = ""          # rolling input, for +++ and AT detection
        self.online = False       # True while a BBS session is connected
        self.swallow_lf = False

    # -- output
    def write(self, s):
        data = s.replace("\n", "\r\n").encode("latin-1", "replace")
        step = max(1, self.cps // 30) if self.cps else len(data) or 1
        for i in range(0, len(data), step):
            _, w, _ = select.select([], [self.fd], [], 3)
            if not w:  # nobody reading the other end: dump the queue, drop carrier
                termios.tcflush(self.slave_fd, termios.TCIFLUSH)
                raise Hangup("caller went away")
            os.write(self.fd, data[i:i + step])
            if self.cps:
                time.sleep(step / self.cps)

    def type_out(self, s, lo=0.02, hi=0.09):
        """Write like a human typing (for the sysop)."""
        for ch in s:
            self.write(ch)
            time.sleep(random.uniform(lo, hi))

    def drain(self, quiet=0.3, limit=6.0):
        """Discard input until the line has been silent for `quiet` seconds."""
        self.buf = b""
        end = time.time() + limit
        while time.time() < end and select.select([self.fd], [], [], quiet)[0]:
            os.read(self.fd, 4096)

    # -- input
    def getc(self, timeout=None):
        if not self.buf:
            r, _, _ = select.select([self.fd], [], [], timeout)
            if not r:
                return None
            self.buf = os.read(self.fd, 4096)
        ch, self.buf = self.buf[:1].decode("latin-1"), self.buf[1:]
        if self.online:
            self.recent = (self.recent + ch.upper())[-8:]
            if self.recent.endswith("+++"):
                raise Hangup("+++")
            if any(p in self.recent for p in self.RESET_PATTERNS):
                raise Hangup("modem reset")
        return ch

    def key(self):
        """One keypress, skipping escape sequences (arrow keys etc)."""
        while True:
            c = self.getc()
            if c == "\x1b":
                nxt = self.getc(0.05)
                if nxt in ("[", "O"):
                    while True:
                        t = self.getc(0.05)
                        if t is None or t.isalpha() or t == "~":
                            break
                continue
            if c == "\n" and self.swallow_lf:
                self.swallow_lf = False
                continue
            self.swallow_lf = False
            return c

    def readline(self, maxlen=70, mask=False, echo=True):
        s = ""
        while True:
            c = self.key()
            if c in "\r\n":
                self.swallow_lf = c == "\r"
                if echo:
                    self.write("\n")
                return s.strip()
            if c == "\x18":      # ZMODEM debris (CAN/ZDLE): throw the line away
                s = ""
                continue
            if c in "\x08\x7f":
                if s:
                    s = s[:-1]
                    if echo:
                        self.write("\b \b")
            elif c >= " " and len(s) < maxlen:
                s += c
                if echo:
                    self.write("*" if mask else c)


# ---------------------------------------------------------------- state
def default_state():
    return {
        "caller_count": 1336,
        "last_callers": [
            {"handle": "Night Owl", "city": "Halifax", "when": "1996-03-14 02:11"},
            {"handle": "Ratchet", "city": "Winnipeg", "when": "1996-03-14 01:42"},
            {"handle": "Byte Bandit", "city": "Tacoma", "when": "1996-03-13 23:05"},
        ],
        "messages": [
            {"from": "Sysop Doc", "to": "All", "subj": "Welcome to NEXUS!",
             "date": "1996-03-01",
             "body": "Welcome aboard. Be excellent to each other, no warez,\n"
                     "and please do not tie up the line for more than an hour.\n"
                     "My mom needs the phone in the morning.\n\n-- Doc"},
            {"from": "Night Owl", "to": "All", "subj": "14.4 modem for sale",
             "date": "1996-03-09",
             "body": "Upgraded to a 28.8, so my old 14.4 external is up for\n"
                     "grabs. Works great, slight burn smell. $40 OBO."},
            {"from": "Ratchet", "to": "Night Owl", "subj": "Re: 14.4 modem for sale",
             "date": "1996-03-10",
             "body": "> slight burn smell\n\nI'll give you $15 and a box of 3.5\" floppies."},
        ],
    }


def load_state():
    try:
        return json.loads(DATA_FILE.read_text())
    except (OSError, ValueError):
        return default_state()


def save_state(st):
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(st, indent=2))


def seed_files():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    samples = {
        "README.TXT": "NEXUS BBS FILE LIBRARY\r\n\r\nIf you are reading this, ZMODEM works. Congratulations!\r\n",
        "MODEMFAQ.TXT": "Q: Why is my modem screaming?\r\nA: That is the handshake. It is happy.\r\n\r\n"
                        "Q: Why did I get disconnected?\r\nA: Someone picked up the phone.\r\n",
        "NEXUS.ANS": "".join(c + l + "\r\n" for c, l in zip(BANNER_COLORS, BANNER)) + RST,
        "DIALDIR.TXT": "Other boards worth calling:\r\n"
                       "  The Rusty Anchor    555-0199  2400\r\n"
                       "  Static Garden       555-0142  14400\r\n"
                       "  Midnight Express    555-0177  9600\r\n",
    }
    for name, body in samples.items():
        p = FILES_DIR / name
        if not p.exists():
            p.write_text(body, encoding="latin-1")


# ---------------------------------------------------------------- the BBS
class Session:
    def __init__(self, line, state):
        self.l, self.st = line, state
        self.w = line.write
        self.start = time.time()
        self.handle = "Guest"

    def time_left(self):
        left = 60 - int((time.time() - self.start) // 60)
        if left <= 0:
            self.w(f"\n{RED}Your time limit has expired. Call again tomorrow!{RST}\n")
            raise Hangup("time up")
        return left

    def pause(self):
        self.w(f"{DIM}-- press any key --{RST}")
        self.l.key()
        self.w("\r" + " " * 22 + "\r")

    def ask(self, prompt, **kw):
        self.w(f"{YEL}{prompt}{WHT}")
        ans = self.l.readline(**kw)
        self.w(RST)
        return ans

    # -- flow
    def run(self):
        self.w(CLS)
        for c, l in zip(BANNER_COLORS, BANNER):
            self.w(c + "        " + l + "\n")
        self.w(f"\n{DCYN}          Bulletin Board System  *  Node 1  *  Est. 1994{RST}\n")
        self.w(f"{DIM}          Running on a 486DX2/66 with 8 MB RAM and a dream{RST}\n\n")
        self.login()
        while True:
            self.main_menu()

    def login(self):
        self.handle = self.ask("What is your handle? ", maxlen=20) or "Guest"
        city = self.ask("Calling from (city): ", maxlen=24) or "Parts Unknown"
        self.ask("Password: ", maxlen=20, mask=True)
        self.w(f"\n{GRN}Checking credentials", )
        for _ in range(3):
            time.sleep(0.4)
            self.w(".")
        st = self.st
        st["caller_count"] += 1
        st["last_callers"].insert(0, {"handle": self.handle, "city": city,
                                      "when": datetime.now().strftime("%Y-%m-%d %H:%M")})
        st["last_callers"] = st["last_callers"][:10]
        save_state(st)
        self.w(f" OK{RST}\n\n{WHT}Welcome, {CYN}{self.handle}{WHT}! "
               f"You are caller {YEL}#{st['caller_count']}{WHT}.{RST}\n")
        self.w(f"{GRY}You have {YEL}60{GRY} minutes today. There are "
               f"{YEL}{len(st['messages'])}{GRY} messages in the message base.{RST}\n\n")
        self.pause()

    def main_menu(self):
        t = self.time_left()
        self.w(CLS)
        self.w(f"{BLU}+{'-' * 50}+{RST}\n")
        self.w(f"{BLU}|{WHT}{'NEXUS BBS  --  Main Menu':^50}{BLU}|{RST}\n")
        self.w(f"{BLU}+{'-' * 50}+{RST}\n\n")
        items = [("M", "Message base"), ("F", "File library"),
                 ("B", "Bulletins"), ("D", "Door games"),
                 ("W", "Who's online"), ("C", "Chat with sysop"),
                 ("L", "Last callers"), ("G", "Goodbye (log off)")]
        for i in range(0, len(items), 2):
            row = ""
            for k, label in items[i:i + 2]:
                row += f"  {BLU}[{YEL}{k}{BLU}]{GRY} {label:<20}"
            self.w(row + RST + "\n")
        self.w(f"\n{DGRN}[{self.handle}] [Time left: {t} min]{RST} {WHT}Command: {RST}")
        actions = {"M": self.messages, "F": self.files, "B": self.bulletins,
                   "D": self.doors, "W": self.whos_online, "C": self.chat,
                   "L": self.last_callers, "G": self.goodbye}
        while True:
            k = self.l.key().upper()
            if k in actions:
                self.w(k + "\n")
                actions[k]()
                return

    def goodbye(self):
        if self.ask("\nReally log off? (Y/n) ", maxlen=1).upper() == "N":
            return
        self.w(f"\n{CYN}Thanks for calling NEXUS, {self.handle}. Keep your carrier strong.{RST}\n")
        time.sleep(1)
        raise Hangup("logoff")

    # -- messages
    def messages(self):
        while True:
            msgs = self.st["messages"]
            self.w(f"\n{MAG}=== Message Base: General ==={RST}\n\n")
            self.w(f"{WHT}{'#':>3}  {'From':<14}{'To':<12}{'Subject':<30}{RST}\n")
            for i, m in enumerate(msgs, 1):
                self.w(f"{YEL}{i:>3}  {CYN}{m['from'][:13]:<14}{GRY}{m['to'][:11]:<12}"
                       f"{WHT}{m['subj'][:30]}{RST}\n")
            choice = self.ask("\nRead which # ([P]ost, [Q]uit)? ", maxlen=4).upper()
            if choice in ("Q", ""):
                return
            if choice == "P":
                self.post()
            elif choice.isdigit() and 1 <= int(choice) <= len(msgs):
                m = msgs[int(choice) - 1]
                self.w(f"\n{BLU}Msg #{choice}  {GRY}Date: {m['date']}\n"
                       f"{BLU}From: {CYN}{m['from']}  {BLU}To: {GRY}{m['to']}\n"
                       f"{BLU}Subj: {WHT}{m['subj']}{RST}\n{DIM}{'-' * 50}{RST}\n")
                self.w(GRY + m["body"] + RST + "\n\n")
                self.pause()

    def post(self):
        to = self.ask("To (Enter for All): ", maxlen=20) or "All"
        subj = self.ask("Subject: ", maxlen=30)
        if not subj:
            return
        self.w(f"{DIM}Enter your message. Type /S on its own line to save, /A to abort.{RST}\n")
        lines = []
        while True:
            self.w(f"{DIM}{len(lines) + 1:>2}:{RST} ")
            ln = self.l.readline(maxlen=72)
            if ln.upper() == "/S":
                break
            if ln.upper() == "/A":
                self.w(f"{RED}Aborted.{RST}\n")
                return
            lines.append(ln)
        self.st["messages"].append({"from": self.handle, "to": to, "subj": subj,
                                    "date": datetime.now().strftime("%Y-%m-%d"),
                                    "body": "\n".join(lines)})
        save_state(self.st)
        self.w(f"{GRN}Message saved.{RST}\n")

    # -- files
    def files(self):
        while True:
            entries = sorted(p for p in FILES_DIR.iterdir() if p.is_file())
            self.w(f"\n{MAG}=== File Library ==={RST}\n\n")
            for i, p in enumerate(entries, 1):
                kb = max(1, p.stat().st_size // 1024)
                self.w(f"{YEL}{i:>3}  {CYN}{p.name:<16}{GRY}{kb:>4}K{RST}\n")
            self.w(f"\n{DIM}Uploads land in bbs_files/uploads for the sysop to review.{RST}\n")
            c = self.ask("[#] download, [U]pload, [Q]uit: ", maxlen=4).upper()
            if c in ("Q", ""):
                return
            if c == "U":
                self.w(f"{GRN}Ready to receive. Start your ZMODEM upload now "
                       f"(minicom: Ctrl-A S, choose zmodem).{RST}\n")
                self.zmodem(["rz", "-b", "-E"], UPLOAD_DIR)
            elif c.isdigit() and 1 <= int(c) <= len(entries):
                p = entries[int(c) - 1]
                self.w(f"{GRN}Sending {p.name} via ZMODEM. Your terminal should "
                       f"start receiving automatically...{RST}\n")
                self.zmodem(["sz", "-b", p.name], FILES_DIR)

    def zmodem(self, cmd, cwd):
        self.l.online = False   # ZMODEM frames may contain "+++"; don't hang up
        time.sleep(0.5)
        self.l.buf = b""
        try:
            rc = subprocess.run(cmd, cwd=cwd, stdin=self.l.fd, stdout=self.l.fd,
                                stderr=subprocess.DEVNULL, timeout=300).returncode
        except subprocess.TimeoutExpired:
            rc = -1
        self.l.drain(quiet=1.0)
        self.l.online = True
        self.w(f"\n{GRN if rc == 0 else RED}Transfer "
               f"{'complete' if rc == 0 else 'failed or aborted'}.{RST}\n")
        log(f"{' '.join(cmd)} -> exit {rc}")

    # -- bulletins
    BULLETINS = [
        ("Rules of the board",
         "1. No warez. I mean it.\n2. Real names not required, real manners are.\n"
         "3. Don't hog the line past midnight on school nights.\n"
         "4. Upload/download ratio is 1:5. Uploads of cat ASCII art count double."),
        ("Hardware upgrade fund",
         "We are $112 away from a second phone line (Node 2 for real!).\n"
         "Donations accepted at the monthly pizza meetup."),
        ("Minicom tips from the sysop",
         "Lost?            Ctrl-A Z\nLeave?           Ctrl-A X\n"
         "Capture to file? Ctrl-A L\nUpload?          Ctrl-A S\n"
         "Stair-stepping?  Ctrl-A U"),
    ]

    def bulletins(self):
        while True:
            self.w(f"\n{MAG}=== Bulletins ==={RST}\n\n")
            for i, (title, _) in enumerate(self.BULLETINS, 1):
                self.w(f"  {YEL}{i}{BLU}) {WHT}{title}{RST}\n")
            c = self.ask("\nRead which (Enter to quit)? ", maxlen=2)
            if not c.isdigit() or not 1 <= int(c) <= len(self.BULLETINS):
                return
            title, body = self.BULLETINS[int(c) - 1]
            self.w(f"\n{CYN}{title}{RST}\n{DIM}{'-' * len(title)}{RST}\n{GRY}{body}{RST}\n\n")
            self.pause()

    # -- doors
    def doors(self):
        self.w(f"\n{MAG}=== Door Games ==={RST}\n\n"
               f"  {YEL}1{BLU}) {WHT}Guess-O-Matic{RST}\n"
               f"  {YEL}2{BLU}) {WHT}Fortune Cookie{RST}\n")
        c = self.ask("\nPlay which (Enter to quit)? ", maxlen=1)
        if c == "1":
            self.guess()
        elif c == "2":
            self.fortune()

    def guess(self):
        self.w(f"\n{CYN}GUESS-O-MATIC v1.2{RST}  I'm thinking of a number from 1 to 100.\n")
        n = random.randint(1, 100)
        for tries in range(1, 8):
            g = self.ask(f"Guess {tries}/7: ", maxlen=3)
            if not g.isdigit():
                self.w(f"{RED}That's not a number, smart guy.{RST}\n")
                continue
            g = int(g)
            if g == n:
                self.w(f"{GRN}*** YOU GOT IT in {tries}! ***{RST}\n\a")
                break
            self.w(f"{YEL}{'Higher' if g < n else 'Lower'}...{RST}\n")
        else:
            self.w(f"{RED}Out of guesses. It was {n}.{RST}\n")
        self.pause()

    FORTUNES = [
        "A ZMODEM transfer started in haste is finished at 0 cps.",
        "Your next download will reach 99% before someone picks up the phone.",
        "He who types +++ without guard time shall stay online forever.",
        "You will soon upgrade to a faster modem. The BBS will still be slow.",
        "The line is busy. The line is always busy. Try again.",
        "Fortune favors those who remember Ctrl-A Z.",
    ]

    def fortune(self):
        self.w(f"\n{YEL}  .-\"\"\"-.\n {YEL} /  {WHT}*{YEL}   \\   {GRY}You crack open the cookie...{RST}\n"
               f"{YEL}  '-...-'{RST}\n\n  {CYN}{random.choice(self.FORTUNES)}{RST}\n\n")
        self.pause()

    # -- misc screens
    def whos_online(self):
        lurker = random.choice(["Night Owl", "Ratchet", "Byte Bandit", "Pixel Witch"])
        doing = random.choice(["Reading messages", "Downloading MODEMFAQ.TXT",
                               "Playing Guess-O-Matic", "Idle (probably asleep)"])
        self.w(f"\n{MAG}=== Who's Online ==={RST}\n\n"
               f"{WHT}Node  User            Activity{RST}\n"
               f"{YEL}  1   {CYN}{self.handle:<16}{GRY}Viewing who's online{RST}\n"
               f"{YEL}  2   {CYN}{lurker:<16}{GRY}{doing}{RST}\n"
               f"{YEL}  3   {DIM}--              Waiting for caller{RST}\n\n")
        self.pause()

    def last_callers(self):
        self.w(f"\n{MAG}=== Last Callers ==={RST}\n\n")
        for c in self.st["last_callers"]:
            self.w(f"{CYN}{c['handle'][:18]:<19}{GRY}{c['city'][:20]:<21}{DIM}{c['when']}{RST}\n")
        self.w("\n")
        self.pause()

    SYSOP_REPLIES = [
        (r"\b(hi|hello|hey|yo)\b", "hey! glad you called in. what's up?"),
        (r"minicom", "minicom! respect. ctrl-a z if you ever get lost in there"),
        (r"zmodem|download|upload|file", "file library is under F. zmodem should kick off automatically"),
        (r"modem|baud|speed", "running a 14.4 on this node. saving up for a 28.8"),
        (r"\b(bye|later|cya|gtg)\b", "later! don't forget to log off properly, the line gets weird otherwise"),
        (r"\?$", "good question. honestly no idea, it's 2am"),
    ]
    SYSOP_FILLER = ["heh", "nice", "oh totally", "sorry, was eating cereal",
                    "hold on my mom's yelling about the phone", "word"]

    def chat(self):
        self.w(f"\n{YEL}Paging the sysop")
        for _ in range(5):
            self.w(".\a")
            time.sleep(0.7)
        self.w(f"{RST}\n\n{GRN}*** Sysop Doc has entered chat. Type /Q to leave. ***{RST}\n\n")
        self.w(f"{CYN}Doc: {RST}")
        self.l.type_out(f"oh hey {self.handle}! what can i do for ya?")
        self.w("\n")
        while True:
            self.w(f"{YEL}{self.handle}: {WHT}")
            msg = self.l.readline(maxlen=70)
            self.w(RST)
            if msg.upper() == "/Q":
                self.w(f"{GRN}*** Chat ended. ***{RST}\n")
                time.sleep(0.5)
                return
            time.sleep(random.uniform(0.6, 1.5))
            reply = next((r for pat, r in self.SYSOP_REPLIES
                          if re.search(pat, msg.lower())), random.choice(self.SYSOP_FILLER))
            self.w(f"{CYN}Doc: {RST}")
            self.l.type_out(reply)
            self.w("\n")


# ---------------------------------------------------------------- the modem
def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def modem(line, baud):
    echo = True
    line.write("\n")
    while True:
        try:
            cmd = line.readline(maxlen=60, echo=echo).upper().replace(" ", "")
        except Hangup:
            continue
        if not cmd:
            continue
        if not cmd.startswith("AT"):
            line.write("\n[NEXUS-MODEM] Type  ATDT 555-1234  to dial NEXUS BBS.\n")
            continue
        body = cmd[2:]
        if "E0" in body:
            echo = False
        if "E1" in body:
            echo = True
        if body.startswith("I"):
            line.write("\nNEXUS HAYES-COMPATIBLE 14400 v.32bis\n")
        if "D" in body:
            number = body[body.index("D") + 1:].lstrip("TP")
            log(f"dial {number or '(blank)'}")
            time.sleep(0.8)
            if not number:
                line.write("\nNO DIALTONE\n")
                continue
            for _ in range(2):
                line.write("RINGING\n")
                time.sleep(1.2)
            line.write(f"CONNECT {baud or 115200}\n")
            time.sleep(0.6)
            line.online = True
            reason = "?"
            try:
                Session(line, load_state()).run()
            except Hangup as e:
                reason = str(e)
            line.online = False
            line.recent = ""
            log(f"disconnect: {reason}")
            if reason in ("+++", "modem reset"):
                line.drain()
                line.write("\nOK\n")
            elif reason != "caller went away":
                try:
                    line.write("\nNO CARRIER\n")
                except Hangup:
                    pass
            continue
        line.write("\nOK\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baud", type=int, default=9600, help="simulated line speed, 0 = unlimited")
    ap.add_argument("--link", default=str(HERE / "ttyBBS"), help="symlink to create for the port")
    args = ap.parse_args()

    seed_files()
    master, slave = os.openpty()
    tty.setraw(slave)          # no echo/translation in the line discipline
    pts = os.ttyname(slave)
    link = Path(args.link)
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        sys.exit(f"{link} exists and is not a symlink; refusing to overwrite")
    link.symlink_to(pts)

    def cleanup(*_):
        if link.is_symlink():
            link.unlink()
            log("shutting down")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    log(f"NEXUS BBS modem on {pts} (linked at {link}), {args.baud or 'unlimited'} baud")
    log(f"connect with:  minicom -D {link}    then type  ATDT 555-1234")
    try:
        modem(Line(master, slave, args.baud), args.baud)
    finally:
        cleanup()


if __name__ == "__main__":
    main()
