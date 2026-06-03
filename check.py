#!/usr/bin/env python3
import os
import re
import csv
import glob
import sys
import traceback
from PTN.parse import PTN
import json
import requests
from thefuzz import fuzz
import time
import math
import argparse
from mediainfo import get_media_info, format_media_info
from settings import Settings
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

# For gg-bot -t flag and Upload Assistant --trackers flag.
# LEFT SIDE = internal tracker name from tracker_info.json / settings.json
# RIGHT SIDE = tracker code expected by gg-bot / Upload Assistant
TRACKER_MAP = {
    "aither": "ATH",
    "blutopia": "BLU",
    "fearnopeer": "FNP",
    "reelflix": "RFX",
    "lst": "LST",
    "onlyencodes": "OE",
    "ulcx": "ULCX",
    "yuscene": "YUS",
    "beyondhd": "BHD",
    "morethantv": "MTV",
    "zenith": "ZNTH",
    "midnightscene": "MNS",
    "greatposterwall": "GPW",
}


class UploadChecker:
    def __init__(self):
        self.settings = Settings()
        self.update_settings()
        self.tracker_info = self.settings.tracker_info

        self.output_folder = "./outputs/"
        self.data_folder = "./data/"

        os.makedirs(self.output_folder, exist_ok=True)
        os.makedirs(self.data_folder, exist_ok=True)

        self.scan_data = {}
        self.search_data = {}
        self.request_timeout = (10, 45)
        self.term_size = shutil.get_terminal_size((120, 20))
        self.extract_filename = re.compile(r"^.*[\\\/](.*)")

        try:
            for tracker in self.enabled_sites:
                self.search_data[tracker] = {
                    "safe": {},
                    "risky": {},
                    "danger": {},
                }
        except Exception as e:
            print("Error loading enabled sites ", e)

        try:
            self.database_location = f"{self.data_folder}database.json"
            self.search_data_location = f"{self.data_folder}search_data.json"

            if not os.path.exists(self.database_location):
                with open(self.database_location, "w") as outfile:
                    json.dump({}, outfile)

            if not os.path.exists(self.search_data_location):
                with open(self.search_data_location, "w") as outfile:
                    json.dump(self.search_data, outfile)

        except Exception as e:
            print("Error initializing json files: ", e)

        try:
            if os.path.getsize(self.database_location) > 10:
                with open(self.database_location, "r") as file:
                    self.scan_data = json.load(file)

            if os.path.getsize(self.search_data_location) > 10:
                with open(self.search_data_location, "r") as file:
                    self.search_data = json.load(file)

            self.ensure_search_data_trackers()

        except Exception as e:
            print("Error loading json files: ", e)

    def scan_directories(self, verbose=False):
        try:
            print("Scanning Directories")

            if not self.directories:
                print("Please add a directory")
                print("setting-add -t dir -s <dir>")
                return False

            for directory in self.directories:
                if directory in self.scan_data:
                    dir_data = self.scan_data[directory]
                else:
                    dir_data = {}

                files = glob.glob(f"{directory}**\\*.mkv", recursive=True) or glob.glob(
                    f"{directory}**/*.mkv", recursive=True
                )

                for f in files:
                    if verbose:
                        print("=" * self.term_size.columns)
                        print(f"Scanning: {f}")

                    file_location = f
                    file_name = self.extract_filename.match(f).group(1)
                    bytes_size = os.path.getsize(f)
                    file_size = self.convert_size(bytes_size)

                    if verbose:
                        print("File size: ", file_size)

                    if file_name in dir_data:
                        parsed_existing = parse_file(file_name)
                        existing_group = (
                            parsed_existing["group"]
                            if "group" in parsed_existing
                            else self.extract_group_from_name(file_name)
                        )
                        existing_group = self.normalize_group(existing_group)

                        if existing_group and dir_data[file_name].get("group") != existing_group:
                            dir_data[file_name]["group"] = existing_group
                            if verbose:
                                print(file_name, "Group backfilled:", existing_group)

                        if verbose:
                            print(file_name, "Already exists in database.")
                        continue

                    parsed = parse_file(file_name)

                    group = (
                        parsed["group"]
                        if "group" in parsed
                        else self.extract_group_from_name(file_name)
                    )
                    group = self.normalize_group(group)

                    banned = False
                    codec = parsed["codec"] if "codec" in parsed else None
                    year = str(parsed["year"]).strip() if "year" in parsed else ""
                    title = parsed["title"].strip() if "title" in parsed else file_name
                    year_in_title = re.search(r"\d{4}", title)

                    if year_in_title and not year:
                        year = year_in_title.group().strip()
                        title = re.sub(r"[\d]{4}", "", title).strip()
                        if verbose:
                            print("Year manually added from title: ", title, year)

                    quality = (
                        re.sub(r"[^a-zA-Z]", "", parsed["quality"]).strip()
                        if "quality" in parsed
                        else None
                    )
                    quality = quality.lower() if quality else None

                    if quality == "bluray":
                        quality = "encode"
                    elif quality == "web":
                        quality = "webrip"

                    resolution = parsed["resolution"].strip() if "resolution" in parsed else None

                    if group and group in self.banned_groups:
                        if verbose:
                            print(group, "Is flagged for banning. Banned")
                        banned = True
                    elif bytes_size < (self.minimum_size * 1024) * 1024:
                        if verbose:
                            print(file_size, "Is below accepted size. Banned")
                        banned = True
                    elif "season" in parsed or "episode" in parsed:
                        if verbose:
                            print(file_name, "Is flagged as tv. Banned")
                        banned = True
                    elif quality and quality in self.ignore_qualities:
                        if verbose:
                            print(quality, "Is flagged for banning. Banned")
                        banned = True
                    elif (
                        resolution
                        and codec
                        and "265" in codec
                        and "2160" not in resolution
                        and quality == "encode"
                    ):
                        if verbose:
                            print(resolution, "@", codec, "Is flagged for banning. Banned")
                        banned = True

                    if "excess" in parsed:
                        for kw in self.ignore_keywords:
                            if kw.lower() in (excess.lower() for excess in parsed["excess"]):
                                if verbose:
                                    print("Keyword ", kw, "Is flagged for banning. Banned")
                                banned = True
                                break

                    dir_data[file_name] = {
                        "file_location": file_location,
                        "file_name": file_name,
                        "file_size": file_size,
                        "title": title,
                        "quality": quality,
                        "resolution": resolution,
                        "year": year,
                        "tmdb": None,
                        "banned": banned,
                        "group": group,
                    }

                    if verbose and not banned:
                        print(dir_data[file_name])

                self.scan_data[directory] = dir_data
                self.save_database()

        except Exception as e:
            print("Error scanning directories: ", e)
            print(traceback.format_exc())

    def get_tmdb(self, verbose=False):
        try:
            if not self.scan_data:
                print("Please scan directories first")
                return False

            print("Searching TMDB")

            if not self.tmdb_key:
                print("Please add a TMDB key")
                print("setting-add -t tmdb -s <key>")
                return False

            for directory in self.scan_data:
                if verbose:
                    print("Searching files from: ", directory)

                for key, value in self.scan_data[directory].items():
                    if value.get("banned"):
                        continue

                    if value.get("tmdb"):
                        if verbose:
                            print(value["title"], " Already searched on TMDB.")
                        continue

                    title = value["title"]

                    if verbose:
                        print("=" * self.term_size.columns)
                        print(f"Searching TMDB for {title}")

                    year = value["year"] if value.get("year") else ""
                    year_url = f"&year={year}" if year else ""
                    clean_title = re.sub(r"[^0-9a-zA-Z]", " ", title)
                    query = clean_title.replace(" ", "%20")

                    try:
                        url = (
                            "https://api.themoviedb.org/3/search/movie"
                            f"?query={query}&include_adult=false&language=en-US&page=1"
                            f"&api_key={self.tmdb_key}{year_url}"
                        )
                        res = requests.get(url, timeout=self.request_timeout)
                        data = json.loads(res.content)
                        results = data["results"] if "results" in data else None

                        if not results:
                            if verbose:
                                print("No results, Banning.")
                            value["banned"] = True
                            self.save_database()
                            continue

                        for r in results:
                            if "vote_count" in r and (r["vote_count"] == 0 or r["vote_count"] <= 5):
                                value["banned"] = True
                                self.save_database()
                                continue

                            tmdb_title = r["title"]
                            tmdb_year = (
                                re.search(r"\d{4}", r["release_date"]).group().strip()
                                if r.get("release_date")
                                else None
                            )
                            match = fuzz.ratio(tmdb_title, clean_title)

                            if verbose:
                                print("attempting to match result: ", tmdb_title, "with: ", title)

                            if match >= 85:
                                value["tmdb"] = r["id"]
                                value["tmdb_title"] = tmdb_title
                                value["tmdb_year"] = tmdb_year
                                if verbose:
                                    print("Match successful")
                                break

                        if verbose and not value.get("tmdb"):
                            print("Couldn't find a match.")

                    except Exception as e:
                        print(f"Something went wrong when searching TMDB for {title}", e)
                        print(traceback.format_exc())

                self.save_database()

            self.save_database()

        except Exception as e:
            print("Error searching TMDB: ", e)
            print(traceback.format_exc())

    ###########################################################################
    # API search handlers for different tracker layouts.
    ###########################################################################

    def search_unit3d_tracker(self, tracker, key, tmdb):
        url = self.tracker_info[tracker]["url"]
        url = f"{url}api/torrents/filter?tmdbId={tmdb}&categories[]=1&api_token={key}"

        response = requests.get(url, timeout=self.request_timeout)
        response.raise_for_status()

        res_data = response.json()
        raw_results = res_data["data"] if res_data.get("data") else []

        results = []

        for result in raw_results:
            info = result.get("attributes", {})
            name = info.get("name")
            group = (
                info.get("group")
                or info.get("release_group")
                or info.get("releaseGroup")
                or self.extract_group_from_name(name)
            )

            results.append({
                "resolution": info.get("resolution") or self.extract_resolution_from_name(name),
                "quality": info.get("type") or self.extract_quality_from_name(name),
                "name": name,
                "url": info.get("details_link") or info.get("url"),
                "group": self.normalize_group(group),
            })

        return results

    def search_bhd_tracker(self, tracker, key, tmdb):
        base_url = self.tracker_info[tracker]["url"].rstrip("/")
        url = f"{base_url}/api/torrents/{key}"

        payload = {
            "action": "search",
            "tmdb_id": f"movie/{tmdb}",
            "categories": "Movies",
            "sort": "created_at",
            "order": "desc",
        }

        response = requests.post(url, data=payload, timeout=self.request_timeout)
        response.raise_for_status()
        res_data = response.json()

        if not res_data.get("success"):
            raise RuntimeError(f"BHD API error: {res_data}")

        raw_results = res_data.get("results") or []
        results = []

        for result in raw_results:
            name = result.get("name")
            group = (
                result.get("group")
                or result.get("release_group")
                or result.get("releaseGroup")
                or self.extract_group_from_name(name)
            )

            results.append({
                "resolution": result.get("type") or self.extract_resolution_from_name(name),
                "quality": result.get("source") or self.extract_quality_from_name(name) or result.get("type"),
                "name": name,
                "url": result.get("url"),
                "category": result.get("category"),
                "size": result.get("size"),
                "seeders": result.get("seeders"),
                "group": self.normalize_group(group),
            })

        return results

    def get_torznab_attr(self, item, name):
        namespace = "{http://torznab.com/schemas/2015/feed}"
        for attr in item.findall(f"{namespace}attr"):
            if attr.get("name") == name:
                return attr.get("value")
        return None

    def extract_resolution_from_name(self, name):
        if not name:
            return None

        match = re.search(r"\b(2160p|1080p|720p|576p|480p)\b", str(name), re.IGNORECASE)
        return match.group(1) if match else None

    def extract_quality_from_name(self, name):
        if not name:
            return ""

        patterns = [
            ("remux", r"\bremux\b"),
            ("bluray", r"\bblu[ ._-]?ray\b|\bbd\b"),
            ("webdl", r"\bweb[ ._-]?dl\b|\bwebdl\b"),
            ("webrip", r"\bweb[ ._-]?rip\b|\bwebrip\b"),
            ("web", r"\bweb\b"),
            ("hdtv", r"\bhdtv\b"),
            ("dvd", r"\bdvd\b|\bdvdrip\b"),
        ]

        name = str(name)

        for quality, pattern in patterns:
            if re.search(pattern, name, re.IGNORECASE):
                if quality == "bluray":
                    return "encode"
                if quality == "web":
                    return "webrip"
                return quality

        return ""

    def normalize_group(self, group):
        if not group:
            return None

        group = str(group).strip().strip(" ._-").lower()
        group = re.sub(r"[^a-z0-9]+", "", group)

        return group if group else None

    def extract_group_from_name(self, name):
        if not name:
            return None

        name = str(name).strip()

        # Standard release suffix: Movie.Name.2020.1080p.WEB-DL-GROUP
        match = re.search(r"-([A-Za-z0-9][A-Za-z0-9._-]*)$", name)

        if not match:
            return None

        return self.normalize_group(match.group(1))

    def release_groups_match(self, file_group, tracker_group=None, tracker_name=None):
        file_group = self.normalize_group(file_group)

        if not file_group:
            return False

        tracker_group = self.normalize_group(tracker_group)

        if tracker_group and file_group == tracker_group:
            return True

        # Fallback for APIs that do not expose a group field.
        if tracker_name:
            extracted = self.extract_group_from_name(tracker_name)
            if extracted and extracted == file_group:
                return True

        return False

    def section_for_tracker_message(self, info):
        if isinstance(info, bool):
            return "safe" if info is False else None

        message = str(info)

        if "Possible" in message:
            return "safe"

        if "upgrade" in message:
            return "safe"

        if "recommended" in message:
            return "risky"

        return None

    def search_torznab_tracker(self, tracker, key, tmdb):
        info = self.tracker_info[tracker]
        base_url = info["url"].rstrip("/") + "/"
        torznab_path = info.get("torznab_path", "api/torznab")
        url = urljoin(base_url, torznab_path)

        params = {
            "apikey": key,
            "t": "movie",
            "tmdbid": tmdb,
            "cat": info.get("torznab_movie_categories", "2000,2030,2040,2045,2050"),
        }

        response = requests.get(url, params=params, timeout=self.request_timeout)
        response.raise_for_status()

        root = ET.fromstring(response.content)

        error = root.find("error")
        if error is not None:
            code = error.get("code")
            description = error.get("description")
            raise RuntimeError(f"Torznab API error {code}: {description}")

        results = []

        for item in root.findall("./channel/item"):
            title = item.findtext("title") or ""
            link = item.findtext("comments") or item.findtext("guid") or item.findtext("link")
            size = item.findtext("size") or self.get_torznab_attr(item, "size")
            seeders = self.get_torznab_attr(item, "seeders")
            leechers = self.get_torznab_attr(item, "leechers")
            info_hash = self.get_torznab_attr(item, "infohash")

            results.append({
                "resolution": self.extract_resolution_from_name(title),
                "quality": self.extract_quality_from_name(title),
                "name": title,
                "url": link,
                "size": int(size) if size else None,
                "seeders": int(seeders) if seeders else None,
                "leechers": int(leechers) if leechers else None,
                "info_hash": info_hash,
                "group": self.extract_group_from_name(title),
            })

        return results

    def search_gazelle_tracker(self, tracker, key, tmdb, title=None, year=None):
        info = self.tracker_info[tracker]

        base_url = info["url"].rstrip("/") + "/"
        gazelle_path = info.get("gazelle_path", "ajax.php")

        login_url = urljoin(base_url, "login.php")
        api_url = urljoin(base_url, gazelle_path)

        searchstr = title or str(tmdb)

        gazelle_auth = self.current_settings.get("gazelle_auth", {}).get(tracker, {})
        username = gazelle_auth.get("username")
        password = gazelle_auth.get("password")

        session = requests.Session()

        if username and password:
            login_payload = {
                "username": username,
                "password": password,
            }

            login_response = session.post(login_url, data=login_payload, allow_redirects=True,timeout=self.request_timeout)
            login_response.raise_for_status()

        params = {
            "action": "browse",
            "searchstr": searchstr,
        }

        if year:
            params["year"] = year

        # it seems that only some gazelle trackers are using API keys as query parameters, while others expect them in headers or not at all.
        ######
        if key:
            params["apikey"] = key

        response = session.get(api_url, params=params, allow_redirects=True, timeout=self.request_timeout)
        response.raise_for_status()

        if "login.php" in response.url:
            raise RuntimeError(
                f"Gazelle login failed or cookie not accepted for {tracker}. "
                f"Redirected to login.php. Check username/password/API key."
            )

        try:
            res_data = response.json()
        except Exception:
            preview = response.text[:300].replace("\n", " ")
            raise RuntimeError(
                f"Gazelle did not return JSON. "
                f"Status={response.status_code}, "
                f"Content-Type={response.headers.get('content-type')}, "
                f"URL={response.url}, "
                f"Preview={preview}"
            )

        if res_data.get("status") != "success":
            raise RuntimeError(f"Gazelle API error: {res_data}")

        groups = res_data.get("response", {}).get("results") or []

        results = []

        for group in groups:
            group_name = group.get("groupName") or ""
            group_year = group.get("groupYear")

            for torrent in group.get("torrents", []):
                media = torrent.get("media") or ""
                fmt = torrent.get("format") or ""
                encoding = torrent.get("encoding") or ""
                remaster_title = torrent.get("remasterTitle") or ""
                remaster_year = torrent.get("remasterYear") or ""

                name_parts = [
                    group_name,
                    str(group_year) if group_year else "",
                    str(remaster_year) if remaster_year else "",
                    remaster_title,
                    media,
                    fmt,
                    encoding,
                ]

                name = " ".join(part for part in name_parts if part)

                results.append({
                    "resolution": self.extract_resolution_from_name(name),
                    "quality": self.extract_quality_from_name(name),
                    "name": name,
                    "url": urljoin(
                        base_url,
                        f"torrents.php?id={group.get('groupId')}&torrentid={torrent.get('torrentId')}"
                    ),
                    "size": torrent.get("size") or torrent.get("data"),
                    "seeders": torrent.get("seeders"),
                    "leechers": torrent.get("leechers"),
                    "group": self.extract_group_from_name(name),
                })

        return results

    def search_tracker_api(self, tracker, key, tmdb, title=None, year=None):
        api_type = self.tracker_info[tracker].get("api_type", "unit3d")

        if api_type == "bhd":
            return self.search_bhd_tracker(tracker, key, tmdb)

        if api_type == "torznab":
            return self.search_torznab_tracker(tracker, key, tmdb)

        if api_type == "gazelle":
            return self.search_gazelle_tracker(tracker, key, tmdb, title, year)

        return self.search_unit3d_tracker(tracker, key, tmdb)

    def search_trackers(self, verbose=False):
        try:
            print("Searching trackers")

            for tracker in self.enabled_sites:
                api_key = self.current_settings["keys"].get(tracker)
                if not api_key:
                    print(f"No API key for {tracker} found.")
                    print("If you want to use this tracker, add an API key to the settings.")
                    if not input("Continue? [y/n] ").lower().startswith("y"):
                        return False

            search_items = []

            for directory in self.scan_data:
                for file_key, value in self.scan_data[directory].items():
                    if value.get("banned"):
                        continue

                    if value.get("tmdb") is None:
                        continue

                    existing_trackers = set(value.get("trackers", {}).keys())
                    remaining_trackers = [
                        t for t in self.enabled_sites
                        if t not in existing_trackers
                    ]

                    if not remaining_trackers:
                        continue

                    search_items.append((directory, file_key, value, remaining_trackers))

            total_items = len(search_items)

            if total_items == 0:
                print("No files left to search.")
                return

            for current_index, (directory, key, value, remaining_trackers) in enumerate(search_items, start=1):
                print("=" * self.term_size.columns)
                print(f"[{current_index}/{total_items}] Searching Trackers for {value['title']}")

                if verbose:
                    print(f"Filename: {value['file_name']}")

                    tmdb = value["tmdb"]
                    quality = value["quality"] if value.get("quality") else None
                    resolution = value["resolution"] if value.get("resolution") else None
                    file_group = self.normalize_group(value.get("group"))

                    if not file_group:
                        file_name_for_group = value.get("file_name") or ""
                        parsed_group = parse_file(file_name_for_group).get("group") if file_name_for_group else None
                        file_group = self.normalize_group(
                            parsed_group or self.extract_group_from_name(file_name_for_group)
                        )

                        if file_group:
                            value["group"] = file_group

                    if "trackers" not in value:
                        value["trackers"] = {}

                    try:
                        for tracker in remaining_trackers:
                            try:
                                if tracker in value["trackers"]:
                                    if verbose:
                                        print(
                                            f"{self.output_folder}{tracker} already searched. "
                                            f"For {value['title']} Skipping."
                                        )
                                    continue

                                tracker_key = self.current_settings["keys"].get(tracker)
                                if not tracker_key:
                                    print(f"No API key for {tracker} found. Skipping.")
                                    continue

                                results = self.search_tracker_api(
                                    tracker,
                                    tracker_key,
                                    tmdb,
                                    title=value.get("tmdb_title") or value.get("title"),
                                    year=value.get("tmdb_year") or value.get("year"),
                                )

                                tracker_message = None

                                if results and not self.allow_dupes:
                                    print("Duplicate results detected and allow_dupes is set to False. Banning.")
                                    value["trackers"][tracker] = True
                                    continue

                                if results:
                                    loop_results = []

                                    for i, result in enumerate(results):
                                        dupe_res = False
                                        dupe_quality = False
                                        dupe_group = False

                                        tracker_resolution = result.get("resolution")
                                        tracker_quality = re.sub(
                                            r"[^a-zA-Z]",
                                            "",
                                            result.get("quality") or "",
                                        ).strip()

                                        tracker_group = self.normalize_group(result.get("group"))
                                        file_group_clean = self.normalize_group(file_group)
                                        tracker_name = result.get("name")

                                        dupe_group = self.release_groups_match(
                                            file_group_clean,
                                            tracker_group,
                                            tracker_name,
                                        )

                                        clean_tracker_resolution = (
                                            "".join(re.findall(r"\d+", tracker_resolution))
                                            if tracker_resolution
                                            else None
                                        )

                                        clean_file_resolution = (
                                            "".join(re.findall(r"\d+", resolution))
                                            if resolution
                                            else None
                                        )

                                        if (
                                            clean_file_resolution
                                            and clean_tracker_resolution
                                            and clean_file_resolution == clean_tracker_resolution
                                        ):
                                            dupe_res = True

                                        # Same resolution + same group = secure duplicate.
                                        if dupe_res and dupe_group:
                                            tracker_message = True
                                            value["trackers"][tracker] = tracker_message
                                            break

                                        if quality and tracker_quality.lower() == quality.lower():
                                            dupe_quality = True

                                        if dupe_res and dupe_quality:
                                            tracker_message = True
                                            value["trackers"][tracker] = tracker_message
                                            break

                                        elif (dupe_res and not quality) or (
                                            quality and dupe_quality and not resolution
                                        ):
                                            tracker_message = (
                                                f"Source was found on {tracker}, but couldn't get enough info "
                                                "from filename. Manual search required."
                                            )
                                            value["trackers"][tracker] = tracker_message
                                            break

                                        elif dupe_res and quality:
                                            loop_message = tracker_quality.lower()
                                            loop_results.append(loop_message)

                                    else:
                                        if loop_results:
                                            is_upgrade = True
                                            for lr in loop_results:
                                                if not self.settings.is_upgrade(quality, lr):
                                                    is_upgrade = False
                                                    break

                                            if is_upgrade:
                                                tracker_message = (
                                                    f"Resolution found on {tracker}, "
                                                    f"but seems like an upgrade. {quality}"
                                                )
                                                value["trackers"][tracker] = tracker_message
                                            else:
                                                tracker_message = (
                                                    f"Resolution found on {tracker}, "
                                                    "but could be a new quality. Manual search recommended."
                                                )
                                                value["trackers"][tracker] = tracker_message
                                        else:
                                            tracker_message = (
                                                f"Possible new release. "
                                                f"{quality if quality else ''} {resolution if resolution else ''}"
                                            )
                                            value["trackers"][tracker] = tracker_message

                                else:
                                    tracker_message = False
                                    value["trackers"][tracker] = tracker_message

                                # Create the hardlink immediately after this tracker has been classified.
                                section = self.section_for_tracker_message(tracker_message)
                                if section:
                                    self.hardlink_single_file(
                                        tracker,
                                        section,
                                        value["file_location"],
                                    )

                                if verbose:
                                    if tracker_message is True:
                                        print(f"Already on {tracker}")
                                    elif tracker_message is False:
                                        print(f"Not on {tracker}")
                                    else:
                                        print(tracker_message)

                            except requests.exceptions.Timeout as e:
                                print(
                                    f"Timeout searching {tracker} for {value['title']}. "
                                    "Search was not cached and will be retried next run."
                                )
                                continue

                            except requests.exceptions.RequestException as e:
                                print(
                                    f"Request error searching {tracker} for {value['title']}: {e}. "
                                    "Search was not cached and will be retried next run."
                                )
                                continue

                            except Exception as e:
                                print(
                                    f"Something went wrong searching {tracker} for {value['title']}: {e}"
                                )
                                print(traceback.format_exc())
                                continue

                        print("Waiting for cooldown...", self.cooldown, "seconds")
                        time.sleep(self.cooldown)

                    except Exception as e:
                        print(f"Something went wrong searching trackers for {value['title']} ", e)
                        print(traceback.format_exc())

                    self.save_database()

            self.save_database()

        except Exception as e:
            print("Error searching tracker: ", e)
            print(traceback.format_exc())

    def ensure_search_data_trackers(self):
        changed = False

        for tracker in self.enabled_sites:
            if tracker not in self.search_data:
                self.search_data[tracker] = {
                    "safe": {},
                    "risky": {},
                    "danger": {},
                }
                changed = True
                print(f"Added missing search_data block for {tracker}")

            for section in ["safe", "risky", "danger"]:
                if section not in self.search_data[tracker]:
                    self.search_data[tracker][section] = {}
                    changed = True

        if changed:
            self.save_search_data()

    def create_search_data(self, mediainfo=True):
        try:
            print("Creating search data.")
            self.ensure_search_data_trackers()

            for directory in self.scan_data:
                for key, value in self.scan_data[directory].items():
                    if value.get("banned"):
                        continue

                    if "trackers" not in value:
                        continue

                    media_info = None

                    try:
                        for tracker, info in value["trackers"].items():
                            self.ensure_search_data_trackers()

                            title = value["title"]
                            year = value.get("year")
                            file_location = value["file_location"]
                            file_size = value["file_size"]
                            quality = value.get("quality")
                            resolution = value.get("resolution")
                            tmdb = value.get("tmdb")
                            tmdb_year = value.get("tmdb_year")

                            extra_info = (
                                "TMDB Release year and given year are different "
                                "this might mean improper match manual search required"
                                if year != tmdb_year
                                else ""
                            )

                            if isinstance(info, bool):
                                if info is False:
                                    message = f"Not on {tracker}"
                                elif info is True:
                                    message = "Dupe!"
                                else:
                                    message = str(info)
                            else:
                                message = str(info)

                            if "Dupe!" in message:
                                continue

                            if mediainfo is True and not media_info:
                                audio_language, subtitles, video_info, audio_info = get_media_info(file_location)

                                if not any(lang.startswith("en") for lang in audio_language) and not any(
                                    sub.startswith("en") for sub in subtitles
                                ):
                                    extra_info += " No English subtitles found in media info"

                                media_info = {
                                    "audio_language(s)": audio_language,
                                    "subtitle(s)": subtitles,
                                    "video_info": video_info,
                                    "audio_info": audio_info,
                                }

                            elif mediainfo is True and media_info:
                                audio_language = media_info["audio_language(s)"]
                                subtitles = media_info["subtitle(s)"]

                                if not any(lang.startswith("en") for lang in audio_language) and not any(
                                    sub.startswith("en") for sub in subtitles
                                ):
                                    extra_info += " No English subtitles found in media info"

                            tracker_info = {
                                "file_location": file_location,
                                "year": year,
                                "quality": quality,
                                "resolution": resolution,
                                "tmdb": tmdb,
                                "tmdb_year": tmdb_year,
                                "message": message.strip(),
                                "file_size": file_size,
                                "extra_info": extra_info.strip(),
                                "media_info": media_info,
                            }

                            if tmdb_year == year:
                                if "English" in extra_info:
                                    self.search_data[tracker]["danger"][title] = tracker_info
                                    continue

                                if isinstance(info, bool) and info is False:
                                    self.search_data[tracker]["safe"][title] = tracker_info
                                    self.hardlink_single_file(tracker, "safe", file_location)
                                    continue

                                if "Possible" in message:
                                    self.search_data[tracker]["safe"][title] = tracker_info
                                    self.hardlink_single_file(tracker, "safe", file_location)
                                    continue

                                if "upgrade" in message:
                                    self.search_data[tracker]["safe"][title] = tracker_info
                                    self.hardlink_single_file(tracker, "safe", file_location)
                                    continue

                                if "required" in message:
                                    self.search_data[tracker]["danger"][title] = tracker_info
                                    continue

                                if "recommended" in message:
                                    self.search_data[tracker]["risky"][title] = tracker_info
                                    self.hardlink_single_file(tracker, "risky", file_location)
                                    continue

                                self.search_data[tracker]["danger"][title] = tracker_info
                                continue

                            else:
                                self.search_data[tracker]["danger"][title] = tracker_info

                    except Exception as e:
                        print("Error creating search_data.json:", e)
                        print(traceback.format_exc())

            self.save_search_data()

        except Exception as e:
            print("Error creating search_data.json", e)
            print(traceback.format_exc())

    def hardlink_single_file(self, tracker, section, file_location):
        try:
            hardlink_output_folder = self.current_settings.get("hardlink_output_folder")

            if not hardlink_output_folder:
                return

            source = Path(file_location)

            if not source.exists():
                print(f"Source file does not exist, skipping hardlink: {source}")
                return

            section_dir = Path(hardlink_output_folder) / tracker / section
            section_dir.mkdir(parents=True, exist_ok=True)

            target = section_dir / source.name

            if target.exists():
                return

            os.link(source, target)
            print(f"Hardlinked [{tracker}/{section}]: {target}")

        except OSError as e:
            print(f"Could not hardlink {file_location}: {e}")

        except Exception as e:
            print(f"Error creating hardlink for {file_location}: {e}")


    def export_hardlinks(self, sections=("safe",), fallback_copy=False):
        try:
            hardlink_output_folder = self.current_settings.get("hardlink_output_folder")

            if not hardlink_output_folder:
                print("No hardlink_output_folder configured. Skipping hardlink export.")
                return

            base_dir = Path(hardlink_output_folder)
            base_dir.mkdir(parents=True, exist_ok=True)

            for tracker in self.enabled_sites:
                data = self.search_data.get(tracker, {})
                tracker_dir = base_dir / tracker
                tracker_dir.mkdir(parents=True, exist_ok=True)

                for section in sections:
                    if section not in data:
                        continue

                    section_dir = tracker_dir / section
                    section_dir.mkdir(parents=True, exist_ok=True)

                    for title, value in data[section].items():
                        source = Path(value["file_location"])

                        if not source.exists():
                            print(f"Source file does not exist, skipping: {source}")
                            continue

                        target = section_dir / source.name

                        if target.exists():
                            print(f"Hardlink already exists, skipping: {target}")
                            continue

                        try:
                            os.link(source, target)
                            print(f"Hardlinked: {target}")

                        except OSError as e:
                            if fallback_copy:
                                shutil.copy2(source, target)
                                print(f"Hardlink failed, copied instead: {target}")
                            else:
                                print(f"Could not hardlink {source} -> {target}: {e}")

        except Exception as e:
            print("Error creating hardlinks:", e)
            print(traceback.format_exc())

    def save_database(self):
        try:
            with open(self.database_location, "w") as of:
                json.dump(self.scan_data, of)
        except Exception as e:
            print("Error writing to database.json: ", e)

    def save_search_data(self):
        try:
            with open(self.search_data_location, "w") as of:
                json.dump(self.search_data, of)
        except Exception as e:
            print("Error writing to search_data.json: ", e)

    def clear_data(self):
        try:
            with open(self.search_data_location, "w") as of:
                json.dump({}, of)
            with open(self.database_location, "w") as of:
                json.dump({}, of)
            print("Data cleared!")
        except Exception as e:
            print("Error clearing json data: ", e)

    def run_all(self, mediainfo=True, verbose=False):
        check_1 = self.scan_directories(verbose)

        if check_1 is False:
            return

        check_2 = self.get_tmdb(verbose)

        if check_2 is False:
            return

        self.search_trackers(verbose)
        self.create_search_data(mediainfo)
        self.export_hardlinks(sections=("safe", "risky"))
        self.export_gg()
        self.export_ua()
        self.export_txt()
        self.export_csv()

    def export_gg(self):
        try:
            os.makedirs(self.output_folder, exist_ok=True)

            for tracker, data in self.search_data.items():
                output_path = f"{self.output_folder}{tracker}_gg.txt"

                with open(output_path, "w") as f:
                    f.write("")

                py_version = "python3" if "linux" in sys.platform else "py"
                tracker_flag = TRACKER_MAP.get(tracker)

                if not tracker_flag:
                    print(f"No TRACKER_MAP entry for {tracker}. Skipping gg export.")
                    continue

                if data.get("safe"):
                    for file, value in data["safe"].items():
                        line = (
                            py_version
                            + " "
                            + f'"{self.gg_path}auto_upload.py" '
                            + "-p "
                            + f'"{value["file_location"]}"'
                            + " -t "
                            + tracker_flag
                        )

                        with open(output_path, "a") as append:
                            append.write(line + "\n")

                print("Exported gg-bot auto_upload commands.", output_path)

        except Exception as e:
            print("Error exporting gg commands:", e)
            print(traceback.format_exc())

    def export_ua(self):
        if not self.ua_path or len(self.ua_path) == 0:
            print("ua_path not configured.")
            return

        os.makedirs(self.output_folder, exist_ok=True)

        for tracker, data in self.search_data.items():
            output_path = f"{self.output_folder}{tracker}_ua.txt"

            with open(output_path, "w") as f:
                py_version = "py" if "win" in sys.platform else "python3"
                tracker_flag = TRACKER_MAP.get(tracker)

                if not tracker_flag:
                    print(f"No TRACKER_MAP entry for {tracker}. Skipping UA export.")
                    continue

                if data.get("safe"):
                    for value in data["safe"].values():
                        line = (
                            py_version
                            + f' "{self.ua_path}upload.py"'
                            + f" --trackers {tracker_flag}"
                            + f' "{value["file_location"]}"\n'
                        )
                        f.write(line)

            print(f"Exported Upload-Assistant commands to {output_path}")

    def export_txt(self):
        try:
            os.makedirs(self.output_folder, exist_ok=True)

            for tracker, data in self.search_data.items():
                output_path = f"{self.output_folder}{tracker}_uploads.txt"

                with open(output_path, "w") as f:
                    f.write("")

                for safety, d in data.items():
                    if d:
                        with open(output_path, "a") as file:
                            file.write(safety + "\n")

                    for k, v in d.items():
                        title = k
                        url_query = title.replace(" ", "%20")
                        file_location = v["file_location"]
                        quality = v["quality"]
                        tmdb = v["tmdb"]
                        info = v["message"]
                        file_size = v["file_size"]
                        extra_info = v["extra_info"] if v["extra_info"] else ""
                        tmdb_year = v["tmdb_year"]
                        year = v["year"]
                        tmdb_search = f"https://www.themoviedb.org/movie/{tmdb}"
                        tracker_url = self.tracker_info.get(tracker, {}).get("url", "")
                        tracker_tmdb = f"{tracker_url}torrents?view=list&tmdbId={tmdb}"
                        tracker_string = f"{tracker_url}torrents?view=list&name={url_query}"
                        media_info = v["media_info"] if "media_info" in v else "None"
                        clean_mi = ""

                        if media_info:
                            audio_language, audio_info, subtitles, video_info = format_media_info(media_info)
                            clean_mi = f"""
            Language(s): {audio_language}
            Subtitle(s): {subtitles}
            Audio Info: {audio_info}
            Video Info: {video_info}
                            """

                        line = f"""
        Movie Title: {title}
        File Year: {year}
        TMDB Year: {tmdb_year}
        Quality: {quality}
        File Location: {file_location}
        File Size: {file_size}
        TMDB Search: {tracker_tmdb}
        String Search: {tracker_string}
        TMDB: {tmdb_search}
        Search Info: {info}
        Extra Info: {extra_info}
        Media Info: {clean_mi}
        """

                        with open(output_path, "a") as f:
                            f.write(line + "\n")

                print(f"Manual info saved to {output_path}")

        except Exception as e:
            print("Error writing uploads.txt: ", e)
            print(traceback.format_exc())

    def export_csv(self):
        try:
            os.makedirs(self.output_folder, exist_ok=True)

            for tracker, data in self.search_data.items():
                output_path = f"{self.output_folder}{tracker}_uploads.csv"

                with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
                    fieldnames = [
                        "Safety",
                        "Movie Title",
                        "TMDB Year",
                        "Extra Info",
                        "Search Info",
                        "Quality",
                        "File Location",
                        "File Size",
                        "TMDB Search",
                        "String Search",
                        "TMDB",
                        "Media Info",
                        "File Year",
                    ]

                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()

                    if data:
                        for safety, d in data.items():
                            for k, v in d.items():
                                title = k
                                url_query = title.replace(" ", "%20")
                                file_location = v["file_location"]
                                quality = v["quality"]
                                tmdb = v["tmdb"]
                                info = v["message"]
                                file_size = v["file_size"]
                                extra_info = v["extra_info"] if v["extra_info"] else ""
                                tmdb_year = v["tmdb_year"]
                                year = v["year"]
                                tmdb_search = f"https://www.themoviedb.org/movie/{tmdb}"
                                tracker_url = self.tracker_info.get(tracker, {}).get("url", "")
                                tracker_tmdb = f"{tracker_url}torrents?view=list&tmdbId={tmdb}"
                                tracker_string = f"{tracker_url}torrents?view=list&name={url_query}"
                                media_info = v["media_info"] if v["media_info"] else "None"
                                clean_mi = ""

                                if media_info:
                                    audio_language, audio_info, subtitles, video_info = format_media_info(media_info)
                                    clean_mi = (
                                        f"Language(s): {audio_language}, "
                                        f"Subtitle(s): {subtitles}, "
                                        f"Audio Info: {audio_info}, "
                                        f"Video Info: {video_info}"
                                    )

                                writer.writerow({
                                    "Safety": safety,
                                    "Movie Title": title,
                                    "File Year": year,
                                    "TMDB Year": tmdb_year,
                                    "Quality": quality,
                                    "File Location": file_location,
                                    "File Size": file_size,
                                    "TMDB Search": tracker_tmdb,
                                    "String Search": tracker_string,
                                    "TMDB": tmdb_search,
                                    "Search Info": info,
                                    "Extra Info": extra_info,
                                    "Media Info": clean_mi,
                                })

                print(f"Manual info saved to {output_path}")

        except Exception as e:
            print("Error writing uploads.csv: ", e)
            print(traceback.format_exc())

    def update_settings(self):
        self.current_settings = self.settings.current_settings
        self.directories = self.current_settings["directories"]
        self.tmdb_key = self.current_settings["tmdb_key"]
        self.enabled_sites = self.current_settings["enabled_sites"]
        self.cooldown = self.current_settings["search_cooldown"]
        self.minimum_size = self.current_settings["min_file_size"]
        self.allow_dupes = self.current_settings["allow_dupes"]
        self.banned_groups = self.current_settings["banned_groups"]
        self.ignore_qualities = self.current_settings["ignored_qualities"]
        self.ignore_keywords = self.current_settings["ignored_keywords"]
        self.gg_path = self.current_settings["gg_path"]
        self.ua_path = self.current_settings["ua_path"]

    def update_setting(self, target, value):
        self.settings.update_setting(target, value)
        self.update_settings()

    def get_setting(self, target):
        setting = self.settings.return_setting(target)
        if setting:
            print(setting)
        else:
            print("Not set yet.")

    def reset_setting(self):
        self.settings.reset_settings()
        self.update_settings()

    def remove_setting(self, target):
        self.settings.remove_setting(target)
        self.update_settings()

    def convert_size(self, size_bytes):
        if size_bytes == 0:
            return "0B"

        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)

        return "%s %s" % (s, size_name[i])


