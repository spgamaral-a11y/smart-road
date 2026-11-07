#!/usr/bin/env python3
"""Phase 0 probe for DATA/docs/SPEC_EXPORT_GPS_CSV.md: what a dashcam file really contains.

Run it on your own machine, where the clips, ExifTool and Tesseract are. Copy the clips
into the repository's Input/ folder (or link your footage folder there), then:

    python3 scripts/probe_dashcam.py                    every video in Input/, subfolders included
    python3 scripts/probe_dashcam.py CLIP.MP4 FOLDER    or just these clips and folders

Give it the clips Phase 0 asks for: a VIOFO clip recorded normally, a VIOFO timelapse
clip, and a Garmin clip downloaded from YouTube. For each one it records what spec §10
(Phase 0) asks for:

- the two ExifTool commands, worded as in the spec, plus ExifTool's JSON fixes;
- `moov`'s children, the track handlers and any make or encoder strings: the evidence
  profile detection uses (spec §8.9);
- the Novatek `gps ` table, decoded with the layout in spec A.3 and compared with ExifTool;
- the stamp, read with Tesseract (and RapidOCR, if installed) on 5 frames, in each
  built-in stamp layout;
- whether the stamp changes on every frame, and the timelapse speed-up from 3 clusters
  of reads (spec A.8).

From those it works out the camera's UTC offset, whether mvhd holds local time or UTC,
whether the stamp time matches the GPS time, and how many GPS blocks there are per video
second. It also measures what the spec's estimates assume: decode speed, OCR time per
read, whether seeking lands on the exact frame, and where the bottom of the image stops
changing (the bonnet).

Everything goes to Output/probe/ (git keeps only Output/README.md):

    phase0_report.md   Send this back. Stamp text is masked to the fields the parser reads,
                       so your plate and custom text don't appear in it.
    <clip>/probe.json  The same, machine-readable, also masked.
    <clip>/exiftool_*  ExifTool's raw output.
    <clip>/crops/      The stamp crops OCR saw. They show your plate: keep them to yourself.
    <clip>/frame_50pct_stamp_masked.jpg and <clip>/static_map.png: geometry hints, with the
                       stamp area blacked out.

Needs Python with opencv-python (or opencv-python-headless) and numpy, Tesseract and
ExifTool. On Ubuntu:

    sudo apt install tesseract-ocr libimage-exiftool-perl
    pip install rapidocr_onnxruntime        (optional, a second OCR engine)

On Windows: winget install -e --id UB-Mannheim.TesseractOCR, and
winget install -e --id OliverBetz.ExifTool. On macOS: brew install tesseract exiftool.

This is a diagnostic, not part of the app. The stamp parser and the timelapse detection
below are byte-for-byte copies of spec A.1 and A.8; the Novatek reader follows spec A.3.
Phase 3's modules in smartroad/survey/ replace them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import platform
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
#: The dedicated folders (spec §6.0). Environment variables move them, e.g. to a footage drive.
INPUT_DIR = Path(os.environ.get("SMARTROAD_INPUT") or ROOT / "Input")
OUTPUT_DIR = Path(os.environ.get("SMARTROAD_OUTPUT") or ROOT / "Output")
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}
QT_EPOCH = dt.datetime(1904, 1, 1)
STAMP_EPOCH = dt.datetime(2000, 1, 1)
UTC = dt.timezone.utc

# ============================================================ copied from spec A.1 (version 1.4)
DEG = r"[°º˚*oO]"                  # degree sign and its usual OCR misreads
MIN = r"['’′`´°º*]"                # minute mark (OCR often reads it as a degree sign or '*')
SEC = r"(?:[\"”″]|'')"             # second mark
HEM_LAT = r"[NS$5]"                # '$' and '5' are OCR misreads of 'S'
SPEED = re.compile(r"(?P<v>\d{1,3})\s*(?P<u>KM\s*/?\s*H|MPH)", re.I)
COORD_DMS = re.compile(
    rf"(?P<lath>{HEM_LAT})\s*(?P<latd>\d{{1,3}})\s*(?:{DEG}\s*|\s+)(?P<latm>\d{{1,2}})\s*(?:{MIN}\s*|\s+)"
    rf"(?P<lats>\d{{1,2}}(?:\.\d+)?)\s*{SEC}?\s*[,;]?\s*"
    rf"(?P<lonh>[EW])\s*(?P<lond>\d{{1,3}})\s*(?:{DEG}\s*|\s+)(?P<lonm>\d{{1,2}})\s*(?:{MIN}\s*|\s+)"
    rf"(?P<lons>\d{{1,2}}(?:\.\d+)?)", re.I)
COORD_DDM = re.compile(                                       # Garmin default: hddd°mm.mmm'
    rf"(?P<lath>{HEM_LAT})\s*(?P<latd>\d{{1,3}})\s*(?:{DEG}\s*|\s+)(?P<latm>\d{{1,2}}\.\d{{1,5}})\s*{MIN}?\s*[,;]?\s*"
    rf"(?P<lonh>[EW])\s*(?P<lond>\d{{1,3}})\s*(?:{DEG}\s*|\s+)(?P<lonm>\d{{1,2}}\.\d{{1,5}})", re.I)
COORD_DD = re.compile(                                        # VIOFO: S12.035136 E13.955326
    rf"(?P<lath>{HEM_LAT})\s*(?P<lat>\d{{1,2}}\.\d{{4,7}})\s*{DEG}?\s*[,;]?\s*(?P<lonh>[EW])\s*(?P<lon>\d{{1,3}}\.\d{{4,7}})"
    rf"|(?P<lat2>\d{{1,2}}\.\d{{4,7}})\s*{DEG}?\s*(?P<lath2>[NS])\s*[,;]?\s*(?P<lon2>\d{{1,3}}\.\d{{4,7}})\s*{DEG}?\s*(?P<lonh2>[EW])",
    re.I)
SIGN = r"[-\u2212\u2013]"                # minus, and the Unicode minus / en dash OCR returns for it
COORD_SDD = re.compile(                                       # Garmin: -26.36774 27.31358 (signed, no hemisphere)
    rf"(?:(?P<las>{SIGN})|(?<![\d.\-\u2212\u2013]))(?P<lat>\d{{1,2}}\.\d{{4,7}})(?:\s*[,;]\s*|\s+)"
    rf"(?P<los>{SIGN})?(?P<lon>\d{{1,3}}\.\d{{4,7}})(?!\d)")


def _coord_sdd_exact(decimals: int) -> re.Pattern:
    """Signed decimal degrees with a known number of decimals: also splits run-together text
    such as "-26.3677427.31358", where only the decimal count says where latitude ends."""
    return re.compile(
        rf"(?:(?P<las>{SIGN})|(?<![\d.\-\u2212\u2013]))(?P<lat>\d{{1,2}}\.\d{{{decimals}}})\s*[,;]?\s*"
        rf"(?P<los>{SIGN})?(?P<lon>\d{{1,3}}\.\d{{{decimals}}})")    # no end check: speed may follow


DATE_TIME = re.compile(
    r"(?:(?P<y1>\d{4})[-/.](?P<m1>\d{1,2})[-/.](?P<d1>\d{1,2})"          # YYYY-MM-DD
    r"|(?P<p>\d{1,2})[-/.](?P<q>\d{1,2})[-/.](?P<y2>\d{4}))"             # DD-MM-YYYY or MM-DD-YYYY
    r"\s*,?\s*(?P<H>\d{1,2})\s?:\s?(?P<M>\d{2})\s?:\s?(?P<S>\d{2})"     # OCR may put a space beside ':'
    r"(?:\s*(?P<ap>[AP])\.?\s*M\b\.?)?", re.I)


@dataclass(frozen=True)
class StampReading:
    speed_kmh: float | None = None
    lat: float | None = None
    lon: float | None = None
    local: dt.datetime | None = None          # camera local time, naive
    date_ambiguous: bool = False              # day and month both <= 12: the order came from date_order
    coord_format: str | None = None           # "dd" | "ddm" | "dms" | "sdd"


def _sign(h: str, v: float) -> float:
    return -v if h.upper() in ("S", "$", "5", "W") else v


def _blank(text: str, m: re.Match) -> str:
    return text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]


def parse_stamp(text: str, date_order: str = "DMY", *, min_year: int = 2010,
                max_year: int | None = None, signed_dd: bool = False,
                coord_decimals: int | None = None) -> StampReading:
    """signed_dd: also accept signed decimal degrees with no hemisphere letter (Garmin). Off by
    default, because a lost minus sign can't be seen in a single reading (see the sign vote, §8.4).
    coord_decimals: the stamp's fixed number of decimals, so run-together coordinates can be split.
    Speed is searched last, in the text left after the date/time and the coordinates are taken
    out, so digits that run into "KM/H" ("27.3135870KM/H") can't be read as the speed."""
    max_year = max_year or dt.date.today().year + 1
    speed = lat = lon = when = fmt = None
    ambiguous = False
    rest = text
    if m := COORD_DMS.search(text):
        la = int(m["latd"]) + int(m["latm"]) / 60 + float(m["lats"]) / 3600
        lo = int(m["lond"]) + int(m["lonm"]) / 60 + float(m["lons"]) / 3600
        ok_parts = int(m["latm"]) < 60 and int(m["lonm"]) < 60 and float(m["lats"]) < 60 and float(m["lons"]) < 60
        cand = (_sign(m["lath"], la), _sign(m["lonh"], lo), "dms") if ok_parts else None
    elif m := COORD_DDM.search(text):
        la = int(m["latd"]) + float(m["latm"]) / 60
        lo = int(m["lond"]) + float(m["lonm"]) / 60
        ok_parts = float(m["latm"]) < 60 and float(m["lonm"]) < 60
        cand = (_sign(m["lath"], la), _sign(m["lonh"], lo), "ddm") if ok_parts else None
    elif m := COORD_DD.search(text):
        if m["lat"]:
            cand = (_sign(m["lath"], float(m["lat"])), _sign(m["lonh"], float(m["lon"])), "dd")
        else:
            cand = (_sign(m["lath2"], float(m["lat2"])), _sign(m["lonh2"], float(m["lon2"])), "dd")
    elif signed_dd and (m := (coord_decimals and _coord_sdd_exact(coord_decimals).search(text))
                        or COORD_SDD.search(text)):
        cand = (-float(m["lat"]) if m["las"] else float(m["lat"]),
                -float(m["lon"]) if m["los"] else float(m["lon"]), "sdd")
    else:
        cand = None
    if m:
        rest = _blank(rest, m)
    if cand and -90 <= cand[0] <= 90 and -180 <= cand[1] <= 180 and (cand[0], cand[1]) != (0.0, 0.0):
        lat, lon, fmt = round(cand[0], 7), round(cand[1], 7), cand[2]
    for m in DATE_TIME.finditer(text):
        amb = False
        if m["y1"]:
            y, mo, d = int(m["y1"]), int(m["m1"]), int(m["d1"])
        else:
            y, p, q = int(m["y2"]), int(m["p"]), int(m["q"])
            if p > 12:
                d, mo = p, q
            elif q > 12:
                mo, d = p, q
            else:
                amb = p != q
                d, mo = (p, q) if date_order == "DMY" else (q, p)
        if not min_year <= y <= max_year:                  # catches OCR years like 7075
            continue
        h = int(m["H"])
        if m["ap"]:
            if not 1 <= h <= 12:
                continue
            h = (h % 12) + (12 if m["ap"].upper() == "P" else 0)
        try:
            when = dt.datetime(y, mo, d, h, int(m["M"]), int(m["S"]))
        except ValueError:
            continue
        ambiguous = amb
        rest = _blank(rest, m)
        break
    if (m := SPEED.search(rest)) and int(m["v"]) <= 300:      # 870 km/h is digits run into the unit
        speed = float(m["v"]) * (1.609344 if m["u"].upper() == "MPH" else 1.0)
    return StampReading(speed, lat, lon, when, ambiguous, fmt)
