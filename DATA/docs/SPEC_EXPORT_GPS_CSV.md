# Smart Road: frame export, CSV export and GPS/time tagging

**Spec for Claude Code (VS Code).** Target repo: `spgamaral-a11y/smart-road` at commit `af57388`.
Version 1.4, 2026-11-07. Suggested location in the repo: `DATA/docs/SPEC_EXPORT_GPS_CSV.md`.

**Changes in 1.4: real stamps, downloaded footage, background exports** (checked against the two screenshots supplied on 2026-11-07; see `DATA/docs/DASHCAM_NOTES.md`)

- **The Garmin stamp needed a new coordinate format.** The real Garmin stamp reads `GARMIN 01/11/2020 07:17:05 -26.36774 27.31358 70 KM/H`: signed decimal degrees with no hemisphere letter. Both OCR engines read it exactly, but the 1.3 parser returned **no position** for it. The parser gains a signed format, switched on by the Garmin profile, with the profile's decimal count to split run-together digits (A.1, Table 3). Speed is now read last, from the text left over, and values above 300 km/h are rejected.
- **Profiles from the real stamps.** Stamp regions, tokens (`VIOFO`, `GARMIN`) and camera presets (horizon, sky and hood cut-offs) are measured from the screenshots (§8.9). A profile can now be recognised from its stamp text when the container carries no evidence.
- **Downloaded and edited footage** (§8.10). The Garmin footage comes from YouTube, which keeps only the burned-in stamp: no camera file name, container clock or embedded GPS. Such files use the stamp alone. Edited videos can contain cuts, which the clock fit now recognises instead of re-basing the earlier frames onto a later clip's clock (A.7). Timelapse detection reads three clusters of frames, so a title card or a cut can't bias it (A.8).
- **Exports run in the background** (§5.7). Changing a setting no longer stops a running export.
- **Per-video part files** (§6.3). Each video's rows are written to their own files first, so a CSV that Excel has open can't make a run fail.
- **Locating a grading.** GPS source defaults to `Auto`. Every graded frame row already carries its video time, clock time and position; a `map_url` column is added to `frames.csv` and `detections.csv`, and the preview shows clock time and position per graded frame once they are known (S7).
- **Sampling stays per second of driving.** Distance-based sampling is not planned.

**Changes in 1.3: source profiles** (§8.9)

- **Profiles.** Everything that depends on the camera make now lives in a `SourceProfile`: file-name formats, the container-clock rule, the embedded GPS reader, whether embedded GPS time is a real clock, the stamp region, date order, timelapse capture rates and a camera-geometry preset.
- **Two profiles, VIOFO and Garmin.** Each video's profile is detected from its file name and container, with no subprocess. A new *Source profile* setting (`Auto` / `VIOFO` / `Garmin`) overrides detection, but detection still runs and warns on a contradiction, as for Recording mode.
- **A registry for later makes.** Profiles are registered in `smartroad/survey/profiles.py`. The GUI lists the registry, so adding a make later means adding a profile (and, if needed, a GPS reader), not changing the pipeline or the CSV schema. Phone footage is out of scope for now.
- **New columns.** `videos.csv` gains `source_profile`, `profile_source`, `camera_height_m`, `focal_35mm`, `horizon` and `hood_cutoff`.
- **Settings.** *Container clock is local time*, the stamp region and the embedded GPS backend now default to `From profile`. A new *Camera geometry for export* setting chooses between the sidebar values (default, as before) and each video's profile preset.

**Changes in 1.2: timelapse video** (§8.8)

- **Time base.** Every video gets a time base that converts video time into **driving time**: `elapsed_s = video_time_s × speed-up`. Every clock, position, GPX and speed calculation now uses driving time. Normal video is simply speed-up 1, so there is a single code path.
- **Sampling.** The "Frames per second" selector now counts per second of **driving**. Frames are chosen by frame number, and short steps are decoded sequentially for exact frames.
- **Detection and override.** The recording mode is detected per video, from 3 stamp reads or from the embedded GPS times. A new *Recording mode* setting (`Auto` / `Normal` / `Timelapse` + rate) overrides detection, but the cheap check still runs and warns on any contradiction.
- **Location sources.** In timelapse, every frame's stamp is read and is the preferred position source. VIOFO keeps one GPS fix per second of *video*, which in a 1 fps timelapse is one fix per 30 s of driving.
- **New columns.** `frame_number` and `elapsed_s` in `frames.csv` and `detections.csv` (now 40 columns). `recording_mode`, `speedup`, `capture_fps`, `mode_source` and `driving_duration_s` in `videos.csv`.
- **Embedded GPS alignment.** It now fits a slope instead of assuming 1 s per block. That fit also yields the timelapse speed-up.
- Version 1.1 would have failed on timelapse: its clock fit, run on video time, found no consistent readings, and the per-frame check rejected every frame.

**Changes in 1.1** (answers to the Phase 0 questions):

