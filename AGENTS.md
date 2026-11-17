# Agent notes

- `track_profile_2_web.py` contains QGIS integration and exports;
  `track_profile_2_web.html` contains the preview UI and map behavior.
- Keep changes focused and avoid adding dependencies without need.
- Run the relevant Behave scenarios described in [README.md](README.md);
  QGIS scenarios require the QGIS Python environment.
- Release packaging includes only the files listed in `.github/workflows/cd.yml`.