# ============================================================ copied from spec A.8 (version 1.4)
CAPTURE_RATES = (1, 2, 3, 5, 10, 15)          # timelapse capture rates offered by dashcams (VIOFO: 1/2/3/5/10 fps)
SNAP_TOL = 0.05                               # snap a measured speed-up within 5 % of playback_fps / capture_rate


@dataclass(frozen=True)
class TimeBase:
    mode: str                 # "normal" | "timelapse"
    speedup: float            # driving seconds per video second
    playback_fps: float
    source: str               # "declared" | "stamp" | "gps" | "filenames" | "assumed"

    @property
    def capture_interval_s(self) -> float:      # driving seconds between consecutive frames
        return self.speedup / self.playback_fps

    def elapsed(self, t_video: float) -> float:
        return t_video * self.speedup

    def frame_elapsed(self, frame_number: int) -> float:
        return frame_number * self.capture_interval_s


def snap(speedup: float, playback_fps: float) -> tuple[str, float]:
    if abs(speedup - 1.0) <= SNAP_TOL:
        return "normal", 1.0
    for rate in CAPTURE_RATES:
        nominal = playback_fps / rate
        if nominal > 1 and abs(speedup - nominal) <= SNAP_TOL * nominal:
            return "timelapse", nominal
    return ("timelapse" if speedup > 1 else "normal"), speedup


def slope(points: list[tuple[float, float]]) -> float | None:
    """Robust slope: median of pairwise slopes between points at least 0.5 video-s apart (Theil-Sen)."""
    s = [(y2 - y1) / (x2 - x1) for i, (x1, y1) in enumerate(points) for (x2, y2) in points[i + 1:] if x2 - x1 >= 0.5]
    return statistics.median(s) if len(s) >= 2 else None


def detect(playback_fps: float, *, stamp_clusters: list[list[tuple[float, float]]] = (),
           gps_blocks: list[tuple[int, float]] = (), block_video_s: float = 1.0,
           declared: TimeBase | None = None) -> tuple[TimeBase, list[str]]:
    """stamp_clusters: a few (video t, stamp seconds) reads, 1 video-second apart, at each of 10 %,
    50 % and 90 % of the file. The slope is taken inside each cluster and the median across them,
    so a title card, or a cut between clusters in an edited video, can't bias it.
    gps_blocks: (block index, fix UTC seconds)."""
    notes, measured = [], None
    per = [m for c in stamp_clusters if (m := slope(list(c))) is not None]
    if per:
        m = statistics.median(per)
        if len(per) > 1 and max(per) - min(per) > SNAP_TOL * m:
            notes.append("speed-up differs along the file: " + ", ".join(f"x{p:.1f}" for p in per))
        measured = ("stamp", m)
    elif (m := slope([(i * block_video_s, u) for i, u in gps_blocks])) is not None:
        measured = ("gps", m)
    if declared:
        if measured:
            mode, sp = snap(measured[1], playback_fps)
            if abs(sp - declared.speedup) > SNAP_TOL * declared.speedup:
                notes.append(f"declared {declared.mode} x{declared.speedup:g} but {measured[0]} says x{measured[1]:.1f}")
        return declared, notes
    if measured:
        mode, sp = snap(measured[1], playback_fps)
        return TimeBase(mode, sp, playback_fps, measured[0]), notes
    notes.append("recording mode undetermined: assumed normal")
    return TimeBase("normal", 1.0, playback_fps, "assumed"), notes


def sample_frames(n_frames: int, tb: TimeBase, per_driving_s: float, max_frames: int | None = None):
    """(frame_number, t_video, t_elapsed) for the graded frames, chosen by driving time."""
    step = max(1, round(1 / (per_driving_s * tb.capture_interval_s)))
    out = [(k, k / tb.playback_fps, tb.frame_elapsed(k)) for k in range(step // 2, n_frames, step)]
    return out[:max_frames] if max_frames else out
# ============================================================ end of the copies


# ------------------------------------------------------------------------------ helpers
def fmt_dt(d: dt.datetime | None) -> str:
    if d is None:
        return "–"
    s = d.strftime("%Y-%m-%d %H:%M:%S")
    return s + (f".{d.microsecond // 1000:03d}" if d.microsecond else "")


def fmt_offset(seconds: float) -> str:
    m = round(abs(seconds) / 60)
    return f"{'+' if seconds >= 0 else '-'}{m // 60:02d}:{m % 60:02d}"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, a)))


def jsonable(o):
    if isinstance(o, dt.datetime):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, bytes):
        return o.hex()
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(type(o).__name__)


def write_image(path: Path, image, quality: int = 90) -> None:
    """cv2.imwrite fails on non-ASCII Windows paths, so encode in memory and write with Python."""
    ext = path.suffix.lower()
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if ext in (".jpg", ".jpeg") else []
    ok, buf = cv2.imencode(ext, image, params)
    if ok:
        path.write_bytes(buf.tobytes())


def coarse(v: float | None, args) -> float | None:
    return None if v is None else round(v, 2 if args.coarse else 6)