- **Per-frame stamp fallback.** When the stamp clock can't be fitted, or a frame lies outside the fitted span, each graded frame's own stamp is read. The value is accepted only if neighbouring readings agree, and the row is marked `time_source=overlay-frame` (§8.4).
- **More stamp formats.** The stamp parser now reads:
  - Garmin coordinates: degrees and decimal minutes `hddd°mm.mmm'` (Garmin's default), degrees-minutes-seconds, and decimal degrees with a trailing hemisphere;
  - MDY dates with automatic order detection, unpadded `3/4/2025` dates and 12-hour `AM`/`PM` clocks.

  See §8.4 and A.1.
- **Time zone changes and clock corrections inside a video are handled.** UTC stays continuous, while local time and `utc_offset` follow the camera row by row. A jump of a whole number of 15-minute steps is a time zone change. Any other jump is a clock correction, for example GPS sync after power-on (§8.7).
- **Tesseract is now called directly**, with the whitelist passed as its own argument, instead of through `pytesseract`. On Windows, `pytesseract` passes the quotes through to Tesseract, so the 1.0 whitelist was silently ignored there. The whitelist now includes `° ' "` (A.2).
- **Garmin embedded GPS.** The ExifTool backend now also reads `SampleTime`. For Garmin dashcams, ExifTool's `GPSDateTime` is computed from the file's creation date, not measured by GPS, so it is not used as a clock (§8.2).
- **Schema changes.**
  - `videos.csv`: `utc_offset` is split into `utc_offset_start` and `utc_offset_end`, and a `clock_events` column is added.
  - `time_source` gains the value `overlay-frame`.
  - `gps_quality` gains the value `stamp-frame`.

Prompt to start Claude Code with:

> Read `DATA/docs/SPEC_EXPORT_GPS_CSV.md` completely, then the files listed in its §0. Do Phase 0 and stop to show me the results.

---

## 0. Working rules for Claude Code

1. Read this spec end to end first. Then read `app.py`, `smartroad/survey/video.py`, `smartroad/survey/frames.py`, `smartroad/detect/tiled.py`, `smartroad/pci/from_detections.py`, `CLASSES` in `smartroad/data/build_yolo.py`, `tests/test_video.py` and `tests/test_frames.py`. Follow their style: frozen dataclasses, type hints, and module docstrings that explain *why*.
2. Implement the phases in §10 in order. At the end of each phase:
   - run `pytest tests -q`. All existing tests and the new ones must pass or skip cleanly. The README says 181 tests, but the suite has grown since, so don't treat that number as the target;
   - commit as `phase N: <summary>`.

   Stop for my review after Phase 0 and after Phase 3.
3. Don't change existing behaviour. Photograph mode, the video preview and every existing public function in `smartroad/` keep working as they do now. New parameters are keyword-only, and their defaults reproduce today's behaviour.
4. **MUST** means required. **SHOULD** means do it unless it conflicts with a MUST, and say so if it does. **COULD** means do it only after everything else passes.
5. Only ask me about the items in §12. Everything else has a default in this spec, so use it.

## 1. Goal

Today the app grades a short clip interactively, and nothing survives a page reload. After this work it must grade whole dashcam drives, one video or a folder of them, and leave a durable, searchable record:

- every graded frame saved as a JPEG in an output folder;
- one CSV row per detected feature, giving:
  - what it is;
  - where it is (lat/lon);
  - the time into the video file;
  - the recording date and time;
- the same schema for every video and every run, so runs can be merged and analysed in Excel, pandas or QGIS.

Reference camera: **VIOFO A129 Plus** with its GPS mount:

- Novatek NT96670 chip;
- MP4 files;
- 2560×1600 front camera.

It burns in a stamp like the one on the sample frame:

`84 KM/H S12.035136 E13.955326 <custom text> VIOFO A129 Plus <plate> 15-03-2025 10:56:44`

Everything camera-specific is a default, never a hard-coded assumption.

## 2. What exists today (verified at `af57388`)

**GUI.** Streamlit, in a single file, `app.py`. The sidebar has:

- `Input` (Photograph | Drive video);
- `Source` (Sample | Upload);
- `Sample every (s)`, 0.5–5.0, default 1.0;
- `Max frames`, 4–40, default 15;
- severity;
- detection: confidence 0.25, tiled on, overlap 0.20, sky cut-off 0.45;
- camera geometry: height 1.70 m, focal length 25 mm, horizon 0.139, measure out to 15 m.

**Video path.**

1. `detect_video(video_bytes, every_s, max_frames, …)` is `@st.cache_data` on the raw bytes.
2. `extract_frames(…, long_side=1280)` writes temporary JPEGs.
3. Each frame is detected (`_detect`) and graded (`grade`), which returns a `FrameAssessment`: `pci`, `rating`, `max_cdv`, `q`, `inspected_area_m2`, `quantities`, `deduct_values`, `excluded`.
4. Results stay in memory as `(t, PIL image, detections, assessment)`. Nothing is written to disk.

**"Graded frame"** in this spec means one of those sampled frames after detection and ASTM grading.

**`smartroad/survey/video.py`** has:

- `probe_video`;
- `frame_times`, which starts half an interval in;
- `iter_frames`, which seeks with `CAP_PROP_POS_MSEC`;
- `extract_frames`.

**`smartroad/survey/frames.py`** already has the following. `app.py` doesn't use them yet.

- `read_gpx` (GPX 1.1 namespace only);
- `Track` (indexed by time, linear interpolation, ±10 s edge clamp);
- `video_start_time` (mvhd creation time);
- `locate_frames`;
- `haversine_m`.

**Reuse these. Don't write a second GPX or track implementation.**

**Constraints stated in the code that this work must respect.**

1. **No ffmpeg or ffprobe subprocess in the app path.** Streamlit runs the script on a worker thread. On macOS, a subprocess spawned there after Metal initialises segfaults (see the `video.py` docstring). Decode video in-process with OpenCV.
2. **CI is light.** It installs only numpy, pillow, openpyxl, pyyaml and pytest. There is no OpenCV, torch, Streamlit or OCR. New library modules must import those lazily. Tests that need them use `pytest.importorskip(...)` or skip the way `tests/test_video.py` does.
3. **One copy of every calculation.** As the `pci_from_quantities` docstring puts it, "two copies drift". The export path and the GUI share the same detect and grade code.

**Upload limit.** `maxUploadSize` is 300 MB. A 3-minute A129 Plus clip at about 27 Mbps is about 600 MB, so dashcam files must be readable **from a local path**, not only by upload.

## 3. Decisions (how the request is interpreted)

| Request | Decision |
|---|---|
| Save each graded frame as a picture to the Output folder | Every graded frame is saved as a JPEG under `Output/<run>/frames/<video>/`. The default image is annotated: boxes, labels, the searched region and an info footer. Options: raw image or both; all frames, only frames with detections, or only frames with PCI below a threshold. |
| Select how many frames per second | `Sample every (s)` becomes a **Frames per second** selector. It sets the grading rate, and so the saving rate. Internally `every_s = 1 / fps`, so `frame_times()` and everything downstream stay unchanged. |
| Export the result as a CSV file | Three CSVs per run, plus `run.json`. **`detections.csv`** has one row per detected feature and is the main output. **`frames.csv`** has one row per graded frame, *including frames with no detections*; without it you can't tell road that was inspected and found fine from road that was never inspected. **`videos.csv`** has one row per video: status, clock, GPS coverage. |
| GPS source: inside the video, an external GPX file, or the coordinates written on the video | Selectable: None, Embedded in video, GPX file(s), or On-screen stamp (OCR). The GPS columns are always present in the CSV, so the schema stays the same whichever source is chosen. They are empty when the source is None. |
| Time and date, from the same three sources | Selectable: Auto (follows the GPS source), Embedded GPS clock, On-screen stamp, File name, Container (mvhd), or Manual. |
| Batches whose results can be searched and analysed | A new input mode, **Batch folder**. Runs can be resumed, and each video gets a stable `video_id`. A CLI and a merge tool reuse the same pipeline. |
| Timelapse video (1 frame per second) must work too | Each video gets a time base. Driving time (`elapsed_s`) drives every clock and position calculation, and frames are sampled by driving time. The recording mode is detected per video; the user setting is an override that is still checked (§8.8). |
| Footage from more than one dashcam make: VIOFO and Garmin now, others later | Each video gets a source profile, detected from its file name and container, with a sidebar override that is still checked. The profile holds everything make-specific, so adding a make later means adding a profile, not changing the pipeline (§8.9). |
| Find the GPS location and clock time of a particular grading | Each graded frame (one per second of driving by default) gets its video time, driving time, local and UTC clock time, position and speed in `frames.csv`, and every detection repeats them in `detections.csv`, with a `map_url` link. GPS source defaults to `Auto` (§5.4). The preview shows the same per graded frame once *Check location & time* has run (S7). |
| Exports can run in the background | Run export and Run batch start a background job; settings can change while it runs and apply to the next job (§5.7). |
| Garmin footage downloaded from YouTube | Downloads keep only the burned-in stamp, so time and position come from the stamp alone; edited videos may contain cuts (§8.10). |

## 4. Scope

**MUST**

- **M1** Frames-per-second selector (§5.2).
- **M2** Save graded frames, with options for which frames, style, footer and size (§5.3, §6).
- **M3** CSV export: `detections.csv`, `frames.csv`, `videos.csv` and `run.json`, in Standard and Excel PT/EU formats (§7).
- **M4** Location from three sources (§8):
  - embedded GPS, with a built-in Novatek decoder and an ExifTool backend;
  - GPX 1.0 and 1.1, including several files at once;
  - OCR of the on-screen stamp, with Tesseract and RapidOCR.
- **M5** Date & time source selector, camera UTC offset and fine offset (§8.5). Also:
  - the per-frame stamp fallback (§8.4);
  - time zone changes and clock corrections inside a video (§8.7).
- **M6** A **Check location & time** button that runs §8 for one video, without detection (§5.5).
- **M7** A **Local file** source for Drive video, and a **Batch folder** mode (§5.1, §5.6).
- **M8** Runs can be resumed, and each video's rows are written atomically (§6.3).
- **M9** A **hood/stamp cut-off** at the bottom of the search region, so the car's hood and the burned-in stamp are not searched for distress (§5.2). The default is 1.0, which changes nothing.
- **M10** The tests in §11.
- **M11** Timelapse video (§8.8):
  - a time base per video, so all timing uses driving time;
  - frames sampled by driving time;
  - automatic detection of the recording mode, with the user setting as an override that is still checked;
  - the stamp read on every frame.
- **M12** Source profiles (§8.9):
  - a `SourceProfile` registry, with a VIOFO and a Garmin profile;
  - per-video detection, with the user setting as an override that is still checked;
  - the profile and the camera geometry used are recorded per video in `videos.csv`.
- **M13** Background exports (§5.7): a job registry, a progress panel that survives setting changes and page reloads, Stop and Resume.
- **M14** Downloaded and edited footage (§8.10): stamp-only time and position, recognition of the profile from the stamp, cuts.

**SHOULD**

- **S1** A CLI, `python -m smartroad.export`, with the commands `run`, `gps` and `merge` (§9.4).
- **S2** A condition map after each run: `st.map` of the frames, coloured by ASTM band.
- **S3** GPS and capture time written into the EXIF of saved JPEGs, using Pillow only (Appendix A.6).
- **S4** A `quantity` column per detection: m², m or count.
- **S5** A `tracks/<video>.gpx` file with the track actually used.
- **S6** A README section, "Export: frames, CSV and GPS".
- **S7** Once *Check location & time* has run for a video, the preview's all-frames table gains `Clock time`, `Lat`, `Lon` and `Map` columns, and the worst-frame heading shows its clock time and position.

**COULD**

- **C1** GPS lag calibration, by comparing embedded positions with stamp positions.
- **C2** An option to mask the stamp (plate and custom text) in saved frames.
- **C3** A `detections.geojson` file.
- **C4** An option to skip grading frames while the vehicle is stopped (speed under 3 km/h), counted in `videos.csv`. Timelapse, and parking-mode timelapse especially, records long stops cheaply, and every frame of a stop shows the same patch of road.

**WON'T (this time)**

- Changes to Photograph mode.
- Frame-to-frame deduplication, or a PCI per road section. `sections.py` exists but is not wired in.
- Map-matching to a road network.
- Lens undistortion.
- Batch mode on the Hugging Face Space.
- Phone footage (iPhone, Android). It would be added later as a new profile in the registry (§8.9).
- Distance-based sampling. Frames are sampled per second of driving (§5.2).

## 5. GUI

### 5.1 Input (sidebar, top)

- `Input` becomes `Photograph | Drive video | Batch folder`. Hide **Batch folder** and **Local file** when the `SPACE_ID` environment variable is set (Hugging Face).
- In Drive video mode, `Source` becomes `Sample | Upload | Local file`.
  - **Local file** is `st.text_input("Video file path")`. Check that the file exists and that its suffix is .mp4, .mov or .m4v, in any case.
  - The preview of a local file is cached on `(path, size, mtime, settings)`, never on the file's bytes.
- Batch folder mode has these inputs:
  - **Folder**: a text input.
  - **Include subfolders**: on by default.
  - **File pattern**: default `*.mp4;*.mov`, case-insensitive.
  - **Front camera only**: on by default. It keeps names whose stem ends in `F`, and is ignored when no name ends in F, R or I. It applies only to files whose profile names files by camera (`camera_letters`, §8.9): VIOFO does, Garmin doesn't.
  - **Scan**: a button that shows a table with each file's name, size (MB), duration (s), start time (from the file name), and whether it is already done in the selected run.

### 5.2 Sampling and search region (sidebar)

- Replace the `Sample every (s)` slider with `st.select_slider("Frames per second of driving", options=[0.2, 0.25, 0.5, 1, 2, 3, 4, 5], value=1)`.
  - The rate is per second of **driving**, not per second of video. The two are the same for normal video. For timelapse they are not (§8.8).
  - Under it, show the caption `≈ {60/3.6/fps:.0f} m between frames at 60 km/h`.
  - Once the recording mode is known, add the frame step, for example `= every frame (timelapse, 1 fps capture)` or `= every 30th frame`.
  - A rate above the capture rate is capped at every frame, with a note.
  - Wherever the UI says "1 per {every_s} s", say "{fps:g} per s" instead.
- Add `Recording mode` (§8.8):
  - **`Auto`** (default): detect per video.
  - **`Normal video`.**
  - **`Timelapse`**, with a capture rate: `1`, `2`, `3`, `5` or `10` fps, default 1.

  Help text: "Timelapse files play 1 s of video for many seconds of driving. Auto measures this from the stamp or the embedded GPS. Choose a mode only if a file has neither, or to save the check."
- Rename `Max frames` to `Max frames (preview)`. Export ignores it and uses `Frames per video` from §5.3 instead.
- The preview keeps sampling by video time, unchanged. When the mode is known to be timelapse, its caption says: "Timelapse: the preview samples by video time; export samples by driving time."
- **M9.** Add a `Hood / stamp cut-off (bottom)` slider:
  - range 0.50–1.00, default 1.00;
  - help text: "Rows below this fraction are not searched: bonnet, dashboard, burned-in stamp";
  - passed to `road_roi()` as a new keyword-only argument, `bottom_fraction=1.0`. With the default, the region is identical to today's;
  - both detection paths drop boxes whose centre is below the cut;
  - grading uses the same cut, so the inspected area doesn't include the bonnet.

  On the sample frame the bonnet starts about 81 % of the way down, so the VIOFO preset is about 0.80. Confirm this against the green outline in the preview.

### 5.3 Export (sidebar, `### Export`)

| Widget | Default | Notes |
|---|---|---|
| Output folder | `<repo>/Output` | Text input. Created on the first run. Add `Output/` to `.gitignore`. |
| Run label | empty | Converted to a slug and added to the end of the run folder name. |
| Frames per video | All | `All`, or `Limit` plus a number, for quick tests. |
| Save graded frames | on | |
| · Which frames | All graded frames | `All graded frames`, `Only frames with detections`, or `Only frames with PCI below` plus a number (default 70). |
| · Style | Annotated | `Annotated`, `Raw`, or `Both`. Both also writes `…_raw.jpg`. |
| · Info footer | on | A band added **below** the image, so the original pixels are untouched (§6.2). |
| · Image size | As graded (1280 px) | Or `Original resolution`, with boxes scaled by original width ÷ graded width. |
| · JPEG quality | 90 | 60–100. |
| · GPS & time in EXIF | on | S3. Written only when the values are known. |
| Write CSV files | on | |
| · CSV format | Standard | `Standard (comma, dot decimal)` or `Excel PT/EU (semicolon, comma decimal)` (§7.1). |
| · Include raw stamp text | off | Off for privacy: the stamp can show the licence plate. |

### 5.4 Location & time (sidebar, `### Location & time`)

| Widget | Default | Notes |
|---|---|---|
| Source profile | Auto | `Auto (per file)`, or one of the registered profiles: `VIOFO`, `Garmin`. Help text: "Auto recognises each file's make. Choose one only if detection gets a file wrong." Rules in §8.9. |
| If not recognised | VIOFO | The profile used, with a warning, when Auto recognises no registered make. |
| Camera geometry for export | Sidebar values | `Sidebar values` uses the Camera geometry and hood cut-off sliders for every video, as before. `From profile (per video)` uses each video's profile preset, for batches that mix makes (§8.9). The preview always uses the sidebar values. |
| GPS source | Auto | `Auto`, `None`, `Embedded in video`, `GPX file(s)`, or `On-screen stamp (OCR)`. **Auto**, per video: GPX if GPX files are given; otherwise the profile's embedded GPS if the file has it; otherwise the on-screen stamp if an OCR engine is installed; otherwise none. The source used is written to `gps_source`. |
| Downloaded / re-encoded video | Auto | `Auto`, `Yes` or `No`. **Yes** means the file name, container clock and embedded GPS are not the camera's, so only the stamp is used (§8.10). **Auto** answers Yes when the profile was recognised from the stamp alone. |
| Date & time source | Auto | `Auto`, `Embedded GPS clock`, `On-screen stamp (OCR)`, `File name`, `Container (mvhd)`, or `Manual`. Rules in §8.5. |
| Camera clock UTC offset at start (h) | +1.0 | From −12 to +14, in steps of 0.25. Help text: "Stamps and file names use the camera's local time. Angola (WAT) is UTC+1 with no daylight saving." Used only when the offset can't be measured or carried over from the previous video (§8.7). |
| Local time columns | Camera's clock | `Camera's clock` means what the camera showed, with the offset per row. `Fixed UTC offset` plus a number gives every row the same zone, for a report in one zone (§8.7). |
| Fine time offset (s) | 0.0 | Added to the resolved video clock. |
| Max gap to interpolate (s) | 5 | Beyond this, the location is left blank and `gps_quality` is `gap`. |
| ▸ Embedded GPS | From profile | Backend: `From profile`, `Auto (built-in, then ExifTool)`, `Built-in only`, or `ExifTool only`. `From profile` means built-in then ExifTool for VIOFO, and ExifTool only for Garmin (§8.9). The ExifTool path is found with `shutil.which("exiftool")` and can also be typed in. |
| ▸ GPX | — | A `st.file_uploader(type="gpx", accept_multiple_files=True)` **and** a text box for the path to a .gpx file or a folder of them. Merge both. |
| ▸ On-screen stamp | Auto | See the list below this table. |
| Container clock is local time | From profile | `From profile`, `On` or `Off`. Many dashcams write local time into mvhd, which the MP4 format reserves for UTC. Phase 0 confirms the value for each profile (§8.9). |
| Manual start | — | A local date and time. Shown only for Manual. |

The ▸ On-screen stamp expander contains:

- **Engine:** `Auto`, `Tesseract` or `RapidOCR`.
- **Tesseract path:** found automatically, first on the PATH, then at `C:\Program Files\Tesseract-OCR\tesseract.exe`.
- **Stamp region:** `From profile` (default) or four custom fractions `x0, y0, x1, y1`. VIOFO's region is `0.0, 0.955, 1.0, 1.0` (§8.9).
- **Date order:** `Auto` (default; starts from the profile's order), `DMY` or `MDY`. Year-first dates are always detected. The rules for Auto are in §8.4.
- **Read every:** 1.0 s.
- **Read each frame's stamp when the clock can't be fitted:** on (§8.4).

If an optional dependency is missing, its option stays visible but disabled. Its help text says what to install:

| Option | Install |
|---|---|
| Tesseract | `winget install -e --id UB-Mannheim.TesseractOCR`. Nothing to install with pip: the app calls `tesseract.exe` itself (A.2). |
| RapidOCR | `pip install rapidocr_onnxruntime` |
| ExifTool | `winget install -e --id OliverBetz.ExifTool` |

### 5.5 Main area: single video (Drive video mode)

The existing preview stays as it is: strip, chart, worst frame and all-frames table. Once *Check location & time* has run for the video, the all-frames table gains `Clock time`, `Lat`, `Lon` and `Map` columns, and the worst-frame heading shows its clock time and position (S7). Add a new section, `#### Export this video`, below it. It contains:

- **A one-line plan**, for example `Whole video · 1 fps → ~180 frames · GPS: Embedded · Output: Output/20261106-193012_benguela`.
- **Check location & time.** This runs §8 only, with no detection, and shows:
  - the recording mode, speed-up and how it was decided (§8.8), for example `timelapse ×30 (1 fps capture), from the stamp`;
  - the clock source;
  - start and end times, in UTC and local time;
  - the GPS source and backend, the number of fixes and the coverage %;
  - an `st.map` of the fixes;
  - for OCR: the first stamp crop (`st.image`), the raw OCR text and the parsed values.

  Cache the result in `st.session_state`, keyed on `(video_id, geo settings)`, so that **Run export** can reuse it.
- **Run export**, the primary button. It starts a background job (§5.7) and returns at once. The job panel shows `Frame i of N · ETA mm:ss`. When the job finishes, show:
  - metrics: frames, detections, mean and minimum PCI, GPS coverage %;
  - the condition map (S2);
  - a table of detections by class;
  - `st.download_button` for `detections.csv`, for `frames.csv`, and for a zip of all the CSVs plus `run.json`;
  - the path of the run folder.

Sample and Upload sources are written to a temporary file first, as today, and deleted afterwards. Local file uses the original path.

### 5.6 Main area: Batch folder mode

- Show the scan table. Order the videos by the recording time in their file names, and by name when there is none.
- **Check location & time** works on one video chosen from the scan table.
- **Run target:** `New run` or `Resume: <run folder>`. The Resume list shows the run folders under the output folder whose `run.json` has `"finished": null`.
- **Run batch** starts a background job (§5.7). Its panel shows overall progress (`video k of K`) and the progress of the current video. If a video fails, it is recorded in `videos.csv` with `status=failed` and an `error`, and the batch carries on with the next one.
- When the batch finishes, show the same summary as §5.5, computed over all the videos.

### 5.7 Behaviour rules

- **Background jobs** (`smartroad/export/jobs.py`). Streamlit reruns the script whenever a widget changes, so the export must not run inside the script.
  - **Run export** and **Run batch** submit a job to a registry held in `st.cache_resource`. The job runs `process_video` or `process_batch` on a worker thread, with the `ExportSettings` frozen at submit time, and the button returns at once.
  - A progress panel, an `@st.fragment(run_every="2s")`, reads the job's state and shows `video k of K · frame i of N · ETA mm:ss`, the last warning and a **Stop** button. Changing a setting doesn't touch a running job; it applies to the next one. Show: `Export running in the background. Settings you change now apply to the next export.`
  - The job writes `progress.json` into the run folder at least every 2 s, so a reloaded page or a second browser tab finds it again.
  - **Stop** sets `should_stop`. The current video is abandoned (its part files are not written) and finished videos are kept. If the server process ends, the job ends with it, and **Resume** continues from the part files (§6.3).
  - One job at a time per output folder. A second submit is refused with a message naming the running job.
  - The job loads its own detector with `make_detector`, so the preview and the job never share a model object: YOLO predictors are not thread-safe. Two model instances fit easily in GPU memory; on CPU, the preview slows the job down while both run.
  - The pipeline never calls `st.*` (it already must not import Streamlit). Its progress and stop callbacks are the only link to the GUI.
- **Memory.** The export path never uses `st.cache_data` on video bytes and never keeps all frames in memory. For each frame it processes, saves, buffers the rows and moves on.
- **Failures.**
  - A failed location or time source never stops a video. The columns are left blank, and the reason is shown in the UI and written to `videos.csv` under `warnings`.
  - If `grade()` raises `ValueError` on the first frame, the camera settings are wrong: stop the run and show the message.
  - If a later frame fails, leave its PCI blank and add a warning.
- **Missing values.** Never write 0,0 coordinates or placeholder dates. A missing value is an empty cell.

## 6. Output layout

### 6.1 Folders and names

```
Output/
└── 20261106-193012_benguela/            run folder: YYYYMMDD-HHMMSS[_label]
    ├── run.json
    ├── run.log
    ├── progress.json                                       background job state (§5.7)
    ├── parts/3f9a0c1d2b4e5f60/                             one folder per video_id (§6.3)
    │   ├── frames.csv
    │   ├── detections.csv
    │   └── video.json                                      its videos.csv row, status included
    ├── videos.csv
    ├── frames.csv
    ├── detections.csv
    ├── tracks/2025_0315_105644_0012F.gpx                  (S5)
    └── frames/2025_0315_105644_0012F/
        └── 2025_0315_105644_0012F_00012_00011500ms.jpg
```

- **Frame image name:** `{video_stem}_{frame_index:05d}_{round(t_s*1000):08d}ms.jpg`. `frame_index` starts at 1 and follows sampling order. Raw copies add `_raw` before `.jpg`.
- **Paths in the CSVs** are relative to the run folder and use forward slashes.
- **`run.log`** is the Python `logging` output for the run: warnings, errors and per-video timings.
- **`video_id`** is the first 16 hex characters of `sha1(str(size) + first 1 MiB + last 1 MiB)`. It stays the same when a file is renamed or copied. It is the key for joining and de-duplicating across runs.

### 6.2 Annotated image

- Draw the boxes in the existing class colours, with the searched region outlined, as `draw()` does today.
- For saved frames, call `draw()` with a new keyword-only `labels=True`. This adds a small tag above each box, for example `pothole 0.73`. The preview keeps `labels=False`.
- The footer is a dark band added under the image. It uses `ImageFont.load_default(size=…)`, scaled to the image width, and has three lines (parts that are missing are left out):

```
PCI 48.6 · Poor · 3 detections: pothole 1, alligator crack 2
2025-03-15 10:56:55 (UTC+01:00) · -12.032725, 13.955326 · 84 km/h
2025_0315_105644_0012F.MP4 · 00:00:11.500 · frame 12
```

### 6.3 Atomic per-video writes and resume

**Writing.** The part files are the source of truth; the top-level CSVs are built from them. On Windows, Excel locks a CSV while it is open, so appending to a file the user is looking at would otherwise fail the run.

1. Buffer the rows for one video in memory. They are small.
2. When the video finishes, write `parts/<video_id>/frames.csv` and `detections.csv`, each to a temporary name first and then renamed with `os.replace`.
3. **Only then** write `parts/<video_id>/video.json`, with `status=done`, the same way.
4. Append the video's rows to the top-level `frames.csv`, `detections.csv` and `videos.csv`. If a file is locked (`PermissionError`), skip it, mark it stale in `progress.json` and say so in the job panel; the run carries on.
5. At the end of the run, rebuild every stale top-level file from the parts. If one is still locked, write `detections (1).csv` (and so on) beside it and warn. A **Rebuild CSVs** button and the `merge` CLI rebuild them on demand.

**Resuming.**

1. A video is done when `parts/<video_id>/video.json` says `done`. Skip it.
2. Delete part folders that have no `video.json`: they are left over from a crash or a Stop.
3. Rebuild the top-level CSVs from the parts.

**`run.json`** is written at the start, with `"finished": null`, and updated at the end. It holds:

- the run's `run_id`, label, created and finished UTC times, and input paths;
- the git commit, read from `.git/HEAD` and the refs or packed-refs, **without a subprocess**;
- the Python version, platform and device (cuda, mps or cpu);
- the weights file;
- the full `ExportSettings` (§9.2);
- totals.

The CLI accepts `--settings run.json`, so a run set up in the GUI can be repeated without the GUI.

## 7. CSV specification

### 7.1 Formats

| | Standard (default) | Excel PT/EU |
|---|---|---|
| Delimiter | `,` | `;` |
| Decimal separator (numeric columns only) | `.` | `,` |
| Encoding | UTF-8, no BOM | UTF-8 with BOM (`utf-8-sig`) |
| Line ending | `\n` | `\r\n` |
| Quoting | `csv.QUOTE_MINIMAL` | same |

Missing values are empty cells. Booleans are `1` or `0`.

**Date and time formats.** These columns are strings, so they keep `.` and `:` in both formats.

| Column | Format |
|---|---|
| `date_local` | `YYYY-MM-DD` |
| `time_local` | `HH:MM:SS.mmm` |
| `video_time_hms` | `HH:MM:SS.mmm` |
| `datetime_utc` | `YYYY-MM-DDTHH:MM:SS.mmmZ` |
| `utc_offset` | `+01:00` |

**Precision.**

| Values | Decimal places |
|---|---|
| lat, lon | 7 |
| times in seconds | 3 |
| speed, heading | 1 |
| PCI, max CDV, area | 1 |
| confidence, quantity | 3 |

The column order is part of the contract. Define it once in `smartroad/export/csv_out.py`, as `DETECTION_COLUMNS`, `FRAME_COLUMNS` and `VIDEO_COLUMNS`, and test it.

### 7.2 `detections.csv`: one row per detected feature (the main output)

| # | Column | Example | Meaning |
|---|---|---|---|
| 1 | run_id | `20261106-193012_benguela` | |
| 2 | video_id | `3f9a0c1d2b4e5f60` | §6.1 |
| 3 | video_file | `2025_0315_105644_0012F.MP4` | File name only. |
| 4 | video_relpath | `Movie/2025_0315_105644_0012F.MP4` | Relative to the batch folder. For a single video, the file name. |
| 5 | camera | `F` | `F`, `R` or `I` from the file name. Blank if unknown. |
| 6 | frame_index | `12` | Starts at 1. |
| 7 | frame_number | `345` | Frame position in the file, starting at 0. Exact even in timelapse, where one video second holds 30 frames. |
| 8 | video_time_s | `11.500` | **Time into the video file.** |
| 9 | video_time_hms | `00:00:11.500` | |
| 10 | elapsed_s | `11.500` | **Driving time** since the file started. It equals `video_time_s` for normal video, and is `video_time_s × speed-up` for timelapse (§8.8). All clock and position logic uses this. |
| 11 | date_local | `2025-03-15` | **Recording date**, in camera local time. |
| 12 | time_local | `10:56:55.500` | |
| 13 | datetime_utc | `2025-03-15T09:56:55.500Z` | |
| 14 | utc_offset | `+01:00` | |
| 15 | time_source | `embedded` | `embedded`, `overlay` (fitted stamp clock), `overlay-frame` (this frame's own stamp, §8.4), `filename`, `container`, `manual` or `none`. |
| 16 | lat | `-12.0327250` | WGS84, decimal degrees. |
| 17 | lon | `13.9553260` | |
| 18 | gps_source | `embedded` | `embedded`, `gpx`, `overlay` or `none`. |
| 19 | gps_quality | `interpolated` | `interpolated`, `clamped`, `stamp-frame`, `gap` or `missing` (§8.6). |
| 20 | speed_kmh | `84.0` | From the source if it gives one, otherwise derived from the track. |
| 21 | heading_deg | `0.0` | From the source if it gives one, otherwise the bearing between fixes. |
| 22 | feature_class | `pothole` | Detector class name. Use this to filter. |
| 23 | feature_label | `Pothole` | The `PRETTY` label. |
| 24 | astm_distress | `potholes` | From `CLASS_TO_DISTRESS`. Blank for `marking_manhole`. |
| 25 | astm_number | `13` | From `smartroad.pci.astm.number_of`. Blank if there is none. |
| 26 | graded | `1` | 1 if the feature counted towards the frame's PCI: its class is mapped **and** it lies inside the measurable band. |
| 27 | confidence | `0.734` | |
| 28–31 | bbox_x1, bbox_y1, bbox_x2, bbox_y2 | `512,603,688,690` | Whole pixels in the **graded** image. |
| 32–33 | image_w, image_h | `1280,800` | Size of the graded image. |
| 34 | on_seam | `0` | From tiled inference. |
| 35 | quantity | `1.000` | S4. m², m or equivalent pothole count, computed per box the way `quantify()` does. |
| 36 | quantity_unit | `count` | `m2`, `m` or `count`. |
| 37 | severity_assumed | `medium` | The severity set in the sidebar. The model doesn't predict severity. |
| 38 | frame_pci | `48.6` | PCI of the frame the feature is in. |
| 39 | frame_rating | `Poor` | |
| 40 | image_file | `frames/2025_0315_105644_0012F/2025_0315_105644_0012F_00012_00011500ms.jpg` | Blank if the frame was not saved. |
| 41 | map_url | `https://www.google.com/maps/search/?api=1&query=-12.0327250,13.9553260` | A link to the position, for finding a grading on a map. Blank when lat/lon are blank. The decimals always use `.`, in both CSV formats. |

### 7.3 `frames.csv`: one row per graded frame, including frames with no detections

Columns 1–21 are the same as in `detections.csv`. They are followed by:

- `pci`, `rating`, `max_cdv`, `inspected_area_m2`, `severity_assumed`, `n_detections`, `n_graded`;
- one count per class, in the order of `smartroad.data.build_yolo.CLASSES`:
  - `n_longitudinal_transverse_crack`
  - `n_alligator_crack`
  - `n_block_crack`
  - `n_patching`
  - `n_pothole`
  - `n_weathering_raveling`
  - `n_lane_shoulder_drop_off`
  - `n_marking_manhole`
- `image_file`;
- `stamp_text`. This column is always present, and empty unless *Include raw stamp text* is on;
- `map_url`, as in `detections.csv`.

At startup, check that the model's `names[0..7]` match `CLASSES`, and warn if they don't.

### 7.4 `videos.csv`: one row per video

`run_id, video_id, video_file, video_relpath, camera, source_profile, profile_source, reencoded, camera_height_m, focal_35mm, horizon, hood_cutoff, status, error, warnings, duration_s, fps, width, height, recording_mode, speedup, capture_fps, mode_source, driving_duration_s, frames_graded, detections, mean_pci, min_pci, min_pci_time_s, start_utc, end_utc, start_local, utc_offset_start, utc_offset_end, time_source, clock_events, date_order, gps_source, gps_backend, gps_fixes, gps_coverage_pct, processing_s, frames_per_min`

| Column | Values |
|---|---|
| `status` | `done`, `failed` or `skipped` |
| `source_profile` | The profile key, `viofo` or `garmin` (§8.9) |
| `profile_source` | `detected`, `declared` or `fallback`. A declared profile that detection contradicts, or a fallback, also writes a warning. |
| `reencoded` | 1 if the file was treated as downloaded or re-encoded (§8.10), else 0 |
| `camera_height_m`, `focal_35mm`, `horizon`, `hood_cutoff` | The camera geometry actually used to grade this video: the sidebar values or the profile preset |
| `gps_backend` | `builtin`, `exiftool`, `gpx`, `ocr-tesseract`, `ocr-rapidocr`, or empty |
| `gps_coverage_pct` | % of graded frames that have lat/lon |
| `recording_mode` | `normal` or `timelapse` (§8.8) |
| `speedup` | Driving seconds per video second: 1 for normal video, 30 for a 1 fps timelapse played at 30 fps |
| `capture_fps` | Frames captured per second of driving: the file's fps for normal video, the timelapse rate (1, 2, 3, 5, 10) otherwise |
| `mode_source` | `declared`, `stamp`, `gps`, `filenames` or `assumed`. A declared mode that the evidence contradicts also writes a warning. |
| `driving_duration_s` | `duration_s × speedup` |
| `utc_offset_start`, `utc_offset_end` | The camera's offset at the first and last graded frame, for example `+01:00`. The next video in a batch starts from `utc_offset_end` (§8.7). |
| `time_source` | The source used by most rows. Rows can differ, for example `overlay-frame` where the fit didn't cover them. |
| `clock_events` | Separated by `; `, for example `time zone +01:00→+02:00 at 1409.5 s; clock corrected +37.0 s at 12.5 s; per-frame stamp for 14 frames` |
| `date_order` | `DMY`, `MDY` or `YMD`, and how it was decided (`DMY (from a day > 12)`, `MDY (matches file name)`, `DMY (default)`) |
| `warnings` | Separated by `; `. For example: two clocks more than 5 s apart, or an OCR parse rate below 80 %. |

### 7.5 Example (Standard format, illustrative values)

```
run_id,video_id,video_file,video_relpath,camera,frame_index,frame_number,video_time_s,video_time_hms,elapsed_s,date_local,time_local,datetime_utc,utc_offset,time_source,lat,lon,gps_source,gps_quality,speed_kmh,heading_deg,feature_class,feature_label,astm_distress,astm_number,graded,confidence,bbox_x1,bbox_y1,bbox_x2,bbox_y2,image_w,image_h,on_seam,quantity,quantity_unit,severity_assumed,frame_pci,frame_rating,image_file,map_url
20261106-193012_benguela,3f9a0c1d2b4e5f60,2025_0315_105644_0012F.MP4,2025_0315_105644_0012F.MP4,F,12,345,11.500,00:00:11.500,11.500,2025-03-15,10:56:55.500,2025-03-15T09:56:55.500Z,+01:00,embedded,-12.0327250,13.9553260,embedded,interpolated,84.0,0.0,pothole,Pothole,potholes,13,1,0.734,512,603,688,690,1280,800,0,1.000,count,medium,48.6,Poor,frames/2025_0315_105644_0012F/2025_0315_105644_0012F_00012_00011500ms.jpg,"https://www.google.com/maps/search/?api=1&query=-12.0327250,13.9553260"
```

In Excel PT/EU format the same row uses `;` as the delimiter and decimal commas in numeric columns: `11,500`, `-12,0327250`, `48,6`. The example is a normal 30 fps video, so `frame_number` 345 sits at 11.5 s and `elapsed_s` equals `video_time_s`. String columns such as `00:00:11.500` and `10:56:55.500` don't change. The `map_url` cell is quoted in Standard format because it contains a comma.

## 8. Location & time

### 8.1 Model

- **Times.** Internally, every time is a timezone-aware UTC `datetime`.
  - Camera local time = UTC + `utc_offset_h`. The offset is fixed within each clock segment, and can change between segments when the camera changes zone (§8.7).
  - Offsets are measured from the footage, carried over, or taken from the setting. They are never looked up in a zone database, so there is no daylight-saving logic and `tzdata` is not needed.
- **Per frame.** Each graded frame gets one `GeoSample` with: `utc`, `local`, `lat`, `lon`, `speed_kmh`, `heading_deg`, `gps_source`, `gps_quality` and `time_source` (§9.2).
- **Per video.** `build_geo_context(...)` runs once per video and returns a `GeoContext`. Its `at(t_s)` method gives the `GeoSample` for any time in the video.
- **Positions** always come from `smartroad.survey.frames.Track`. Add two methods; existing behaviour doesn't change:
  - `Track.from_fixes(fixes)` builds `TrackPoint`s with chainage, using the same `MIN_STEP_M` rule;
  - `Track.gap_s(when)` returns the number of seconds to the nearest fix.

### 8.2 Embedded GPS (Novatek dashcams such as the A129 Plus)

**Facts**

- The A129 Plus uses a Novatek NT96670 chip.
- Novatek MP4 files have a **`gps ` box directly inside `moov`**. Its payload is:
  - 4 unused bytes;
  - a big-endian u32 count `n`;
  - `n` pairs of big-endian u32 values: absolute offset and size.
- Each pair points to a `free` box whose bytes 4–12 read `freeGPS `. There is one block per second of video, **also in timelapse files**. In a 1 fps timelapse, that is one fix per 30 frames (§8.8).
- The block format varies between models and firmware versions. ExifTool decodes more than 40 of them. A dashcamtalk.com user reports that ExifTool produces a GPX file from A129 Plus videos, while Sergei's older `nvtk_mp42gpx.py` script no longer does.

**Built-in decoder** (`smartroad/survey/novatek.py`, MUST). Layout in Appendix A.3, checked against ExifTool.

1. Read the `gps ` table. Search all of `moov`'s children for it, because its position among them varies.
2. In each block, find the marker `[AV][NS][EW]\0` at offset 36 or later.
   - Read 6 little-endian u32 values starting 24 bytes before the marker: hour, minute, second, year (add 2000 if below 100), month, day.
   - Read 4 little-endian float32 values after the marker: latitude (DDMM.MMMM), longitude (DDDMM.MMMM), speed (knots), track (degrees).
   - `A` means a valid fix and `V` means no fix.

   Because it searches for the marker, this works for the VIOFO A119 V3 layout (marker at offset 40) and the older Novatek layout (marker at offset 72).
3. Validate each block:
   - the date and time fields are in range;
   - lat and lon are in range and not 0,0;
   - consecutive valid fixes imply 300 km/h or less.

   If more than 20 % of the blocks that are not void fail, treat the layout as **unsupported for this file**. In Auto mode, fall back to ExifTool.
4. Align the fixes with the video. Block *i* covers video seconds [i, i+1). VIOFO writes one block per second of **video** in both normal and timelapse mode (§8.8).
   - Fit `fix_utc_i = utc0 + i × s` robustly, using the median of pairwise slopes (A.8).
   - `s` is the number of driving seconds per video second: 1 for normal video, the speed-up for timelapse. The same fit therefore detects timelapse (§8.8).
   - `video_start_utc = utc0`.
   - Frame UTC = `video_start_utc + elapsed_s + fine_offset`.

**ExifTool backend** (`smartroad/survey/exiftool_gps.py`, MUST)

- **Command.** Run `[exe, "-ee3", "-n", "-j", "-G3", "-a", "-api", "LargeFileSupport=1", "-GPSDateTime", "-GPSLatitude", "-GPSLongitude", "-GPSSpeed", "-GPSTrack", "-SampleTime", path]`:
  - as a list, with no shell;
  - with a 120 s timeout;
  - on Windows, with `creationflags=subprocess.CREATE_NO_WINDOW`.
- **Output.** Parse the keys `Doc<N>:<Tag>` (Appendix A.4). `GPSSpeed` is already in km/h.
- **Placing fixes on the video timeline.**
  - **With `SampleTime`** (timed metadata tracks, such as Garmin): place each fix at video time `t = SampleTime`. Its driving time is `t × speed-up` (§8.8). This is exact, so the void-block heuristic below is not needed.
  - **Without `SampleTime`** (Novatek `freeGPS`): ExifTool **drops void blocks**, so `DocN` is not the block index.
    - If the built-in reader found the table (`n` blocks) and ExifTool returned `m ≤ n` fixes, assume the `n − m` missing blocks come first: the camera had no fix yet after power-on. Fix *k* (counting from 1) is then block `n − m + k − 1`.
    - If there is no table, take the video clock from §8.5 and place the fixes by their UTC time.
- **Is `GPSDateTime` a real clock?**
  - For Novatek `freeGPS`, `GPSDateTime` is the receiver's own UTC.
  - Garmin dashcam telemetry has no GPS time. ExifTool computes `GPSDateTime` as the container `CreateDate` + `SampleTime`, and warns "Approximating GPSDateTime".
  - Rule: if `GPSDateTime − SampleTime` is the same for every fix (within 1 s) and equals `video_start_time()`, then `GPSDateTime` is **not** a clock. Use the positions, and take the clock from §8.5 (stamp, file name or container). Record `embedded GPSDateTime is approximated (container clock)` in `clock_events`.
- **macOS.** Don't call ExifTool from inside the Streamlit process; that is the fork-after-Metal crash described in `video.py`. Use the built-in decoder there. The CLI can still use ExifTool.

### 8.3 External GPX

- **`read_gpx` must not depend on the namespace.** It must accept:
  - GPX 1.1, with the current behaviour, so the existing tests are unchanged;
  - GPX 1.0 (`http://www.topografix.com/GPX/1/0`), which is what ExifTool's `gpx.fmt` writes;
  - files with no namespace.
- **Add `read_gpx_many(paths)`.** It joins the points from all files, sorts them by time, drops exact duplicates and recomputes chainage. In batch mode, one GPX file can cover a whole day of driving.
- **Clock.** A GPX file gives positions against UTC, but not the video's start time, so resolve the video clock with §8.5.
  - In Auto mode, try the stamp, then the file name, then the container clock.
  - If none works, the error tells the user to set Manual start.
  - Then look up positions with `Track.at(video_start_utc + t_s)`.
- **Overlap check.** Keep the check from `locate_frames` and its message ("do not overlap … Pass offset_s").

### 8.4 On-screen stamp (OCR)

**Crop.** Read the stamp from the **full-resolution** frame, before it is resized to 1280. `iter_samples` (§9.1) provides the crop.

**Preprocessing for Tesseract**

1. Convert to grayscale.
2. Resize so the crop is 128 px tall (`INTER_CUBIC`).
3. Apply an Otsu threshold.
4. Invert, so the text is dark on white.
5. Add a 20 px white border.

Then call Tesseract **directly**, as an argument list (A.2):

- pass `--psm 7`;
- pass the whitelist as one argument, `tessedit_char_whitelist=<chars>`. It must include the space and `° ' "`, because Garmin-style coordinates need those symbols. Without them, Tesseract drops the degree sign: `N47°36.123'` becomes `N4736.123`, which can't be parsed;
- read the output as UTF-8, not the Windows code page.

Don't use `pytesseract`. On Windows it splits its `config` string with `shlex.split(..., posix=False)`, which keeps quote characters inside the arguments. The quoted whitelist from version 1.0 would reach Tesseract as an option name starting with `"`, and be ignored.

**Engines**

| Engine | Notes |
|---|---|
| Tesseract | `tesseract` called with `subprocess.run([...])` on a temporary PNG. The default when it is installed. It runs as a subprocess, so the macOS caveat for ExifTool applies too. On Windows, pass `creationflags=CREATE_NO_WINDOW`. |
| RapidOCR | `rapidocr_onnxruntime`, in-process, installed with pip only. Give it the colour crop at 2× with **no padding**: in testing it returned nothing when the crop was padded or contained flat masked blocks. |

Auto picks Tesseract if it is installed, and RapidOCR otherwise.

**Parsing.** Use the parser in A.1. It reads:

- **Speed** in KM/H or MPH.
- **Coordinates** in three formats, tried in this order:
  1. degrees-minutes-seconds, `hddd°mm'ss.s"`;
  2. Garmin's default, degrees and decimal minutes, `hddd°mm.mmm'`;
  3. decimal degrees, with the hemisphere first (VIOFO, `S12.035136`) or last (`37.7749° N`);
  4. signed decimal degrees with no hemisphere letter (Garmin, `-26.36774 27.31358`), **only** when the video's profile sets `signed_dd` (§8.9). With the profile's `coord_decimals`, digits that run together (`-26.3677427.31358`) are split by the decimal count.

  The parser tolerates common OCR misreads of the symbols: `°` read as `o`, `º`, `*` or a space, and `'` read as `°`, `*` or `′`.

  If the hemisphere letter or the degree sign was lost, the parser returns **no** coordinate. It never guesses the sign, or where degrees end and minutes begin. The signed format is the exception: a lost minus sign can't be seen in one reading, so the sign vote under **Positions** catches it.
- **Speed** is read last, from the text left after the date/time and the coordinates are taken out, so digits that run into the unit (`27.3135870KM/H`) can't be read as the speed. Values above 300 km/h are rejected.
- **Dates** `YYYY-MM-DD`, `DD-MM-YYYY` and `MM-DD-YYYY`:
  - with `-`, `/` or `.` as the separator;
  - unpadded days and months allowed;
  - years from 2010 to next year.
- **Times** on a 24-hour or 12-hour clock: `AM`/`PM`, `a.m.`/`p.m.`, single-digit hours, and a stray space next to `:`.

Never rely on spaces in the OCR text: RapidOCR drops them, and so does Tesseract when the whitelist leaves out the space.

**Date order (Auto).** A date such as `03/04/2025` is ambiguous. For each video, decide the order as follows:

1. If any reading in the video has a day above 12, that settles it. If readings disagree, use the majority and warn.
2. Otherwise, try both orders against an independent date: first the embedded GPS date (±1 day, because of the UTC offset), then the file-name date, then the container date. Use the order that matches.
3. Otherwise, use the order decided for the previous video in the batch (same camera).
4. Otherwise, use DMY and warn.

Record the result in `videos.csv` `date_order`. Choosing `DMY` or `MDY` in the settings skips detection.

**Pre-pass.** Read the stamp every `read_every_s` seconds **of driving** (default 1.0) at t = 0.5, 1.5, … across the whole video. This is what *Check location & time* runs.

In timelapse there is no separate pre-pass. Each frame carries its own stamp, so the readings are taken from the graded frames themselves, during the main loop (§8.8). *Check location & time* then reads up to 60 frames spread evenly across the file.

**Driving time.** Throughout this section, `t` means driving time (`elapsed_s`, §8.8), not video time. For normal video the two are the same.

**Clock fit, in segments.** A camera's clock can jump inside a video, for two reasons: a time zone change (§8.7), or a correction when GPS syncs the clock after power-on. So the fit looks for segments where the offset is constant, instead of one offset per video. The reference implementation is in A.7.

1. For each reading with a valid date and time, compute `offset_i = local_i − t_i`.
2. **Clock levels.** Sort the offsets and split them wherever neighbouring values differ by more than 1.5 s. A group with at least 3 readings is a *level*. Readings that belong to no level are OCR errors; drop them.
3. **Segments.** Walk the readings in time order, grouping consecutive readings on the same level.
   - A run of fewer than 3 readings is treated as outliers.
   - Runs of the same level on either side of those outliers join into one segment.
4. **Segment clock.** For each segment, `base = median(offset) + 0.5 s`. The 0.5 s compensates for the stamp showing whole seconds.
   - The boundary between two segments is halfway between the last reading of one and the first reading of the next.
   - The first and last segments extend 10 s beyond their outermost readings.
5. **Classify each step** `Δ = base_next − base_prev`, in this order:
   - **Cut** (an edited video, §8.10): the stamp positions jump between the two segments by more than max(200 m, 50 m/s × the time between them). Each segment keeps its own clock: nothing is re-based, the zone carries over, and UTC jumps with the footage.
   - **Time zone change:** Δ is within 90 s of a non-zero multiple of 15 min. Both segments keep their own clock, and the zone offset changes by that multiple (§8.7).
   - **Clock correction:** anything else, when the positions show the vehicle didn't jump, or when there are no positions and the step comes within the first 120 s of driving (GPS syncs the clock soon after power-on). The later clock is trusted, because it is GPS-synced. The earlier segment is re-based onto it.
   - **Cut**, otherwise: a late step with no positions to judge it.

   Positions on each side are the median of the 3 nearest readings that have them, so one OCR error can't fake a cut. Steps more than 30 s apart in driving time are judged by the time rule alone.
6. **Fit failure.** The fit fails when there is no segment, meaning fewer than 3 consistent readings. Frames outside every segment's span are *not covered*.

**Per-frame stamp fallback.** This is on by default (§5.4). It applies to every frame when the fit fails, and to frames the fit doesn't cover. For each such frame:

1. OCR the frame's own stamp crop. `iter_samples` already provides it.
2. Set `local = stamp time + 0.5 s`.
3. Accept the reading only if one of the 3 nearest other stamp readings on either side agrees with it. These can come from the pre-pass or from other frames. "Agrees" means the difference in stamp time equals the difference in driving time within 2 s, or differs by a zone-sized step.
4. If accepted, the row gets `time_source=overlay-frame`. Its zone offset is the nearest segment's, or the start offset if there is no segment (§8.7).
5. If rejected, the frame falls through to the next clock in the Auto chain (§8.5). If there is none, the date and time stay blank.

Record `per-frame stamp for N frames` in `clock_events`. Accepted readings need their neighbours, so apply this step after the video's main loop, while the rows are still buffered (§6.3).

**Positions**

1. Drop readings that have no coordinates.
2. **Sign vote** (signed format only): drop readings whose latitude or longitude sign disagrees with the majority of the video's readings, unless the value is within 0.5° of zero (a real crossing of the equator or the prime meridian). A run of readings with a lost minus sign would otherwise survive the next step.
3. Drop any reading that is more than max(50 m, 2 s × speed) from the median of the two readings on each side of it (a Hampel filter).
4. Build the stamp track **on driving time**, not on UTC: a fixed internal epoch plus `t_i`. Positions then don't depend on whether the clock fit succeeded.
5. If the track can't place a frame (`gap` or `missing`) but the frame's own stamp has a coordinate, use it and mark the row `gps_quality=stamp-frame`. The check: the coordinate must be within max(50 m, 2 s × speed) of the nearest track reading, unless there is no track at all.

**Accuracy.** Show this in the UI: the stamp updates once a second, so timing is ±1 s, about ±25 m at 90 km/h. Prefer Embedded GPS when the file has it.

**Measured results**, on the 2560×1600 VIOFO frame (crop = bottom 72 rows) and on rendered Garmin-style stamps:

- **VIOFO stamp.** Tesseract 5.3.4 and RapidOCR both parsed it exactly at full resolution, at 1280×800, and after JPEG quality 50. This used the 1.1 whitelist and parser.
- **Speed.** Each crop took about 120–190 ms on 2 CPU cores.
- **Low resolution.** At 960×600, Tesseract misread the year as `7075`. The year check rejects it.
- **Garmin-style stamps.** Lines such as `N47°36.123' W122°19.456' 35 MPH 10/25/2025 04:23:15 PM` parse correctly with both engines once `° ' "` are whitelisted. Without those symbols, Tesseract dropped the degree signs and the coordinates couldn't be read.
- These stamps were drawn in DejaVu Sans Mono, not a real Garmin font, so Phase 0 must confirm the result on real Garmin footage.
- **Real stamps (1.4).** On the two screenshots supplied on 2026-11-07, Tesseract 5.3.4 and RapidOCR 1.2.3 read both stamps exactly (DASHCAM_NOTES.md):
  - the Garmin stamp (1920×1080, white text without a band) at 1920×1080, 1280×720, 854×480 and 640×360;
  - the VIOFO stamp (screenshot at 2000×1250) at 2000×1250 and 1280×800. At 960×600, Tesseract read the year as 2075, which the year check rejects; RapidOCR still read it exactly;
  - 44–363 ms per crop. The slowest call was RapidOCR's first, which loads its model.

### 8.5 Clock: where the date and time come from

| Date & time source | How `video_start_utc` is found | `time_source` |
|---|---|---|
| Embedded GPS clock | §8.2 alignment | `embedded` |
| On-screen stamp | The §8.4 segment clock. Frames it doesn't cover use the per-frame stamp fallback. Then local → UTC with each segment's zone (§8.7). | `overlay` or `overlay-frame` |
| File name | The VIOFO file-name regex (A.5) gives the local start time, then local → UTC | `filename` |
| Container (mvhd) | `video_start_time()`. If *Container clock is local time* is on (by default, the profile's value, §8.9), treat the value as local, then local → UTC | `container` |
| Manual | The date and time typed by the user (local), then local → UTC | `manual` |
| **Auto** | Depends on the GPS source; see below | whichever was used |

**Auto**, by GPS source:

| GPS source | Clock used |
|---|---|
| Embedded | The embedded GPS clock, if it is a real GPS clock (§8.2). Otherwise as for GPX. |
| Stamp | The stamp: the segment clock, then the per-frame fallback. Then the file name, then the container. |
| GPX | The stamp, if an OCR engine is available: the segment clock, then the per-frame fallback. Otherwise the file name, then the container. GPX positions are looked up at each frame's own UTC, so a per-frame clock works too. |
| None | The embedded GPS clock if a `gps ` table exists. Otherwise the file name, then the container. |

- The fallback runs frame by frame: a frame takes the first clock in its chain that gives it a time.
- The fine time offset is added last.
- If no clock can be found, the date and time columns are left blank and `time_source` is `none`. The `video_time_*` columns are always filled.
- When two clocks are available, compare them. If they differ by more than 5 s, add a warning, because the UTC offset is usually wrong.
- For a downloaded or re-encoded file (§8.10), skip the file-name and container clocks and the embedded GPS: they describe the download, not the drive. The stamp is the only clock.

### 8.6 Interpolation and quality

| gps_quality | When | lat/lon |
|---|---|---|
| `interpolated` | Between two fixes, and the gap is no larger than the max gap | Filled |
| `clamped` | Outside the track but within `EDGE_TOLERANCE_S`, where `Track` clamps | Filled |
| `stamp-frame` | The track couldn't place the frame, but the frame's own stamp gave a coordinate that passed the check in §8.4 | Filled |
| `gap` | The nearest fix is further away than the max gap | Blank |
| `missing` | There is no source or no clock, or `Track.at` raised an error | Blank |

**Speed and heading**

- `speed_kmh` comes from the source (embedded or stamp) when it gives one. Otherwise it comes from `Track` (m/s × 3.6).
- `heading_deg` comes from the source when it gives one. Otherwise it is the initial bearing between the fixes on either side of the frame:
  `atan2(sin Δλ·cos φ2, cos φ1·sin φ2 − sin φ1·cos φ2·cos Δλ)`, normalised to 0–360.

### 8.7 Time zone changes and clock corrections inside a video

**Decision: UTC is the only continuous timeline. Local time shows what the camera showed, with the offset recorded on every row.**

1. **`datetime_utc` never jumps** when the camera changes zone. Ordering, durations, and joins with GPX or other surveys all use UTC.
2. **Local columns follow the camera.** `date_local` and `time_local` show the camera's clock as it was displayed, and each row has its own `utc_offset`. A zone change appears as `utc_offset` changing between two rows: `time_local` jumps, `datetime_utc` does not. With *Local time columns = Fixed UTC offset*, every row uses that one offset, for a report in a single zone.
3. **Detecting a change** needs the stamp (§8.4). A step in the stamp clock that persists for at least 3 readings is:
   - a **time zone change** if it is a non-zero multiple of 15 min, within 90 s. This covers daylight saving (±1 h), whole-hour zones, and 30- and 45-minute zones;
   - otherwise a **clock correction**. The later clock wins and earlier frames are re-based, because cameras set their clock from GPS after power-on.
4. **The first segment's zone** (the start offset) is taken from the first of these that is available:
   1. **Measured**, if the same video has a real GPS clock (Novatek embedded GPS). The offset is stamp local time − GPS UTC, rounded to 15 min, for each segment. A zone change is then measured directly. If the result disagrees with the setting, warn, for example "camera zone looks like +02:00; settings say +01:00".
   2. **Carried over** in a batch, from the previous video's `utc_offset_end`, if that video ended less than 12 h before this one started. The batch runs in chronological order (§5.6). On resume, read it from `videos.csv`.
   3. **The setting** *Camera clock UTC offset at start*.

   Each later segment adds its zone step to the previous segment's offset.
5. **Without the stamp**, a change inside a video can't be seen. This applies to the file-name, container and manual clocks, and to embedded positions without a real clock. The offset is then constant for the whole video, taken from 4.2 or 4.3. This is a stated limitation.
6. **Reporting.** Every step goes into `clock_events`. The Check panel lists the segments, for example `10:56:44–11:20:13 UTC+01:00 · 12:20:14–12:59:59 UTC+02:00 (zone change at 1409.5 s)`.
7. **Ambiguity.** A clock correction of exactly one hour looks like a zone change.
   - With a real GPS clock (4.1), the offset is measured, so there is no ambiguity.
   - Without one, treat the step as a zone change and flag it in `clock_events` as "zone change or 1-hour clock error".
8. **Cuts in edited videos** (§8.10). At a cut, UTC jumps with the footage, which is correct: the clips were recorded at different times. Nothing is re-based across a cut, and a cut that happens to be a whole number of 15 minutes is still a cut when the position jumps. `clock_events` records `cut at t=… s: clock +… s, moved … m`.

**Why this design**

- **Joining and sorting.** UTC must be continuous for the data to be joined and sorted. A jump in local time is a display matter, and the per-row offset keeps it without losing information.
- **Matching the saved frames.** The local columns match the stamp that is visible in the saved frames, so the CSV and the pictures agree.
- **Which cases occur.**
  - The VIOFO in Angola doesn't trigger zone changes: West Africa Time has no daylight saving, and VIOFO cameras use a fixed offset that you set yourself. The case that will occur there is the clock correction after a cold start, and it uses the same mechanism.
  - Zone changes matter for cameras that set their zone from GPS position, as Garmin devices can, and for footage from countries with daylight saving.

### 8.8 Timelapse

**What is different.** A timelapse file plays back at a normal frame rate, but its frames were captured far apart in time. On the A129 Plus, timelapse captures at 1, 2, 3, 5 or 10 fps and plays back at 30 fps. At a 1 fps capture, one second of video is 30 seconds of driving.

The spec handles this with one number per video, the **speed-up** (driving seconds per video second), held in a `TimeBase` (A.8):

- **Driving time:** `elapsed_s = video_time_s × speedup = frame_number × capture_interval_s`, where `capture_interval_s = speedup / playback_fps`.
- **What uses it:** every clock, position, GPX and speed calculation uses `elapsed_s`. `video_time_s` is kept only to find the frame in the file.
- **Normal video** is simply `speedup = 1`. There is one code path, not two.

**Sampling.** Graded frames are chosen by driving time, as frame numbers:

- `step = max(1, round(1 / (rate × capture_interval_s)))`, taking frames `step//2, step//2 + step, …`.
- **Normal video:** this reproduces `frame_times()` exactly. At 1 per second on a 30 fps file it takes frames 15, 45, 75, … so existing behaviour doesn't change.
- **1 fps timelapse:** 1 per second of driving means every frame.
- **Decoding:** when the step is 15 frames or fewer, read the file sequentially instead of seeking: `grab()` every frame and `retrieve()` only the selected ones. This is faster at short steps and lands on the exact frame.

**Location sources in timelapse**

| Source | Status | Notes |
|---|---|---|
| On-screen stamp | **Preferred** | The camera stamps each frame when it captures it, so every frame carries its own time and position: one per second of driving at 1 fps. Read the stamp on every graded frame (§8.4). |
| Embedded GPS | **Sparse** | VIOFO stores one GPS packet per second of *video* in both modes, as reported on the Mapillary forum. In a 1 fps timelapse that is one fix per 30 frames, or one every 30 s of driving (about 500 m at 60 km/h). Use it for the clock and the speed-up, and for positions only when there is no stamp. Then warn: "timelapse: embedded GPS has one fix per 30 s of driving; positions are interpolated over ~N m; use the on-screen stamp for per-frame positions". |
| GPX | Works unchanged | Looked up at `video_start_utc + elapsed_s`. |

**Detecting the mode (Auto).** The first piece of evidence available wins:

1. **Stamp.** Read 3 clusters of 3 frames, each frame 1 video-second apart, starting at 10 %, 50 % and 90 % of the file. Take the slope of stamp time against video time inside each cluster (Theil–Sen, A.8) and the median across clusters, so a title card without a stamp, or a cut in an edited video, can't bias it. If the cluster slopes disagree by more than 5 %, warn. A file shorter than 30 s of video is read as one cluster of 9 frames spread across it. About 1 means normal; otherwise the slope is the speed-up.
2. **Embedded GPS.** The slope `s` from §8.2.
3. **File names in a batch.** For files recorded back to back in the same session, (start of the next file − start of this file) ÷ this file's duration ≈ speed-up. Use this only when there is no other evidence.
4. **No evidence.** Assume normal video, set `mode_source=assumed`, and warn.

Snap the measured speed-up to `playback_fps / r` for r ∈ {1, 2, 3, 5, 10, 15} fps when it is within 5 % (29.97 fps playback gives 29.97). Otherwise keep the measured value and warn.

The mode is decided **per video**, so one folder can mix files recorded while driving with parking-mode timelapse files.

**The user setting (Recording mode, §5.2).** Decision: it is an override, not a replacement for detection.

- **What it does.** Choosing `Normal` or `Timelapse` with a rate skips detection. It is the only way to get correct times for a file that has neither a stamp nor GPS.
- **Check a declared mode anyway.** The check reuses readings the pipeline takes anyway: the 9 stamp reads, or the GPS slope.
  - If the evidence contradicts the declared speed-up by more than 5 %, keep the declaration, because it is the user's choice.
  - Write a warning to `videos.csv` and show it in the Check panel.
  - A wrong speed-up makes every time, position and speed in the CSV wrong by the same factor, and the result still looks plausible. This check is what catches it.
- **Speed sanity check (every video).** Compare the reported speed (stamp or GPS) with the speed derived from positions over `elapsed_s`. If they differ by more than a factor of 2 on the median frame, warn: "time scale looks wrong".

**Why not make the user choose instead of detecting?**

- **Little code saved.** The time base (`elapsed_s`) is needed for timelapse however the mode is decided. Detection is one slope, computed from readings the pipeline takes anyway.
- **Real risk.** If a whole folder is declared timelapse but some files are normal, or the other way round, those files' times are silently off by a factor of 30.
- **Where the setting helps:** files with no stamp and no GPS, and making the assumption visible. Hence: Auto by default, the setting as an override, and a check that runs either way.

**What doesn't change.**

- Detection, grading, PCI, frame saving and the CSV formats work the same way.
- `video_time_s` and the frame file names still use the time within the file.
- Two new columns, `elapsed_s` and `frame_number`, give the driving time and the exact frame.

### 8.9 Source profiles

**Why.** Every rule above that depends on the camera make (the file-name format, whether mvhd holds local time, which embedded GPS reader works, whether embedded GPS time is a real clock, where the stamp is, the date order, the timelapse capture rates, the hood) lives in one place, a `SourceProfile`. The pipeline asks the video's profile instead of testing for a make. Two profiles ship now, VIOFO and Garmin. More makes are added later as more profiles.

**Interface** (`smartroad/survey/profiles.py`):

```python
@dataclass(frozen=True)
class CameraPreset:
    height_m: float = 1.70
    focal_35: float = 25.0
    horizon: float = 0.139
    sky_cutoff: float = 0.45            # the detector's top cut-off (the sidebar's Sky cut-off)
    hood_cutoff: float = 1.0
    calibrated: bool = False            # True only after a lens and mount calibration for this make


@dataclass(frozen=True)
class ContainerProbe:
    """What can be read without decoding video or starting a subprocess."""
    name: str                           # file name
    moov_children: tuple[str, ...]      # e.g. ("mvhd", "trak", "trak", "udta", "gps ")
    handlers: tuple[str, ...]           # track handler types, e.g. ("vide", "soun", "meta")
    strings: dict[str, str]             # make/model/encoder strings found in udta or meta, if any


@dataclass(frozen=True)
class SourceProfile:
    key: str                                        # stable id written to videos.csv: "viofo", "garmin"
    label: str                                      # shown in the sidebar
    detect: Callable[[ContainerProbe], str | None]  # evidence text if the file is this make, else None
    filename_patterns: tuple[re.Pattern, ...]       # names that carry a local start time (A.5)
    camera_letters: bool                            # names end in F/R/I, so "Front camera only" applies
    container_clock_local: bool                     # mvhd holds camera local time (§8.5)
    embedded_gps: str | None                        # key into GPS_READERS: "novatek", "exiftool", or None
    gpsdatetime_is_clock: bool                      # False when GPSDateTime is CreateDate + SampleTime (§8.2)
    stamp_roi: tuple[float, float, float, float] | None   # fractions of the frame; None = no stamp expected
    stamp_tokens: tuple[str, ...]                   # text that identifies the make on its stamp, e.g. ("GARMIN",)
    signed_dd: bool                                 # stamp shows signed decimal degrees with no hemisphere (A.1)
    coord_decimals: int | None                      # the stamp's fixed number of coordinate decimals, if any
    date_order: str                                 # "Auto", "DMY" or "MDY"
    capture_rates: tuple[int, ...]                  # timelapse capture rates to snap to (§8.8)
    camera: CameraPreset


@dataclass(frozen=True)
class ProfileMatch:
    profile: SourceProfile
    source: str                         # "detected" | "declared" | "fallback"
    evidence: str                       # e.g. "gps box in moov", "file name", "stamp: GARMIN"
    reencoded: bool                     # recognised from the stamp alone: downloaded or re-encoded (§8.10)
    warnings: tuple[str, ...]


PROFILES: dict[str, SourceProfile] = {}             # the registry, in registration order

def register(profile: SourceProfile) -> SourceProfile: ...
def probe_container(path: Path) -> ContainerProbe: ...      # in-process struct parsing, like video_start_time()
def resolve_profile(path: Path, *, declared: str = "auto", fallback: str = "viofo",
                    read_stamp: Callable[[tuple[float, float, float, float]], str | None] | None = None
                    ) -> ProfileMatch: ...      # read_stamp: OCR one frame at 50 % of the file in a region
```

`GPS_READERS` in `geo.py` maps a reader key to a function `(path, info, timebase) -> fixes`. `novatek` is the built-in decoder with ExifTool as its fallback (§8.2). `exiftool` is the ExifTool backend alone. The *Embedded GPS* backend setting (§5.4) overrides the profile's reader.

**The two profiles**

| Field | VIOFO | Garmin |
|---|---|---|
| `detect` evidence | A Novatek `gps ` box among `moov`'s children, or a file name matching `VIOFO_NAME` (A.5) | A `GRMN\d{4}` file name, or a Garmin make string in the container. Phase 0 records which atoms real Garmin files carry. |
| `stamp_tokens` | `("VIOFO",)` (the model name on the stamp, `VIOFO A129 Plus`) | `("GARMIN",)` (the stamp starts with `GARMIN`) |
| `filename_patterns` | `VIOFO_NAME` | None. `GRMN0007.MP4` carries no time. |
| `camera_letters` | Yes | No |
| `container_clock_local` | True. Phase 0 confirms it. | True until Phase 0 measures it. When a second clock exists, the 5 s comparison in §8.5 warns if this is wrong. |
| `embedded_gps` | `novatek` | `exiftool` (timed metadata track, placed by `SampleTime`) |
| `gpsdatetime_is_clock` | True (receiver UTC) | False (§8.2) |
| `stamp_roi` | `(0.0, 0.955, 1.0, 1.0)`. Measured: text at y 0.972–0.985, x 0.28–0.99. | `(0.0, 0.95, 0.62, 1.0)`. Measured: white text without a band at y 0.965–0.985, x 0.01–0.58, 23 px tall at 1080p. Other Garmin models may differ; the stamp region can be changed in the sidebar. |
| `signed_dd`, `coord_decimals` | False, None | True, 5 (`-26.36774 27.31358`) |
| Stamp layout (for reference) | `84 KM/H S12.035136 E13.955326 <custom text> VIOFO A129 Plus <plate> 15-03-2025 10:56:44` | `GARMIN 01/11/2020 07:17:05 -26.36774 27.31358 70 KM/H` |
| `date_order` | `Auto` (DMY on the sample frame) | `Auto`. The sample, `01/11/2020`, is ambiguous: 1 November or 11 January. |
| `capture_rates` | `(1, 2, 3, 5, 10)` | `(1, 2, 3, 5, 10, 15)` until Phase 0 measures Travelapse |
| `camera` | Height 1.70, focal 25 (the sidebar defaults, not measured); horizon 0.61, sky cut-off 0.58, hood cut-off 0.80, measured on the screenshot (road vanishes at y ≈ 0.61, bonnet from y ≈ 0.82); `calibrated=False` | Height 1.70, focal 25 (not measured); horizon 0.50, sky cut-off 0.47, hood cut-off 0.62, measured on the screenshot (road vanishes at y ≈ 0.50, bonnet from y ≈ 0.63, dashboard from y ≈ 0.72); `calibrated=False` |

**Rules**

- **Auto.** Call each registered profile's `detect` in registration order; the first match wins, and its evidence goes into the Check panel.
  - If no container evidence matches and an OCR engine is installed, read the stamp of one frame at 50 % of the file in each registered profile's `stamp_roi`. Normalise the text (upper case, spaces removed, `1`→`I`, `0`→`O`; RapidOCR reads `VIOFO` as `V1OFO`) and look for each profile's `stamp_tokens`. A match is `profile_source=detected` with evidence `stamp: GARMIN`, and sets `reencoded` (§8.10).
  - If neither matches, use the *If not recognised* profile, set `profile_source=fallback` and warn: `not recognised as VIOFO or Garmin; using VIOFO defaults`.
- **Declared.** Choosing a profile skips the choice, but detection still runs. If another profile matches, keep the declaration and warn, as for a declared Recording mode (§8.8).
- **What a profile changes.** Only defaults. Every setting the profile feeds has a `From profile` value (*Container clock is local time*, *Embedded GPS* backend, stamp region; date order `Auto` starts from it). Any explicit value overrides the profile for every video.
- **Camera geometry.** With *Camera geometry for export* = `Sidebar values` (the default), grading is exactly as before. With `From profile (per video)`, each video is graded with its profile's `CameraPreset`. Either way, the values used go into `videos.csv`. While `calibrated` is False, the run summary says `PCI indicative: <profile> geometry not calibrated` (§13).
- **Unchanged.** Photograph mode and the video preview don't use profiles, except that the preview's Check panel shows the detected profile.
- **Camera presets.** Horizon and cut-offs were measured on one screenshot per make; height and focal length are the sidebar defaults, not measurements. §13 describes a geometry overlay that would let the user check them.
- **Batches.** The profile is resolved per video, so one folder can mix VIOFO and Garmin files. The time-zone carry-over (§8.7) and the date-order carry-over (§8.4) apply only between videos with the same profile.

**Adding a make later**

1. Write a `SourceProfile` for it and `register()` it in `profiles.py`.
2. If the make stores GPS or time in a way no existing reader handles, add a reader module under `smartroad/survey/`, add it to `GPS_READERS`, and name it in the profile's `embedded_gps`. A new clock source works the same way, as a new entry in the Auto chain (§8.5).
3. Add its file names to the A.5 table and a probe fixture to `test_profiles.py`.

The sidebar lists `PROFILES`, so it needs no change, and the CSV schema doesn't change.

### 8.10 Downloaded and edited footage

The Garmin footage for this work comes from YouTube. A download or any re-encode keeps the picture, and so the burned-in stamp, but not the camera's file:

| Lost | Consequence |
|---|---|
| The camera's file name (`GRMN0007.MP4`, `2025_0315_105644_0012F.MP4`) | No file-name clock, no front/rear letter, no profile evidence from the name |
| The container clock (mvhd) | It is the re-encode time, not the recording time |
| Embedded GPS (Novatek `gps ` box, Garmin metadata track) | No embedded positions or GPS clock |
| Often the original resolution and bit rate | Fine cracks are lost; see below |

**Rules**

- **Recognising it.** *Downloaded / re-encoded video* (§5.4) is `Auto` by default: a file whose profile was recognised from the stamp alone (§8.9) is treated as re-encoded. `Yes` forces it, for example for a VIOFO clip trimmed in an editor; `No` turns it off.
- **Time and position from the stamp alone.** The Auto chains skip the file-name and container clocks and the embedded GPS (§8.5). GPS source `Auto` resolves to the stamp.
- **Date order.** The container date is not used as a reference (§8.4, Date order step 2). An ambiguous date such as `01/11/2020` with no day above 12 in the video falls to the previous video of the same profile, then to DMY, with a warning.
- **UTC offset.** It can't be measured without a GPS clock, so it comes from the setting (§8.7, 4.3), with a warning naming the offset used. Set it for the place the video was recorded: the Garmin sample is in South Africa, UTC+2.
- **Cuts.** An uploader may join clips. The clock fit treats a step with a position jump as a cut, not a clock correction (§8.4 step 5, A.7). Title cards and overlays without a stamp give rows with blank time and position (`time_source=none`, `gps_quality=missing`), and their detections are still written.
- **Re-timed uploads.** An upload played faster than real time is detected like a timelapse (§8.8): ×2 playback is `timelapse ×2`. A speed-up that matches no capture rate is kept as measured, with a warning.
- **Detection quality.** YouTube's compression removes fine cracks, so downloaded footage finds fewer distresses than the camera's own file and its PCI reads high. Use downloaded footage to test the pipeline (stamp, clock, positions, CSVs), not to grade roads. Download the highest resolution offered: the Garmin stamp still read correctly at 640×360, but detection needs the detail.
- **Copyright and privacy.** Don't commit downloaded footage or frames from it to this public repository. Tests use synthetic clips and stamp text.

## 9. Architecture

### 9.1 Files

New files under `smartroad/survey/`. The package docstring already describes it as "turning a driven survey into georeferenced … imagery".

| File | Contents |
|---|---|
| `novatek.py` | `read_gps_table(path)`, `decode_block(data)`, `read_embedded_gps(path)` → `EmbeddedGps(blocks, fixes, layout_ok, video_start_utc)` |
| `exiftool_gps.py` | `find_exiftool()`, `read_exiftool_gps(path, exe)` → list of fixes, `align_to_blocks(fixes, n_blocks)` |
| `stamp.py` | `StampReading`, `parse_stamp()` (A.1), `resolve_date_order(readings, reference_dates)`, `crop_stamp(frame_bgr, roi)`, `preprocess_for_tesseract()` (A.2) |
| `ocr.py` | `OcrEngine` protocol with `name` and `read(crop_bgr) -> str`. `TesseractEngine` calls `tesseract` through `subprocess` with an argument list (A.2), **not** pytesseract. `RapidOcrEngine`. `pick_engine(name, tesseract_cmd)`. |
| `clock.py` | `parse_dashcam_filename()` (A.5), `fit_stamp_clock()` (segments, A.7), `per_frame_fallback()`, `resolve_clock()`, `start_zone()` (measured, carried over or configured, §8.7), local/UTC helpers |
| `geo.py` | `GeoSettings`, `GeoSample`, `GeoContext`, `build_geo_context()` |
| `timebase.py` | `TimeBase` (mode, speedup, playback_fps, source; `elapsed()`, `frame_elapsed()`, `capture_interval_s`), `detect_timebase()`, `snap()`, `slope()` (Theil–Sen), `sample_frames(n_frames, timebase, per_driving_s, max_frames)`. Reference implementation in A.8. |
| `profiles.py` | `CameraPreset`, `ContainerProbe`, `SourceProfile`, `ProfileMatch`, the `PROFILES` registry with `register()`, `probe_container()`, `resolve_profile()`, and the VIOFO and Garmin profiles (§8.9) |

New package `smartroad/export/`:

| File | Contents |
|---|---|
| `settings.py` | `ExportSettings` and its sub-dataclasses, with `to_dict()` and `from_dict()` for JSON |
| `inference.py` | `make_detector(model, *, conf, tiled, overlap, top, bottom, device)` and `make_grader(*, height_m, focal_35, horizon, near_m, far_m, severity, top, bottom, class_names)`. This logic moves out of `app.py`'s `_detect` and `grade` **with no change in behaviour**, and `app.py` calls these instead. |
| `annotate.py` | `COLOURS`, `PRETTY` and `draw()`, moved out of `app.py` (which imports them back), plus `add_footer()` |
| `frames_out.py` | File naming, the which-frames filter, JPEG and EXIF writing |
| `csv_out.py` | Column tuples, formats, row builders, and `RunFolder` (create, write one video's part files, append to the top-level CSVs or mark them stale, rebuild from parts, purge incomplete parts, list done ids; §6.3) |
| `jobs.py` | `JobRegistry` (one per server process, held in `st.cache_resource`), `Job` (thread, frozen settings, state, `should_stop`), `progress.json` reading and writing. **Must not import streamlit**; the GUI polls it (§5.7). |
| `pipeline.py` | `process_video()` and `process_batch()`. **Must not import streamlit, torch or ultralytics.** |
| `__main__.py` | The CLI (S1) |

Changes to existing files:

| File | Change |
|---|---|
| `app.py` | The UI in §5. Imports `COLOURS`, `PRETTY` and `draw` from `smartroad.export.annotate`, and the detect and grade logic from `smartroad.export.inference`. With default settings, nothing visible changes. |
| `smartroad/detect/tiled.py` | `road_roi(..., *, bottom_fraction=1.0)` |
| `smartroad/survey/frames.py` | `read_gpx` no longer depends on the namespace. Add `read_gpx_many`, `Track.from_fixes` and `Track.gap_s`. |
| `smartroad/survey/video.py` | Add `iter_samples(path, frame_numbers, *, long_side, stamp_roi=None)`. It yields `(frame_number, graded PIL image, stamp crop BGR or None, (orig_w, orig_h))`. It decodes sequentially (`grab`/`retrieve`) when the gaps between frame numbers are 15 or fewer, and seeks otherwise. Existing functions are unchanged. |
| `smartroad/pci/from_detections.py` | Add `detection_quantity(det, camera, *, class_names, roi, near_m, far_m)`, returning `(amount, unit)` or `None`. It uses the existing private helpers (S4). |
| `requirements.txt` | Add `rapidocr_onnxruntime>=1.2`. It is optional when the app runs. Tesseract needs only its program, which pip doesn't install. |
| `pyproject.toml` | Add the optional dependency group `geo = ["rapidocr_onnxruntime>=1.2"]`. |
| `.gitignore` | Add `Output/`. |
| `README.md` | Add the section from S6. |

Leave `deploy/hf_space/requirements.txt` as it is.

### 9.2 Key interfaces

```python
# smartroad/survey/geo.py
@dataclass(frozen=True)
class GeoSample:
    utc: datetime | None
    local: datetime | None          # naive camera-local time
    utc_offset_h: float
    lat: float | None
    lon: float | None
    speed_kmh: float | None
    heading_deg: float | None
    gps_source: str                  # embedded | gpx | overlay | none
    gps_quality: str                 # interpolated | clamped | stamp-frame | gap | missing
    time_source: str                 # embedded | overlay | overlay-frame | filename | container | manual | none

class GeoContext:
    track: Track | None              # the track used (map, tracks/*.gpx)
    summary: dict[str, object]       # feeds videos.csv
    stamp_samples: list[tuple[float, str]]   # (t, raw OCR text), for the Check panel
    timebase: TimeBase               # §8.8: normal (speedup 1) or timelapse
    def at(self, elapsed_s: float) -> GeoSample: ...   # driving time, not video time

def build_geo_context(video: Path, info: VideoInfo, settings: GeoSettings, *,
                      gpx: Track | None = None, ocr: OcrEngine | None = None,
                      log: Callable[[str], None] = lambda _: None) -> GeoContext: ...
```

```python
# smartroad/export/pipeline.py
Detector = Callable[[np.ndarray], list[Detection]]                 # RGB image at graded size
Grader = Callable[[tuple[int, int], list[Detection]], FrameAssessment]

def process_video(video: Path, settings: ExportSettings, run: RunFolder, *,
                  detector: Detector, grader: Grader, class_names: dict[int, str],
                  root: Path | None = None, gpx: Track | None = None,
                  geo: GeoContext | None = None,          # reuse from "Check location & time"
                  progress: Callable[[int, int, str], None] = lambda *_: None,
                  should_stop: Callable[[], bool] = lambda: False) -> VideoSummary: ...

def process_batch(videos: list[Path], settings: ExportSettings, run: RunFolder, *,
                  root: Path, **same) -> list[VideoSummary]: ...
```

`ExportSettings` groups frozen sub-dataclasses:

| Group | Contents |
|---|---|
| `sampling` | fps, max_frames, long_side=1280 |
| `detector` | conf 0.25, tiled True, overlap 0.20, top 0.45, bottom 1.0 |
| `camera` | height 1.70, focal 25.0, horizon 0.139, near 3.0, far 15.0, severity "medium" |
| `frames` | the frame-saving widgets in §5.3 |
| `csv` | the CSV widgets in §5.3 |
| `geo` | every widget in §5.4, except the two below |
| `profile` | source profile `auto`, fallback `viofo`, camera geometry `sidebar` (§8.9) |

The defaults must equal the GUI defaults, and a test checks this.

### 9.3 Per-video flow

```
info  = probe_video(video)
prof  = resolve_profile(video, declared=..., fallback=..., read_stamp=...)  # §8.9: container, then stamp tokens
tb    = declared_timebase or detect_timebase(video, info, ocr=engine)     # §8.8: 9 stamp reads in 3 clusters, or GPS slope
geo   = geo or build_geo_context(video, info, tb, settings.geo, gpx=gpx, ocr=engine)
sel   = sample_frames(info.n_frames, tb, per_driving_s=fps, max_frames=limit or None)
for i, (n, img, stamp, orig) in enumerate(iter_samples(video, [k for k, _, _ in sel], long_side=1280,
                                                        stamp_roi=roi_if_needed), 1):
    t_video, elapsed = n / info.fps, tb.frame_elapsed(n)
    dets = detector(np.asarray(img));  fa = grader(img.size[::-1], dets)
    if tb.mode == "timelapse" and stamp is not None:
        geo.add_stamp_reading(elapsed, ocr.read(stamp))    # timelapse: the frames are the pre-pass (§8.8)
    buffer (n, t_video, elapsed, dets, fa, stamp) ; save_frame(...) if selected(fa, dets)
    progress(i, len(sel), eta);  if should_stop(): raise Stopped
geo.finish()                                           # clock fit + per-frame fallback over all readings
rows = [frame row + detection rows using geo.at(elapsed) for each buffered frame]
run.append_video(frame_rows, detection_rows, video_row)     # atomic per video (§6.3)
```

The export decodes frames in memory. The preview saves each frame as a JPEG at quality 92 and reads it back. Export results can therefore differ very slightly from the preview; say so in the README.

### 9.4 CLI (S1)

```
python -m smartroad.export run   --input D:\DCIM\Movie --recursive --front-only --label benguela ^
                                 --settings Output\20261106-193012_benguela\run.json
python -m smartroad.export run   --input clip.MP4 --fps 1 --gps embedded --tz 1 --out Output
python -m smartroad.export gps   clip.MP4 --gps overlay --gpx-out clip.gpx     # location only, no detection
python -m smartroad.export merge Output --out Output\_merged                   # latest run wins per video_id
```

`merge` joins the CSVs from every run folder. For each `video_id`, it keeps only the rows from the most recent run that finished that video, so results made with different settings are never mixed within one video.

## 10. Phases

### Phase 0: probe real footage

No changes in `smartroad/`. `DATA/docs/DASHCAM_NOTES.md` already holds what the two screenshots show (1.4). Using one A129 Plus clip that I'll provide, and one Garmin clip downloaded from YouTube (§12, question 7), add per clip:

1. The output of `exiftool -ee3 -api debug=1 -G3 -a -s -GPSType -GPSDateTime -GPSLatitude -GPSLongitude -GPSSpeed CLIP.MP4`. `GPSType` names the decoder variant ExifTool used.
2. The output of `exiftool -a -G1 -s -time:all CLIP.MP4`, for the container clock.
3. The stamp read with Tesseract on 5 frames.
4. The file name.
5. `moov`'s children, the track handler types and any make/model strings: the evidence `detect` will use (§8.9).

From these, work out:

- the camera's UTC offset;
- whether mvhd holds local time or UTC;
- whether the stamp time matches the GPS time;
- for Garmin, the stamp region, the date order and the Travelapse capture rate.

If ExifTool or Tesseract is missing, give me the `winget` commands from §5.4 and stop.

**Done when** the notes are committed and the defaults in §5.4 and both profiles in §8.9 are confirmed or corrected.

### Phase 1: refactor, frames per second, hood cut-off, frame saving

Covers M1, M2, M9, and the Local file part of M7.

Write the sampler against `TimeBase` (A.8) from the start, with speed-up 1. Phase 3 then adds timelapse without touching the main loop.

- Add `export/annotate.py`, `export/inference.py`, `export/settings.py`, `export/frames_out.py` and `video.iter_samples`.
- Add `survey/profiles.py` with the registry, `probe_container()`, `resolve_profile()` and both profiles. In this phase a profile supplies only the hood cut-off and camera preset, used when *Camera geometry for export* is `From profile`.
- Add a minimal `pipeline.process_video` that only saves frames.
- Add the Run export button.

**Done when:**

- with default settings, the app looks and behaves as before;
- exporting a local clip at 1 fps produces one JPEG per time returned by `frame_times()`, for example 6 for a 6.0 s clip;
- the §11.1 tests for this phase pass.

### Phase 2: CSV

Covers M3.

- Add `csv_out.py` and `RunFolder`, with per-video part files (§6.3).
- Add `jobs.py` and the background job panel (§5.7). Run export becomes a background job.
- Write `frames.csv`, `detections.csv`, `videos.csv` and `run.json`. In this phase the location columns stay blank, and the time comes from the file name or the container clock.

**Done when:**

- the format, schema, atomic-write and job tests pass;
- the files open correctly in Excel (Portuguese locale) and in pandas;
- a running export survives slider changes and a page reload, and keeps running while `detections.csv` is open in Excel.

### Phase 3: location and time

Covers M4, M5, M6 and M11 (timelapse), plus S3 (EXIF) and S5 (`tracks/*.gpx`).

- Add `novatek.py`, `exiftool_gps.py`, `stamp.py`, `ocr.py`, `clock.py` and `geo.py`.
- Wire the rest of each profile in: file-name patterns, container-clock rule, GPS reader, `gpsdatetime_is_clock`, stamp region, date order and capture rates. Add the *Source profile* and *If not recognised* widgets.
- Add the `frames.py` additions from §9.1.
- Add downloaded and edited footage handling (§8.10): stamp-token recognition, the *Downloaded / re-encoded video* setting, cuts, cluster-based timelapse detection, the signed coordinate format and the sign vote.
- Add the sidebar section from §5.4 and the Check location & time button.

**Done when:**

- the §11 tests pass;
- checks 2 and 3 in §11.3 work on my clip, and check 8 on the downloaded Garmin clip.

### Phase 4: batch, resume, CLI, merge

Covers the Batch folder part of M7, plus M8, S1 and S2.

**Done when** check 6 in §11.3 passes.

### Phase 5: docs and extras

Covers S4 and S6, then C1–C3 if there is time.

## 11. Tests and acceptance

### 11.1 Unit tests

These must pass in CI's light environment, or skip with a reason.

| File | What it checks |
|---|---|
| `test_stamp.py` | **Parsing:** every row of the three tables in A.1 gives the expected values, Tables 1 and 2 with `signed_dd` both off and on, including `date_ambiguous` and the coordinate format: VIOFO decimal degrees, Garmin DDM and DMS, MDY, 12-hour clocks, and the OCR variants. **Refusals:** a lost hemisphere or degree sign gives no coordinate; 62 minutes is rejected; `13:23:15 PM` is rejected; `10:56:44 A129` has no date. **`resolve_date_order`:** a day above 12 decides; a file-name date decides an ambiguous date; otherwise the previous video's order; otherwise DMY with a warning. **Sign vote:** a minority of readings with a lost minus sign is dropped; a real equator crossing (values within 0.5° of zero) is kept. |
| `test_clock.py` | The file-name cases in A.5. Local↔UTC at +1.0 and −3.5. Every scenario in A.7: clean, outliers, +1 h and −1 h zone steps, a +45 min step, a 37 s clock correction, a correction followed by a zone step, a failed fit, and the per-frame fallback. The cut scenarios in A.7: a cut with a position jump, a +1 h cut with a position jump, a late step without positions, a late correction with continuous positions, a zone change followed by a cut. `start_zone()`: measured, then carried over (within 12 h), then the setting. Every row of the Auto table in §8.5, as a parametrised test. |
| `test_novatek.py` | **Input:** synthetic MP4 bytes built in the test, like `_mp4()` in `test_frames.py`, with a `gps ` table placed before `trak` and after it, 1 void block and 6 valid GPSType 3 blocks (A.3). **Checks:** decoded values within 1e-6°; the block indices keep the void block; `video_start_utc` is the first fix minus 1 s; a corrupted layout gives `layout_ok=False`. |
| `test_exiftool_gps.py` | The JSON fixture (A.4) gives the expected fixes. Alignment with n=7 and m=6 puts fix 1 at block 1. A Garmin-like fixture, with `SampleTime` and `GPSDateTime = CreateDate + SampleTime`, places fixes by `SampleTime` and is **not** used as a clock. Only if `find_exiftool()` finds ExifTool: run it on the synthetic file and require the same fixes as the built-in decoder. |
| `test_gpx_ext.py` | GPX 1.0, a file with no namespace, and two files merged and sorted. `test_frames.py` is untouched and still passes. |
| `test_csv_out.py` | **Layout:** exact column tuples; exact bytes for both formats (BOM, `;`, decimal comma, CRLF). **Values:** `None` gives an empty cell, booleans are 1 or 0, paths are relative with forward slashes. **Rows:** one per detection; frames without detections are present; `map_url` is blank without a position and uses `.` decimals in both formats. **Parts and resume:** part folders without `video.json` are removed; a locked top-level file (simulated `PermissionError`) is marked stale and rebuilt from the parts at the end, or written as `detections (1).csv` when still locked. |
| `test_frames_out.py` | File names. Which-frames filters. The footer adds height and leaves the original pixels byte-for-byte identical. The EXIF round trip (A.6). Box scaling at original resolution. |
| `test_geo.py` | `GeoContext` over a known `Track`: interpolation, `gap` (blank), `clamped`, `missing`, and derived speed and heading. |
| `test_timebase.py` | Every check in A.8. **Detection:** ×30 and ×15 from the stamp; ×1 for normal video; ×30 from VIOFO GPS block times (1 block per video second, fixes 30 s apart); no evidence gives normal with a note. **Declared mode:** contradicted by the evidence, it is kept and warned; confirmed, no warning. **Snapping:** 29.97 fps. **Sampling:** every frame; every 2nd frame; a rate above the capture rate is capped; normal 30 fps gives frames 15, 45, 75, the same as `frame_times()`. **Long clip:** a 1-hour timelapse clip's `elapsed_s` reaches 3600 while its `video_time_s` reaches 120. **Clusters:** a title card without a stamp, a cut between clusters and a cut inside one cluster (A.8). |
| `test_profiles.py` | **Registry:** both profiles registered, keys unique, the sidebar options equal the registry. **Detection:** a synthetic MP4 with a `gps ` box is VIOFO; `2025_0315_105644_0012F.MP4` is VIOFO by name; `GRMN0007.MP4` is Garmin; an unknown file falls back with a warning. **Declared:** a declared Garmin profile on a file with a `gps ` box is kept and warned. **Overrides:** an explicit setting beats the profile; `From profile` takes the profile's value. **Extension:** registering a test profile makes it detectable with no other change. **Stamp tokens:** with a fake `read_stamp` returning the Garmin sample text, a file with no container evidence is Garmin, `reencoded=True`; `V1OFO` text is VIOFO; no token falls back. |
| `test_jobs.py` | A job runs a fake pipeline on a thread and writes `progress.json`; Stop ends it after the current frame and no part files are written for the unfinished video; a second submit to the same output folder is refused; the registry's state is unchanged by a simulated rerun. |
| `test_settings.py` | `ExportSettings()` defaults equal the `app.py` sidebar defaults. The JSON round trip. |
| `test_tiled.py` (extend) | `road_roi(..., bottom_fraction=1.0)` gives the same result as before. A box whose centre is below the cut is dropped. |

### 11.2 Integration tests

These skip without OpenCV or an OCR engine.

**`test_pipeline_stamp.py`**

Setup:

- Write a 4 s, 1280×800, 10 fps clip with `cv2.VideoWriter` (`mp4v`).
- Draw this stamp on a dark band in the bottom rows with `cv2.putText`: `84 KM/H S12.035136 E13.955326 TEST VIOFO A129 Plus 15-03-2025 10:56:44`. Advance it by 1 s and 0.00021° of latitude per second. Tesseract 5.3.4 read this text exactly in testing.
- Use a fake detector that returns one pothole box per frame, and the real grader.

Expected:

- 4 JPEGs at 1 fps;
- 4 rows in `frames.csv` and 4 in `detections.csv`;
- lat within 1e-5 of the stamp value;
- `date_local` is 2025-03-15;
- `time_local` for frame 1 is 10:56:44.5 ± 0.5 s;
- `datetime_utc` is the local time minus 1 h.

**`test_pipeline_resume.py`.** Two clips. Stop after the first with `should_stop`, then resume. Expected: no duplicate `(video_id, frame_index)`, and both videos are `done`.

**`test_pipeline_clock.py`.** Same synthetic stamp clip as `test_pipeline_stamp.py`, 12 s long, in four variants:

- **Zone change.** The stamp jumps +1 h at t = 6 s.
  - Expected: `datetime_utc` advances by about 1 s between the frames at 5.5 s and 6.5 s, while `time_local` jumps by about 1 h 0 m 1 s.
  - `utc_offset` changes from `+01:00` to `+02:00`.
  - `videos.csv` `utc_offset_end` is `+02:00`, and `clock_events` names the change.
- **Clock correction.** The stamp is 37 s slow for t < 4 s.
  - Expected: the rows before 4 s are re-based (UTC is continuous).
  - `clock_events` says `clock corrected +37.0 s`.
- **Fit failure.** Name the clip `2025_0315_105644_0001F.MP4`. Only the frames at t = 1.5 and 2.5 s have a readable stamp, and the rest are blanked. The pre-pass then has 2 readings, which is too few to fit a clock, but they agree with each other.
  - Expected: those two frames get `time_source=overlay-frame`, and the other frames fall back to the file-name clock (`time_source=filename`).
- **Cut.** At t = 6 s the stamp jumps +2 h 13 min 7 s and 35 km east, as in an edited video.
  - Expected: `clock_events` names a cut. The rows before 6 s keep their own clock (nothing is re-based), `datetime_utc` jumps by about 2 h 13 min between the frames at 5.5 s and 6.5 s, and `utc_offset` stays `+01:00`.

**`test_pipeline_timelapse.py`.** Skips without OpenCV or an OCR engine.

Setup:

- Write a 90-frame clip at 30 fps (3 s of video) with `cv2.VideoWriter`.
- Frame *k*'s stamp shows `10:56:44 + k s`, with latitude `−12.035136 + 0.00021·k`. This is a 1 fps timelapse covering 90 s of driving.

Expected, in Auto mode:

- `recording_mode=timelapse`, `speedup=30`, `mode_source=stamp`.
- At 1/3 per driving second, 30 frames are graded, every 3rd frame.
- `elapsed_s` = `frame_number`; `video_time_s` = `frame_number / 30`.
- `time_local` advances 3 s per row.
- Lat matches each frame's own stamp within 1e-6.
- The clock fit gives one segment.
- With Recording mode set to `Normal video`, the same clip still runs, and `videos.csv` carries the contradiction warning.

This scenario was run end to end with the 1.2 code (A.8): detection ×30 from 3 stamp reads, 10/10 frames exact with both sequential and seek decoding, 30 graded frames OCR'd in 3.9 s, one clock segment, and per-frame latitudes exact.

**`test_tesseract_argv.py`** (skips without Tesseract).

- Build the command with `TesseractEngine` and check that the whitelist arrives as **one** argv element containing a space, `°` and `'`. On Windows, also check `subprocess.list2cmdline` round-trips it.
- OCR a rendered `N47°36.123' W122°19.456'` line and parse it.

**`test_stamp_fixture.py`.** Runs only if `tests/data/stamp_a129plus_masked.png` exists (§12, question 5). With any available engine, `parse_stamp` gives 84 km/h, −12.035136, 13.955326, 2025-03-15 10:56:44.

### 11.3 Manual acceptance (on my footage)

1. **No regressions.** With export off and before *Check location & time* runs, the app looks and behaves exactly as before, for photos and for the video preview.
2. **Embedded GPS.** *Check location & time* on one clip shows a track along the road actually driven, and its start time matches the stamp within 1 s.
3. **Stamp OCR.** On the same clip, the reading at the time of the sample frame is S12.035136 E13.955326, 15-03-2025 10:56:44. Embedded and stamp positions agree after any lag correction: median distance under 15 m, maximum under 40 m.
4. **Frame files.** A 1 fps export with "All graded frames" produces as many JPEGs as `frames.csv` has rows, and every `image_file` in `detections.csv` exists.
5. **Opening the CSVs.**
   - The Excel PT/EU file opens in Excel with the columns split and the decimals correct.
   - The Standard file loads in QGIS as a point layer (X = lon, Y = lat, EPSG:4326).
6. **Resume.** A batch of 10 or more clips can be stopped midway and resumed without duplicate rows. Every video ends as `done`, or as `failed` with a reason.
7. **Merge.** Merging two runs keeps the latest run for each `video_id`.
8. **Downloaded Garmin clip.** With every setting on Auto: `source_profile=garmin`, `profile_source=detected`, `reencoded=1`; positions and times come from the stamp; a frame's `time_local`, lat and lon match the stamp visible in its saved image.
9. **Background export.** While an export runs, change a slider and reload the page: the job keeps running, the panel finds it again, and **Stop** ends it with the finished videos kept.
10. **Finding a grading.** Pick the worst frame in `frames.csv`; its `map_url` opens the place, and its `video_time_hms` shows the same frame in a video player.

## 12. Open questions

The default is used until each question is answered.

1. **Camera time zone setting.** Default: +1.0 h. Phase 0 confirms it.
2. **Date format on the stamp.** Default: DD-MM-YYYY, as on the sample frame.
3. **Rear-camera files (`…R.MP4`).** Default: skipped, front camera only.
4. **Meaning of frames per second.** Answered 2026-11-07: keep sampling per second of driving as the default, one selector for grading and saving. Use the GPS source to tie each graded frame's video time to its position and clock time. Distance-based sampling is not planned.
5. **Stamp test image.** `tests/data/stamp_a129plus_masked.png` is supplied with this spec. It is the 2560×72 stamp strip from the sample frame, with the plate and custom text painted out. It still shows a position and a date. Should it be committed to this public repo? Default: no, and the test that uses it is skipped.
6. **Machine.** Default: Windows, with an NVIDIA GPU optional. This decides the ExifTool and Tesseract paths and whether the macOS rules apply.
7. **Garmin footage.** Answered 2026-11-07: the Garmin footage is downloaded from YouTube, so only the stamp survives (§8.10). A screenshot of it set the Garmin profile (§8.9). The ExifTool Garmin path stays covered by unit tests until an original Garmin file is available.
8. **Local time columns.** Default: *Camera's clock*. Switch to *Fixed UTC offset* if reports must always be in one zone (§8.7).
9. **Timelapse source.** Which camera records the timelapse, and at what capture rate? Default: an A129 Plus timelapse at 1 fps, played back at 30 fps, with the stamp on. Phase 0 should include one timelapse clip and record three things:
   - the GPS block count against the frame count (expect one block per *video* second);
   - whether the stamp changes on every frame;
   - whether the file names differ from those of normal recordings.
10. **Garmin model.** Answered 2026-11-07: unknown (YouTube footage). The Garmin profile follows the screenshot's stamp. Another layout is added to the profile when footage with it turns up.
11. **Background exports.** Answered 2026-11-07: yes, exports run in the background (§5.7).

## 13. Known limitations

Record these in the README. Don't fix them now.

- **PCI and quantities depend on camera geometry.**
  - The defaults (height 1.70 m, focal length 25 mm, horizon 0.139) were calibrated for the Tashkent survey camera.
  - The A129 Plus front lens covers 140° and is visibly barrel-distorted. The pinhole model in `geometry/ipm.py` doesn't account for that.
  - Feature type, time and location are unaffected. `quantity`, `frame_pci` and `pci` from dashcam footage are only indicative until the lens is calibrated.
  - `run.json` stores the camera geometry, so results can be recalculated later.
- **One frame is not an ASTM sample unit**, as the README already says. The CSVs are a georeferenced inventory, not a certified section PCI.
- **Camera presets are first estimates.** Horizon and cut-offs were measured on one screenshot per make; height and focal length are not measured. The default focal length, 25 mm, suits a narrow lens; a 140° dashcam lens is far wider. A geometry overlay on the preview (lines at 3, 5, 10 and 15 m, and the width of a 3.5 m lane at each) would let the user tune height and focal length by eye; it is not in this spec.
- **Downloaded footage** (§8.10): detection finds fewer fine cracks, so PCI reads high; the UTC offset comes from the setting; the date order of ambiguous dates may be a guess.
- **Cuts without positions.** On a stamp without coordinates, a cut in the first 120 s of driving is taken for a clock correction.
- **Lost minus signs.** If OCR drops the minus sign on every reading of a video, the sign vote can't see it, and the positions land in the wrong hemisphere. The map in the Check panel shows it.

## Appendix A: validated reference material

Everything below was run on 2026-11-06 against the sample frame and synthetic test files, with:

- Tesseract 5.3.4 (called directly, A.2) and rapidocr_onnxruntime 1.2.3;
- ExifTool 13.61, Pillow 12.3 and OpenCV 5.0.

The 1.4 additions (the signed coordinate format, the cut classification and the cluster-based timelapse detection) were run on 2026-11-07, with Tesseract 5.3.4, rapidocr_onnxruntime 1.2.3 and OpenCV 5.0, against the two screenshots supplied that day and synthetic data. The code in A.1, A.7 and A.8 is the code that was run: every row and scenario of 1.3 still passes, and the new ones pass.

### A.1 Stamp parser

```python
"""Parse one OCR'd dashcam stamp line: speed, position, local date and time.

Formats: VIOFO decimal degrees (S12.035136 E13.955326), degrees + decimal minutes
(hddd°mm.mmm'), degrees-minutes-seconds, decimal degrees with a trailing hemisphere, and, when the
profile asks for it, signed decimal degrees with no hemisphere (Garmin: -26.36774 27.31358);
YYYY-MM-DD, DD-MM-YYYY and MM-DD-YYYY dates; 24-hour and 12-hour (AM/PM) clocks.
Never relies on spaces: RapidOCR (and Tesseract when the whitelist omits the space)
runs tokens together, e.g. "E13.955326CUSTOM" or "XX15-03-2025".
"""
import datetime as dt
import re
from dataclasses import dataclass

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
```

**Expected results.** All of these pass. Empty cells mean `None`.

**Table 1: OCR output from the VIOFO sample frame.** The plate is replaced by `AA-00-BB` and the custom text by `CUSTOM`. Date order DMY.

| OCR text | order | speed_kmh | lat | lon | local | ambiguous | format |
|---|---|---|---|---|---|---|---|
| `84 KM/H S12.035136 E13.955326 CUSTOM VIOFO A129 Plus AA-00-BB 15-03-2025 10:56:44` | DMY | 84 | -12.035136 | 13.955326 | 2025-03-15 10:56:44 | no | dd |
| `84 KM/H $12.035136 E13.955326 CUSTOM VIOFO A129 Plus AA-00-BB 15-03-2025 10:56:44` | DMY | 84 | -12.035136 | 13.955326 | 2025-03-15 10:56:44 | no | dd |
| `84 KM/H S12.035136 E13.955326CUSTOM VIOFO A129 Plus AA-00-BB15-03-2025 10:56:44` | DMY | 84 | -12.035136 | 13.955326 | 2025-03-15 10:56:44 | no | dd |
| `84KM/H S12.035136 E13.955326CUSTOMVIOFO A129 PIus AA-00-BB15-03-2025 10:56:44` | DMY | 84 | -12.035136 | 13.955326 | 2025-03-15 10:56:44 | no | dd |
| `84KM/HS12.035136E13.955326CUSTOM VIOFOA129PlusAA-00-BB 15-03-202510:56:44` | DMY | 84 | -12.035136 | 13.955326 | 2025-03-15 10:56:44 | no | dd |
| `7 84 KM/H S12.035136 E13.955326 CUSTOM VIOFO A129 Plus AA-00-BB 15-03-2025 10:56:44` | DMY | 84 | -12.035136 | 13.955326 | 2025-03-15 10:56:44 | no | dd |
| `84 KM/H S12.035136 E13.955326 CUSTOM VIOFO A129 Plus AA-00-BB 15-03-7075 10:56:44` | DMY | 84 | -12.035136 | 13.955326 | | no | dd |
| `52 MPH N40.712776 W74.005974 2025/03/15 10:56:44` | DMY | 83.685888 | 40.712776 | -74.005974 | 2025-03-15 10:56:44 | no | dd |
| `0 KM/H 12-34-56 2025/03/15 10:56:44` | DMY | 0 | | | 2025-03-15 10:56:44 | no | |
| `0 KM/H VIOFO A129 Plus 03/04/2025 08:00:01` | DMY | 0 | | | 2025-04-03 08:00:01 | yes | |

**Table 2: MDY dates, 12-hour clocks, Garmin coordinates and OCR variants (new in 1.1).**

| OCR text | order | speed_kmh | lat | lon | local | ambiguous | format |
|---|---|---|---|---|---|---|---|
| `0 KM/H VIOFO A129 Plus 03/04/2025 08:00:01` | MDY | 0 | | | 2025-03-04 08:00:01 | yes | |
| `35 MPH 10/25/2025 04:23:15 PM` | DMY | 56.32704 | | | 2025-10-25 16:23:15 | no | |
| `35 MPH 3/4/2025 4:23:15 PM` | MDY | 56.32704 | | | 2025-03-04 16:23:15 | yes | |
| `12/04/2025 12:05:09 AM` | MDY | | | | 2025-12-04 00:05:09 | yes | |
| `12/04/2025 12:05:09 PM` | MDY | | | | 2025-12-04 12:05:09 | yes | |
| `12/04/2025 11:59:59 p.m.` | MDY | | | | 2025-12-04 23:59:59 | yes | |
| `10/25/2025 13:23:15 PM` | MDY | | | | | no | |
| `10/25/2025 04:23:15PM` | MDY | | | | 2025-10-25 16:23:15 | no | |
| `10:56:44 A129` | DMY | | | | | no | |
| `15-03-2025 10:56:44 A129 Plus` | DMY | | | | 2025-03-15 10:56:44 | no | |
| `N47°36.123' W122°19.456' 35 MPH 10/25/2025 04:23:15 PM` | MDY | 56.32704 | 47.60205 | -122.3242667 | 2025-10-25 16:23:15 | no | ddm |
| `N 47° 36.123' W 122° 19.456'` | MDY | | 47.60205 | -122.3242667 | | no | ddm |
| `S12°02.108' E013°57.320'` | DMY | | -12.0351333 | 13.9553333 | | no | ddm |
| `S12o02.108 E013o57.320` | DMY | | -12.0351333 | 13.9553333 | | no | ddm |
| `S12 02.108 E013 57.320` | DMY | | -12.0351333 | 13.9553333 | | no | ddm |
| `S12*02.108' E013*57.320'` | DMY | | -12.0351333 | 13.9553333 | | no | ddm |
| `S1202.108 E01357.320` | DMY | | | | | no | |
| `S12°62.108' E013°57.320'` | DMY | | | | | no | |
| `N47°36'07.4" W122°19'27.4"` | MDY | | 47.6020556 | -122.3242778 | | no | dms |
| `37.7749° N, 122.4194° W` | MDY | | 37.7749 | -122.4194 | | no | dd |
| `$12°02.108° E013°57.320*84 KM/H15/03/2025 10:56:44` (RapidOCR) | DMY | 84 | -12.0351333 | 13.9553333 | 2025-03-15 10:56:44 | no | ddm |
| `84 KM/H S12°02.108° E013°57.320: 15/03/2025 10:56:44` (RapidOCR) | DMY | 84 | -12.0351333 | 13.9553333 | 2025-03-15 10:56:44 | no | ddm |
| `GARMIN 35 MPH N47°36.123° W122°19.456° 10/25/2025 04:23: 15 PM` (RapidOCR) | MDY | 56.32704 | 47.60205 | -122.3242667 | 2025-10-25 16:23:15 | no | ddm |
| `N47°36.123' W122°19.456′35 MPH10/25/2025 04:23:15 PM` (RapidOCR) | MDY | 56.32704 | 47.60205 | -122.3242667 | 2025-10-25 16:23:15 | no | ddm |
| `12°02.108' E013°57.320' 84 KM/H 15/03/2025 10:56:44` (hemisphere lost) | DMY | 84 | | | 2025-03-15 10:56:44 | no | |
| `N4736.123 W12219.456 35 MPH 10/25/2025 04:23:15 PM` (degree signs lost) | MDY | 56.32704 | | | 2025-10-25 16:23:15 | no | |

Tables 1 and 2 pass with `signed_dd` off (the default) and on.

**Table 3: real stamps and the signed format (new in 1.4).** The last column gives the options: **Garmin** is the Garmin profile's `signed_dd=True, coord_decimals=5`; **signed** is `signed_dd=True` with no decimal count; **none** is the defaults, as for VIOFO. The plate and custom text of the real VIOFO stamp are masked.

| OCR text | order | speed_kmh | lat | lon | local | ambiguous | format | options |
|---|---|---|---|---|---|---|---|---|
| `GARMIN 01/11/2020 07:17:05 -26.36774 27.31358 70 KM/H` (both engines, real frame) | DMY | 70 | -26.36774 | 27.31358 | 2020-11-01 07:17:05 | yes | sdd | Garmin |
| `GARMIN 01/11/2020 07:17:05 -26.36774 27.31358 70 KM/H` | MDY | 70 | -26.36774 | 27.31358 | 2020-01-11 07:17:05 | yes | sdd | Garmin |
| `GARMIN 01/11/2020 07:17:05 -26.36774 27.31358 70 KM/H` | DMY | 70 | -26.36774 | 27.31358 | 2020-11-01 07:17:05 | yes | sdd | signed |
| `GARMIN 01/11/2020 07:17:05 -26.36774 27.31358 70 KM/H` (1.3 behaviour) | DMY | 70 | | | 2020-11-01 07:17:05 | yes | | none |
| `GARMIN01/11/202007:17:05-26.3677427.31358 70KM/H` (spaces lost) | DMY | 70 | -26.36774 | 27.31358 | 2020-11-01 07:17:05 | yes | sdd | Garmin |
| `GARMIN01/11/202007:17:05-26.3677427.3135870KM/H` (spaces lost) | DMY | 70 | -26.36774 | 27.31358 | 2020-11-01 07:17:05 | yes | sdd | Garmin |
| `GARMIN01/11/202007:17:05-26.3677427.3135870KM/H` (no decimal count: can't split; 870 km/h rejected) | DMY | | | | 2020-11-01 07:17:05 | yes | | signed |
| `GARMIN 01/11/2020 07:17:05 −26.36774 27.31358 70 KM/H` (Unicode minus) | DMY | 70 | -26.36774 | 27.31358 | 2020-11-01 07:17:05 | yes | sdd | Garmin |
| `GARMIN 01/11/2020 07:17:05 26.36774 27.31358 70 KM/H` (minus lost: the sign vote drops it) | DMY | 70 | 26.36774 | 27.31358 | 2020-11-01 07:17:05 | yes | sdd | Garmin |
| `GARMIN 10/25/2025 04:23:15 PM 47.60205 -122.32427 35 MPH` | MDY | 56.32704 | 47.60205 | -122.32427 | 2025-10-25 16:23:15 | no | sdd | Garmin |
| `GARMIN 25/10/2025 16:23:15 -26.36774 27.31358 0 KM/H` | DMY | 0 | -26.36774 | 27.31358 | 2025-10-25 16:23:15 | no | sdd | Garmin |
| `84 KM/H S12.035136 E13.955326 CUSTOM V1OFO A129 PIusAA-00-BB 15-03-2025 10:56:44` (RapidOCR, real frame) | DMY | 84 | -12.035136 | 13.955326 | 2025-03-15 10:56:44 | no | dd | none |

### A.2 Crop and OCR settings

Crop: `frame[int(H * 0.955):H, 0:W]`. That is 72 rows on a 1600-px frame. Garmin (1.4): `frame[int(H * 0.95):H, 0:int(W * 0.62)]`, 54 rows on a 1080-px frame.

```python
import os
import subprocess
import sys
import tempfile

import cv2

# One argv element. Includes the space and the symbols Garmin-style coordinates need.
TESS_WHITELIST = "0123456789.:-/ ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz°'\""


def preprocess_for_tesseract(crop_bgr):
    g = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    s = 128 / g.shape[0]
    g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.copyMakeBorder(255 - b, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)


def tesseract_read(crop_bgr, exe: str = "tesseract") -> str:
    """Read one stamp line. No shell and no shlex, so the whitelist reaches Tesseract intact
    on Windows too (pytesseract keeps the quotes there). The PNG is written with Python's
    own I/O because cv2.imwrite fails on non-ASCII Windows paths (e.g. a user named João)."""
    ok, png = cv2.imencode(".png", preprocess_for_tesseract(crop_bgr))
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "stamp.png")
        with open(path, "wb") as fh:
            fh.write(png.tobytes())
        argv = [exe, path, "stdout", "--psm", "7", "-c", f"tessedit_char_whitelist={TESS_WHITELIST}"]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        out = subprocess.run(argv, capture_output=True, timeout=30, creationflags=flags)
    return out.stdout.decode("utf-8", errors="replace").strip()      # UTF-8, not the Windows code page


# RapidOCR: colour crop x2, NO padding; join the boxes left to right
# res, _ = RapidOCR()(cv2.resize(crop_bgr, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
# text = " ".join(r[1] for r in sorted(res or [], key=lambda r: min(p[0] for p in r[0])))
```

### A.3 Novatek `gps ` table and `freeGPS` block

**`gps ` box** (a direct child of `moov`). Its payload is:

- 4 unused bytes;
- `n`, a big-endian u32;
- `n` pairs of big-endian u32 values: absolute file offset and size.

**Block** (`m` = the offset of the marker):

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | box size (u32 BE) |
| 4 | 8 | `freeGPS ` |
| 12 | 4 | length/version (u32 LE). Ignore. |
| m − 24 | 6 × 4 | hour, minute, second, year (add 2000 if below 100), month, day (u32 LE) |
| m | 1 | `A` = fix, `V` = no fix |
| m + 1 | 1 | `N` or `S` |
| m + 2 | 1 | `E` or `W` |
| m + 3 | 1 | `\0` |
| m + 4 | 4 | latitude, float32 LE, DDMM.MMMM |
| m + 8 | 4 | longitude, float32 LE, DDDMM.MMMM |
| m + 12 | 4 | speed, float32 LE, knots (× 1.852 for km/h) |
| m + 16 | 4 | track, float32 LE, degrees |

`m = 40` in the VIOFO A119 V3 layout (ExifTool GPSType 3). `m = 72` in the older Novatek layout.

To convert DDMM.MMMM to degrees: `d = int(v // 100); deg = d + (v - 100 * d) / 60`, then negate for S or W.

**Validation.** A synthetic MP4 was built with 1 void block and 6 valid blocks. ExifTool 13.61 reported `GPSType 3`. ExifTool and the built-in decoder returned the same first fix: −12.0351359, 13.9553263, 84.0 km/h, 2025-03-15T09:56:38Z. ExifTool skipped the void block, so its Doc1 was block 1; the built-in decoder kept the block index.

**Gotcha.** When the `gps ` box was the *last* child of `moov` (after `udta`), ExifTool ignored it. The built-in reader must search every child of `moov`.

### A.4 ExifTool output

This is the actual output for the synthetic file, shortened:

```json
[{
  "SourceFile": "novatek2.mp4",
  "Doc1:GPSDateTime": "2025:03:15 09:56:38Z",
  "Doc2:GPSDateTime": "2025:03:15 09:56:39Z",
  "Doc1:GPSLatitude": -12.0351359049479,
  "Doc1:GPSLongitude": 13.9553263346354,
  "Doc1:GPSSpeed": 84.0000024871826,
  "Doc1:GPSTrack": 0
}]
```

`GPSDateTime` can carry fractional seconds (`…:38.500Z`), so parse both forms.

### A.5 Dashcam file names

```python
VIOFO_NAME = re.compile(
    r"(?P<Y>20\d{2})_?(?P<m>\d{2})(?P<d>\d{2})_?(?P<H>\d{2})(?P<M>\d{2})(?P<S>\d{2})"
    r"(?:_(?P<seq>\d{1,6}))?(?P<cam>[FRI])?\.(?:MP4|MOV|TS)$", re.I)
```

Use `VIOFO_NAME.search(name)`. The time it gives is camera local time.

| Name | Local start | cam |
|---|---|---|
| `2025_0315_105644_0012F.MP4` (manual: "Year_Date_Time_***F") | 2025-03-15 10:56:44 | F |
| `20250914171951_000183F.MP4` (A129 Plus Duo, newer firmware) | 2025-09-14 17:19:51 | F |
| `20191014_153940F.MP4` (A129 Pro style) | 2019-10-14 15:39:40 | F |
| `2025_0315_105644_012R.MP4` | 2025-03-15 10:56:44 | R |
| `yangizamon_15s.mp4`, `GRMN0007.MP4` | no match | |

### A.6 EXIF with Pillow only (no piexif)

```python
from PIL import Image, ExifTags
from PIL.TiffImagePlugin import IFDRational


def _dms(deg: float):
    a = abs(deg); d = int(a); m = int((a - d) * 60); s = (a - d - m / 60) * 3600
    return (IFDRational(d, 1), IFDRational(m, 1), IFDRational(round(s * 10000), 10000))


def exif_for(local, utc, offset, lat, lon, speed_kmh, description) -> Image.Exif:
    exif = Image.Exif()
    exif[ExifTags.Base.ImageDescription] = description
    exif[ExifTags.Base.DateTime] = local.strftime("%Y:%m:%d %H:%M:%S")
    sub = exif.get_ifd(ExifTags.IFD.Exif)
    sub[ExifTags.Base.DateTimeOriginal] = local.strftime("%Y:%m:%d %H:%M:%S")
    sub[ExifTags.Base.OffsetTimeOriginal] = offset                    # e.g. "+01:00"
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[ExifTags.GPS.GPSVersionID] = b"\x02\x03\x00\x00"
    gps[ExifTags.GPS.GPSLatitudeRef] = "S" if lat < 0 else "N"
    gps[ExifTags.GPS.GPSLatitude] = _dms(lat)
    gps[ExifTags.GPS.GPSLongitudeRef] = "W" if lon < 0 else "E"
    gps[ExifTags.GPS.GPSLongitude] = _dms(lon)
    if speed_kmh is not None:
        gps[ExifTags.GPS.GPSSpeedRef] = "K"
        gps[ExifTags.GPS.GPSSpeed] = IFDRational(round(speed_kmh * 10), 10)
    gps[ExifTags.GPS.GPSDateStamp] = utc.strftime("%Y:%m:%d")
    gps[ExifTags.GPS.GPSTimeStamp] = (IFDRational(utc.hour, 1), IFDRational(utc.minute, 1),
                                      IFDRational(round(utc.second * 1000 + utc.microsecond / 1000), 1000))
    return exif

# image.save(path, quality=90, exif=exif_for(...))
```

This snippet assumes every value is known. The real implementation leaves out whatever is unknown. ExifTool read the result back as:

- GPS Latitude −12.035136, GPS Longitude 13.955326, GPS Speed 84;
- GPS Date/Time 2025:03:15 09:56:44Z;
- Date/Time Original 2025:03:15 10:56:44, Offset Time Original +01:00.

### A.7 Stamp clock fit, in segments

Reference implementation of §8.4 and §8.7. It assumes stamp-only data, so the first segment's zone is passed in from `start_zone()`. With a real GPS clock, measure each segment's zone instead. Readings may carry the stamp's lat/lon, which tells a cut from a clock correction (new in 1.4).

```python
"""Stamp clock fit v3: piecewise segments, each step classified as a time-zone change, a clock
correction or a cut in an edited video; per-frame fallback."""
from __future__ import annotations
import datetime as dt
import math
import statistics
from dataclasses import dataclass, field

EPOCH = dt.datetime(2000, 1, 1)          # local times are naive; work in seconds from a fixed epoch
TOL_S = 1.5                              # readings within this of each other share a clock
MIN_RUN = 3                              # a clock level / segment needs this many readings
ZONE_STEP_S = 900                        # zone offsets are multiples of 15 min
ZONE_SLACK_S = 90                        # |step - k*15min| <= 90 s  ->  a time-zone change
EDGE_S = 10.0                            # a segment may be extrapolated this far past its first/last reading
SYNC_WINDOW_S = 120.0                    # without positions, a step this soon after the first reading is a clock correction
CUT_MIN_M = 200.0                        # a position jump larger than this ...
MAX_SPEED_MS = 50.0                      # ... and faster than 180 km/h means the footage was cut
POS_GAP_S = 30.0                         # positions further apart than this in time can't judge a step


def _secs(local: dt.datetime) -> float:
    return (local - EPOCH).total_seconds()


def _dist_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(a))


@dataclass
class Segment:
    t_first: float                       # first / last reading (driving seconds)
    t_last: float
    base: float                          # local clock at t=0, seconds from EPOCH
    zone_h: float = 0.0                  # UTC offset of this segment, hours
    step_in: str = "start"               # "start" | "tz" | "sync" | "cut"
    lo: float = 0.0                      # coverage in driving seconds (set by fit)
    hi: float = 0.0
    pos_first: tuple[float, float, float] | None = None   # (t, lat, lon), median of the first 3 positioned readings
    pos_last: tuple[float, float, float] | None = None    # the same for the last 3


@dataclass
class ClockFit:
    segments: list[Segment] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return bool(self.segments)

    def at(self, t: float):
        """(local, utc, zone_h) from the fitted clock, or None if t is not covered."""
        for s in self.segments:
            if s.lo <= t < s.hi:
                local = EPOCH + dt.timedelta(seconds=s.base + t)
                return local, local - dt.timedelta(hours=s.zone_h), s.zone_h
        return None


def _median_pos(points):
    if not points:
        return None
    return (statistics.median(p[0] for p in points), statistics.median(p[1] for p in points),
            statistics.median(p[2] for p in points))


def _moved(a: Segment, b: Segment) -> tuple[bool | None, float | None]:
    """Did the vehicle jump between segment a and segment b? None if positions can't tell."""
    if not a.pos_last or not b.pos_first:
        return None, None
    gap = b.pos_first[0] - a.pos_last[0]
    if gap > POS_GAP_S:
        return None, None
    m = _dist_m(a.pos_last[1], a.pos_last[2], b.pos_first[1], b.pos_first[2])
    return m > max(CUT_MIN_M, MAX_SPEED_MS * gap), m


def fit_stamp_clock(readings, zone_start_h: float) -> ClockFit:
    """readings: (t, stamp local datetime) or (t, local, lat, lon), t in driving seconds, for every
    stamp whose date/time parsed. lat/lon may be None. Positions let a step be told apart from a cut."""
    pos = {r[0]: (r[2], r[3]) for r in readings if len(r) >= 4 and r[2] is not None and r[3] is not None}
    obs = sorted((r[0], _secs(r[1]) - r[0]) for r in readings)
    if len(obs) < MIN_RUN:
        return ClockFit(events=[f"clock fit failed: {len(obs)} readings"])
    # 1. clock levels: 1-D clusters of offsets, split where neighbours differ by > TOL_S
    vals = sorted(o for _, o in obs)
    clusters, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] > TOL_S:
            clusters.append(cur); cur = [v]
        else:
            cur.append(v)
    clusters.append(cur)
    levels = [(c[0], c[-1]) for c in clusters if len(c) >= MIN_RUN]
    def level(o):
        return next((k for k, (a, b) in enumerate(levels) if a <= o <= b), None)
    # 2. runs in time order; isolated readings of another level (< MIN_RUN in a row) are outliers
    runs: list[list[tuple[float, float]]] = []
    labels: list[int | None] = []
    for t, o in obs:
        k = level(o)
        if k is None:
            continue
        if labels and labels[-1] == k:
            runs[-1].append((t, o))
        else:
            runs.append([(t, o)]); labels.append(k)
    keep = [(r, k) for r, k in zip(runs, labels) if len(r) >= MIN_RUN]
    merged: list[tuple[list, int]] = []
    for r, k in keep:                                   # same level again after dropped outliers -> same segment
        if merged and merged[-1][1] == k:
            merged[-1][0].extend(r)
        else:
            merged.append((list(r), k))
    if not merged:
        return ClockFit(events=["clock fit failed: no 3 consistent readings"])
    segs = []
    for r, _ in merged:
        located = [(t, *pos[t]) for t, _ in r if t in pos]
        segs.append(Segment(r[0][0], r[-1][0], statistics.median(o for _, o in r) + 0.5,
                            pos_first=_median_pos(located[:3]), pos_last=_median_pos(located[-3:])))
    fit = ClockFit(segs)
    t0 = obs[0][0]
    # 3. classify each step. A position jump means a cut; otherwise a 15-min multiple is a zone change;
    #    otherwise a clock correction, unless it comes late in a video with no positions to judge it.
    jumps: list[float | None] = [None]
    for a, b in zip(segs, segs[1:]):
        d = b.base - a.base
        k = round(d / ZONE_STEP_S)
        moved, m = _moved(a, b)
        jumps.append(m)
        if moved:
            b.step_in = "cut"
        elif k != 0 and abs(d - k * ZONE_STEP_S) <= ZONE_SLACK_S:
            b.step_in = "tz"
        elif moved is False or b.t_first - t0 <= SYNC_WINDOW_S:
            b.step_in = "sync"
        else:
            b.step_in = "cut"
    # 4. clock corrections re-base the earlier segment onto the later (GPS-synced) clock; a cut stops it
    for j in range(len(segs) - 2, -1, -1):
        if segs[j + 1].step_in == "sync":
            fit.events.append(f"clock corrected by {segs[j + 1].base - segs[j].base:+.1f} s at t={segs[j + 1].t_first:.1f} s")
            segs[j].base = segs[j + 1].base
    # 5. zones forward from the start zone; UTC stays continuous across a zone change, not across a cut
    segs[0].zone_h = zone_start_h
    for j, (a, b) in enumerate(zip(segs, segs[1:]), 1):
        if b.step_in == "tz":
            b.zone_h = a.zone_h + round((b.base - a.base) / ZONE_STEP_S) * ZONE_STEP_S / 3600
            fit.events.append(f"time zone {a.zone_h:+.2f} h -> {b.zone_h:+.2f} h at t={b.t_first:.1f} s")
        else:
            b.zone_h = a.zone_h
            if b.step_in == "cut":
                why = f"moved {jumps[j]:.0f} m" if jumps[j] is not None else "no positions, late step"
                fit.events.append(f"cut at t={b.t_first:.1f} s: clock {b.base - a.base:+.1f} s, {why}")
    # 6. coverage: boundaries halfway between segments; ends extrapolated by EDGE_S
    for j, s in enumerate(segs):
        s.lo = s.t_first - EDGE_S if j == 0 else (segs[j - 1].t_last + s.t_first) / 2
        s.hi = s.t_last + EDGE_S if j == len(segs) - 1 else (s.t_last + segs[j + 1].t_first) / 2
    return fit


def per_frame_fallback(frames: list[tuple[float, dt.datetime | None]], zone_h: float):
    """Each frame's own stamp (+0.5 s), kept only if one of its 3 nearest readings on either side
    agrees within 2 s (or by a zone-sized step)."""
    out = []
    for i, (t, loc) in enumerate(frames):
        if loc is None:
            out.append(None); continue
        ok = len([f for f in frames if f[1] is not None]) == 1
        for j in (i - 3, i - 2, i - 1, i + 1, i + 2, i + 3):         # nearest readings on both sides
            if 0 <= j < len(frames) and frames[j][1] is not None:
                d = (_secs(frames[j][1]) - _secs(loc)) - (frames[j][0] - t)
                k = round(d / ZONE_STEP_S)
                if abs(d) <= 2.0 or (k != 0 and abs(d - k * ZONE_STEP_S) <= ZONE_SLACK_S):
                    ok = True
        if ok:
            local = loc + dt.timedelta(seconds=0.5)
            out.append((local, local - dt.timedelta(hours=zone_h), zone_h))
        else:
            out.append(None)
    return out
```

**Validated scenarios.** All pass. They use 180 readings at 1 Hz, with the stamp showing whole seconds of a known clock, a start zone of +1 h, and the start at 2025-03-15 10:56:44 local.

| Scenario | Result |
|---|---|
| Clean | 1 segment. UTC at t = 0.5 s is 09:56:44.5 ± 0.5 s. Covered from −10 s to the last reading + 10 s. |
| 11 isolated OCR errors (±9 s to ±1 h) | 1 segment. UTC exact. |
| Zone +1 h at t = 100 s | 2 segments, step `tz`, zone +1 → +2 h. UTC advances 1 s across the change while local jumps 1 h 0 m 1 s. |
| Daylight saving −1 h at t = 100 s | Zone +1 → 0 h. UTC continuous, and the repeated hour is unambiguous. |
| +45 min step | `tz`: zone 5.75 → 6.5 h. |
| Clock 37 s slow for the first 12 s | Step `sync`. Early frames re-based. Event `clock corrected by +37.0 s at t=12.5 s`. |
| Sync at 12 s, then zone +1 h at 100 s | Steps `start, sync, tz`. UTC continuous throughout. |
| 2 readings, or 30 random offsets | Unresolved, so the per-frame fallback is used. |
| Per-frame fallback | Good frames give `stamp + 0.5 s` and `UTC = local − zone`. A frame misread by 7 min is dropped, even when it sits next to a good frame. |

All of the above also pass with positions on every reading (the vehicle moving north at 20 m/s). New in 1.4:

| Scenario | Result |
|---|---|
| Cut at t = 90 s: clock +2 h 13 min 7 s, position 35 km east | Steps `start, cut`. Nothing re-based: UTC at 50.5 s and at 150.5 s each follow their own clip. Zone stays +1 h. Event `cut at t=90.5 s: clock +7987.0 s, moved 35000 m`. |
| Cut at t = 90 s that looks like a zone change: clock +1 h, position 35 km east | Steps `start, cut`. Zone stays +1 h. |
| Late step with no positions: clock +200 s at t = 150 s | Steps `start, cut`. Event `… no positions, late step`. |
| Late correction with continuous positions: clock 200 s slow until t = 150 s | Steps `start, sync`. Early frames re-based. |
| Zone +1 h at t = 60 s, then a cut at t = 120 s | Steps `start, tz, cut`. Zone +1 → +2 h, kept across the cut. |

### A.8 Time base: normal video and timelapse

Reference implementation of §8.8.

```python
"""Video time vs driving time. Normal video: 1 s of video = 1 s of driving. Timelapse: 1 s of video = speedup s."""
from __future__ import annotations
import statistics
from dataclasses import dataclass

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
```

**Validated checks.** All pass. Playback is 30 fps.

| Check | Result |
|---|---|
| Stamp: 1 fps timelapse (stamp +1 s per frame; 3 clusters of 3 reads at 10, 50 and 90 % of a 60 s file) | `timelapse`, ×30, source `stamp` |
| Stamp: 2 fps timelapse | `timelapse`, ×15 |
| Stamp: normal video, 3 clusters across 180 s | `normal`, ×1 |
| GPS: VIOFO blocks, 1 per video second, fixes 30 s apart | `timelapse`, ×30, source `gps` |
| GPS: fixes 1 s apart | `normal`, ×1 |
| No evidence | `normal`, source `assumed`, with a note |
| Declared timelapse ×30, stamp says normal | Declaration kept, warning written |
| Declared timelapse ×30, stamp agrees | No warning |
| 29.97 fps playback, measured ×29.96 | Snapped to ×29.97 |
| Sample 1 per driving second, 1 fps timelapse, 1800 frames | 1800 frames, every frame. Frame 30: `elapsed` 30 s, video time 1.0 s. |
| 0.5 per driving second | 900 frames, every 2nd frame |
| 5 per driving second | Capped at every frame (1800) |
| Normal 30 fps, 1 per second, 180 frames | Frames 15, 45, 75, …, the same as `frame_times()` |
| Title card: no stamp in the first 10 s of a 1 fps timelapse (new in 1.4) | ×30 from the other clusters |
| Cut between clusters: normal video, clock +3 h at 200 s of 600 (new in 1.4) | `normal`, ×1. One Theil–Sen fit over all 9 reads would say ×12.2. |
| Cut inside one cluster (new in 1.4) | ×1 from the median of the clusters, and a note that the speed-up differs along the file |

**End to end** (`test_pipeline_timelapse.py` scenario). A 90-frame, 30 fps `mp4v` clip whose stamp advances 1 s and 0.00021° per frame:

- 3 stamp reads (1.2 detection; 1.4 reads one cluster of 9 frames in a clip this short) detect `timelapse ×30`, with a 1.0 s capture interval;
- sequential decoding and seeking by frame number each read the right stamp on 10 of 10 test frames;
- 30 graded frames (every 3rd) were OCR'd in 3.9 s;
- the clock fit on driving time gives one segment, with no events. Frame 31: `elapsed` 31 s, video time 1.033 s, local 10:57:15.5 (captured at 10:57:15);
- per-frame stamp latitudes are exact.

The same readings fed to the 1.1 clock fit, on video time, produced `clock fit failed: no 3 consistent readings`.
