# Output

Results land here. Git ignores everything in this folder except this README.

| Folder | Written by | Contents |
|---|---|---|
| `Output/<YYYYMMDD-HHMMSS>[_label]/` | The app's export (from Phase 1) and `python -m smartroad.export` | One run: `detections.csv`, `frames.csv`, `videos.csv`, `run.json`, `run.log`, the saved frames and the per-video part files (spec §6). |
| `Output/probe/` | `scripts/probe_dashcam.py` | `phase0_report.md`, and per clip `probe.json`, ExifTool's output, stamp crops and geometry hints. |

**What is safe to share:**

- `phase0_report.md` and the CSVs: the stamp text is masked to date, time, position and speed,
  so they don't show the plate. They do show positions.
- Saved frames and `Output/probe/*/crops/`: no. The burned-in stamp shows the plate and the
  custom text.

Point the code at another folder with `SMARTROAD_OUTPUT=/path/to/results`. Old runs can be
deleted at any time; nothing else refers to them.
