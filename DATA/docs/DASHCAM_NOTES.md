# Dashcam notes

Phase 0 of `SPEC_EXPORT_GPS_CSV.md`. What the footage shows, as measured, so the profile defaults in spec §8.9 rest on evidence. The horizon and bonnet positions are starting values for your own camera settings (spec §5.2); profiles carry no camera settings.

**Status.** Started from two screenshots supplied on 2026-11-07, one VIOFO and one Garmin. Then the probe ran on real files, a VIOFO A129 Plus front timelapse and a Garmin YouTube download: see *Phase 0 results*. Still wanted: a VIOFO clip recorded at normal speed, and a re-run of the updated probe on the timelapse to confirm the clock offset to the second.

The screenshots are **not** committed. The VIOFO one shows the licence plate and custom text, and the Garmin one is a frame of someone else's YouTube video. In this file the plate is written `AA-00-BB` and the custom text `CUSTOM`.

## Method

- **Stamp position:** near-white pixels (all channels > 200, chroma < 40) in the bottom 12 % of the frame.
- **OCR:** the spec's A.2 settings exactly. Tesseract 5.3.4 is called directly with the whitelist; RapidOCR (rapidocr_onnxruntime 1.2.3) gets the colour crop at 2×. OpenCV 5.0. Each frame was also scaled down to the resolutions a download or the graded image would have.
- **Parsing:** the spec's A.1 parser as it stood in 1.3, then the 1.4 parser.
- **Geometry:** read by eye from the frame, ±0.02 of the frame height.

## VIOFO A129 Plus (front camera)

| Item | Finding |
|---|---|
| Frame | Screenshot at 2000×1250, the camera's 2560×1600 scaled down (same 16:10 shape) |
| Stamp | `84 KM/H S12.035136 E13.955326 CUSTOM VIOFO A129 Plus AA-00-BB 15-03-2025 10:56:44`. Light text with no band, over the bonnet. |
| Stamp position | y 0.972–0.985, x 0.28–0.99; 17 px tall at 1250 px (about 22 px at 1600). The spec's region `(0.0, 0.955, 1.0, 1.0)` holds it. |
| Coordinates | Hemisphere letter, then decimal degrees with 6 decimals (format `dd`) |
| Date | `DD-MM-YYYY`. 15-03 is unambiguous because the day is above 12. |
| OCR | Exact with both engines at 2000×1250 and 1280×800. At 960×600, Tesseract read the year as 2075, which the year check rejects; RapidOCR stayed exact. RapidOCR reads `VIOFO` as `V1OFO` and `Plus` as `PIus`; neither affects parsing, and stamp-token matching normalises `1` to `I`. |
| Time per crop | Tesseract 128–204 ms, RapidOCR 76–302 ms (the first call loads the model) |
| Horizon | The road vanishes at y ≈ 0.61: a starting value for *Horizon row* |
| Bonnet | From y ≈ 0.82. With the camera settings right, raise *Measure from* until its line sits just above this. |
| Lens | Strong barrel distortion with dark corners: the lens circle is inside the frame. Tiles in the corners cost time and see little road. |
| Artefact | A dark reflection on the windscreen sits over the middle of the lane, about x 0.51–0.59, y 0.62–0.83. It doesn't move between frames, so the detector may box it on every frame. A polarising filter removes it at the source. |

## Garmin (model unknown, from a YouTube video)

| Item | Finding |
|---|---|
| Frame | 1920×1080 |
| Stamp | `GARMIN 01/11/2020 07:17:05 -26.36774 27.31358 70 KM/H`. White text with a dark edge and no band, over the dashboard. |
| Stamp position | y 0.965–0.985, x 0.01–0.58; 23 px tall at 1080 px. Built-in `Garmin` stamp layout: `(0.0, 0.95, 0.62, 1.0)`. |
| Coordinates | **Signed decimal degrees with no hemisphere letter**, 5 decimals. The 1.3 parser returned no position for this format; the 1.4 parser reads it when the profile sets `signed_dd` (A.1, Table 3). |
| Position | −26.36774, 27.31358: west of Johannesburg, South Africa (UTC+2, no daylight saving) |
| Date | `MM/DD/YYYY`: the Day 5 download shows `01/15/2020` (Phase 0), so this screenshot's `01/11/2020` is **11 January 2020**, Day 1 of the same trip. |
| Time | 24-hour, `07:17:05` |
| Speed | `70 KM/H`, after the coordinates |
| OCR | Exact with both engines at 1920×1080, 1280×720, 854×480 and 640×360 |
| Time per crop | Tesseract 111–161 ms, RapidOCR 44–363 ms |
| Horizon | The road vanishes at y ≈ 0.50: a starting value for *Horizon row* |
| Bonnet | From y ≈ 0.63, and the dashboard from y ≈ 0.72. *Measure from* should put its line just above y 0.63. The road between the horizon and the bonnet is only about 140 px tall, so the measurable band is thin and PCI is coarse. |
| Other | A hand and a suction mount at the lower left, below the cut-off. Vertical striping across the sky and fields, from compression or scaling; watch whether the detector reads it as cracking. |
| Source | Downloaded from YouTube, so no camera file name, container clock or embedded GPS survives (spec §8.10). Time and position must come from the stamp. |

## Collecting the rest: `scripts/probe_dashcam.py`

The probe collects everything Phase 0 needs from a clip and writes `Output/probe/phase0_report.md`. Stamp text in the report is masked to the fields the parser reads, so the plate and custom text don't appear in it. Run it on your machine (Ubuntu), where the clips are. Once:

```bash
sudo apt install tesseract-ocr libimage-exiftool-perl
```

Then copy the clips into the repository's `Input/` folder (subfolders are fine, see `Input/README.md`) and, from the repository folder:

```bash
python3 scripts/probe_dashcam.py
```

With no arguments it probes every video in `Input/`. Clips elsewhere can be given as paths or folders instead.

It needs Python with `opencv-python` (or `opencv-python-headless`) and `numpy`, as the app does; `pip install rapidocr_onnxruntime` adds a second OCR engine. If ExifTool or Tesseract is missing, it prints the install commands and stops. The `crops/` folders it writes show the plate: keep them local.

## Clips received (2026-11-07)

Shared in a private Google Drive folder. They can't be fetched into a cloud session: the files are private, Google's download host is outside the session's network, and the Drive connector stops at 10 MB. So the probe runs on your machine.

| File | Size | What it is |
|---|---|---|
| `20250313075907_000570R.MP4` | 142 MB | VIOFO, newer-firmware name (spec A.5): local start 2025-03-13 07:59:07, sequence 570, **rear** camera (`R`) |
| `Day 5, Lubango, Angola to Porto Amboim, Angola. Last day of travel.mp4` | 246 MB | A YouTube download, probably the Garmin footage (an overland trip; the Garmin screenshot was in South Africa) |

Still missing: a VIOFO **front** clip (`…F.MP4`, the 2560×1600 camera the spec targets) and a VIOFO timelapse clip.

## Phase 0 results (2026-11-07, probe on the user's machine)

Ubuntu, Python 3.12.3, OpenCV 5.0.0, Tesseract 5.3.4, RapidOCR 1.4.4, ExifTool 12.76.

### `20250315112600_000694F.MP4`: VIOFO A129 Plus, front camera

| Item | Finding |
|---|---|
| File | 226.6 MB; 2560×1600, H.264, 30 fps, 1800 frames, 60 s of video; decoded at 327 frames/s; constant frame rate |
| Mode | **1 fps timelapse, ×30**: the stamp clusters say ×30 and the GPS blocks are 30 s apart; the stamp changes on every frame. 60 s of video cover 30 min of driving. The file name has the normal pattern, so only the stamp or GPS can tell the mode. |
| Container | `ftyp mp42`; top level `ftyp, skip, mdat, moov`; `moov` children `mvhd, trak, udta, gps `; one video track (`avc1`); `udta` has a `user` atom reading `NOVATEK` and `DEMO1` |
| Embedded GPS | `gps ` box last in `moov`; 60 blocks, all valid, marker at offset 40: the spec's A.3 layout decodes it. One block per second of video. First fix 11:25:42 UTC at −11.930558, 13.973020; last 11:55:12 UTC at −11.680786, 13.857951. |
| ExifTool 12.76 | The same 60 fixes, despite the box being last in `moov`: its blocks sit inside `mdat`. The void-blocks-first rule holds trivially (no void blocks). |
| Stamp | `<speed> KM/H S11.913344 E13.967692 <custom text> VIOFO A129 Plus <plate> 15-03-2025 11:28:30`. The built-in layout reads time, position and speed on 5 of 5 frames with both engines. Suggested region: (0.274, 0.962, 0.994, 0.996). |
| Clock: stamp vs GPS | By block timing, −11.5 s: **no +1 h, so the camera's clock runs on UTC**. The 11.5 s, and positions 460 m off when fix *i* is put at video second *i*, are what a fix taken about 12 s into each 30-s window produces. A synthetic clip built that way gives exactly these numbers. The updated probe measures it directly by position (spec A.9). |
| File name | 11:26:00 = first frame's stamp + 29.5 s, about one video second |
| Container clock | `CreateDate` 11:55:59 = last frame's stamp + 28.5 s: the **end** of the recording, on the camera's clock. The file's modification time (11:55:58) agrees. |
| Seeking | Exact on 10 of 10 frames, by frame number and by time (H.264) |
| OCR time | Tesseract 80–90 ms per read; RapidOCR 400–800 ms |
| Static rows | The probe's first static map found none: over 30 min of driving the light on the bonnet changes. The updated probe measures over short stretches. |

### `Day 5, Lubango, Angola to Porto Amboim, Angola. Last day of travel.mp4`: Garmin, YouTube download

| Item | Finding |
|---|---|
| File | 245.5 MB; 1920×1080, H.264, 29.97 fps, 19 165 frames, 10 min 39 s |
| Re-encoded | Handler names "ISO Media file produced by Google Inc." (YouTube), encoder `Lavf62.3.100`; mvhd not set; no GPS of any kind; recognised as Garmin from the stamp |
| Stamp | `GARMIN 01/15/2020 05:45:44 -14.78312 13.75958 106 KM/H`: **month/day/year**, signed decimal degrees with 5 decimals; read on 5 of 5 frames by the Garmin layout with both engines. Suggested region (0.0, 0.873, 0.601, 0.996). |
| Driving covered | 05:45 to 13:53 local on 15 January 2020, from −14.78 to −11.20 latitude (Lubango to Porto Amboim) |
| Speed-up | **Varies along the file:** ×49, ×57 and ×32 at 10, 50 and 90 %. Each stamp shows on 2 consecutive frames, 4 s of driving apart. An edited, re-timed upload: no single time base fits, hence `recording_mode=variable` (spec §8.8). |
| Seeking | Exact on 10 of 10 frames |

## Still to measure (Phase 0)

1. **The timelapse again, with the updated probe:** the clock offset by position (spec A.9) and where each fix sits in its window, to the second; and the bonnet line over short stretches.
2. **A VIOFO clip at normal speed:** the file-name and container-clock offsets at ×1 (expected about 1 s), and the 1-second block alignment.
3. **The camera's Time Zone menu:** is it GMT+0? That would confirm the stamp runs on UTC by setting, not by accident.
4. **Optional, the rear clip** (`20250313075907_000570R.MP4`): its stamp layout and whether it carries GPS too.