ptn = PTN()


def parse_file(name):
    return ptn.parse(name)


ch = UploadChecker()
parser = argparse.ArgumentParser()

FUNCTION_MAP = {
    "scan": ch.scan_directories,
    "tmdb": ch.get_tmdb,
    "search": ch.search_trackers,
    "save": ch.create_search_data,
    "run-all": ch.run_all,
    "clear-data": ch.clear_data,
    "setting-add": ch.update_setting,
    "setting-rm": ch.remove_setting,
    "setting": ch.get_setting,
    "txt": ch.export_txt,
    "csv": ch.export_csv,
    "gg": ch.export_gg,
    "ua": ch.export_ua,
}

parser.add_argument("command", choices=FUNCTION_MAP.keys())

parser.add_argument(
    "-m",
    "--mediainfo",
    action="store_false",
    help="Turn off mediainfo scanning, only accessible with the [save] command",
    default=True,
)

parser.add_argument(
    "--target",
    "-t",
    help=(
        "Specify the target setting to update."
        "\nValid targets: directories, tmdb_key, enabled_sites, gg_path, ua_path, "
        "hardlink_output_folder, search_cooldown, min_file_size, allow_dupes, "
        "banned_groups, ignored_qualities, ignored_keywords"
        "\nYou can also use setting-add to add api keys by tracker nickname."
    ),
)

parser.add_argument("--set", "-s", help="Specify the new value for the target setting")

parser.add_argument(
    "--verbose",
    "-v",
    action="store_true",
    help="Enable verbose output. Only works with [scan, tmdb, search, and run-all]",
    default=False,
)

args = parser.parse_args()

func = FUNCTION_MAP[args.command]
func_args = {}

if "mediainfo" in ch.create_search_data.__code__.co_varnames:
    if args.command in {"run-all", "save"}:
        func_args["mediainfo"] = args.mediainfo

if args.command == "setting" or args.command == "setting-rm":
    func_args["target"] = args.target

if args.command == "setting-add":
    func_args["value"] = args.set
    func_args["target"] = args.target

if args.command in {"scan", "tmdb", "search", "run-all"}:
    func_args["verbose"] = args.verbose

func(**func_args)
