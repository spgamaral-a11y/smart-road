# Sentinel: implementation plan and review of SPEC_EXPORT_GPS_CSV v1.4

Branch: `sentinel`, based on `af57388`. Companion to `DATA/docs/SPEC_EXPORT_GPS_CSV.md` and `DATA/docs/DASHCAM_NOTES.md`.

Scope: **VIOFO and Garmin dashcams.** Phone footage is out of scope; the source-profile registry (spec §8.9) is where it would be added later.

## 0. Decisions so far

| Date | Decision | Where in the spec |
|---|---|---|
| 2026-11-07 | Source profiles; VIOFO and Garmin only; phones later | §8.9 |
| 2026-11-07 | Sampling stays per second of driving. Each graded frame's video time is tied to its position and clock time through the GPS source, so a grading can be found from the CSV. No distance sampling. | §3, §7 (`map_url`), §12 Q4 |
| 2026-11-07 | Exports run in the background | §5.7 |
| 2026-11-07 | Garmin footage comes from YouTube; the model is unknown | §8.10, §12 Q7 and Q10 |

## 1. What the screenshots changed (spec 1.4)

Both stamps were read with the spec's own OCR settings (A.2), with Tesseract 5.3.4 and RapidOCR. Both engines read both stamps exactly. Details are in `DASHCAM_NOTES.md`.

1. **The Garmin stamp uses a format the parser didn't accept.** `GARMIN 01/11/2020 07:17:05 -26.36774 27.31358 70 KM/H` has signed decimal degrees and no hemisphere letter. The 1.3 parser read the time and speed but returned no position, so every Garmin row would have had blank lat/lon. Fixed in A.1, which now accepts this format when the profile switches it on:
   - The decimal count (5) splits digits that OCR runs together, such as `-26.3677427.31358`.
   - Speed is read last, so `…27.3135870KM/H` can't become 870 km/h.
   - A per-video sign vote catches readings where OCR lost the minus sign.

   All 36 earlier parser rows still pass, with the new format switched both on and off.
2. **The Garmin date is ambiguous.** `01/11/2020` could be 1 November or 11 January. YouTube footage has no other date to check it against, so it falls back to DMY with a warning unless the video shows a day above 12 somewhere (§8.10).
3. **Downloaded footage keeps only the stamp.** YouTube drops the camera's file name, container clock and embedded GPS. Spec §8.10 covers this:
   - the profile is recognised from the stamp text (`GARMIN`, `VIOFO`);
   - such files use the stamp alone for time and position;
   - the UTC offset comes from the setting, which should be +2 for the South African sample;
   - PCI from YouTube footage reads high, because compression removes fine cracks. Use it to test the pipeline, not to grade roads.
4. **Edited videos can contain cuts.** The 1.3 clock fit called any clock jump that wasn't a time-zone change a "clock correction", and moved every earlier frame onto the later clock. At a cut, that gives every frame before it the wrong time without any warning. The fit now recognises a cut from a position jump, or from a late step when there are no positions, and leaves both sides alone (A.7).
5. **Timelapse detection could be fooled** by a title card with no stamp, or by a cut. On one test, a single fit over reads spread across the file reported ×12.2 on normal-speed video. Detection now fits three clusters separately and takes the median (A.8).
6. **Camera presets measured on the screenshots:**

   | | Horizon | Sky cut-off | Hood cut-off |
   |---|---|---|---|
   | VIOFO | 0.61 | 0.58 | 0.80 |
   | Garmin | 0.50 | 0.47 | 0.62 |

   The sidebar default horizon, 0.139, belongs to the Tashkent camera. Height and focal length are still unmeasured (spec §13).
7. **Garmin road band.** The visible road between the horizon and the bonnet is only about 140 px tall at 1080p, so PCI from that mount is coarse.
8. **VIOFO windscreen reflection.** A dark reflection sits over the middle of the lane on the VIOFO frame and doesn't move between frames. See §2.6.

The code in A.1, A.7 and A.8 is byte-for-byte the code that was run. The 36 rows of parser tables 1–2 and the 12 rows of the new Table 3 pass, as do the 9 old and 5 new clock-fit scenarios and the 16 timelapse checks.

## 2. Remaining bottlenecks and proposals

Items marked **[proposal]** are not in the spec; each needs your OK.

### 2.1 Detection throughput is the dominant cost

At 1280×800 with 640 px tiles, each graded frame is about 3–6 tile inferences of YOLO11-L. These are estimates; Phase 1 measures them per stage in `run.log`.

| Footage | Frames at 1/s | GPU (est.) | CPU (est.) |
|---|---|---|---|
| 3-minute clip | 180 | about 1 min | about 10–25 min |
| 4 hours of driving | 14 400 | about 1 h | **12–30 h** |

Fixes that don't change results:

1. **Batch the tiles [proposal].** Send all of a frame's tiles to `model.predict` in one call, with `half=True` on CUDA. The change goes in `detect_tiled`, behind a keyword argument whose default keeps today's behaviour.
2. **Decode while detecting [proposal].** Decode and OCR in a producer thread with a bounded queue. OpenCV decoding and Tesseract subprocesses release the GIL.
3. **Skip stopped frames (C4, already in the spec as COULD).** This is the remaining lever for traffic-light stops, now that distance sampling is out. It leaves the per-second rule intact while moving.

