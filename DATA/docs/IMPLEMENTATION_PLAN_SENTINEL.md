# Sentinel: implementation plan and review of SPEC_EXPORT_GPS_CSV v1.3

Branch: `sentinel`, based on `af57388`. Companion to `DATA/docs/SPEC_EXPORT_GPS_CSV.md`.

Scope: **VIOFO and Garmin dashcams.** Phone footage is out of scope for now. The source-profile registry (spec §8.9) is where a phone profile, or any other make, would be added later without changing the pipeline, the GUI or the CSV schema.

This document does three things:

1. Summarises how the spec handles more than one camera make (§1).
2. Lists the bottlenecks and risks found in review, each with a proposed fix (§2).
3. Re-cuts the phases so that every phase ends with something you can use (§3).

Items marked **[change]** propose a change to the spec. Items marked **[add]** propose an extension. Neither is in the spec yet; each needs your OK first.

---

## 1. Source profiles (now in the spec, §8.9)

The spec now gives every video a `SourceProfile`, detected from its file name and container with no subprocess, and overridable in the sidebar. A profile holds everything make-specific:

| Field | VIOFO | Garmin |
|---|---|---|
| Detection evidence | Novatek `gps ` box in `moov`, or a VIOFO file name | `GRMN####` file name, or a Garmin make string (Phase 0 confirms which atoms) |
| Start time in the file name | Yes (`2025_0315_105644_0012F.MP4`) | No (`GRMN0007.MP4`) |
| Front/rear letter in the name | Yes | No |
| Container clock is local time | Yes (Phase 0 confirms) | Unknown until Phase 0 |
| Embedded GPS reader | Built-in Novatek, then ExifTool | ExifTool (timed metadata, `SampleTime`) |
| Embedded GPS time is a real clock | Yes | No (CreateDate + SampleTime) |
| Stamp region | Bottom 4.5 % | Provisional; Phase 0 sets it |
| Timelapse capture rates | 1, 2, 3, 5, 10 fps | Phase 0 measures Travelapse |
| Camera preset | Sidebar defaults, hood 0.80, uncalibrated | Sidebar defaults, uncalibrated |

Design points:

- **Auto per file, with an override that is still checked.** It works the same way as Recording mode: a declared profile is kept, but detection still runs and warns on a contradiction. Unrecognised files use the *If not recognised* profile (VIOFO by default) and get a warning.
- **Profiles supply defaults only.** Every setting a profile feeds has a `From profile` value, and an explicit value wins for every video.
- **Camera geometry.** *Camera geometry for export* defaults to `Sidebar values`, which grades exactly as today. `From profile (per video)` is for batches that mix VIOFO and Garmin. `videos.csv` records the geometry actually used, so PCI can be recalculated later.
- **Extensibility.** A make is a registered `SourceProfile`, plus a GPS reader in `GPS_READERS` if it needs a new one. The sidebar lists the registry. A new make needs no GUI, pipeline or schema change; the steps are in spec §8.9, *Adding a make later*.
- **Unchanged.** Photograph mode and the video preview don't use profiles. The GUI stays a Streamlit app used in the browser, and preview and export share the same detect, grade and draw code.

### 1.1 Further proposals

- **GPS source `Auto` as the default [change].** It would walk the profile's chain per video: embedded track, then stamp, then GPX, then none. With the spec's default of `None`, a batch produces no positions unless the user remembers to change it.
- **Stamp region calibration [add].** The Check panel already shows the stamp crop. Add four number inputs that live-update the crop preview, plus a **Save to profile** button that stores the region in `Output/profiles.json`. A new Garmin model then needs no code change.
- **Path inputs on Windows.** *Copy as path* in Explorer adds quotes. Strip surrounding quotes and whitespace from every path text box.

---

## 2. Bottlenecks and risks

Ordered by impact. Timings are **estimates to be measured in Phase 1**. From the first commit, `run.log` should record per-frame decode, detect, grade, OCR and save times.

### 2.1 Detection throughput is the dominant cost

At 1280×800 with 640 px tiles, 0.20 overlap and a 0.45 sky cut-off, each graded frame takes about 3–6 tile inferences of YOLO11-L.

| Footage | Frames at 1/s | GPU (est.) | CPU (est.) |
|---|---|---|---|
| 3-minute clip | 180 | about 1 min | about 10–25 min |
| 4 hours of driving | 14 400 | about 1 h | **12–30 h** |

Choosing *Original resolution* for saved images doesn't change this, because detection still runs at the graded size. Grading at full resolution would roughly quadruple the tile count.

**Fixes, in order of value:**

