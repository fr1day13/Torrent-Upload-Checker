This is made as a redesign of the UNIT3D Upload Checker to include different trackers and make the check process better.
For now its a working alpha version.

Main change of this branche is now, that i integrated the prowlarr api as a way to search trackers.


# Changes
- Added Prowlarr-backed Torznab search support
- Added Gazelle API as usable tracker
- Added BeyondHD
- Added Morethantv as Luminance tracker
- Added hardlinking functionality
- Search counter

With the included gazelle and luminance tracker search, other trackers like that can be added by addint those into the tracker_info.json and adding the tags to settings.py as well as check.py for UA and GG.
... more to follow 

# Features

- Scan directories for movies (.mkv only)
- Parse filenames then search on TMDB
- Use TMDB id + resolution (if found) to search trackers for unique movies
- Ability to ignore groups, qualities, and other keywords.
- Scan the file with mediainfo to ensure either English audio or English subtitles.
- Export possible uploads to gg-bot commands and .txt or .csv files

## Sites Supported

- Aither
- Blutopia
- FearNoPeer
- LST
- OnlyEncodes
- ReelFliX
- Upload.cx
- Rastastugan
- HomieHelpDesk

Any UNIT3D trackers can be supported by adding the necessary info.

## Quick Start
1. install
2. set trackers to use (prowlarr search is recommended)
3. set hardlink folder (highly recommended if the files are not already seperated)
4. run the search

```sh
git clone https://github.com/fr1day13/Torrent-Upload-Checker.git
```

```sh
cd UNIT3D-Upload-Checker
```

```sh
pip install -r requirements.txt
```

```sh
chmod +x check.py
```

### Add Required Settings

directories with files to search

```sh
./check.py setting-add --target dir --set /home/movies/
```

-t and -s accepted (instead of --target and --set)

Add tracker key or keys: (aith, blu, fnp, rfx)

```sh
./check.py setting-add -t blu -s <api_key>
```

Or use Prowlarr as the tracker search backend:

```sh
./check.py setting-add -t prowlarr_url -s http://localhost:9696
./check.py setting-add -t prowlarr_api_key -s <prowlarr_api_key>
./check.py setting-add -t prowlarr_indexer:blu -s <prowlarr_indexer_id>
```

The Prowlarr indexer ID is the numeric ID from the indexer's Torznab URL, for example `http://localhost:9696/1/api`.

Prowlarr searches run in this order:

```text
TMDB ID
title + year + release group
title + year
```

Both the parsed file year and the TMDB release year are used when they differ, because trackers can index either year.

Set the hardlink output folder:

```sh
./check.py setting-add -t hardlink_output_folder -s /home/uploads/
```

The folder is created when the setting is added. Hardlinks are written below it by tracker and section, for example `blu/safe`.

Enable sites:

```sh
./check.py setting-add -t sites -s blu
```

Trackers still need to be enabled with `sites` after adding either a direct tracker API key or a Prowlarr indexer ID. This list controls which trackers are searched.

Your TMDB api key.

```sh
./check.py setting-add -t tmdb -s <api_key>
```

run all

```sh
./check.py run-all -v
```

## Example Outputs

### CSV

![csv output](https://i.ibb.co/SmkvfV1/2024-04-03-19-38-21.png)

### TXT

<https://github.com/frenchcutgreenbean/UNIT3D-Upload-Checker/blob/main/manual_txt_example.txt>

### GG

<https://github.com/frenchcutgreenbean/UNIT3D-Upload-Checker/blob/main/manual_bot_example.txt>

## Accepted commands

| Command | Description| Flags |
|---------|------------|-------|
| run-all | Runs all scanning, searching, and exporting functions. | -v -m |
| setting | Prints a given setting's value.| |
| setting-add | Adds or edits a setting. | |
| setting-rm | Only works on lists, returns prompt to remove specific value. | |

*-v and -m only affect certain functions; see below.*

### Examples

```sh
./check.py setting -t dir
['/home/user/media/'] 
```

```sh
./check.py setting-add -t dir -s /home/user/movies
/home/user/movies/  Successfully added to  directories
```

```sh
./check.py setting-rm -t dir
Which option would you like to remove? ['/home/user/media/', '/home/user/movies/']
Type in the number of the option you want to remove:
0 being the first option, 1 being the second option, etc.
0
Removed: /home/user/media/
```

### Manually run the commands in run-all

| Command | Description | Flags |
|---------|----------|-------|
| scan | Scans directories in main.py| -v |
| tmdb | Searches TMDB for found movies| -v |
| search | Searches trackers by TMDB id|-v |
| save | Creates search_data.json| -m |
| gg | Creates gg auto_upload commands txt file| |
| txt | Creates txt file with useful information | |
| csv | Creates CSV file with useful information | |

-m or --mediainfo This will disable scanning with mediainfo. *Not recommended*.

-v or --verbose Prints more stuffs.

## FAQ

Q: What puts a movie in "safe"?

- A: If the file does not exist on the tracker, or the resolution is new.

Q: What puts a movie in "risky"?

- A: The movie exists on the tracker, but the quality is new. e.g. web-dl, remux, etc.

Q: What puts a movie in "danger"?

- A: There are multiple reasons why the movie gets put in "danger".

- 1: The year from the filename is different to the one matched on TMDB.

- 2: Mediainfo couldn't find English language subtitles or audio.

- 3: The movie exists on the tracker, but quality couldn't be extracted from filename.

Q: Why is tracker x not supported?

- A: I only added trackers I am on. Pull requests are welcomed!

Q: How can I add support for different UNIT3D trackers?

- A: First you need to edit tracker_info.json. Then, append the relevant details in settings.py. self.tracker_nicknames & self.default_settings["keys"]

## Reference Repositories

- Prowlarr: <https://github.com/Prowlarr/Prowlarr>
- cross-seed: <https://github.com/cross-seed/cross-seed>
