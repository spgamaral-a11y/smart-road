# Sentinel: implementation plan and review of SPEC_EXPORT_GPS_CSV v1.5

Branch: `sentinel`, based on `af57388`. Companion to `DATA/docs/SPEC_EXPORT_GPS_CSV.md` and `DATA/docs/DASHCAM_NOTES.md`.

Scope: **VIOFO and Garmin dashcams.** Phone footage is out of scope; the source-profile registry (spec §8.9) is where it would be added later.

## 0. Decisions so far

| Date | Decision | Where in the spec |
|---|---|---|
| 2026-11-07 | Source profiles; VIOFO and Garmin only; phones later | §8.9 |
| 2026-11-07 | Sampling stays per second of driving. Each graded frame's video time is tied to its position and clock time through the GPS source, so a grading can be found from the CSV. No distance sampling. | §3, §7 (`map_url`) |
| 2026-11-07 | Exports run in the background | §5.7 |
| 2026-11-07 | Garmin footage comes from YouTube; the model is unknown | §8.10 |
| 2026-11-07 | Camera settings are user-set in the sidebar, as in the original GUI. The bonnet exclusion is calculated from them. Profiles carry no camera settings. | §5.2 (M9) |
| 2026-11-07 | Added: speed-ups that don't change results, stamp reads from decoded frames, stamp layouts saved from the GUI, distance lines | M15–M18 |

## 1. What 1.5 changed, and why

### 1.1 Bonnet exclusion from the camera settings

Today's GUI already measures road only between a near and a far distance. The camera model turns both into image rows from height, focal length and horizon (`Camera.usable_row_range`). The near distance is fixed at 3.0 m in `app.py`. Spec 1.5 builds the bonnet exclusion on that calculation:

- **`Measure from (m)`** sits beside *Measure out to (m)*. Its default, 3.0, is today's fixed value.
- **The exclusion row** is the image row of *Measure from*, from the camera model. Boxes lying entirely below it are dropped, in the video preview and the export.
- **The *Hood / stamp cut-off* slider and the profile camera presets are gone.**

A setting is needed alongside the camera height because the bonnet's length belongs to the car, not the camera. On a windscreen dashcam the bonnet typically hides the road out to about 4–7 m. With correct camera settings, a fixed 3 m line would land on the bonnet.

Checked on the real grading code with three camera geometries: dropping boxes that lie entirely below the row leaves PCI and quantities unchanged. Those boxes never had area inside the measured band; only the "outside measurable band" count shrinks. With the defaults, the row is at 79 % of the frame height on the sample clip.

### 1.2 Distance lines

The distance lines replace guessing:
- the horizon;
- lines at *Measure from*, every 5 m, and *Measure out to*;
- lane-width ticks on each line;
- the unmeasured zone below the *Measure from* line, shaded.

They use the same camera model as grading, so they show exactly what is measured. Tune height, focal length and horizon until the ticks match the lane edges, then raise *Measure from* until its line clears the bonnet. `DASHCAM_NOTES.md` has starting values for the horizon (VIOFO 0.61, Garmin 0.50) and the bonnet line (0.82, 0.63).

### 1.3 Batching was already half done

`detect_tiled` already sends up to 8 tiles per model call. A 1280×800 frame with the default sky cut-off has 3 tiles of 640×440, so each frame was already one call. The speed-up actually added is sending **several frames'** tiles in one call (`detect_tiled_many`, 4 frames by default), fed by the decode-ahead thread. Both can be switched off, and acceptance check 12 requires identical CSVs either way. Expect a gain on a GPU; on a CPU it changes little.

### 1.4 Stamp reads and stamp layouts

- **No second pass.** The export reads the stamp on frames it decodes anyway, and OCR runs alongside detection instead of before it. With VIOFO's embedded GPS clock, only the 9 timebase reads are OCR'd.
- **Stamp layouts.** The stamp region can be adjusted, suggested and saved from the GUI. *Suggest* uses the method that found both stamps on the screenshots. Saved layouts live in `~/.smartroad/profiles.json`, outside the repository, and each video picks its profile's best-matching layout.

