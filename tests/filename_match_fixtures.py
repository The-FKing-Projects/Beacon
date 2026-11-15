"""Offline fixtures for conservative .deb filename likely matching.

Deterministic tables only — no network. Used by tracking unit tests to lock
Feishin / Moonfin / LocalSend / gh-style heuristics and important non-matches
(wrong arch, wrong product, musl/glibc bat). Heuristic behavior lives in
tracking.asset_match; these fixtures must not invent new match rules.
"""

# (filename, package, architecture, expected_prefix)
# expected_prefix is the start of asset_match()'s return string.

FEISHIN_STYLE_CASES = [
    # Positives: product-linux-arch (optional separators / arch aliases).
    ("Feishin-linux-amd64.deb", "feishin", "amd64", "Likely candidate"),
    ("feishin-linux-amd64.deb", "feishin", "amd64", "Likely candidate"),
    ("Feishin_linux_amd64.deb", "feishin", "amd64", "Likely candidate"),
    ("Feishin-linux-x86_64.deb", "feishin", "amd64", "Likely candidate"),
    ("Feishin-linux-arm64.deb", "feishin", "arm64", "Likely candidate"),
    ("Feishin-linux-aarch64.deb", "feishin", "arm64", "Likely candidate"),
    ("Feishin-1.17.0-linux-amd64.deb", "feishin", "amd64", "Likely candidate"),
    # Negatives.
    ("Feishin-linux-arm64.deb", "feishin", "amd64", "Not suggested"),
    ("Feishin-linux-amd64.deb", "feishin", "arm64", "Not suggested"),
    ("Feishin-linux-amd64.deb", "other", "amd64", "Unverified"),
    # Hyphen folding matches clover-eye style (fei-shin ≡ feishin); use a
    # distinct product token that must stay unverified.
    ("Feishin-linux-amd64.deb", "feishinx", "amd64", "Unverified"),
    ("Feishin-musl-linux-amd64.deb", "feishin", "amd64", "Unverified"),
    ("Feishin-linux.deb", "feishin", "amd64", "Unverified"),
    ("Feishin-windows-amd64.deb", "feishin", "amd64", "Unverified"),
]

MOONFIN_STYLE_CASES = [
    # Positives: Linux+version → amd64 only; explicit arch before version.
    ("Moonfin_Linux_v3.1.0.deb", "moonfin", "amd64", "Likely candidate"),
    ("moonfin_linux_v3.1.0.deb", "moonfin", "amd64", "Likely candidate"),
    ("Moonfin-Linux-v3.1.0.deb", "moonfin", "amd64", "Likely candidate"),
    ("Moonfin_Linux_3.1.0.deb", "moonfin", "amd64", "Likely candidate"),
    ("Moonfin_Linux_amd64_v3.1.0.deb", "moonfin", "amd64", "Likely candidate"),
    ("Moonfin_Linux_x86_64_v3.1.0.deb", "moonfin", "amd64", "Likely candidate"),
    ("Moonfin_Linux_arm64_v3.1.0.deb", "moonfin", "arm64", "Likely candidate"),
    # Negatives.
    ("Moonfin_Linux_v3.1.0.deb", "moonfin", "arm64", "Unverified"),
    ("Moonfin_Linux_v3.1.0.deb", "moonfin", "i386", "Unverified"),
    ("Moonfin_Linux_v3.1.0.deb", "other", "amd64", "Unverified"),
    ("OtherApp_Linux_v1.0.0.deb", "moonfin", "amd64", "Unverified"),
    ("Moonfin_Windows_v3.1.0.deb", "moonfin", "amd64", "Unverified"),
    ("Moonfin_Linux.deb", "moonfin", "amd64", "Unverified"),
    ("Moonfin_v3.1.0.deb", "moonfin", "amd64", "Unverified"),
    ("Moonfin_Linux_arm64_v3.1.0.deb", "moonfin", "amd64", "Not suggested"),
]

# bat glibc vs musl: linux token stripping must not promote musl assets.
BAT_LINUX_TOKEN_CASES = [
    ("bat_0.26.1_amd64.deb", "bat", "amd64", "Likely candidate"),
    ("bat-musl_0.26.1_arm64.deb", "bat", "arm64", "Unverified"),
    ("bat-musl_0.26.1_musl-linux-amd64.deb", "bat", "amd64", "Unverified"),
    ("bat-musl_0.26.1_linux-amd64.deb", "bat", "amd64", "Unverified"),
    ("bat_0.26.1_musl-linux-amd64.deb", "bat", "amd64", "Unverified"),
]

# LocalSend-style hyphenated arch aliases and version-before-linux names.
LOCALSEND_STYLE_CASES = [
    ("LocalSend-1.18.2-linux-x86-64.deb", "localsend", "amd64", "Likely candidate"),
    ("LocalSend-1.18.2-linux-arm-64.deb", "localsend", "arm64", "Likely candidate"),
    ("LocalSend-1.18.2-linux-x86-64.deb", "localsend", "arm64", "Not suggested"),
    ("LocalSend-1.18.2-linux-arm-64.deb", "localsend", "amd64", "Not suggested"),
    ("LocalSend-1.18.2-linux-x86-64.deb", "other", "amd64", "Unverified"),
    ("LocalSend-1.18.2-linux-x86_64.deb", "localsend", "amd64", "Likely candidate"),
]

# gh / cli underscore name_VERSION_linux_ARCH (needs version strip after linux).
GH_STYLE_CASES = [
    ("gh_2.104.0_linux_amd64.deb", "gh", "amd64", "Likely candidate"),
    ("gh_2.104.0_linux_arm64.deb", "gh", "arm64", "Likely candidate"),
    ("gh_2.104.0_linux_amd64.deb", "gh", "arm64", "Not suggested"),
    ("gh_2.104.0_linux_amd64.deb", "cli", "amd64", "Unverified"),
    # Hyphenated product-version-linux-arch already worked; keep locked.
    ("rclone-v1.76.0-linux-amd64.deb", "rclone", "amd64", "Likely candidate"),
]

# Message fragments required for specific positive outcomes.
REQUIRED_MESSAGE_FRAGMENTS = [
    (
        "Moonfin_Linux_v3.1.0.deb",
        "moonfin",
        "amd64",
        "Linux platform token treated as amd64",
    ),
    (
        "Feishin-linux-amd64.deb",
        "feishin",
        "amd64",
        "filename matches package name and amd64 architecture",
    ),
    (
        "Moonfin_Linux_amd64_v3.1.0.deb",
        "moonfin",
        "amd64",
        "filename matches package name and amd64 architecture",
    ),
    (
        "LocalSend-1.18.2-linux-x86-64.deb",
        "localsend",
        "amd64",
        "filename matches package name and amd64 architecture",
    ),
    (
        "gh_2.104.0_linux_amd64.deb",
        "gh",
        "amd64",
        "filename matches package name and amd64 architecture",
    ),
]


def all_prefix_cases():
    """Yield every (filename, package, arch, expected_prefix) fixture row."""
    for row in FEISHIN_STYLE_CASES:
        yield row
    for row in MOONFIN_STYLE_CASES:
        yield row
    for row in BAT_LINUX_TOKEN_CASES:
        yield row
    for row in LOCALSEND_STYLE_CASES:
        yield row
    for row in GH_STYLE_CASES:
        yield row
