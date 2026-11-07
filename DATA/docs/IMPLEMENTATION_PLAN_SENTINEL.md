# Sentinel: implementation plan and review of SPEC_EXPORT_GPS_CSV v1.2

Branch: `sentinel`, based on `af57388`. Companion to `DATA/docs/SPEC_EXPORT_GPS_CSV.md`.

The spec is precise and mostly ready to build. This document does three things:

1. Makes the spec **source-agnostic**, so VIOFO, Garmin and phone footage all go through one GUI and one pipeline (§1).
2. Lists the bottlenecks and risks found in review, each with a proposed fix (§2).
3. Re-cuts the phases so that every phase ends with something you can use (§3).

Items marked **[change]** alter the spec. Items marked **[add]** extend it. Everything else follows the spec as written.

---

## 1. Source-agnostic input: VIOFO, Garmin, phones

### 1.1 The problem

The spec treats VIOFO as the reference camera and adds Garmin as a variant. Phones differ in ways the spec doesn't cover:

| | VIOFO A129 Plus | Garmin dashcam | Phone (iOS / Android) |
|---|---|---|---|
| Burned-in stamp | Yes (speed, position, date, time) | Optional, in a different layout | No |
| Embedded GPS | Novatek `freeGPS`, 1 fix per video second | Timed metadata track; ExifTool only | **Usually one start position only** (`©xyz` / ISO 6709), no track |
| Container clock (mvhd) | Probably local time (Phase 0 to confirm) | Unknown (Phase 0) | **True UTC**, set by the network |
| Extra clock metadata | — | — | iOS `com.apple.quicktime.creationdate` holds local time **with the zone offset** |
| File names | `2025_0315_105644_0012F.MP4` | `GRMN0007.MP4` (no time) | `IMG_1234.MOV` (no time), `VID_20250315_105644.mp4`, `20250315_105644.mp4`, `PXL_…` (Pixel; the zone of the time in the name needs confirming) |
| Frame rate | Constant | Constant | **Variable (VFR)** on most phones |
| Orientation | Landscape | Landscape | Rotation flag; may be portrait |
| Timelapse | 1/2/3/5/10 fps capture, constant | Travelapse (rate to confirm) | iOS time-lapse **changes its interval as recording goes on**; Android hyperlapse also crops and stabilises |
| Lens / mount | 140°, barrel distortion, about 1.3–1.5 m high | Wide (about 140–180°) | About 26 mm-equivalent, distortion already corrected; mount height varies |
| Typical way to get a track | Embedded or stamp | Embedded (ExifTool) or stamp | **A separate GPX logger app** on the same phone |

The spec's global defaults (*Container clock is local time = on*, stamp region at the bottom 4.5 %, DMY dates, front camera only, one set of camera geometry) are correct for VIOFO and wrong for phones. In a mixed batch they are wrong for some of the files whatever value is chosen.

### 1.2 Proposal: per-video source profiles **[add]**

Add a **Source profile** to every video. It is detected automatically and can be overridden, the same way the spec treats Recording mode (§8.8):

```
smartroad/survey/profiles.py
  @dataclass(frozen=True) class SourceProfile:
      name: str                      # "viofo-novatek" | "garmin" | "phone-ios" | "phone-android" | "generic"
      container_clock_local: bool    # VIOFO True (Phase 0), phones False
      stamp_roi: tuple | None        # None = no stamp expected, so OCR is skipped
      date_order: str                # "auto" | "DMY" | "MDY"
      filename_patterns: tuple       # regexes, each tagged local or UTC
      camera: CameraPreset           # height_m, focal_35, horizon, hood cut-off
      gps_chain: tuple               # order to try: ("embedded", "stamp", "gpx")
      front_only_suffix: bool
  detect_profile(path, info) -> (SourceProfile, evidence: str)
```

**Detection** reads only container metadata, in-process (no subprocess):

- a Novatek `gps ` box → `viofo-novatek`;
- the `com.apple.quicktime.*` keys, or `©mak` / `com.android.*` keys → phone;
- a Garmin file-name pattern, or Garmin make/model atoms → `garmin` (the atoms need confirming on a real Garmin clip in Phase 0);
- anything else → `generic`, which assumes nothing: no stamp, container clock treated as UTC, and a warning.

**GUI.** Add `Source profile: Auto (per file) | VIOFO / Novatek | Garmin | Phone | Generic` at the top of *Location & time*. Picking a profile *pre-fills* the widgets in §5.4 and the camera-geometry block; the user can still change any of them. Auto applies a profile per file, so one batch can mix cameras.

