# Price-List-Query-Backend
Backend for the price list web site

GOTO https://www.pythonguis.com/ to know about build process

## TODO
- add settings.json to edit dblocation
- add automatic sync settings
- add Number of items updated toast/info to be shown after updating.
- add option to enter custom time
- add option to update or rewrite whole db
- add option to image rewrite.

## Release Flow
- Trigger the `Version Bump` GitHub Actions workflow.
- That workflow updates `app_version.py` and `installer.nsi`, commits the change, and creates the matching `vX.Y.Z` tag.
- Pushing that tag automatically triggers `Build Windows Release`.
- `Build Windows Release` builds `dist/Price List Update.exe` and `Price List Update-installer.exe`, then uploads them to the GitHub release for that tag.