# ------------------------------------------------------------------------------ tools
INSTALL = {
    "linux": {"tesseract": "sudo apt install tesseract-ocr", "exiftool": "sudo apt install libimage-exiftool-perl"},
    "win32": {"tesseract": "winget install -e --id UB-Mannheim.TesseractOCR",
              "exiftool": "winget install -e --id OliverBetz.ExifTool"},
    "darwin": {"tesseract": "brew install tesseract", "exiftool": "brew install exiftool"},
}
WINDOWS_PLACES = {
    "tesseract": [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                  r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"],
    "exiftool": [r"C:\Program Files\ExifTool\ExifTool.exe", r"C:\Program Files\exiftool\exiftool.exe",
                 r"C:\Windows\exiftool.exe"],
}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def find_tool(name: str, given: str | None) -> str | None:
    if given:
        p = Path(given.strip().strip('"'))
        return str(p) if p.is_file() else None
    if found := shutil.which(name):
        return found
    if sys.platform == "win32":
        links = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / f"{name}.exe"
        for place in [*WINDOWS_PLACES[name], str(links)]:
            if Path(place).is_file():
                return place
    return None


def run(argv: list[str], timeout: float = 120) -> tuple[int | None, str, str, float]:
    """A subprocess as an argument list, no shell, output read as UTF-8 (not the Windows code page)."""
    t0 = time.perf_counter()
    try:
        p = subprocess.run(argv, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return None, "", f"timed out after {timeout:.0f} s", time.perf_counter() - t0
    except OSError as exc:
        return None, "", str(exc), time.perf_counter() - t0
    return (p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace"),
            time.perf_counter() - t0)


def first_line(argv: list[str]) -> str:
    rc, out, err, _ = run(argv, 30)
    lines = (out or err).strip().splitlines()
    return lines[0].strip() if lines else "?"


# ------------------------------------------------------------------------------ OCR (spec A.2)
TESS_WHITELIST = "0123456789.:-/ ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz°'\""


class TesseractEngine:
    name = "tesseract"

    def __init__(self, exe: str) -> None:
        self.exe = exe
        self.version = first_line([exe, "--version"])

    def read(self, crop) -> str:
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        s = 128 / g.shape[0]
        g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
        _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        img = cv2.copyMakeBorder(255 - b, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        ok, png = cv2.imencode(".png", img)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "stamp.png")
            with open(path, "wb") as fh:
                fh.write(png.tobytes())
            _, out, _, _ = run([self.exe, path, "stdout", "--psm", "7", "-c",
                                f"tessedit_char_whitelist={TESS_WHITELIST}"], 30)
        return out.strip()


class RapidEngine:
    name = "rapidocr"

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR
        self.engine = RapidOCR()
        try:
            from importlib.metadata import version
            self.version = f"rapidocr_onnxruntime {version('rapidocr_onnxruntime')}"
        except Exception:
            self.version = "rapidocr_onnxruntime"

    def read(self, crop) -> str:
        res, _ = self.engine(cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
        return " ".join(r[1] for r in sorted(res or [], key=lambda r: min(p[0] for p in r[0])))


@dataclass(frozen=True)
class Layout:
    name: str
    roi: tuple[float, float, float, float]
    signed_dd: bool = False
    coord_decimals: int | None = None


LAYOUTS = (Layout("VIOFO A129 Plus", (0.0, 0.955, 1.0, 1.0)),
           Layout("Garmin", (0.0, 0.95, 0.62, 1.0), True, 5),
           Layout("Wide bottom strip", (0.0, 0.92, 1.0, 1.0), True, None))

MAKE_TOKENS = re.compile(r"V[I1l|][O0]F[O0]|G[A4]RM[I1l|][NM]|A1[123]9|P[lI1]us|Pro|Duo|KM\s*/?\s*H|MPH", re.I)
MAKE_NAMES = {"VIOFO": re.compile(r"V[I1L|][O0]F[O0]"), "GARMIN": re.compile(r"G[A4]RM[I1L|][NM]")}


def mask_text(text: str, layout: Layout) -> str:
    """Keep only what the parser reads (date, time, coordinates, speed) and make names.
    Everything else, such as the plate and the custom text, becomes dots."""
    keep = [False] * len(text)
    patterns = [COORD_DMS, COORD_DDM, COORD_DD, COORD_SDD, DATE_TIME, SPEED, MAKE_TOKENS]
    if layout.coord_decimals:
        patterns.append(_coord_sdd_exact(layout.coord_decimals))
    for rx in patterns:
        for m in rx.finditer(text):
            keep[m.start():m.end()] = [True] * (m.end() - m.start())
    return "".join(c if keep[i] or c.isspace() else "·" for i, c in enumerate(text))


def score(r: StampReading) -> int:
    return 2 * (r.local is not None) + 2 * (r.lat is not None) + (r.speed_kmh is not None)


def crop(frame, roi):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = roi
    return frame[int(h * y0):max(int(h * y0) + 1, int(h * y1)), int(w * x0):max(int(w * x0) + 1, int(w * x1))]


def suggest_stamp_roi(frame) -> tuple[float, float, float, float] | None:
    """Spec §5.4, Suggest: rows of near-white text in the bottom 12 %, padded by 1 %."""
    h, w = frame.shape[:2]
    y0 = int(h * 0.88)
    sub = frame[y0:].astype(int)
    white = (sub.min(axis=2) > 200) & (sub.max(axis=2) - sub.min(axis=2) < 40)
    rows = np.where(white.sum(axis=1) > 15)[0]
    if not len(rows):
        return None
    band = white[rows.min():rows.max() + 1]
    cols = np.where(band.sum(axis=0) > 0)[0]
    pad_y, pad_x = 0.01, 0.01
    return (round(float(max(0.0, cols.min() / w - pad_x)), 3), round(float(max(0.0, (rows.min() + y0) / h - pad_y)), 3),
            round(float(min(1.0, (cols.max() + 1) / w + pad_x)), 3),
            round(float(min(1.0, (rows.max() + 1 + y0) / h + pad_y)), 3))


# ------------------------------------------------------------------------------ the file
def list_videos(folder: Path) -> list[Path]:
    """Every video under `folder`, in any letter case, skipping hidden files and folders.
    Follows symbolic links, so Input/ can point at a footage drive."""
    found = []
    for here, dirs, files in os.walk(folder, followlinks=True):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        found += [Path(here) / f for f in sorted(files)
                  if not f.startswith(".") and Path(f).suffix.lower() in VIDEO_SUFFIXES]
    return found


VIOFO_NAME = re.compile(
    r"(?P<Y>20\d{2})_?(?P<m>\d{2})(?P<d>\d{2})_?(?P<H>\d{2})(?P<M>\d{2})(?P<S>\d{2})"
    r"(?:_(?P<seq>\d{1,6}))?(?P<cam>[FRI])?\.(?:MP4|MOV|TS)$", re.I)
GARMIN_NAME = re.compile(r"^GRMN\d{4}\.(?:MP4|MOV)$", re.I)


def file_facts(path: Path) -> dict:
    size = path.stat().st_size
    h = hashlib.sha1(str(size).encode("ascii"))
    with open(path, "rb") as fh:
        h.update(fh.read(1 << 20))
        fh.seek(max(0, size - (1 << 20)))
        h.update(fh.read(1 << 20))
    out = {"name": path.name, "size_mb": round(size / 1e6, 1), "video_id": h.hexdigest()[:16],
           "name_local_start": None, "name_camera": None, "name_pattern": None}
    if m := VIOFO_NAME.search(path.name):
        try:
            out["name_local_start"] = dt.datetime(int(m["Y"]), int(m["m"]), int(m["d"]),
                                                  int(m["H"]), int(m["M"]), int(m["S"]))
            out["name_pattern"] = "VIOFO (date and time)"
        except ValueError:
            pass
        out["name_camera"] = (m["cam"] or "").upper() or None
    elif GARMIN_NAME.match(path.name):
        out["name_pattern"] = "Garmin (GRMNnnnn, no time)"
    return out


# ------------------------------------------------------------------------------ the container
@dataclass
class Box:
    type: bytes
    offset: int
    size: int
    hlen: int

    @property
    def name(self) -> str:
        return self.type.decode("latin-1")

    @property
    def payload(self) -> int:
        return self.offset + self.hlen

    @property
    def end(self) -> int:
        return self.offset + self.size


def iter_boxes(fh, start: int, end: int):
    pos = start
    while pos + 8 <= end:
        fh.seek(pos)
        head = fh.read(8)
        if len(head) < 8:
            return
        size, typ = struct.unpack(">I4s", head)
        hlen = 8
        if size == 1:
            ext = fh.read(8)
            if len(ext) < 8:
                return
            size, hlen = struct.unpack(">Q", ext)[0], 16
        elif size == 0:
            size = end - pos
        if size < hlen:
            return
        yield Box(typ, pos, min(size, end - pos), hlen)
        if pos + size > end:
            return
        pos += size


def printable_runs(data: bytes, least: int = 4) -> list[str]:
    return [m.group().decode("latin-1") for m in re.finditer(rb"[\x20-\x7e]{%d,}" % least, data)][:8]


def looks_like_box(fh, pos: int, end: int) -> bool:
    fh.seek(pos)
    head = fh.read(8)
    if len(head) < 8:
        return False
    size = struct.unpack(">I", head[:4])[0]
    return 8 <= size <= end - pos and all(32 <= c < 127 or c == 0xA9 for c in head[4:8])


def meta_strings(fh, box: Box, out: dict) -> None:
    """iTunes-style metadata: meta -> (keys) + ilst -> item -> data."""
    start = box.payload if looks_like_box(fh, box.payload, box.end) else box.payload + 4
    keys: list[str] = []
    for c in iter_boxes(fh, start, box.end):
        if c.type == b"keys":
            fh.seek(c.payload + 4)
            count = struct.unpack(">I", fh.read(4))[0]
            for _ in range(min(count, 200)):
                size = struct.unpack(">I", fh.read(4))[0]
                keys.append(fh.read(max(0, size - 4))[4:].decode("utf-8", "replace"))
        elif c.type == b"ilst":
            for item in iter_boxes(fh, c.payload, c.end):
                key = item.name
                if item.type[0] == 0 and keys:
                    idx = struct.unpack(">I", item.type)[0]
                    key = keys[idx - 1] if 0 < idx <= len(keys) else key
                for d in iter_boxes(fh, item.payload, item.end):
                    if d.type == b"data" and d.size <= 4096:
                        fh.seek(d.payload)
                        raw = fh.read(d.size - d.hlen)
                        kind = struct.unpack(">I", raw[:4])[0] & 0xFFFFFF if len(raw) >= 4 else 0
                        out[f"meta {key}"] = (raw[8:].decode("utf-8", "replace") if kind == 1
                                              else raw[8:40].hex())


def udta_strings(fh, box: Box, out: dict) -> None:
    for c in iter_boxes(fh, box.payload, box.end):
        if c.type == b"meta":
            meta_strings(fh, c, out)
            continue
        if c.size > 65536:
            out[f"udta {c.name}"] = f"<{c.size} bytes>"
            continue
        fh.seek(c.payload)
        raw = fh.read(c.size - c.hlen)
        if c.type[0] == 0xA9 and len(raw) >= 4:                      # QuickTime text atom
            n = struct.unpack(">H", raw[:2])[0]
            text = raw[4:4 + n].decode("utf-8", "replace") if 0 < n <= len(raw) - 4 else ""
            out[f"udta {c.name}"] = text or " | ".join(printable_runs(raw))
        else:
            runs = printable_runs(raw)
            out[f"udta {c.name}"] = " | ".join(runs) if runs else f"<{len(raw)} bytes>"


def handler(fh, box: Box) -> tuple[str, str]:
    fh.seek(box.payload)
    raw = fh.read(min(box.size - box.hlen, 512))
    kind = raw[8:12].decode("latin-1") if len(raw) >= 12 else "?"
    name = raw[24:]
    if name and name[0] == len(name) - 1:                              # QuickTime counted string
        name = name[1:]
    return kind, name.split(b"\x00")[0].decode("utf-8", "replace").strip()


def sample_format(fh, stbl: Box) -> str | None:
    for c in iter_boxes(fh, stbl.payload, stbl.end):
        if c.type == b"stsd":
            fh.seek(c.payload + 8 + 4)
            return fh.read(4).decode("latin-1")
    return None


def track_facts(fh, trak: Box) -> dict:
    out = {"handler": None, "handler_name": None, "format": None}
    for c in iter_boxes(fh, trak.payload, trak.end):
        if c.type != b"mdia":
            continue
        for m in iter_boxes(fh, c.payload, c.end):
            if m.type == b"hdlr":
                out["handler"], out["handler_name"] = handler(fh, m)
            elif m.type == b"minf":
                for s in iter_boxes(fh, m.payload, m.end):
                    if s.type == b"stbl":
                        out["format"] = sample_format(fh, s)
    return out


def container_facts(path: Path) -> dict:
    size = path.stat().st_size
    out = {"top_level": [], "moov_children": [], "tracks": [], "strings": {}, "ftyp": None,
           "mvhd": None, "gps_box": None}
    with open(path, "rb") as fh:
        moov = None
        for b in iter_boxes(fh, 0, size):
            out["top_level"].append([b.name, b.size])
            if b.type == b"ftyp":
                fh.seek(b.payload)
                raw = fh.read(min(b.size - b.hlen, 256))
                out["ftyp"] = {"major": raw[:4].decode("latin-1"),
                               "compatible": [raw[i:i + 4].decode("latin-1") for i in range(8, len(raw) - 3, 4)]}
            elif b.type == b"moov":
                moov = b
        if moov is None:
            return out
        for i, c in enumerate(iter_boxes(fh, moov.payload, moov.end)):
            out["moov_children"].append([c.name, c.size])
            if c.type == b"mvhd":
                fh.seek(c.payload)
                version = fh.read(4)[0]
                if version == 1:
                    created, _, scale, duration = struct.unpack(">QQIQ", fh.read(28))
                else:
                    created, _, scale, duration = struct.unpack(">IIII", fh.read(16))
                out["mvhd"] = {"created_raw": created,
                               "created": QT_EPOCH + dt.timedelta(seconds=created) if created else None,
                               "duration_s": round(duration / scale, 3) if scale else None}
            elif c.type == b"gps ":
                out["gps_box"] = {"index_in_moov": i, "offset": c.offset, "payload": c.payload,
                                  "size": c.size, "last": c.end >= moov.end}
            elif c.type == b"trak":
                out["tracks"].append(track_facts(fh, c))
            elif c.type == b"udta":
                udta_strings(fh, c, out["strings"])
            elif c.type == b"meta":
                meta_strings(fh, c, out["strings"])
    return out


# ------------------------------------------------------------------------------ Novatek GPS (spec A.3)
MARKER = re.compile(rb"[AV][NS][EW]\x00")


def decode_block(data: bytes) -> dict:
    if len(data) < 16 or data[4:12] != b"freeGPS ":
        return {"status": "not freeGPS"}
    m = next((x.start() for x in MARKER.finditer(data, 36)), None)
    if m is None:
        for at in (40, 72):                       # a void block may have no hemisphere letters
            if data[at:at + 1] == b"V":
                return {"status": "void", "marker": at}
        return {"status": "unparsed"}
    if m < 24 or len(data) < m + 20:
        return {"status": "unparsed", "marker": m}
    hh, mi, ss, yy, mo, dd = struct.unpack("<6I", data[m - 24:m])
    yy += 2000 if yy < 100 else 0
    lat_raw, lon_raw, knots, track = struct.unpack("<4f", data[m + 4:m + 20])
    try:
        utc = dt.datetime(yy, mo, dd, hh, mi, ss, tzinfo=UTC)
    except ValueError:
        utc = None

    def degrees(v: float, hem: bytes) -> float:
        d = int(v // 100)
        deg = d + (v - 100 * d) / 60
        return -deg if hem in (b"S", b"W") else deg

    lat, lon = degrees(lat_raw, data[m + 1:m + 2]), degrees(lon_raw, data[m + 2:m + 3])
    status = "valid" if data[m:m + 1] == b"A" else "void"
    if status == "valid" and (utc is None or not (-90 <= lat <= 90 and -180 <= lon <= 180)
                              or (lat, lon) == (0.0, 0.0)):
        status = "invalid"
    return {"status": status, "marker": m, "utc": utc, "lat": lat, "lon": lon,
            "speed_kmh": knots * 1.852, "track": track}


def novatek_gps(path: Path, gps_box: dict, args) -> dict:
    out = {"blocks": 0, "counts": {}, "markers": {}, "fixes": [], "hex_first_blocks": []}
    with open(path, "rb") as fh:
        fh.seek(gps_box["payload"])
        head = fh.read(8)
        if len(head) < 8:
            return out
        n = struct.unpack(">I", head[4:8])[0]
        if n > 1_000_000:
            out["error"] = f"implausible block count {n}"
            return out
        table = [struct.unpack(">II", fh.read(8)) for _ in range(n)]
        out["blocks"] = n
        for i, (offset, size) in enumerate(table):
            fh.seek(offset)
            data = fh.read(min(size, 4096))
            b = decode_block(data)
            if i < 2 or (b["status"] in ("unparsed", "not freeGPS") and len(out["hex_first_blocks"]) < 4):
                out["hex_first_blocks"].append({"block": i, "offset": offset, "size": size,
                                                "hex": data[:128].hex()})
            out["counts"][b["status"]] = out["counts"].get(b["status"], 0) + 1
            if "marker" in b:
                out["markers"][str(b["marker"])] = out["markers"].get(str(b["marker"]), 0) + 1
            if b["status"] == "valid":
                out["fixes"].append({"block": i, **b})
    fixes = out["fixes"]
    too_fast = 0
    for a, b in zip(fixes, fixes[1:]):
        secs = (b["utc"] - a["utc"]).total_seconds()
        if secs > 0 and haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) / secs * 3.6 > 300:
            too_fast += 1
    out["too_fast_pairs"] = too_fast
    not_void = sum(v for k, v in out["counts"].items() if k != "void")
    failed = not_void - len(fixes) + too_fast
    out["layout_ok"] = not_void > 0 and failed <= 0.2 * not_void
    if len(fixes) >= 3:
        step = max(1, len(fixes) // 400)
        pts = [(f["block"], f["utc"].timestamp()) for f in fixes[::step]]
        s = slope(pts)
        if s:
            out["slope_s_per_block"] = round(s, 3)
            utc0 = statistics.median(u - s * i for i, u in pts)
            out["utc0"] = dt.datetime.fromtimestamp(utc0, UTC)
    return out


def track_time_at(fixes: list[dict], lat: float, lon: float, max_gap_s: float = 120) -> tuple[float, float] | None:
    """The point of the GPS track (fixes joined by straight lines) nearest to (lat, lon):
    its UTC time in seconds and its distance in metres."""
    kx, ky = math.cos(math.radians(lat)) * 111_320.0, 110_540.0
    pts = [(f["utc"].timestamp(), (f["lon"] - lon) * kx, (f["lat"] - lat) * ky) for f in fixes]
    best = None
    for (ta, ax, ay), (tb, bx, by) in zip(pts, pts[1:]):
        if not 0 < tb - ta <= max_gap_s:
            continue
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        w = 0.0 if l2 == 0 else min(1.0, max(0.0, -(ax * dx + ay * dy) / l2))
        d = math.hypot(ax + w * dx, ay + w * dy)
        if best is None or d < best[1]:
            best = (ta + w * (tb - ta), d)
    return best


def gps_position_at(fixes: list[dict], t_video: float) -> tuple[float, float] | None:
    """Fix i is taken to sit at video second i (spec §8.2); interpolate between neighbours."""
    by_block = {f["block"]: f for f in fixes}
    i = math.floor(t_video)
    a, b = by_block.get(i), by_block.get(i + 1)
    if a and b:
        w = t_video - i
        return a["lat"] + w * (b["lat"] - a["lat"]), a["lon"] + w * (b["lon"] - a["lon"])
    return None


# ------------------------------------------------------------------------------ ExifTool
EXIF_DT = re.compile(r"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?")


def parse_exif_dt(text) -> dt.datetime | None:
    m = EXIF_DT.search(str(text or ""))
    if not m:
        return None
    try:
        d = dt.datetime(*(int(m.group(i)) for i in range(1, 7)))
    except ValueError:
        return None
    if m.group(7):
        d += dt.timedelta(seconds=float(m.group(7)))
    tz = m.group(8)
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        d -= sign * dt.timedelta(hours=int(tz[1:3]), minutes=int(tz[4:6]))
    return d.replace(tzinfo=UTC) if tz else d


def exiftool_section(exe: str, path: Path, clip_dir: Path, gps: dict | None, mvhd: dict | None) -> dict:
    out = {"version": first_line([exe, "-ver"])}
    spec_cmd = [exe, "-ee3", "-api", "debug=1", "-G3", "-a", "-s", "-GPSType", "-GPSDateTime",
                "-GPSLatitude", "-GPSLongitude", "-GPSSpeed", str(path)]
    rc, text, err, secs = run(spec_cmd, 180)
    if rc != 0:                                    # older ExifTool without the debug option ...
        spec_cmd = [a for a in spec_cmd if a not in ("-api", "debug=1")]
        rc, text, err, secs = run(spec_cmd, 180)
    if rc != 0:                                    # ... or without -ee3
        spec_cmd = ["-ee" if a == "-ee3" else a for a in spec_cmd]
        rc, text, err, secs = run(spec_cmd, 180)
    (clip_dir / "exiftool_gps.txt").write_text(text + ("\n" + err if err else ""), encoding="utf-8")
    lines = text.splitlines()
    out.update(gps_cmd="exiftool " + " ".join(spec_cmd[1:-1]) + " CLIP",     # no install path: it can name the user
               gps_lines=len(lines), gps_head=lines[:12], gps_seconds=round(secs, 1),
               gps_type=sorted({ln.split(":", 1)[1].strip() for ln in lines if "GPSType" in ln and ":" in ln}))

    rc, text, err, _ = run([exe, "-a", "-G1", "-s", "-time:all", str(path)], 60)
    (clip_dir / "exiftool_time.txt").write_text(text + ("\n" + err if err else ""), encoding="utf-8")
    out["time_all"] = text.strip().splitlines()

    rc, text, err, _ = run([exe, "-a", "-G1", "-s", "-FileType", "-MajorBrand", "-CompatibleBrands",
                            "-HandlerType", "-HandlerDescription", "-HandlerVendorID", "-Encoder",
                            "-Software", "-Make", "-Model", "-CompressorName", "-VideoFrameRate",
                            "-Duration", "-ImageSize", str(path)], 60)
    (clip_dir / "exiftool_container.txt").write_text(text + ("\n" + err if err else ""), encoding="utf-8")
    out["container"] = text.strip().splitlines()

    json_cmd = [exe, "-ee3", "-n", "-j", "-G3", "-a", "-api", "LargeFileSupport=1", "-GPSDateTime",
                "-GPSLatitude", "-GPSLongitude", "-GPSSpeed", "-GPSTrack", "-SampleTime", str(path)]
    rc, text, err, _ = run(json_cmd, 180)
    if rc != 0:
        rc, text, err, _ = run(["-ee" if a == "-ee3" else a for a in json_cmd], 180)
    (clip_dir / "exiftool_gps.json").write_text(text, encoding="utf-8")
    fixes = []
    try:
        record = json.loads(text)[0]
        docs = sorted({int(k.split(":")[0][3:]) for k in record if k.startswith("Doc") and ":" in k})
        for d in docs:
            g = lambda tag: record.get(f"Doc{d}:{tag}")
            if g("GPSLatitude") is None:
                continue
            fixes.append({"doc": d, "utc": parse_exif_dt(g("GPSDateTime")), "lat": float(g("GPSLatitude")),
                          "lon": float(g("GPSLongitude")), "speed_kmh": g("GPSSpeed"),
                          "sample_time": g("SampleTime")})
    except (ValueError, IndexError, TypeError) as exc:
        out["json_error"] = str(exc)
    out["fixes"] = len(fixes)
    if fixes:
        out["first_fix"], out["last_fix"] = fixes[0], fixes[-1]
    timed = [f for f in fixes if f["sample_time"] is not None and f["utc"] is not None]
    if timed:                                      # spec §8.2: is GPSDateTime a real clock?
        diffs = [f["utc"].timestamp() - float(f["sample_time"]) for f in timed]
        out["sampletime"] = {"fixes": len(timed), "spread_s": round(max(diffs) - min(diffs), 3),
                             "gpsdatetime_minus_sampletime": dt.datetime.fromtimestamp(statistics.median(diffs), UTC)}
        if mvhd and mvhd.get("created"):
            out["sampletime"]["vs_mvhd_s"] = round(
                statistics.median(diffs) - mvhd["created"].replace(tzinfo=UTC).timestamp(), 1)
    if gps and gps.get("fixes") and fixes and not timed:   # spec §8.2: void blocks come first?
        n, m = gps["blocks"], len(fixes)
        by_block = {f["block"]: f for f in gps["fixes"]}
        same = sum(1 for k, f in enumerate(fixes, 1)
                   if (b := by_block.get(n - m + k - 1)) and abs(b["lat"] - f["lat"]) < 1e-5
                   and abs(b["lon"] - f["lon"]) < 1e-5)
        by_time = {f["utc"]: f["block"] for f in gps["fixes"]}
        matched = sorted(by_time[f["utc"]] for f in fixes if f["utc"] in by_time)
        unmatched = sorted(set(range(n)) - set(matched))
        out["alignment"] = {"blocks": n, "exiftool_fixes": m, "match_n_minus_m_rule": same,
                            "unmatched_blocks": unmatched[:20],
                            "void_blocks_first": bool(matched) and all(u < matched[0] for u in unmatched)}
    return out


# ------------------------------------------------------------------------------ video
def open_video(path: Path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        hint = "" if str(path).isascii() else " The path has non-ASCII characters: copy the clip to a plain path."
        raise RuntimeError(f"OpenCV could not open {path.name}.{hint}")
    return cap


def read_at(cap, k: int):
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, k))
    ok, frame = cap.read()
    return frame if ok else None


def thumb(frame):
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (64, 40), interpolation=cv2.INTER_AREA).astype(np.float32)


def video_facts(path: Path, args) -> dict:
    cap = open_video(path)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps, n = float(cap.get(cv2.CAP_PROP_FPS) or 0), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    code = int(cap.get(cv2.CAP_PROP_FOURCC))
    out = {"width": w, "height": h, "fps": round(fps, 3), "frames": n,
           "duration_s": round(n / fps, 3) if fps else None,
           "fourcc": "".join(chr((code >> 8 * i) & 0xFF) for i in range(4)).strip("\x00"),
           "backend": cap.getBackendName()}

    # Sequential decode: speed, timestamps (constant frame rate?), and the reference for the seek check.
    thumbs, stamps = [], []
    t0 = time.perf_counter()
    for _ in range(min(n or args.seek_check, args.seek_check)):
        ok, frame = cap.read()
        if not ok:
            break
        stamps.append(cap.get(cv2.CAP_PROP_POS_MSEC))
        thumbs.append(thumb(frame))
    secs = time.perf_counter() - t0
    out["decode_fps"] = round(len(thumbs) / secs, 1) if secs > 0 else None
    steps = [b - a for a, b in zip(stamps[1:], stamps[2:])]
    if len(steps) >= 5:
        med = statistics.median(steps)
        out["frame_step_ms"] = {"median": round(med, 3), "min": round(min(steps), 3), "max": round(max(steps), 3)}
        out["variable_frame_rate"] = med > 0 and (max(steps) - min(steps)) > 0.5 * med
    if n > 1 and fps:
        last = read_at(cap, n - 1)
        if last is not None:
            out["last_frame_ms"] = round(cap.get(cv2.CAP_PROP_POS_MSEC), 1)
            out["last_frame_expected_ms"] = round((n - 1) / fps * 1000, 1)
    cap.release()

    # Seek check: does seeking land on the frame sequential decoding gives? (spec §8.8, plan §2.2)
    targets = [k for k in range(15, len(thumbs) - 6, 30)][:10]
    out["seek"] = {}
    for mode in (("frame number", "time") if fps else ("frame number",)):
        cap = open_video(path)
        results = []
        for k in targets:
            if mode == "frame number":
                cap.set(cv2.CAP_PROP_POS_FRAMES, k)
            else:
                cap.set(cv2.CAP_PROP_POS_MSEC, k / fps * 1000.0)
            ok, frame = cap.read()
            if not ok:
                results.append(None)
                continue
            th = thumb(frame)
            diffs = {d: float(np.abs(th - thumbs[k + d]).mean()) for d in range(-5, 6) if 0 <= k + d < len(thumbs)}
            best = min(diffs, key=diffs.get)
            if diffs[0] <= diffs[best] + 1e-3:
                best = 0
            results.append(best)
        cap.release()
        out["seek"][mode] = {"targets": targets, "offsets": results,
                             "exact": sum(1 for r in results if r == 0)}
    return out


def static_map(path: Path, n: int, fps: float, speedup: float, clip_dir: Path, windows: int) -> dict:
    """Per-pixel spread over short stretches of the clip: 6 frames about 1 s of driving apart, in
    `windows` places. Within a stretch the road moves and the light doesn't, so the bonnet stays dark;
    across a whole timelapse the light changes and the bonnet would look busy."""
    step = max(1, round(fps / max(speedup, 1e-6)))
    cap = open_video(path)
    spreads = []
    for w in range(windows):
        start = int(max(0, n - 6 * step) * (w + 0.5) / windows)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        stack = []
        for j in range(5 * step + 1):
            if not cap.grab():
                break
            if j % step == 0:
                ok, frame = cap.retrieve()
                if ok:
                    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    stack.append(cv2.resize(g, (320, round(320 * g.shape[0] / g.shape[1])),
                                            interpolation=cv2.INTER_AREA).astype(np.float32))
        if len(stack) >= 4:
            spreads.append(np.stack(stack).std(axis=0))
    cap.release()
    if len(spreads) < 2:
        return {"error": "too few frames"}
    spread = np.mean(spreads, axis=0)
    h, w = spread.shape
    profile = np.median(spread[:, int(0.2 * w):int(0.8 * w)], axis=1)
    reference = float(np.percentile(profile[int(0.3 * h):int(0.9 * h)], 80))
    threshold = 0.3 * reference
    start = int(0.94 * h)                     # the stamp's digits change, so start above it
    bonnet = None
    if reference > 0 and profile[start] < threshold:
        for r in range(start, int(0.3 * h), -1):
            if all(profile[r - j] > threshold for j in range(3)):
                bonnet = r + 1
                break
    img = np.clip(spread / max(1e-6, np.percentile(spread, 99)) * 255, 0, 255).astype(np.uint8)
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if bonnet:
        cv2.line(img, (0, bonnet), (w - 1, bonnet), (0, 0, 255), 1)
    write_image(clip_dir / "static_map.png", img)
    return {"frames": len(spreads) * 6, "windows": len(spreads), "step_frames": step,
            "bonnet_from": round(bonnet / h, 3) if bonnet else None,
            "road_spread": round(reference, 1), "rows": [round(float(v), 1) for v in profile[::max(1, h // 50)]]}


# ------------------------------------------------------------------------------ the stamp
def read_stamp(engine, frame, layout: Layout, args):
    c = crop(frame, layout.roi)
    t0 = time.perf_counter()
    text = engine.read(c)
    ms = (time.perf_counter() - t0) * 1000
    r = parse_stamp(text, args.date_order, signed_dd=layout.signed_dd, coord_decimals=layout.coord_decimals)
    return text, r, ms, c


def reading_dict(text, r: StampReading, ms, layout, engine, args) -> dict:
    return {"engine": engine.name, "layout": layout.name, "ms": round(ms),
            "text": text if args.raw_text else mask_text(text, layout),
            "speed_kmh": r.speed_kmh, "lat": r.lat, "lon": r.lon,
            "local": r.local, "date_ambiguous": r.date_ambiguous, "format": r.coord_format, "score": score(r)}


def stamp_section(path: Path, video: dict, engines: list, clip_dir: Path, args) -> dict:
    n, fps = video["frames"], video["fps"]
    duration = video["duration_s"] or 0
    cap = open_video(path)
    crops_dir = clip_dir / "crops"
    crops_dir.mkdir(exist_ok=True)
    layouts = list(LAYOUTS)
    if args.roi:
        layouts.append(Layout("Custom (--roi)", tuple(float(v) for v in args.roi.split(",")), True, None))
    mid = read_at(cap, n // 2)
    out = {"suggested_roi": suggest_stamp_roi(mid) if mid is not None else None}
    if out["suggested_roi"]:
        layouts.append(Layout("Suggested", out["suggested_roi"], True, None))

    # 1. Five frames across the clip, every layout, every engine.
    fractions = [0.1, 0.3, 0.5, 0.7, 0.9] if args.frames == 5 else [(i + 0.5) / args.frames for i in range(args.frames)]
    samples, totals = [], {}
    for f in fractions:
        k = int(n * f)
        frame = read_at(cap, k)
        if frame is None:
            continue
        entry = {"frame": k, "video_s": round(k / fps, 3), "reads": []}
        for lay in layouts:
            for eng in engines:
                text, r, ms, c = read_stamp(eng, frame, lay, args)
                entry["reads"].append(reading_dict(text, r, ms, lay, eng, args))
                totals[(lay.name, eng.name)] = totals.get((lay.name, eng.name), 0) + score(r)
            write_image(crops_dir / f"{k:06d}_{re.sub(r'[^A-Za-z0-9]+', '_', lay.name)}.png", crop(frame, lay.roi))
        samples.append(entry)
        if f == 0.5 or (args.frames != 5 and len(samples) == 1):
            masked = frame.copy()
            y0 = min(lay.roi[1] for lay in layouts)
            masked[int(masked.shape[0] * y0):] = 0
            small = cv2.resize(masked, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
            write_image(clip_dir / "frame_50pct_stamp_masked.jpg", small, 85)
    out["samples"] = samples
    if not totals or max(totals.values()) == 0:
        out["best"] = None
        cap.release()
        return out
    out["layout_scores"] = []
    for lay_ in layouts:
        for eng_ in engines:
            rds = [rd for smp in samples for rd in smp["reads"]
                   if rd["layout"] == lay_.name and rd["engine"] == eng_.name]
            if rds:
                out["layout_scores"].append({
                    "layout": lay_.name, "engine": eng_.name, "roi": lay_.roi, "score": sum(rd["score"] for rd in rds),
                    "max": 5 * len(rds), "with_time": sum(rd["local"] is not None for rd in rds),
                    "with_position": sum(rd["lat"] is not None for rd in rds),
                    "with_speed": sum(rd["speed_kmh"] is not None for rd in rds),
                    "median_ms": round(statistics.median(rd["ms"] for rd in rds))})
    order = {lay.name: i for i, lay in enumerate(layouts)}
    (best_layout, best_engine) = max(totals, key=lambda k: (totals[k], -order[k[0]]))
    lay = next(x for x in layouts if x.name == best_layout)
    eng = next(e for e in engines if e.name == best_engine)
    out["best"] = {"layout": best_layout, "engine": best_engine, "score": totals[(best_layout, best_engine)],
                   "max_score": 5 * len(samples), "roi": lay.roi}
    texts = [rd["text"] for s in samples for rd in s["reads"] if rd["layout"] == best_layout]
    norm = " ".join(texts).upper().replace(" ", "")
    out["tokens"] = [t for t, rx in MAKE_NAMES.items() if rx.search(norm)]
    best_reads = [rd for s in samples for rd in s["reads"] if rd["layout"] == best_layout and rd["engine"] == best_engine]
    dated = [rd["date_ambiguous"] for rd in best_reads if rd["local"]]
    out["date_ambiguous_all"] = bool(dated) and all(dated)
    out["formats"] = sorted({rd["format"] for rd in best_reads if rd["format"]})

    # 2. Eight consecutive frames from the middle: does the stamp change on every frame?
    cap.set(cv2.CAP_PROP_POS_FRAMES, n // 2)
    seq = []
    for j in range(8):
        ok, frame = cap.read()
        if not ok:
            break
        text, r, ms, _ = read_stamp(eng, frame, lay, args)
        seq.append({"frame": n // 2 + j, "local": r.local})
    secs = [(s["local"] - STAMP_EPOCH).total_seconds() for s in seq if s["local"]]
    out["consecutive"] = {"frames": len(seq), "parsed": len(secs),
                          "steps_s": [round(b - a) for a, b in zip(secs, secs[1:])]}

    # 3. Spec A.8: 3 clusters of 3 reads, 1 video-second apart, at 10 %, 50 % and 90 %.
    if duration >= 30:
        plan = [[(f * duration + j) for j in range(3)] for f in (0.1, 0.5, 0.9)]
    else:
        plan = [[duration * (i + 0.5) / 9 for i in range(9)]]
    clusters, reads = [], []
    for cluster in plan:
        pts = []
        for t in cluster:
            frame = read_at(cap, int(round(t * fps)))
            if frame is None:
                continue
            text, r, ms, _ = read_stamp(eng, frame, lay, args)
            t_video = int(round(t * fps)) / fps
            if r.local:
                pts.append((t_video, (r.local - STAMP_EPOCH).total_seconds()))
            reads.append({"video_s": round(t_video, 3), "local": r.local, "lat": r.lat, "lon": r.lon})
        clusters.append(pts)
    cap.release()
    tb, notes = detect(fps, stamp_clusters=clusters)
    out["timebase"] = {"mode": tb.mode, "speedup": round(tb.speedup, 3), "source": tb.source, "notes": notes,
                       "cluster_slopes": [round(s, 3) if (s := slope(c)) is not None else None for c in clusters]}
    out["all_reads"] = [{"video_s": s["video_s"], "local": rd["local"], "lat": rd["lat"], "lon": rd["lon"]}
                        for s in samples for rd in s["reads"]
                        if rd["layout"] == best_layout and rd["engine"] == best_engine] + reads
    out["ocr_ms"] = {e.name: round(statistics.median(rd["ms"] for s in samples for rd in s["reads"]
                                                     if rd["engine"] == e.name)) for e in engines}
    return out


# ------------------------------------------------------------------------------ putting it together
def compare_clocks(res: dict, args) -> dict:
    """Stamp clock vs GPS clock vs mvhd vs file name (spec §8.5, §8.7)."""
    out = {}
    stamp, gps, video = res.get("stamp") or {}, res.get("gps") or {}, res.get("video") or {}
    speed = (stamp.get("timebase") or {}).get("speedup") or 1.0
    if gps.get("slope_s_per_block"):
        out["gps_speedup"] = gps["slope_s_per_block"]
    reads = [r for r in stamp.get("all_reads", []) if r.get("local")]
    if reads:
        secs = statistics.median((r["local"] - STAMP_EPOCH).total_seconds() - speed * r["video_s"] for r in reads)
        out["stamp_local_start"] = STAMP_EPOCH + dt.timedelta(seconds=secs + 0.5)   # whole-second stamp
    if gps.get("utc0"):
        out["gps_utc_start"] = gps["utc0"]
    if "stamp_local_start" in out and "gps_utc_start" in out:
        offset = (out["stamp_local_start"] - out["gps_utc_start"].replace(tzinfo=None)).total_seconds()
        zone = round(offset / 900) * 900
        out.update(utc_offset=fmt_offset(zone), stamp_minus_gps_s=round(offset, 1),
                   residual_s=round(offset - zone, 1))
        dists = []
        for r in reads:
            if r.get("lat") is not None:
                p = gps_position_at(gps.get("fixes", []), r["video_s"])
                if p:
                    dists.append(haversine_m(r["lat"], r["lon"], *p))
        if dists:
            out["stamp_vs_gps_m"] = {"reads": len(dists), "median": round(statistics.median(dists), 1),
                                     "max": round(max(dists), 1)}
        # The same receiver feeds the stamp and the GPS blocks, so each stamp position lies on the GPS track.
        # The UTC at that point, against the stamp's own time, gives the clock offset without assuming
        # where in its video second a block's fix was taken.
        hits = []
        for r in reads:
            if r.get("lat") is not None:
                hit = track_time_at(gps.get("fixes", []), r["lat"], r["lon"])
                if hit and hit[1] <= 100:
                    utc = dt.datetime.fromtimestamp(hit[0], UTC).replace(tzinfo=None)
                    hits.append(((r["local"] - utc).total_seconds() + 0.5, hit[1]))
        if len(hits) >= 3:
            off = statistics.median(h[0] for h in hits)
            zone = round(off / 900) * 900
            out["by_position"] = {"reads": len(hits), "stamp_minus_gps_s": round(off, 1),
                                  "utc_offset": fmt_offset(zone), "residual_s": round(off - zone, 1),
                                  "spread_s": round(max(h[0] for h in hits) - min(h[0] for h in hits), 1),
                                  "median_distance_m": round(statistics.median(h[1] for h in hits), 1)}
            # Where each block's fix sits inside its video second, in seconds of driving
            local0 = out["stamp_local_start"]
            phases = [((f["utc"].replace(tzinfo=None) + dt.timedelta(seconds=off) - local0).total_seconds()
                       - speed * f["block"]) for f in gps.get("fixes", [])]
            if phases:
                out["by_position"]["fix_into_block_s"] = round(statistics.median(phases), 1)
    mvhd = (res.get("container") or {}).get("mvhd") or {}
    duration = (video.get("duration_s") or 0) * speed
    if mvhd.get("created"):
        created = mvhd["created"]
        candidates = {}
        if "stamp_local_start" in out:
            candidates["local start"] = out["stamp_local_start"]
            candidates["local end"] = out["stamp_local_start"] + dt.timedelta(seconds=duration)
        if "gps_utc_start" in out:
            u = out["gps_utc_start"].replace(tzinfo=None)
            candidates["UTC start"] = u
            candidates["UTC end"] = u + dt.timedelta(seconds=duration)
        out["mvhd_vs"] = {k: round((created - v).total_seconds(), 1) for k, v in candidates.items()}
        if out["mvhd_vs"]:
            best = min(out["mvhd_vs"], key=lambda k: abs(out["mvhd_vs"][k]))
            out["mvhd_is"] = best if abs(out["mvhd_vs"][best]) <= 120 else None
        name_start = (res.get("file") or {}).get("name_local_start")
        if name_start:
            out["mvhd_minus_name_s"] = round((created - name_start).total_seconds(), 1)
        start = out.get("stamp_local_start") or name_start
        if start and duration:
            d_start = (created - start).total_seconds()
            d_end = (created - start - dt.timedelta(seconds=duration)).total_seconds()
            out["mvhd_marks"] = "end" if abs(d_end) < abs(d_start) else "start"
            out["mvhd_minus_marked_s"] = round(d_end if out["mvhd_marks"] == "end" else d_start, 1)
    name_start = (res.get("file") or {}).get("name_local_start")
    if name_start and "stamp_local_start" in out:
        out["name_minus_stamp_s"] = round((name_start - out["stamp_local_start"]).total_seconds(), 1)
    return out


def reencode_hints(res: dict) -> list[str]:
    c = res.get("container") or {}
    hints = []
    for t in c.get("tracks", []):
        name = (t.get("handler_name") or "")
        if re.search(r"google|youtube|handbrake|lavf|ffmpeg", name, re.I):
            hints.append(f"handler name \"{name}\"")
    for k, v in (c.get("strings") or {}).items():
        if re.search(r"google|youtube|handbrake|lavf|ffmpeg|premiere|davinci|capcut", str(v), re.I):
            hints.append(f"{k} = \"{v}\"")
    brands = [(c.get("ftyp") or {}).get("major", "")] + (c.get("ftyp") or {}).get("compatible", [])
    if any(b in ("dash", "iso5", "iso6") for b in brands):
        hints.append(f"ftyp brands {', '.join(b for b in brands if b)}")
    return hints


def source_guess(res: dict) -> tuple[str, str]:
    c, f, s = res.get("container") or {}, res.get("file") or {}, res.get("stamp") or {}
    if c.get("gps_box"):
        return "VIOFO / Novatek", "gps box in moov"
    if f.get("name_pattern", "") and f["name_pattern"].startswith("VIOFO"):
        return "VIOFO / Novatek", "file name"
    if f.get("name_pattern", "") and f["name_pattern"].startswith("Garmin"):
        return "Garmin", "file name"
    if any("garmin" in str(v).lower() for v in (c.get("strings") or {}).values()):
        return "Garmin", "make string in the container"
    if s.get("tokens"):
        return s["tokens"][0].title(), f"stamp: {s['tokens'][0]} (nothing in the container: treat as re-encoded)"
    return "not recognised", "no container evidence and no make on the stamp"


def probe_clip(path: Path, args, tools: dict, engines: list, out_root: Path) -> dict:
    clip_dir = out_root / re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem)
    if clip_dir.exists() and (clip_dir / ".for").exists() and (clip_dir / ".for").read_text() != str(path):
        clip_dir = clip_dir.with_name(clip_dir.name + "_" + hashlib.sha1(str(path).encode()).hexdigest()[:6])
    clip_dir.mkdir(parents=True, exist_ok=True)
    (clip_dir / ".for").write_text(str(path), encoding="utf-8")
    res: dict = {"path": path.name, "errors": {}}
    timings = {}

    def step(name, fn):
        t0 = time.perf_counter()
        print(f"  {name} …", flush=True)
        try:
            res[name] = fn()
        except Exception as exc:                              # one failed step never stops the probe
            res["errors"][name] = f"{type(exc).__name__}: {exc}"
            print(f"    failed: {res['errors'][name]}", flush=True)
        timings[name] = round(time.perf_counter() - t0, 1)

    step("file", lambda: file_facts(path))
    step("container", lambda: container_facts(path))
    gps_box = (res.get("container") or {}).get("gps_box")
    if gps_box:
        step("gps", lambda: novatek_gps(path, gps_box, args))
    if tools.get("exiftool"):
        step("exiftool", lambda: exiftool_section(tools["exiftool"], path, clip_dir, res.get("gps"),
                                                  (res.get("container") or {}).get("mvhd")))
    step("video", lambda: video_facts(path, args))
    if res.get("video") and engines:
        step("stamp", lambda: stamp_section(path, res["video"], engines, clip_dir, args))
    if res.get("video"):
        speedup = ((res.get("stamp") or {}).get("timebase") or {}).get("speedup") \
            or (res.get("gps") or {}).get("slope_s_per_block") or 1.0
        step("static", lambda: static_map(path, res["video"]["frames"], res["video"]["fps"], speedup,
                                          clip_dir, args.static_windows))
    step("clocks", lambda: compare_clocks(res, args))
    res["source"] = source_guess(res)
    res["reencode_hints"] = reencode_hints(res)
    res["timings_s"] = timings
    if res.get("gps"):                           # the per-fix list is long; keep the first and last
        fx = res["gps"].pop("fixes")
        res["gps"]["valid_fixes"] = len(fx)
        if fx:
            res["gps"]["first_fix"] = {k: fx[0][k] for k in ("block", "utc", "lat", "lon", "speed_kmh", "track")}
            res["gps"]["last_fix"] = {k: fx[-1][k] for k in ("block", "utc", "lat", "lon", "speed_kmh", "track")}
            for key in ("first_fix", "last_fix"):
                for c in ("lat", "lon"):
                    res["gps"][key][c] = coarse(res["gps"][key][c], args)
    if res.get("stamp"):
        for r in res["stamp"].get("all_reads", []) + [rd for smp in res["stamp"].get("samples", [])
                                                      for rd in smp["reads"]]:
            r["lat"], r["lon"] = coarse(r["lat"], args), coarse(r["lon"], args)
    for key in ("first_fix", "last_fix"):
        f = (res.get("exiftool") or {}).get(key)
        if f:
            f["lat"], f["lon"] = coarse(f["lat"], args), coarse(f["lon"], args)
    (clip_dir / "probe.json").write_text(json.dumps(res, default=jsonable, indent=1), encoding="utf-8")
    res["dir"] = clip_dir
    return res


# ------------------------------------------------------------------------------ the report
def answers(res: dict) -> list[str]:
    a = []
    src, why = res["source"]
    v, s, g, c, e = (res.get(k) or {} for k in ("video", "stamp", "gps", "clocks", "exiftool"))
    a.append(f"**Source:** {src} ({why})")
    tb = s.get("timebase")
    if tb:
        extra = f"; GPS blocks say ×{c['gps_speedup']:g}" if c.get("gps_speedup") else ""
        a.append(f"**Recording mode:** {tb['mode']} ×{tb['speedup']:g} from the stamp clusters "
                 f"(slopes {tb['cluster_slopes']}){extra}" + (f"; {'; '.join(tb['notes'])}" if tb["notes"] else "")
                 + ("; **the speed-up varies along the file: an edited or re-timed video, so each frame's own "
                    "stamp has to give its time**" if any("differs" in n for n in tb["notes"]) else ""))
    elif c.get("gps_speedup"):
        a.append(f"**Recording mode:** GPS blocks say ×{c['gps_speedup']:g} per video second")
    if c.get("utc_offset"):
        ok = "matches" if abs(c["residual_s"]) <= 1.5 else "does NOT match"
        a.append(f"**Camera UTC offset:** {c['utc_offset']} (stamp − GPS = {c['stamp_minus_gps_s']:+.1f} s; "
                 f"left over after the zone: {c['residual_s']:+.1f} s, so the stamp time {ok} the GPS time)")
    bp = c.get("by_position")
    if bp:
        ok = "matches" if abs(bp["residual_s"]) <= 1.5 else "does NOT match"
        a.append(f"**Camera UTC offset, by position:** {bp['utc_offset']} (stamp − GPS = {bp['stamp_minus_gps_s']:+.1f} s "
                 f"over {bp['reads']} reads, spread {bp['spread_s']} s, stamps {bp['median_distance_m']} m from the "
                 f"track, so the stamp time {ok} the GPS time); each block's fix sits "
                 f"{bp.get('fix_into_block_s')} s of driving into its video second")
    if c.get("stamp_vs_gps_m"):
        d = c["stamp_vs_gps_m"]
        a.append(f"**Stamp vs GPS position, fix i placed at video second i:** median {d['median']} m, "
                 f"max {d['max']} m over {d['reads']} reads")
    mv = (res.get("container") or {}).get("mvhd") or {}
    if mv.get("created"):
        what = c.get("mvhd_is")
        diffs = ", ".join(f"{k} {v:+.1f} s" for k, v in (c.get("mvhd_vs") or {}).items())
        named = f"; file-name time {c['mvhd_minus_name_s']:+.1f} s" if "mvhd_minus_name_s" in c else ""
        verdict = (f"holds the **{what}**" if what else
                   ("matches neither the stamp nor the GPS clock within 2 min" if diffs else
                    "no stamp or GPS clock to compare with"))
        if c.get("mvhd_marks"):
            verdict = (f"marks the **{c['mvhd_marks']} of the recording** on the camera's clock "
                       f"({c['mvhd_minus_marked_s']:+.1f} s from it); closest clock: {what or 'none'}")
        a.append(f"**Container clock (mvhd):** {fmt_dt(mv['created'])} as written; {verdict}"
                 + (f" (mvhd minus: {diffs}{named})" if diffs or named else ""))
    elif mv:
        a.append("**Container clock (mvhd):** not set (0)")
    f = res.get("file") or {}
    if f.get("name_local_start"):
        rel = f" (stamp start differs by {c['name_minus_stamp_s']:+.1f} s)" if "name_minus_stamp_s" in c else ""
        a.append(f"**File name:** {f['name_pattern']}, {fmt_dt(f['name_local_start'])}, camera "
                 f"{f.get('name_camera') or '?'}{rel}")
    elif f.get("name_pattern"):
        a.append(f"**File name:** {f['name_pattern']}")
    else:
        a.append("**File name:** no camera pattern")
    if g:
        per = g["blocks"] / v["duration_s"] if v.get("duration_s") else None
        a.append(f"**Embedded GPS (built-in, A.3):** {g['blocks']} blocks"
                 + (f" for {v['duration_s']:.1f} s of video = {per:.2f} per video second" if per else "")
                 + f"; {', '.join(f'{k} {n}' for k, n in g['counts'].items())}; markers at "
                 f"{', '.join(g['markers']) or '–'}; layout {'OK' if g.get('layout_ok') else 'NOT OK'}"
                 + (("; the `gps ` box is the last child of `moov`"
                     + (" and ExifTool found nothing (spec A.3)" if e and not e.get("fixes") else
                        ", and ExifTool found the fixes anyway" if e else ""))
                    if (res.get("container") or {}).get("gps_box", {}).get("last") else ""))
    elif res.get("container"):
        a.append("**Embedded GPS (built-in, A.3):** no `gps ` box in `moov`")
    if e:
        al = e.get("alignment")
        tail = (f"; void blocks first: {'yes' if al['void_blocks_first'] else 'NO'} "
                f"({al['match_n_minus_m_rule']}/{al['exiftool_fixes']} fixes match the n − m rule)") if al else ""
        st = e.get("sampletime")
        if st:
            tail += (f"; SampleTime on {st['fixes']} fixes, GPSDateTime − SampleTime spread {st['spread_s']} s"
                     + (f", {st['vs_mvhd_s']:+.1f} s from mvhd" if "vs_mvhd_s" in st else "")
                     + (" → approximated from the container, not a clock" if st["spread_s"] <= 1 else ""))
        a.append(f"**ExifTool {e.get('version')}:** GPSType {', '.join(e.get('gps_type') or ['–'])}; "
                 f"{e.get('fixes', 0)} fixes{tail}")
    if s.get("best"):
        b = s["best"]
        amb = "; the date is ambiguous in every read (no day above 12)" if s.get("date_ambiguous_all") else ""
        a.append(f"**Stamp:** layout \"{b['layout']}\" with {b['engine']} scored {b['score']}/{b['max_score']} "
                 f"(time, position, speed); coordinate format {', '.join(s.get('formats') or ['–'])}{amb}")
        cons = s.get("consecutive") or {}
        if cons.get("steps_s"):
            changes = sum(1 for x in cons["steps_s"] if x)
            a.append(f"**Stamp across {cons['frames']} consecutive frames:** steps {cons['steps_s']} s → "
                     + ("changes on every frame" if changes == len(cons["steps_s"]) else
                        f"changes {changes} time(s)"))
    elif "stamp" in res:
        a.append("**Stamp:** no layout parsed any field; see the crops and the suggested region")
    if s.get("suggested_roi"):
        a.append(f"**Suggested stamp region:** {s['suggested_roi']}")
    if v.get("seek"):
        sk = v["seek"]
        a.append("**Seeking:** " + "; ".join(f"by {m}: {r['exact']}/{len(r['targets'])} exact"
                                             + ("" if r["exact"] == len(r["targets"]) else f" (offsets {r['offsets']})")
                                             for m, r in sk.items()))
    st = res.get("static") or {}
    if "bonnet_from" in st:
        a.append("**Static rows (bonnet, dashboard):** "
                 + (f"from y ≈ {st['bonnet_from']}" if st["bonnet_from"] else "none found above the stamp"))
    hints = res.get("reencode_hints")
    a.append("**Re-encode indicators:** " + ("; ".join(hints) if hints else "none"))
    return a


def fix_text(f: dict | None) -> str:
    if not f:
        return "–"
    parts = [f"block {f['block']}" if "block" in f else f"doc {f.get('doc')}", fmt_dt(f.get("utc")) + " UTC",
             f"{f.get('lat')}, {f.get('lon')}"]
    if f.get("speed_kmh") is not None:
        parts.append(f"{float(f['speed_kmh']):.1f} km/h")
    if f.get("sample_time") is not None:
        parts.append(f"SampleTime {f['sample_time']}")
    return " · ".join(parts)


def table(rows: list[list], head: list[str]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(x).replace("|", "\\|") for x in r) + " |" for r in rows]
    return out


def clip_report(res: dict) -> list[str]:
    L = [f"## {res['path']}", ""]
    if res["errors"]:
        L += ["**Steps that failed:**", ""] + [f"- {k}: `{v}`" for k, v in res["errors"].items()] + [""]
    L += ["### Answers for Phase 0", ""] + [f"- {x}" for x in answers(res)] + [""]
    f, v = res.get("file") or {}, res.get("video") or {}
    if f or v:
        L += ["### File and video stream", ""] + table([
            ["Size", f"{f.get('size_mb')} MB"], ["video_id (spec §6.1)", f.get("video_id")],
            ["Frame", f"{v.get('width')}×{v.get('height')} · {v.get('fps')} fps · {v.get('frames')} frames · "
                      f"{v.get('duration_s')} s"],
            ["Codec · OpenCV backend", f"{v.get('fourcc')} · {v.get('backend')}"],
            ["Decode speed", f"{v.get('decode_fps')} frames/s at full resolution"],
            ["Frame step (ms)", v.get("frame_step_ms")], ["Variable frame rate", v.get("variable_frame_rate")],
            ["Last frame at (ms)", f"{v.get('last_frame_ms')} (expected {v.get('last_frame_expected_ms')})"],
        ], ["", ""]) + [""]
    c = res.get("container") or {}
    if c:
        L += ["### Container", "",
              f"- Top level: {', '.join(f'{n} ({s:,} B)' for n, s in c['top_level'][:12])}",
              f"- ftyp: {c.get('ftyp')}",
              f"- moov children, in order: {', '.join(n for n, _ in c['moov_children'])}",
              f"- mvhd: {fmt_dt((c.get('mvhd') or {}).get('created'))} as written "
              f"(raw {(c.get('mvhd') or {}).get('created_raw')}), duration {(c.get('mvhd') or {}).get('duration_s')} s",
              ""]
        L += table([[t["handler"], t["handler_name"], t["format"]] for t in c["tracks"]],
                   ["Track handler", "Handler name", "Sample format"]) + [""]
        if c["strings"]:
            L += table([[k, v] for k, v in c["strings"].items()], ["udta / meta atom", "Value"]) + [""]
    g = res.get("gps") or {}
    if g:
        L += ["### Embedded GPS: built-in reader (spec A.3)", "",
              f"- `gps ` box: child {c['gps_box']['index_in_moov']} of moov; {g['blocks']} blocks; "
              f"{g.get('valid_fixes')} valid; {g['too_fast_pairs']} pairs faster than 300 km/h",
              f"- GPS time per block: {g.get('slope_s_per_block')} s; start {fmt_dt(g.get('utc0'))} UTC",
              f"- First fix: {fix_text(g.get('first_fix'))}", f"- Last fix: {fix_text(g.get('last_fix'))}",
              "- First blocks (hex, 128 bytes each):", "", "```"]
        L += [f"block {h['block']} @ {h['offset']} ({h['size']} B): {h['hex']}" for h in g["hex_first_blocks"]]
        L += ["```", ""]
    e = res.get("exiftool") or {}
    if e:
        L += ["### ExifTool", "", f"`{e.get('gps_cmd')}` gave {e.get('gps_lines')} lines "
              f"in {e.get('gps_seconds')} s. First lines:", "", "```"] + e.get("gps_head", []) + ["```", "",
              "`exiftool -a -G1 -s -time:all CLIP`:", "", "```"] + e.get("time_all", []) + ["```", "",
              "Container tags:", "", "```"] + e.get("container", []) + ["```", ""]
        if e.get("first_fix"):
            L += [f"- JSON (spec §8.2 command): {e['fixes']} fixes; first {fix_text(e['first_fix'])}; "
                  f"last {fix_text(e['last_fix'])}", ""]
        if e.get("alignment"):
            L += [f"- Alignment with the built-in blocks: {e['alignment']}", ""]
    s = res.get("stamp") or {}
    if s.get("samples"):
        L += ["### Stamp OCR", "", "Text is masked to what the parser reads. `·` hides everything else.", ""]
        L += table([[x["layout"], x["roi"], x["engine"], f"{x['score']}/{x['max']}", x["with_time"],
                     x["with_position"], x["with_speed"], x["median_ms"]] for x in s.get("layout_scores", [])],
                   ["Layout", "Region", "Engine", "Score", "Time", "Position", "Speed", "ms"]) + [""]
        best_layout = (s.get("best") or {}).get("layout")
        rows = []
        for smp in s["samples"]:
            for rd in smp["reads"]:
                if rd["layout"] == best_layout:
                    rows.append([f"{smp['video_s']} s", rd["layout"], rd["engine"], f"`{rd['text']}`",
                                 fmt_dt(rd["local"]) + (" (ambiguous)" if rd["date_ambiguous"] else ""),
                                 f"{rd['lat']}, {rd['lon']}" if rd["lat"] is not None else "–",
                                 rd["speed_kmh"] if rd["speed_kmh"] is not None else "–", rd["format"] or "–",
                                 rd["ms"]])
        L += table(rows, ["Video time", "Layout", "Engine", "Masked text", "Local", "Position", "km/h",
                          "Format", "ms"]) + [""]
        L += [f"- Timebase reads: {s.get('timebase')}", f"- Consecutive frames: {s.get('consecutive')}",
              f"- Median OCR time per read: {s.get('ocr_ms')} ms", ""]
    cl = res.get("clocks") or {}
    if cl:
        L += ["### Clocks", "", "```"] + [f"{k}: {fmt_dt(v) if isinstance(v, dt.datetime) else v}"
                                         for k, v in cl.items()] + ["```", ""]
    st = res.get("static") or {}
    if st.get("rows"):
        L += ["### Static map", "", f"Spread of each row over {st.get('windows')} stretches of 6 frames, "
              f"{st.get('step_frames')} frame(s) apart (every ~4 % of the "
              f"height, top to bottom): {st['rows'][::2]}. Road spread {st['road_spread']}; bonnet estimate "
              f"{st['bonnet_from']}. See `static_map.png` (dark = never changes).", ""]
    L += [f"Step times (s): {res.get('timings_s')}", ""]
    return L


def write_report(results: list[dict], tools: dict, engines: list, out_root: Path, args) -> Path:
    L = ["# Phase 0 probe report", "",
         f"Made {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} by `scripts/probe_dashcam.py` for "
         "`DATA/docs/SPEC_EXPORT_GPS_CSV.md` §10, Phase 0.", "",
         f"- Machine: {platform.platform()}, Python {platform.python_version()}, OpenCV {cv2.__version__}",
         f"- Tesseract: {next((e.version for e in engines if e.name == 'tesseract'), 'not found')}",
         f"- RapidOCR: {next((e.version for e in engines if e.name == 'rapidocr'), 'not used')}",
         f"- ExifTool: {first_line([tools['exiftool'], '-ver']) if tools.get('exiftool') else 'not found'}",
         f"- Stamp text: {'NOT masked (--raw-text)' if args.raw_text else 'masked to date, time, position, speed and make names'}"
         f"; positions: {'rounded to 0.01°' if args.coarse else 'full precision'}", ""]
    for res in results:
        L += clip_report(res)
    path = out_root / "phase0_report.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------------------ main
def explain_import_error(exc: ImportError) -> str:
    """Say why OpenCV or numpy didn't import, for the Python actually running this, and how to fix it."""
    me, msg = sys.executable, str(exc)
    lines = [f"Could not import OpenCV or numpy: {msg}",
             f"This script is running on {me} (Python {platform.python_version()}).", ""]
    if re.search(r"lib\S*\.so|DLL load failed|cannot open shared object", msg):
        lines += ["OpenCV is installed, but a system library it needs is missing. Either install the library:",
                  "    sudo apt install libgl1 libglib2.0-0",
                  "or switch to the OpenCV build that doesn't need it:",
                  f'    "{me}" -m pip uninstall -y opencv-python',
                  f'    "{me}" -m pip install opencv-python-headless']
    elif "numpy" in msg.lower() and "no module named 'numpy'" not in msg.lower():
        lines += ["OpenCV and numpy don't match. Reinstall them together:",
                  f'    "{me}" -m pip install --upgrade --force-reinstall numpy opencv-python-headless']
    else:
        lines += ["They aren't installed for this Python; pip may have put them in another one. Install them here:",
                  f'    "{me}" -m pip install opencv-python-headless numpy',
                  "If pip refuses with 'externally-managed-environment' (Ubuntu's own Python), use a virtual",
                  "environment and run the probe with its Python:",
                  "    python3 -m venv ~/.venvs/probe",
                  "    ~/.venvs/probe/bin/pip install opencv-python-headless numpy",
                  "    ~/.venvs/probe/bin/python scripts/probe_dashcam.py"]
    lines += ["", "Have only one of opencv-python and opencv-python-headless installed: together they break each other."]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clips", nargs="*", help=f"video files or folders (default: everything in {INPUT_DIR})")
    ap.add_argument("--out", default=str(OUTPUT_DIR / "probe"), help=f"output folder (default: {OUTPUT_DIR / 'probe'})")
    ap.add_argument("--exiftool", help="path to exiftool, if it isn't found")
    ap.add_argument("--tesseract", help="path to tesseract, if it isn't found")
    ap.add_argument("--no-rapidocr", action="store_true", help="don't use RapidOCR even if installed")
    ap.add_argument("--allow-missing", action="store_true", help="run without ExifTool or Tesseract")
    ap.add_argument("--frames", type=int, default=5, help="stamp sample frames per clip (default 5)")
    ap.add_argument("--date-order", choices=("DMY", "MDY"), default="DMY", help="for ambiguous dates")
    ap.add_argument("--roi", help="an extra stamp region to try, as x0,y0,x1,y1 fractions")
    ap.add_argument("--seek-check", type=int, default=300, help="frames decoded for the seek check (default 300)")
    ap.add_argument("--static-windows", type=int, default=8,
                    help="short stretches of 6 frames for the static map (default 8)")
    ap.add_argument("--raw-text", action="store_true", help="keep the stamp text unmasked (for your eyes only)")
    ap.add_argument("--coarse", action="store_true", help="round positions to 0.01° in the outputs")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    global cv2, np
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        print(explain_import_error(exc))
        return 2

    tools = {"exiftool": find_tool("exiftool", args.exiftool), "tesseract": find_tool("tesseract", args.tesseract)}
    missing = [k for k, v in tools.items() if not v]
    if missing:
        print("Missing: " + ", ".join(missing) + ". Install with:")
        here = INSTALL.get(sys.platform, INSTALL["linux"])
        for k in missing:
            print(f"  {here[k]}")
        if sys.platform not in INSTALL:
            print("  (those are Ubuntu's; use your system's package manager)")
        print("Then run this again (on Windows, in a new terminal). Or pass --exiftool / --tesseract with the path.")
        if not args.allow_missing:
            print("(--allow-missing runs without them, but Phase 0 needs both.)")
            return 2
    engines = []
    if tools["tesseract"]:
        engines.append(TesseractEngine(tools["tesseract"]))
    if not args.no_rapidocr:
        try:
            engines.append(RapidEngine())
        except Exception:
            print("RapidOCR not installed (optional): pip install rapidocr_onnxruntime")

    clips, seen = [], set()
    for raw in args.clips or [str(INPUT_DIR)]:
        target = Path(raw.strip().strip('"')).expanduser()
        found = list_videos(target) if target.is_dir() else [target] if target.is_file() else []
        if not found:
            print(f"No videos in {target}" if target.is_dir() else f"Not found: {target}")
        for path in found:
            if path.resolve() not in seen:
                seen.add(path.resolve())
                clips.append(path)
    if not clips:
        print(f"Nothing to probe. Copy the clips into {INPUT_DIR}, or give their paths.")
        return 1
    out_root = Path(args.out).expanduser()
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"{len(clips)} clip(s); results go to {out_root}")
    results = []
    for path in clips:
        print(f"{path.name}:", flush=True)
        results.append(probe_clip(path, args, tools, engines, out_root))
    report = write_report(results, tools, engines, out_root, args)
    print(f"\nReport: {report}\nSend phase0_report.md back. The crops/ folders show your plate: keep them local.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