**Output.** Add `source_profile`, `profile_source` (`auto` or `declared`), `camera_height_m`, `focal_35mm`, `horizon` and `hood_cutoff` to `videos.csv`, so every PCI can be recomputed per video later.

### 1.3 Other changes for source independence

- **GPS source gets an `Auto` option, used as the default [change].** It walks the profile's `gps_chain` per video: embedded track → stamp → GPX → none. With today's default of `None`, a batch produces no positions unless the user remembers to change it.
- **Phone clocks [add].** Read the iOS `creationdate` key (local time + offset) and the mvhd UTC value. Two benefits: the UTC offset is *measured* instead of taken from a setting, and GPX from a logger app on the same phone shares its clock, so they line up with no correction. Add `phone-metadata` as a `time_source` value.
- **Phone single position.** When a file carries only a start position, use it as a sanity check against the GPX (warn if the GPX is more than 200 m away at that time). Never use it as a track.
- **Variable frame rate [change].** `frame_number / fps` is wrong for VFR footage. `iter_samples` should read the frame's real timestamp (`CAP_PROP_POS_MSEC` after `read()`) and put that in `video_time_s`. Select frames by timestamp when the profile is a phone, or when probing finds VFR (compare `n_frames / fps` with the last frame's timestamp, within 1 %).
- **Rotation.** Take width and height from the first *decoded* frame, not from `probe_video`, because OpenCV auto-rotates frames, which can leave the probed size and the decoded size disagreeing. Skip portrait frames for grading and warn; the camera model assumes a landscape view of the road ahead.
- **Phone timelapse and hyperlapse.** Out of scope. iOS time-lapse has no constant speed-up, so the single-number `TimeBase` can't describe it. Detect it (from metadata or from GPX speed ÷ apparent speed) and mark the video `status=skipped` with that reason.
- **Snapping.** The capture-rate list (1, 2, 3, 5, 10, 15) comes from VIOFO's menu. Move it into the profile, so Garmin can add its own rates; the existing "keep the measured value and warn" fallback covers the rest.
- **Stamp region calibration [add].** The *Check location & time* panel already shows the first stamp crop. Add drag-free calibration: four number inputs that live-update the crop preview, and a **Save to profile** button that stores it in `Output/profiles.json`. Garmin and other cameras then need no code change.
- **Path inputs on Windows.** *Copy as path* in Explorer adds quotes. Strip surrounding quotes and whitespace from every path text box.

The GUI stays a Streamlit app used in the browser, as today. Detection, grading and drawing go through the same shared functions (`export/inference.py`, `export/annotate.py`), so preview and export render the same way.

---

## 2. Bottlenecks and risks

Ordered by impact. Timings are **estimates to be measured in Phase 1**: `run.log` should record per-frame decode, detect, grade, OCR and save times from the first commit.

### 2.1 Detection throughput is the dominant cost

At 1280×800 with 640 px tiles, 0.20 overlap and a 0.45 sky cut-off, each graded frame is about 3–6 tile inferences of YOLO11-L.

| Footage | Frames at 1/s | GPU (est.) | CPU (est.) |
|---|---|---|---|
| 3-minute clip | 180 | about 1 min | about 10–25 min |
| 4 hours of driving | 14 400 | about 1 h | **12–30 h** |

Choosing *Original resolution* for saved images doesn't change this: detection runs at the graded size either way. Grading at full resolution would roughly quadruple the tile count.

**Fixes, in order of value:**

1. **Sample by distance, not only by time [add].** Add `Sample by: Time | Distance (m)` once a track exists. A road survey wants a frame every *N* metres. At 1 frame per second, a stop at a traffic light grades the same patch of road 60 times a minute, and urban driving is often 20–40 % stopped. Distance sampling also supersedes C4 (skip stopped frames) and makes frames comparable across speeds and cameras. Fall back to time when there is no track.
2. **Batch the tiles.** Send all of a frame's tiles to `model.predict` in one call (a list of arrays), and use `half=True` on CUDA. This changes no results beyond floating-point noise. The change goes in `detect_tiled`, behind a keyword argument with today's behaviour as the default.
3. **Overlap decoding with inference.** Decode and OCR in a producer thread with a bounded queue (size 8–16). OpenCV decoding and Tesseract subprocesses release the GIL, so this is close to free parallelism. HEVC at 2560×1600 costs real CPU time, and today it runs strictly in series with detection.

