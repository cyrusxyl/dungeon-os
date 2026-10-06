"""Who sits where: the host, and which device plays which character.

A device is a browser with a random token (no password). The token is private. Other devices see only
`sid`, a short hash of it, so a seat list can go to everyone without letting anyone act as another device.

The host runs the table: Save, Load, Quit, End, Restart and the DM console. The first device that
asks becomes the host. Another device (for example the table screen) takes over with the host code,
which only the host sees.

A seat is one device at one character. A device may hold several seats. The state lives in memory
for one game; a server restart starts with no seats, and the join screen fills them again.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time

DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I


MAX_WRONG_CODES = 5
LOCK_SECONDS = 60


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))


class SeatError(ValueError):
    """A seat or host request the table refuses. The message says why."""


def sid(device: str) -> str:
    return hashlib.sha256(device.encode()).hexdigest()[:8]


class Seats:
    def __init__(self) -> None:
        self.host: str | None = None
        self.code = new_code()
        self.owners: dict[str, str] = {}  # character id -> device
        self.names: dict[str, str] = {}  # device -> player name
        self.away: set[str] = set()  # character ids
        self.wrong_codes = 0
        self.locked_until = 0.0

    # -- host ------------------------------------------------------------

    def is_host(self, device: str | None) -> bool:
        return bool(device) and device == self.host

    def ensure_host(self, device: str) -> bool:
        """The first device to ask becomes the host. True when it is the host now."""
        if self.host is None:
            self.host = device
        return self.is_host(device)

    def take_host(self, device: str, code: str) -> None:
        """Take the host with the code. Five wrong codes lock the door for a minute: the host can open the DM console."""
        if time.monotonic() < self.locked_until:
            raise SeatError("Too many wrong codes. Wait a minute.")
        if not secrets.compare_digest(code.strip().upper().encode(), self.code.encode()):
            self.wrong_codes += 1
            if self.wrong_codes >= MAX_WRONG_CODES:
                self.wrong_codes, self.locked_until = 0, time.monotonic() + LOCK_SECONDS
            raise SeatError("That host code is wrong.")
        self.host = device
        self.wrong_codes = 0
        # The old host's code must not work again.
        self.code = new_code()

    # -- seats -----------------------------------------------------------

    def owns(self, device: str | None, who: str) -> bool:
        return bool(device) and self.owners.get(who) == device

    def mine(self, device: str | None) -> list[str]:
        return [who for who, d in self.owners.items() if d == device]

    def can_play(self, device: str | None) -> bool:
        """A seat holder, or the host (the host may use the table's shared controls, but not another player's character)."""
        return bool(device) and (self.is_host(device) or bool(self.mine(device)))

    def claim(self, device: str, who: str, name: str | None = None) -> None:
        owner = self.owners.get(who)
        if owner and owner != device:
            raise SeatError(f"{self.names.get(owner, 'Another player')} already plays {who}.")
        self.owners[who] = device
        if name:
            self.names[device] = " ".join(name.split())[:24]

    def release(self, device: str, who: str) -> None:
        """The owner gives the seat up. The host may free any seat (a player who left)."""
        if who not in self.owners:
            return
        if not (self.owns(device, who) or self.is_host(device)):
            raise SeatError("That is not your seat.")
        del self.owners[who]
        self.away.discard(who)

    def set_away(self, device: str, who: str, away: bool) -> None:
        if not (self.owns(device, who) or self.is_host(device)):
            raise SeatError("That is not your seat.")
        if who not in self.owners:
            raise SeatError("Nobody plays that character.")
        (self.away.add if away else self.away.discard)(who)

    def player(self, device: str | None, who: str | None = None) -> str:
        """The name to put in front of this device's lines to the DM."""
        return self.names.get((self.owners.get(who) if who else None) or device or "", "") or "Player"

    # -- what everyone may see -------------------------------------------

    def public(self) -> dict:
        return {
            "host": sid(self.host) if self.host else None,
            "seats": [{"who": who, "player": self.names.get(d, "Player"), "sid": sid(d), "away": who in self.away}
                      for who, d in sorted(self.owners.items())],
        }
