# Input

Put the footage to process here. Git ignores everything in this folder except this README, so
clips, which show your licence plate and your route, are never committed.

| What | Where | Notes |
|---|---|---|
| VIOFO clips | `Input/viofo/` | From the card's `DCIM/Movie` folder, as recorded: the camera's file names (`2025_0315_105644_0012F.MP4`) carry the start time and the camera (`F` front, `R` rear). |
| VIOFO timelapse clips | `Input/viofo-timelapse/` | Keep them apart from normal clips so they're easy to run as their own batch. |
| Garmin clips | `Input/garmin/` | Original `GRMNnnnn.MP4` files, or videos downloaded from YouTube. |
| GPX tracks | `Input/gpx/` | From a GPS logger, if the clips have no GPS of their own. |

Subfolders are only a suggestion: everything under `Input/` is read, subfolders included.
Camera settings apply to a whole run, so cameras mounted differently go in separate subfolders
and run as separate batches.

**Footage on another drive.** Dashcam footage runs to hundreds of gigabytes. Link it instead of
copying it, for example:

```bash
ln -s /media/$USER/DASHCAM/DCIM/Movie Input/viofo
```

or point the code at another folder with `SMARTROAD_INPUT=/path/to/footage`.

**Who reads it:**

- `scripts/probe_dashcam.py`, with no arguments, probes every video in `Input/` (Phase 0).
- The app (from Phase 1) offers the videos in `Input/` under Drive video → Local file, and uses
  `Input/` as the default Batch folder (spec §5.1, §6.0).