### 2.2 Long runs inside the Streamlit script **[change]**

The spec runs the export inside the script run and accepts that *any widget change stops it* (§5.7). That is acceptable for a 3-minute clip. For a multi-hour batch it is a trap: touching any slider kills the run.

**Proposal.** Run exports in a **background worker thread** owned by an `st.cache_resource` job registry:

- **Run export** and **Run batch** submit a job (settings frozen at submit time) and return immediately.
- An `@st.fragment(run_every="2s")` panel reads the job's progress (frame i of N, video k of K, ETA, last warning) and renders it. Widgets can change freely; they affect only the *next* job.
- Add **Stop** (sets `should_stop`) and **Resume** buttons.
- The job writes `progress.json` into the run folder, so a reloaded page, or a second browser tab, re-attaches to it.
- `pipeline.py` already must not import Streamlit, and already takes `progress` and `should_stop` callbacks, so this costs little. Resume (M8) stays, but becomes crash recovery instead of the normal way of working.

This keeps the browser interaction the same. The only visible difference is that settings no longer kill a running export.

### 2.3 Appending to CSVs that Excel has open **[change]**

On Windows, Excel locks an open CSV. The spec appends to the top-level `detections.csv` after each video, so the first time you open the file to look at progress, the next append raises `PermissionError` and the run fails.

**Proposal:**

- Write per-video part files: `parts/<video_id>/frames.csv`, `detections.csv` and `video.json`, written to a temporary name and then renamed (`os.replace`), which makes each video atomic for free.
- Build the top-level CSVs from the parts at the end of the run, and on demand (**Rebuild CSVs** button and `merge` CLI). If a top-level file is locked, write `detections (1).csv` and warn instead of failing.
- Resume becomes: a video is done when its `video.json` says `done`. No CSV rewriting.

This also makes `merge` simpler and removes the rewrite-on-resume step in §6.3.

### 2.4 The OCR pre-pass is a second full pass over every video

For normal video, §8.4 reads the stamp every driving second with a seek, and as a separate pass. At about 120–190 ms per Tesseract call, plus process start-up on Windows, a 3-minute clip adds 30–60 s and a second decode of the file. On GPU that is comparable to the detection itself.

**Fixes:**

- **Use the main loop's frames.** When sampling is at 1/s or faster, every graded frame is already decoded at full resolution, so read the stamp there and skip the pre-pass. Keep the pre-pass only for the *Check* button and for slow sampling rates. This is what the spec already does for timelapse; make it the general rule.
- **Skip OCR entirely** when the profile's chain resolved to a good embedded track with a real GPS clock. Keep the 3-read timelapse check.
- Run OCR calls in a small thread pool, 2–4 workers.

### 2.5 Seeking accuracy on real codecs

The spec's "10 of 10 frames exact" was measured on synthetic `mp4v` files. Real VIOFO (H.264/HEVC with B-frames) and phone (HEVC, VFR) files are where OpenCV's `CAP_PROP_POS_FRAMES` seeking is known to land a few frames off. Two consequences:

- `frame_number` in the CSV can be wrong by a few frames. That is harmless for normal video (≤0.1 s) and up to a few seconds of driving in timelapse.
- **Mitigation:** after each seek, read back `CAP_PROP_POS_FRAMES` / `POS_MSEC` and record the *actual* frame. Prefer sequential decoding whenever the step is ≤15 (the spec already does this). Add a Phase 1 check on one real clip from each source.

### 2.6 One set of camera geometry for the whole run

PCI depends on camera height, focal length and horizon (§13 says so). With mixed sources, one global setting makes some videos' PCI wrong without warning. The source profiles in §1.2 fix this. Until lens calibration exists, print `PCI indicative (uncalibrated <profile>)` in the run summary for every profile other than the calibrated Tashkent one.

### 2.7 Smaller issues

