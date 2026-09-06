"""Static check for CPython-only constructs in the firmware.

Why this exists: `test_firmware.py` runs the firmware's logic on CPython, which
is excellent for the decision engine and useless for portability. CPython has
`str.ljust`; MicroPython does not, and the difference does not surface until the
board raises AttributeError halfway through drawing a screen. That bug cost a
demo, so it gets a check.

    python check_micropython.py main.py

Nothing here proves the firmware runs - only that it avoids the specific
constructs the ESP32 MicroPython port is known to omit.
"""
import re
import sys

# Methods CPython's str has and MicroPython's does not. The port drops them to
# save flash; the code must pad and case-fold by hand.
ABSENT_STR_METHODS = (
    "ljust", "rjust", "center", "zfill", "casefold", "title",
    "expandtabs", "removeprefix", "removesuffix", "format_map",
)

# Modules that do not exist on the ESP32 port at all.
ABSENT_MODULES = (
    "dataclasses", "typing", "functools", "itertools", "enum",
    "abc", "logging", "datetime", "decimal", "statistics",
)

RULES = [
    (re.compile(r"\.(" + "|".join(ABSENT_STR_METHODS) + r")\s*\("),
     "str method not present in MicroPython"),
    (re.compile(r"^\s*(?:import|from)\s+(" + "|".join(ABSENT_MODULES) + r")\b"),
     "module not available on the ESP32 port"),
    (re.compile(r"""(?<![A-Za-z0-9_])[fF](?=["'])"""),
     "f-string - not supported by every MicroPython build"),
    (re.compile(r"\bnext\s*\([^)]*,"),
     "next(iterator, default) - the two-argument form is not universal"),
    (re.compile(r"\{:[^}]*\{"),
     "nested format field width - unreliable in MicroPython"),
]


def check(path):
    findings = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            stripped = line.split("#", 1)[0]
            for pattern, why in RULES:
                if pattern.search(stripped):
                    findings.append((number, why, line.rstrip()))
    return findings


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "main.py"
    findings = check(path)
    if not findings:
        print("{}: clean - no known CPython-only constructs".format(path))
        return 0
    print("{}: {} problem(s)".format(path, len(findings)))
    for number, why, text in findings:
        print("  line {}: {}".format(number, why))
        print("    " + text.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main())
