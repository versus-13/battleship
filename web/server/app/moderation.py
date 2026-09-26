"""
Name moderation against a stop-list. No external calls.

The name is normalized (case, homoglyphs, digit-letters, separators, repeats),
then compared with the stop-list. Two kinds of entries in data/stoplist.txt:
    =word   exact token match (short words — only this way, otherwise false positives)
    ~root   substring anywhere (long unambiguous roots)
data/allowlist.txt — tokens that are not a violation even if they contain a root.
data/reserved.txt — the same format for staff words and links (code "reserved").
Long digit runs are phone numbers or messenger ids (code "contacts").
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple

DATA = Path(__file__).parent / "data"
log = logging.getLogger("moderation")

# Latin letters and symbols → Cyrillic/letters (after lower())
HOMOGLYPHS = str.maketrans({
    "a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у",
    "k": "к", "h": "н", "b": "в", "m": "м", "t": "т",
    "0": "о", "3": "з", "4": "ч", "6": "б", "@": "а", "$": "s", "|": "l", "1": "i",
    "ё": "е",
})
# Latin words become a "mix" after that; a separate Latin pass handles them
LATIN_SUBST = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "@": "a", "$": "s", "|": "l", "!": "i"})

NAME_RE = re.compile(r"^[А-Яа-яЁёA-Za-z0-9 _-]+$")
MIN_LEN, MAX_LEN = 2, 16
# a phone or a messenger id: a run of 5+ digits or 6+ digits in total; "Вася2010" passes
DIGIT_RUN, DIGITS_TOTAL = 5, 6


@dataclass
class ModerationResult:
    ok: bool
    code: str = "ok"           # ok | too_short | too_long | invalid_chars | contacts | rejected_profanity | reserved
    rule: Optional[str] = None


def _collapse(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


def normalize_variants(name: str) -> Tuple[str, str, List[str], List[str]]:
    """Returns (Cyrillic variant, Latin variant, Cyrillic tokens, Latin tokens)."""
    s = unicodedata.normalize("NFKC", name).lower()
    cyr_tokens = [_collapse(re.sub(r"[^а-я]", "", t.translate(HOMOGLYPHS))) for t in re.split(r"[\s_\-.]+", s)]
    lat_tokens = [_collapse(re.sub(r"[^a-z]", "", t.translate(LATIN_SUBST))) for t in re.split(r"[\s_\-.]+", s)]
    cyr_tokens = [t for t in cyr_tokens if t]
    lat_tokens = [t for t in lat_tokens if t]
    return "".join(cyr_tokens), "".join(lat_tokens), cyr_tokens, lat_tokens


def _load(path: Path) -> List[str]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


MIN_ROOT = 3


class _Rules:
    def __init__(self, path: Path):
        self.exact: Set[str] = set()
        self.roots: List[str] = []
        for entry in _load(path):
            if entry.startswith("="):
                self.exact.add(_collapse(entry[1:]))
            elif entry.startswith("~"):
                root = _collapse(entry[1:])
                if len(root) < MIN_ROOT:
                    # "~xxx" collapses to "x" and would match every name with an x in it
                    log.warning("%s: корень %r короче %d букв после схлопывания — проверяю как целое слово",
                                path.name, entry, MIN_ROOT)
                    self.exact.add(root)
                else:
                    self.roots.append(root)


class Moderator:
    def __init__(self, stoplist: Optional[Path] = None, allowlist: Optional[Path] = None,
                 reserved: Optional[Path] = None):
        self.stop = _Rules(stoplist or DATA / "stoplist.txt")
        self.reserved = _Rules(reserved or DATA / "reserved.txt")
        self.allow: Set[str] = {_collapse(a) for a in _load(allowlist or DATA / "allowlist.txt")}

    def _violation(self, rules: _Rules, variants) -> Optional[str]:
        cyr, lat, cyr_tokens, lat_tokens = variants
        for tokens in (cyr_tokens, lat_tokens):
            for t in tokens:
                if t not in self.allow and t in rules.exact:
                    return "=" + t
        for joined, tokens in ((cyr, cyr_tokens), (lat, lat_tokens)):
            if all(t in self.allow for t in tokens):
                continue
            for root in rules.roots:
                if root in joined:
                    return "~" + root
        return None

    def check(self, name: str) -> ModerationResult:
        if not isinstance(name, str):
            return ModerationResult(False, "invalid_chars")
        stripped = name.strip()
        if len(stripped) < MIN_LEN:
            return ModerationResult(False, "too_short")
        if len(stripped) > MAX_LEN:
            return ModerationResult(False, "too_long")
        if not NAME_RE.match(stripped) or "  " in stripped:
            return ModerationResult(False, "invalid_chars")
        digits = re.findall(r"\d+", stripped)
        if any(len(d) >= DIGIT_RUN for d in digits) or sum(map(len, digits)) >= DIGITS_TOTAL:
            return ModerationResult(False, "contacts")
        variants = normalize_variants(stripped)
        rule = self._violation(self.stop, variants)
        if rule:
            return ModerationResult(False, "rejected_profanity", rule)
        rule = self._violation(self.reserved, variants)
        if rule:
            return ModerationResult(False, "reserved", rule)
        return ModerationResult(True)


def clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip())


moderator = Moderator()