- **Timelapse detection from 3 reads 1 s apart** relies on whole-second stamps. Normal video gives slopes like {2, 0, 1}, and the median is still 1, but a single misread breaks it. Use **5 reads spread from 10 % to 90 % of the file**. That is still cheap, and the slope is then exact.
- **ExifTool on large files.** `-ee3` reads the whole file, a few seconds per 600 MB clip, so minutes over a 200-file batch. Built-in first is right; also cache results per `video_id` in the run folder.
- **`Container clock is local time = on`** is a VIOFO assumption made global. It belongs to the profile (§1.2), and is wrong for phones.
- **Preview and export disagree slightly** (§9.3: JPEG re-encoding in the preview). Rather than documenting it, make the preview call `iter_samples` too, so there is one decode path (rule 3 in §2 of the spec). The visible change is negligible; flag it in the Phase 1 review.
- **Local file / Batch folder paths are on the machine running Streamlit**, not the browser's machine. Say so in the help text; it matters if the app is ever run on a server.
- **Upload limit.** A phone records 4K at about 350–450 MB per minute, so Upload is for short clips only. Local file covers the rest, as for VIOFO.
- **Stamp privacy.** Saved frames show the plate and the custom text. C2 (masking) is cheap once the stamp region is known per profile; consider promoting it to SHOULD if frames will be shared.
- **CLASSES check.** The model's `names[0..7]` check (§7.3) should block the run, not just warn: a mismatch silently mislabels every row.

---

## 3. Phases (re-cut)

Each phase ends with tests passing, a commit `phase N: <summary>`, and a stop for review where marked ⏸.

| Phase | Content | Done when |
|---|---|---|
| **0 ⏸** Probe footage | As in the spec, but with **one clip from each source**: VIOFO normal, VIOFO timelapse, Garmin, iPhone, Android. Record per clip: ExifTool GPS dump, `-time:all`, mvhd, metadata keys, stamp OCR on 5 frames, file name, VFR check, orientation. | `DATA/docs/DASHCAM_NOTES.md` has a column per source; profile defaults are confirmed or corrected. |
| **1** Refactor + frames | `export/annotate.py`, `export/inference.py` (moved out of `app.py`, no behaviour change), `export/settings.py`, `video.iter_samples` (timestamp-accurate, VFR-aware), `timebase.py` with speed-up 1, `profiles.py` skeleton, FPS selector, hood cut-off, Local file, frame saving. **Timing log from day one.** | App unchanged at defaults; 1 fps export of a local clip gives one JPEG per `frame_times()` entry; timing per stage in `run.log`. |
| **2** Background jobs + CSV | Job registry + fragment progress panel (§2.2); `csv_out.py` with per-video parts (§2.3); `run.json`; time from file name / container / phone metadata. | Schema and byte-format tests; a running export survives slider changes and a page reload; CSVs open in Excel PT while a run continues. |
| **3a** GPX + clocks | Namespace-free `read_gpx`, `read_gpx_many`, `Track.from_fixes` / `gap_s`, `clock.py` (file names incl. phone patterns, container, manual, phone metadata), `geo.py`, Auto GPS source. **This is the phone path, end to end.** | Phone clip + logger GPX gives positions; §8.5 Auto table tests. |
| **3b** Embedded GPS | `novatek.py`, `exiftool_gps.py` (Garmin `SampleTime`), profile detection. | VIOFO track matches the road; Garmin positions via ExifTool; §11.3 check 2. |
| **3c ⏸** Stamp + timelapse | `ocr.py`, `stamp.py`, segment clock fit, per-frame fallback, timebase detection, OCR folded into the main loop (§2.4), stamp-region calibration. | §11.2 integration tests; §11.3 check 3; timelapse clip passes. |
| **4** Batch, resume, CLI, merge | Batch folder (mixed sources, per-file profile), resume from parts, distance sampling (§2.1), `python -m smartroad.export`, condition map. | §11.3 checks 5–7 on a mixed folder. |
| **5** Docs + extras | README section, `quantity` column, EXIF, `tracks/*.gpx`, tile batching / fp16, then C1–C3. | — |

Splitting Phase 3 means the phone path (GPX + clock) lands before the hardest part (OCR and the segment clock), and each part can be reviewed on its own footage.

## 4. Questions only you can answer

These add to §12 of the spec.

1. **Sample clips.** Can you supply one clip per source (VIOFO normal and timelapse, Garmin, iPhone, Android), plus the GPX logger app's output for a phone drive? Phase 0 can't confirm any profile without them. This container has neither ExifTool, Tesseract nor OpenCV, so Phase 0 has to run on your machine, or I write a probe script for you to run.
2. **Distance sampling.** Should *Sample by distance* replace frames per second as the default once a track exists, or stay an option?
3. **Background jobs.** Are you OK with exports running independently of widget changes (§2.2)? It changes the spec's §5.7 rule.
4. **Phone mount.** How are the phones mounted (height, windscreen or dashboard, landscape)? This sets the phone profile's camera preset.
5. **Garmin model.** Which Garmin model is it? Stamp layout, Travelapse behaviour and metadata differ between models.