## 2. Remaining review points

Items marked **[proposal]** are not in the spec.

### 2.1 Detection is still the dominant cost

At 1280×800, each graded frame is 3 tile inferences of YOLO11-L. These are estimates; Phase 1 measures them per stage in `run.log`.

| Footage | Frames at 1/s | GPU (est.) | CPU (est.) |
|---|---|---|---|
| 3-minute clip | 180 | about 1 min | about 10–25 min |
| 4 hours of driving | 14 400 | about 1 h | **12–30 h** |

On a CPU, the remaining lever is C4: skipping frames while the vehicle is stopped (already a COULD in the spec).

### 2.2 Seeking accuracy on real codecs [proposal]

The spec's "exact frame" result was measured on synthetic `mp4v` files. Real files are H.264/HEVC with B-frames, where OpenCV seeking can land a few frames off. `iter_samples` should record the frame actually reached (`CAP_PROP_POS_FRAMES` / `CAP_PROP_POS_MSEC`), and Phase 1 should check it on one real clip from each make.

### 2.3 Static artefacts [proposal]

The VIOFO windscreen reflection sits over the middle of the lane, inside the measured band, so the bonnet exclusion doesn't remove it. Flag a detection as `static_artifact` when a box of the same class sits at the same image position (IoU > 0.5) in most of the previous 10 frames while the vehicle is moving. I recommend waiting until the detector has run on real VIOFO footage, to see whether the reflection actually triggers detections.

### 2.4 Smaller points

- **ExifTool:** cache results per `video_id` in the run folder.
- **Preview decoding:** the preview re-encodes frames as JPEG. Using `iter_samples` for the preview too would give one decode path.
- **Class-name check:** the check that the model's class names match `CLASSES` should block the run, not just warn.
- **Paths:** strip the quotes that *Copy as path* adds in Explorer.
- **Privacy:** C2 (masking the plate and custom text in saved frames) is cheap now that each layout knows the stamp region.

## 3. Phases

| Phase | Content | Done when |
|---|---|---|
| **0 ⏸** Probe footage | Started from the screenshots. Still needed: a VIOFO original clip, a VIOFO timelapse clip and a downloaded Garmin clip. ExifTool, Tesseract and OpenCV run on your machine; I can write the probe script. | Notes cover the three clips. |
| **1** Refactor + frames | `annotate`, `inference` (with `band_rows` / `drop_below_band`), `settings`, `iter_samples`, `timebase` at speed-up 1, `profiles`, FPS selector, *Measure from*, distance lines, Local file, frame saving, timing log. | App unchanged at defaults apart from the outline and dropped boxes, with PCI unchanged; `test_overlay.py` passes. |
| **2** Jobs + CSV + speed-ups | `jobs.py` and the progress panel, `csv_out.py` with part files, `run.json`, `prefetch.py`, `detect_tiled_many`. | Export survives setting changes, reloads and an open Excel file; check 12 passes. |
| **3 ⏸** Location and time | GPX, embedded GPS, stamp OCR on decoded frames, stamp layouts panel, segment clock with cuts, timelapse clusters, downloaded-footage rules. Suggested as three commits. | §11 tests pass; §11.3 checks 2, 3 and 8. |
| **4** Batch, resume, CLI, merge | Batch folder with profile filter, resume from parts, CLI, condition map. | Checks 5–7, 9 and 11. |
| **5** Docs + extras | README, `quantity`, EXIF, `tracks/*.gpx`, C1–C4. | — |

## 4. Questions

1. **Clips for Phase 0.** Can you supply a VIOFO original clip (normal), a VIOFO timelapse clip and one downloaded Garmin clip? Shall I write the probe script that collects what Phase 0 needs on your machine?
2. **Start Phase 1?** Phase 1 doesn't depend on Phase 0's results: refactor, frames per second, bonnet exclusion, distance lines, frame saving. It can start now while you gather the clips.