1. **Sample by distance, not only by time [add].** Add `Sample by: Time | Distance (m)`, used once a track exists. A road survey wants a frame every *N* metres. At 1 frame per second, a stop at a traffic light grades the same patch of road 60 times a minute, and urban driving is often 20–40 % stopped. Distance sampling also supersedes C4 (skip stopped frames). It makes frames comparable across speeds and across VIOFO and Garmin. When there is no track, sampling falls back to time.
2. **Batch the tiles.** Send all of a frame's tiles to `model.predict` in one call, and use `half=True` on CUDA. Results change only by floating-point noise. The change goes in `detect_tiled`, behind a keyword argument whose default keeps today's behaviour.
3. **Decode while detecting.** Decode and OCR in a producer thread that feeds a bounded queue of 8–16 frames. OpenCV decoding and Tesseract subprocesses release the GIL, so this is close to free parallelism. Decoding 2560×1600 HEVC costs real CPU time, and today it runs strictly in series with detection.

### 2.2 Long runs inside the Streamlit script **[change]**

The spec runs the export inside the script run and accepts that *any widget change stops it* (§5.7). That is fine for a 3-minute clip. For a multi-hour batch it is a trap: touching any slider kills the run.

**Proposal.** Run exports in a **background worker thread** owned by an `st.cache_resource` job registry:

- **Run export** and **Run batch** submit a job, with its settings frozen at submit time, and return immediately.
- An `@st.fragment(run_every="2s")` panel reads the job's progress (frame i of N, video k of K, ETA, last warning) and shows it. Widgets can change freely; they affect only the *next* job.
- **Stop** (sets `should_stop`) and **Resume** buttons.
- The job writes `progress.json` into the run folder, so a reloaded page or a second browser tab re-attaches to it.
- `pipeline.py` already must not import Streamlit, and already takes `progress` and `should_stop` callbacks, so this costs little. Resume (M8) stays, but becomes crash recovery rather than the normal way of working.

Interaction in the browser stays the same. The only visible difference is that changing a setting no longer kills a running export.

### 2.3 Appending to CSVs that Excel has open **[change]**

On Windows, Excel locks an open CSV. The spec appends to the top-level `detections.csv` after each video. If you open that file to check progress, the next append raises `PermissionError` and the run fails.

**Proposal:**

- Write per-video part files: `parts/<video_id>/frames.csv`, `detections.csv` and `video.json`. Write each to a temporary name, then rename it with `os.replace`; that makes every video atomic for free.
- Build the top-level CSVs from the parts at the end of the run, and on demand with a **Rebuild CSVs** button and the `merge` CLI. If a top-level file is locked, write `detections (1).csv` and warn instead of failing.
- Resume becomes: a video is done when its `video.json` says `done`. No CSV rewriting.

### 2.4 The OCR pre-pass is a second full pass over every video

For normal video, §8.4 reads the stamp every driving second, with a seek, in a separate pass. At about 120–190 ms per Tesseract call, plus process start-up on Windows, that adds 30–60 s to a 3-minute clip and decodes the file a second time. On a GPU that is comparable to the detection itself.

**Fixes:**

- **Use the main loop's frames.** When sampling is 1 per second or faster, every graded frame is already decoded at full resolution. Read the stamp there, and keep the pre-pass only for the *Check* button and for slow sampling. The spec already does this for timelapse; make it the general rule.
- **Skip OCR** when the embedded track has a real GPS clock (VIOFO `gpsdatetime_is_clock`), but keep the timelapse check. Garmin's embedded time is not a clock, so Garmin keeps the stamp, file-name or container chain.
- Run OCR calls in a small thread pool, 2–4 workers.

### 2.5 Seeking accuracy on real codecs

The spec's "10 of 10 frames exact" result was measured on synthetic `mp4v` files. Real VIOFO and Garmin files are H.264 or HEVC with B-frames, and OpenCV's frame seeking can land a few frames off on them. In normal video that is harmless (≤0.1 s). In timelapse it can be a few seconds of driving.

**Mitigation:** after each seek, read back `CAP_PROP_POS_FRAMES` / `CAP_PROP_POS_MSEC` and record the frame actually reached. Prefer sequential decoding whenever the step is 15 frames or fewer (the spec already does this). Add a Phase 1 check on one real clip from each make.

### 2.6 Camera geometry is uncalibrated for both makes

PCI depends on camera height, focal length and horizon (spec §13). The defaults were calibrated for the Tashkent survey camera, not for a 140° VIOFO or a wide-angle Garmin. Profiles now record which geometry was used and flag it as uncalibrated. A real fix needs one calibration drive per make: a measured mount height plus a few frames of a known road width. That is worth scheduling after Phase 3.

### 2.7 Smaller issues

