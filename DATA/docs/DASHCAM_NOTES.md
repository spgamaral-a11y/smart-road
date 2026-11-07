# Dashcam notes

Phase 0 of `SPEC_EXPORT_GPS_CSV.md`. What the footage shows, as measured, so the profile defaults in spec §8.9 rest on evidence.

**Status.** Started from two screenshots supplied on 2026-11-07, one VIOFO and one Garmin. Still needed from real files: the ExifTool GPS dump, the container clock (mvhd), the GPS block count, and the stamp read on 5 frames, for a VIOFO normal clip, a VIOFO timelapse clip and a downloaded Garmin clip (spec §10, Phase 0).

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
| Horizon | The road vanishes at y ≈ 0.61 |
| Bonnet | From y ≈ 0.82, so a hood cut-off of 0.80 |
| Lens | Strong barrel distortion with dark corners: the lens circle is inside the frame. Tiles in the corners cost time and see little road. |
| Artefact | A dark reflection on the windscreen sits over the middle of the lane, about x 0.51–0.59, y 0.62–0.83. It doesn't move between frames, so the detector may box it on every frame. A polarising filter removes it at the source. |

## Garmin (model unknown, from a YouTube video)

| Item | Finding |
|---|---|
| Frame | 1920×1080 |
| Stamp | `GARMIN 01/11/2020 07:17:05 -26.36774 27.31358 70 KM/H`. White text with a dark edge and no band, over the dashboard. |
| Stamp position | y 0.965–0.985, x 0.01–0.58; 23 px tall at 1080 px. Profile region: `(0.0, 0.95, 0.62, 1.0)`. |
| Coordinates | **Signed decimal degrees with no hemisphere letter**, 5 decimals. The 1.3 parser returned no position for this format; the 1.4 parser reads it when the profile sets `signed_dd` (A.1, Table 3). |
| Position | −26.36774, 27.31358: west of Johannesburg, South Africa (UTC+2, no daylight saving) |
| Date | `01/11/2020`: ambiguous, 1 November (DMY) or 11 January (MDY). Garmin units can be set to either order. The video needs a day above 12 somewhere, or the user's choice. |
| Time | 24-hour, `07:17:05` |
| Speed | `70 KM/H`, after the coordinates |
| OCR | Exact with both engines at 1920×1080, 1280×720, 854×480 and 640×360 |
| Time per crop | Tesseract 111–161 ms, RapidOCR 44–363 ms |
| Horizon | The road vanishes at y ≈ 0.50 |
| Bonnet | From y ≈ 0.63, and the dashboard from y ≈ 0.72, so a hood cut-off of 0.62. The road between the horizon and the bonnet is only about 140 px tall, so the measurable band is thin and PCI is coarse. |
| Other | A hand and a suction mount at the lower left, below the cut-off. Vertical striping across the sky and fields, from compression or scaling; watch whether the detector reads it as cracking. |
| Source | Downloaded from YouTube, so no camera file name, container clock or embedded GPS survives (spec §8.10). Time and position must come from the stamp. |

## Still to measure (Phase 0)

1. **VIOFO original clip:** `exiftool -ee3 -api debug=1 -G3 -a -s -GPSType -GPSDateTime -GPSLatitude -GPSLongitude -GPSSpeed`, `exiftool -a -G1 -s -time:all`, the file name, `moov`'s children, and the stamp on 5 frames. From these: the camera's UTC offset, whether mvhd holds local time, and whether stamp time matches GPS time.
2. **VIOFO timelapse clip:** GPS block count against frame count, whether the stamp changes every frame, and the file names.
3. **Garmin YouTube download:** the container's encoder and handler strings and its mvhd value, to confirm nothing of the camera's survives; the frame rate; the stamp on 5 frames; and whether any frame has a day above 12, which would settle the date order.