### 2.2 The OCR pre-pass is a second pass over every video [proposal]

For normal video, spec §8.4 reads the stamp every driving second in a separate pass. At about 110–200 ms per read, that adds 20–40 s per 3-minute clip, and decodes the file a second time.

- When sampling is 1 per second or faster, every graded frame is already decoded at full resolution. Read the stamp there and keep the pre-pass only for *Check location & time*.
- Skip OCR entirely when VIOFO's embedded track gives a real GPS clock.

### 2.3 Seeking accuracy on real codecs

The spec's "exact frame" result was measured on synthetic `mp4v` files. Real files are H.264/HEVC with B-frames, where OpenCV seeking can land a few frames off. Record the frame actually reached after each seek (`CAP_PROP_POS_FRAMES` / `CAP_PROP_POS_MSEC`), and check it on one real clip from each make in Phase 1.

### 2.4 Stamp region calibration [proposal]

Garmin layouts differ between models, and the model is unknown. In the Check panel, add four number inputs that live-update the stamp crop, plus **Save to profile**, which writes `Output/profiles.json`. A new layout then needs no code change.

### 2.5 Geometry overlay [proposal]

Height and focal length are unmeasured for both makes, and PCI depends on them. Draw distance lines at 3, 5, 10 and 15 m, plus the width a 3.5 m lane would have at each, on the preview frame. The user then tunes height and focal length until the drawn lane matches the real one. It is cheap, and it's the practical way to calibrate from footage alone.

### 2.6 Static artefacts [proposal]

The VIOFO windscreen reflection, the Garmin mount and the bonnet edges stay at the same place in the image while the road moves. Flag a detection as `static_artifact` when a box of the same class overlaps (IoU > 0.5) boxes at the same position in most of the previous 10 frames while the vehicle is moving. Write it as a column; drop flagged boxes from grading only if you want. This needs nothing beyond the detections the pipeline already has.

### 2.7 Smaller points

- **ExifTool:** cache results per `video_id` in the run folder, so Check, Run and Resume read each file once.
- **Preview decoding:** the preview re-encodes frames as JPEG, so the preview and the export can differ slightly. Using `iter_samples` for the preview too gives one decode path.
- **Class-name check:** the check that the model's class names match `CLASSES` should block the run, not just warn.
- **Paths:** strip the quotes that *Copy as path* adds in Explorer, and say in the help text that paths are on the machine running Streamlit.
- **Privacy:** the VIOFO stamp shows the plate and custom text. C2 (masking) is cheap now that each profile knows its stamp region.

## 3. Phases

These match the spec. ⏸ marks a stop for your review.

| Phase | Content | Done when |
|---|---|---|
| **0 ⏸** Probe footage | Started from the screenshots (`DASHCAM_NOTES.md`). Still needed: a VIOFO original clip, a VIOFO timelapse clip and a downloaded Garmin clip. ExifTool, Tesseract and OpenCV have to run on your machine; I can write a probe script for you. | The notes cover the three clips; profile defaults confirmed. |
| **1** Refactor + frames | `export/annotate.py`, `export/inference.py`, `export/settings.py`, `video.iter_samples`, `timebase.py` at speed-up 1, `profiles.py`, FPS selector, hood cut-off, Local file, frame saving, per-stage timing log. | App unchanged at defaults; one JPEG per sampled time; `test_profiles.py` passes. |
| **2** Jobs + CSV | `jobs.py` and the progress panel; `csv_out.py` with per-video part files; `run.json`. | A running export survives slider changes, page reloads and an open Excel file. |
| **3 ⏸** Location and time | GPX, embedded GPS (VIOFO built-in, Garmin ExifTool), stamp OCR with the signed format, segment clock with cuts, timelapse clusters, downloaded-footage rules. I suggest committing it in three steps: GPX and clocks, then embedded GPS, then stamp and timelapse. | §11 tests pass; §11.3 checks 2, 3 and 8. |
| **4** Batch, resume, CLI, merge | Batch folder with a profile per file, resume from parts, CLI, condition map. | §11.3 checks 5–7 and 9 on a folder mixing VIOFO and Garmin. |
| **5** Docs + extras | README section, `quantity`, EXIF, `tracks/*.gpx`, then accepted proposals and C1–C4. | — |

## 4. Questions

1. **Clips for Phase 0.** Can you supply a VIOFO original clip (normal), a VIOFO timelapse clip and one downloaded Garmin clip? Shall I write the probe script that collects everything Phase 0 needs on your machine?
2. **Proposals.** Which of §2.1 (tile batching, decode thread), §2.2 (OCR in the main loop), §2.4 (stamp region calibration), §2.5 (geometry overlay) and §2.6 (static artefacts) should go into the spec? My recommendation: all except §2.6, which can wait until the detector has run on real VIOFO footage.