- **Timelapse detection from 3 reads 1 s apart** relies on whole-second stamps. On normal video the pairwise slopes come out like {2, 0, 1}; the median is still 1, but one misread breaks it. **Proposal:** take **5 reads spread from 10 % to 90 % of the file**. That is still cheap, and the slope is then exact.
- **ExifTool on large files.** `-ee3` reads the whole file, a few seconds per 600 MB clip, so minutes across a 200-file batch. Garmin depends on it, because it has no built-in reader. Cache results per `video_id` in the run folder so that Check, Run and Resume read each file once.
- **The preview and the export decode differently** (§9.3: the preview re-encodes JPEGs). Rather than documenting the difference, the preview could call `iter_samples` too, giving one decode path, as rule 3 in the spec's §2 asks. The visible change would be negligible; flag it at the Phase 1 review.
- **Local file and Batch folder paths are on the machine running Streamlit**, not on the browser's machine. Say so in the help text.
- **Stamp privacy.** Saved frames show the plate and custom text. C2 (masking) becomes cheap once each profile knows its stamp region. Consider promoting it to SHOULD if frames will be shared.
- **Class-name check.** The check that the model's `names[0..7]` match `CLASSES` (§7.3) should block the run, not just warn. A mismatch mislabels every row without anyone noticing.

---

## 3. Phases (re-cut)

Each phase ends with tests passing and a commit `phase N: <summary>`. ⏸ marks a stop for your review.

| Phase | Content | Done when |
|---|---|---|
| **0 ⏸** Probe footage | As in the spec, with a VIOFO normal clip, a VIOFO timelapse clip and a Garmin clip if available. Per clip, record: ExifTool GPS dump, `-time:all`, mvhd, `moov` children and handlers, stamp OCR on 5 frames, file name. | `DATA/docs/DASHCAM_NOTES.md` has a column per clip; both profiles are confirmed or corrected. |
| **1** Refactor + frames | `export/annotate.py`, `export/inference.py` (moved out of `app.py` with no behaviour change), `export/settings.py`, `video.iter_samples` (records the frame actually reached), `timebase.py` with speed-up 1, `profiles.py` (registry, probe, both profiles; camera preset only for now), FPS selector, hood cut-off, Local file, frame saving. **Timing log from day one.** | App unchanged at defaults. A 1 fps export of a local clip gives one JPEG per `frame_times()` entry. `run.log` holds per-stage timings. `test_profiles.py` passes. |
| **2** Background jobs + CSV | Job registry and fragment progress panel (§2.2); `csv_out.py` with per-video parts (§2.3); `run.json`; time from the file name or container, using each profile's rules. | Schema and byte-format tests pass. A running export survives slider changes and a page reload. The CSVs open in Excel (PT) while a run continues. |
| **3a** GPX + clocks | Namespace-free `read_gpx`, `read_gpx_many`, `Track.from_fixes` / `gap_s`, `clock.py` (file name, container, manual), `geo.py` with `GPS_READERS`, Auto GPS source. | GPX positions on a VIOFO and a Garmin clip; the §8.5 Auto-table tests pass. |
| **3b** Embedded GPS | `novatek.py`, `exiftool_gps.py` (Garmin `SampleTime`), the profile's reader and clock rules wired in, *Source profile* widget. | The VIOFO track follows the road. Garmin positions come through ExifTool. §11.3 check 2 passes. |
| **3c ⏸** Stamp + timelapse | `ocr.py`, `stamp.py`, segment clock fit, per-frame fallback, timebase detection, OCR folded into the main loop (§2.4), stamp-region calibration. | §11.2 integration tests pass; §11.3 check 3 passes; the timelapse clip passes. |
| **4** Batch, resume, CLI, merge | Batch folder with a profile per file, resume from parts, distance sampling (§2.1), `python -m smartroad.export`, condition map. | §11.3 checks 5–7 pass on a folder that mixes VIOFO and Garmin. |
| **5** Docs + extras | README section, `quantity` column, EXIF, `tracks/*.gpx`, tile batching and fp16, then C1–C3. | — |

## 4. Questions only you can answer

These add to spec §12.

1. **Sample clips.** Can you supply a VIOFO normal clip, a VIOFO timelapse clip and a Garmin clip? This container has no ExifTool, Tesseract or OpenCV, so Phase 0 has to run on your machine; I can write a probe script for you to run.
2. **Distance sampling.** Should *Sample by distance* become the default once a track exists, or stay an option?
3. **Background jobs.** Are you OK with exports running independently of widget changes (§2.2)? It changes the spec's §5.7 rule.
4. **Garmin model.** Which model is it? This is spec §12, question 10.
