import os
import json
import traceback

import requests

import xml.etree.ElementTree as ET
from urllib.parse import urljoin


class Settings:
    def __init__(self):
        self.data_folder = "./data/"
        self.default_settings = {
            "directories": [],
            "tmdb_key": "",  # https://www.themoviedb.org/settings/api
            "enabled_sites": [],
            "tracker_directories": {},
            "keys": {
                "aither": "",
                "blutopia": "",
                "reelflix": "",
                "lst": "",
                "ulcx": "",
                "onlyencodes": "",
                "rastastugan": "",
                "homiehelpdesk": "",
                "yuscene": "",
                "beyondhd": "",
                "morethantv": "",
                "zenith": "",
                "midnightscene": "",
                "greatposterwall": "",
            },
            "prowlarr": {
                "url": "",
                "api_key": "",
                "indexers": {},
            },
            "gg_path": "",  # Path to GG-Bot e.g. /home/user/gg-bot-upload-assistant/ --- Not required only for export_gg_bot()
            "ua_path": "",  # Path to upload-assistant, e.g. /home/user/uplaad-assistant/ --- Optional
            "hardlink_output_folder": "",
            "search_cooldown": 5,  # In seconds. Anything less than 3 isn't recommended. 30 requests per minute is max before hit rate limits. - HDVinnie
            "min_file_size": 800,  # In MB
            "allow_dupes": True,  # If false only check for completely unique movies
            "banned_groups": [],
            "gazelle_auth": {},
            "ignored_qualities": [
                "dvdrip",
                "webrip",
                "bdrip",
                "cam",
                "ts",
                "telesync",
                "hdtv",
            ],  # See patterns.py for valid options, note "bluray" get's changed to encode in scan_directories()
            "ignored_keywords": [
                "10bit",
                "10-bit",
                "DVD",
            ],  # This could be anything that would end up in the excess of parsed filename.
        }
        self.tracker_nicknames = {
            "reelflix": "reelflix",
            "rfx": "reelflix",
            "aither": "aither",
            "aith": "aither",
            "blu": "blutopia",
            "blutopia": "blutopia",
            "lst": "lst",
            "lstgg": "lst",
            "ulcx": "ulcx",
            "upload.cx": "ulcx",
            "onlyencodes": "onlyencodes",
            "oe": "onlyencodes",
            "ras": "rastastugan",
            "hhd": "homiehelpdesk",
            "yus": "yuscene",
            "yuscene": "yuscene",
            "beyondhd": "beyondhd",
            "bhd": "beyondhd",
            "morethantv": "morethantv",
            "mtv": "morethantv",
            "znth": "zenith",
            "zenith": "zenith",
            "midnightscene": "midnightscene",
            "mns": "midnightscene",
            "greatposterwall": "greatposterwall",
            "gpw": "greatposterwall",

        }

        # Basic hierarchy for qualities used to see if a file is an upgrade
        self.quality_hierarchy = {
            "webrip": 0,
            "web-dl": 1,
            "encode": 2,
            "remux": 3,
        }
        self.current_settings = None
        self.tracker_info = None

        try:
            # Creating settings.json with default settings
            if (
                not os.path.exists(f"{self.data_folder}settings.json")
                or os.path.getsize(f"{self.data_folder}settings.json") < 10
            ):
                self.write_settings_file(self.default_settings)
            # Load settings.json
            if os.path.getsize(f"{self.data_folder}settings.json") > 10:
                with open(f"{self.data_folder}settings.json", "r") as file:
                    self.current_settings = json.load(file)
                    self.validate_directories()
            # Set the settings to our class
            if not self.current_settings:
                self.current_settings = self.default_settings
            self.migrate_settings()
            # Load tracker_info.json used for resolution mapping
            if not self.tracker_info:
                with open("tracker_info.json", "r") as file:
                    self.tracker_info = json.load(file)
        except Exception as e:
            print("Error initializing settings: ", e)

    def migrate_settings(self):
        changed = False

        for key, value in self.default_settings.items():
            if key not in self.current_settings:
                self.current_settings[key] = value
                changed = True

        if "prowlarr" not in self.current_settings:
            self.current_settings["prowlarr"] = self.default_settings["prowlarr"]
            changed = True

        prowlarr = self.current_settings["prowlarr"]
        for key, value in self.default_settings["prowlarr"].items():
            if key not in prowlarr:
                prowlarr[key] = value
                changed = True

        if "tracker_directories" not in self.current_settings:
            self.current_settings["tracker_directories"] = {}
            changed = True

        if changed:
            self.write_settings()

    # Clean directories from loaded settings
    def validate_directories(self):
        try:
            directories = self.current_settings["directories"]
            directories = list(set(directories))
            # Remove trailing slashes for os.path.commonpath
            clean = [
                (
                    dir_path[:-1]
                    if dir_path[-1] == "\\" or dir_path[-1] == "/"
                    else dir_path
                )
                for dir_path in directories
            ]
            clean_copy = clean
            if len(clean) > 1:
                for dir_path in clean:
                    # Check if the directory exists
                    if os.path.exists(dir_path):
                        drive, tail = os.path.splitdrive(dir_path)
                        if drive and not tail.strip("\\/"):
                            print(
                                f"{dir_path} is a root directory, removing child directories"
                            )
                            clean_copy = [
                                c for c in clean_copy if not c.startswith(drive[0])
                            ]
                            clean_copy.append(dir_path)
                            continue
                        elif dir_path in clean_copy:
                            is_subpath = False
                            child_path = None
                            parent_path = None
                            for other_dir in clean_copy:
                                if (
                                    dir_path != other_dir
                                    and os.path.commonpath([dir_path, other_dir])
                                    == dir_path
                                ):
                                    is_subpath = True
                                    child_path = (
                                        other_dir
                                        if len(other_dir) > len(dir_path)
                                        else dir_path
                                    )
                                    parent_path = (
                                        other_dir
                                        if len(other_dir) < len(dir_path)
                                        else dir_path
                                    )
                                    print(
                                        f"{child_path} is a sub-path of {parent_path}, removing"
                                    )
                                else:
                                    continue
                            if is_subpath and child_path in clean_copy:
                                clean_copy.remove(child_path)
                        else:
                            continue

                    else:
                        print(f"{dir_path} does not exist, removing")
            normalized_directories = []
            for c in clean_copy:
                if not c.endswith(os.path.sep):
                    # List comp with os.path.join() wasn't working on root directory on Windows for some reason
                    c += os.path.sep
                    normalized_directories.append(c)
                else:
                    normalized_directories.append(c)
            self.current_settings["directories"] = normalized_directories
            self.write_settings()
        except Exception as e:
            print("Error Validating Directories:", e)
            print(traceback.format_exc())

    # Add and validate new directories.
    def add_directory(self, path):
        directories = self.current_settings["directories"]
        if not os.path.exists(path):
            raise ValueError("Path doesn't exist")
        if path not in directories:
            # Add the new path to the list
            directories.append(path)
            self.validate_directories()

    def normalize_directory_setting(self, path):
        if path.lower() == "all":
            return "all"

        normalized = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(normalized):
            raise ValueError("Path doesn't exist")

        if not normalized.endswith(os.path.sep):
            normalized += os.path.sep

        return normalized

    def normalize_directory_for_compare(self, path):
        normalized = os.path.abspath(os.path.expanduser(path))
        if not normalized.endswith(os.path.sep):
            normalized += os.path.sep

        return normalized

    def update_tracker_directories(self, tracker_input, value):
        if tracker_input not in self.tracker_nicknames:
            print(tracker_input, "is not a supported tracker")
            return

        tracker = self.tracker_nicknames[tracker_input]
        if "tracker_directories" not in self.current_settings:
            self.current_settings["tracker_directories"] = {}

        if value.lower() == "all":
            self.current_settings["tracker_directories"][tracker] = "all"
            self.write_settings()
            print(f"{tracker} will search all directories")
            return

        directory = self.normalize_directory_setting(value)

        configured_directories = [
            self.normalize_directory_for_compare(path)
            for path in self.current_settings["directories"]
        ]

        if directory not in configured_directories:
            print(
                directory,
                "is not in directories. Add it first with setting-add -t dir -s <path>",
            )
            return

        current = self.current_settings["tracker_directories"].get(tracker, "all")
        if current == "all":
            current = []

        if directory in current:
            print(directory, "Already enabled for", tracker)
            return

        current.append(directory)
        self.current_settings["tracker_directories"][tracker] = current
        self.write_settings()

        print(directory, "Successfully added to tracker_directories for", tracker)

    def update_gazelle_auth(self, tracker, field, value):
        if "gazelle_auth" not in self.current_settings:
            self.current_settings["gazelle_auth"] = {}

        if tracker not in self.current_settings["gazelle_auth"]:
            self.current_settings["gazelle_auth"][tracker] = {
                "username": "",
                "password": "",
            }

        self.current_settings["gazelle_auth"][tracker][field] = value
        self.write_settings()

        print(f"Updated gazelle_auth for {tracker}: {field}")

    def update_prowlarr_indexer(self, tracker_input, value):
        if tracker_input not in self.tracker_nicknames:
            print(tracker_input, "is not a supported tracker")
            return

        tracker = self.tracker_nicknames[tracker_input]
        if "prowlarr" not in self.current_settings:
            self.current_settings["prowlarr"] = self.default_settings["prowlarr"]
        if "indexers" not in self.current_settings["prowlarr"]:
            self.current_settings["prowlarr"]["indexers"] = {}

        self.current_settings["prowlarr"]["indexers"][tracker] = str(value)
        self.write_settings()

        print(f"Updated Prowlarr indexer for {tracker}: {value}")

    def update_prowlarr_setting(self, field, value):
        if "prowlarr" not in self.current_settings:
            self.current_settings["prowlarr"] = self.default_settings["prowlarr"]

        self.current_settings["prowlarr"][field] = value.rstrip("/") if field == "url" else value
        self.write_settings()

        print(f"Updated Prowlarr {field}")

    def has_prowlarr_indexer(self, tracker):
        prowlarr = self.current_settings.get("prowlarr", {})
        return bool(
            prowlarr.get("url")
            and prowlarr.get("api_key")
            and prowlarr.get("indexers", {}).get(tracker)
        )

    def has_tracker_search_config(self, tracker):
        return bool(
            self.current_settings.get("keys", {}).get(tracker)
            or self.has_prowlarr_indexer(tracker)
        )

    def validate_tmdb(self, key):
        try:
            url = f"https://api.themoviedb.org/3/configuration?api_key={key}"
            response = requests.get(url)
            if response.status_code != 200:
                print("Invalid API Key")
                return
            else:
                self.current_settings["tmdb_key"] = key
                print("Key is valid and was added to tmdb")
        except Exception as e:
            print("Error searching api:", e)
            return

    def validate_key(self, key, target):
        if target not in self.tracker_nicknames:
            print("Invalid tracker")
            return

        tracker = self.tracker_nicknames[target]

        url = self.tracker_info[tracker]["url"]
        api_type = self.tracker_info[tracker].get("api_type", "unit3d")

        try:
            if api_type == "bhd":
                url = f"{url.rstrip('/')}/api/torrents/{key}"
                response = requests.post(url, data={"action": "search", "page": 1})

                if response.status_code != 200:
                    print("Invalid API Key")
                    return

                data = response.json()
                if not data.get("success"):
                    print("Invalid API Key")
                    return

            elif api_type == "torznab":
                torznab_path = self.tracker_info[tracker].get("torznab_path", "api/torznab")
                url = urljoin(url.rstrip("/") + "/", torznab_path)

                response = requests.get(url, params={
                    "apikey": key,
                    "t": "caps",
                })

                if response.status_code != 200:
                    print("Invalid API Key")
                    return

                root = ET.fromstring(response.content)
                error = root.find("error")

                if error is not None:
                    print("Invalid API Key")
                    return

            else:
                url = f"{url}api/torrents?perPage=10&api_token={key}"
                response = requests.get(url)

                # UNIT3D pushes you to the homepage if the api key is invalid
                if response.history:
                    print("Invalid API Key")
                    return

        except Exception as e:
            print(f"Could not validate API key: {e}")
            return

        self.current_settings["keys"][tracker] = key
        self.write_settings()
        print("Key is valid and was added to", tracker)

    def setting_helper(self, target):
        settings = self.current_settings
        nicknames = self.tracker_nicknames
        matching_keys = [key for key in settings.keys() if target in key]
        matching_nicks = [nick for nick in nicknames.keys() if target in nick]
        if len(matching_nicks) >= 1:
            return False
        if len(matching_keys) == 1:
            return matching_keys[0]
        elif len(matching_keys) > 1:
            print(
                "Multiple settings match the provided substring. Please provide a more specific target."
            )
            print(settings.keys())
            print(
                "Unique substrings accepted: dir, tmdb, sites, gg, search, size, dupes, banned, qual, keywords, prowlarr_url, prowlarr_api_key"
            )
            print(
                "If you're trying to add a tracker key, you can use setting-add -t <site> -s <api_key>"
            )
            print(
                "If you're trying to add a Prowlarr indexer ID, use setting-add -t prowlarr_indexer:<site> -s <indexer_id>"
            )
            print("Accepted sites: ", nicknames.keys())
            return
        else:
            print(target, " is not a supported setting")
            print("Accepted targets: ", settings.keys())
            print(
                "Unique substrings accepted: dir, tmdb, sites, gg, search, size, dupes, banned, qual, keywords, prowlarr_url, prowlarr_api_key"
            )
            print(
                "If you're trying to add a tracker key, you can use setting-add -t <site> -s <api_key>"
            )
            print(
                "If you're trying to add a Prowlarr indexer ID, use setting-add -t prowlarr_indexer:<site> -s <indexer_id>"
            )
            print("Accepted sites: ", nicknames.keys())
            return

    # Update a specific setting
    def update_setting(self, target, value):
        if target.startswith("tracker_directories:"):
            tracker_input = target.split(":", 1)[1]
            self.update_tracker_directories(tracker_input, value)
            return

        if target == "prowlarr_url":
            self.update_prowlarr_setting("url", value)
            return

        if target == "prowlarr_api_key":
            self.update_prowlarr_setting("api_key", value)
            return

        if target.startswith("prowlarr_indexer:"):
            tracker_input = target.split(":", 1)[1]
            self.update_prowlarr_indexer(tracker_input, value)
            return

        if target.startswith("gazelle_user:"):
            tracker_input = target.split(":", 1)[1]

            if tracker_input not in self.tracker_nicknames:
                print(tracker_input, "is not a supported tracker")
                return

            tracker = self.tracker_nicknames[tracker_input]
            self.update_gazelle_auth(tracker, "username", value)
            return

        if target.startswith("gazelle_pass:"):
            tracker_input = target.split(":", 1)[1]

            if tracker_input not in self.tracker_nicknames:
                print(tracker_input, "is not a supported tracker")
                return

            tracker = self.tracker_nicknames[tracker_input]
            self.update_gazelle_auth(tracker, "password", value)
            return

        try:
            settings = self.current_settings
            nicknames = self.tracker_nicknames
            matching_key = self.setting_helper(target)

            if matching_key:
                target = matching_key  # Update target to the full key
                if target == "tmdb_key":
                    self.validate_tmdb(value)
                    settings[target] = value
                if isinstance(settings[target], str):
                    if target == "hardlink_output_folder":
                        os.makedirs(value, exist_ok=True)
                    settings[target] = value
                    print(value, " Successfully added to ", target)
                elif isinstance(settings[target], list):
                    if target == "directories":
                        self.add_directory(value)
                    elif target == "enabled_sites":
                        if value in nicknames:
                            tracker = nicknames[value]
                            if not self.has_tracker_search_config(tracker):
                                print(
                                    "There is currently no direct API key or complete Prowlarr config for",
                                    value,
                                    f"\nAdd one using setting-add -t {value} -s <api_key>",
                                    f"\nor set Prowlarr with setting-add -t prowlarr_indexer:{value} -s <indexer_id>",
                                )
                        else:
                            print(value, " is not a supported site")
                            return
                        if value in settings[target]:  # Don't add duplicates
                            print(value, " Already in ", target)
                            return
                        else:
                            settings[target].append(tracker)  # Add new site
                            print(tracker, "Successfully added to", target)
                    else:
                        settings[target].append(
                            value
                        )  # banned_groups, ignored_qualities, ignored_keywords these shouldn't need extra validation
                        print(value, " Successfully added to ", target)
                elif isinstance(settings[target], bool):
                    if "t" in value.lower():
                        settings[target] = True
                        print(target, " Set to True")
                    elif "f" in value.lower():
                        settings[target] = False
                        print(target, " Set to False")
                    else:
                        print(
                            "Value ", value, " Not recognized, try False, F or True, T"
                        )
                elif isinstance(settings[target], int):
                    settings[target] = int(value)
                    print(value, " Successfully added to ", target)
            # Add a new key
            elif target in nicknames:
                if not value:
                    print("No api key provided")
                else:
                    self.validate_key(value, target)
            self.current_settings = settings
            self.write_settings()
        except Exception as e:
            print("Error updating setting", e)
            print(traceback.format_exc())

    def return_setting(self, target):
        try:
            matching_key = self.setting_helper(target)
            matching_nick = (
                self.tracker_nicknames[target]
                if target in self.tracker_nicknames
                else False
            )
            if matching_key:
                target = matching_key  # Update target to the full key
                return self.current_settings[target]
            elif matching_nick:
                if self.current_settings["keys"][matching_nick]:
                    return self.current_settings["keys"][matching_nick]
        except Exception as e:
            print("Error returning settings: ", e)

    def remove_setting(self, target):
        try:
            matching_key = self.setting_helper(target)
            if matching_key:
                target = matching_key  # Update target to the full key
                setting = self.current_settings[target]
                if isinstance(setting, list):
                    if len(setting) > 0:
                        print(
                            "Which option would you like to remove?",
                            setting,
                            "\nType in the number of the option you want to remove:",
                            "\n0 being the first option, 1 being the second option, etc.",
                        )
                        option = int(input())
                        if option < 0 or option >= len(setting):
                            print("Option out of range")
                            return
                        removed_item = setting.pop(option)
                        # Remove trailing backslash if exists
                        removed_item = removed_item.rstrip("\\")
                        print("Removed:", removed_item)
                    else:
                        print("The setting is empty.")
                else:
                    print("The setting is not a list.")
                    print(f"Use setting-add -t {target} -s <new_value>")
                self.write_settings()
        except Exception as e:
            print("Error removing setting:", e)

    def is_upgrade(self, file, tr):
        if not file or not tr:
            print("error comparing qualities")
            return False
        if (
            file not in self.quality_hierarchy.keys()
            or tr not in self.quality_hierarchy.keys()
        ):
            return False
        if self.quality_hierarchy[file] > self.quality_hierarchy[tr]:
            return True
        else:
            return False

    def write_settings(self):
        try:
            self.write_settings_file(self.current_settings)
        except Exception as e:
            print("Error writing settings: ", e)

    def reset_settings(self):
        try:
            self.write_settings_file(self.default_settings)
        except Exception as e:
            print("Error resetting settings: ", e)

    def write_settings_file(self, settings):
        with open(f"{self.data_folder}settings.json", "w") as outfile:
            json.dump(
                settings,
                outfile,
                indent=4,
                ensure_ascii=False,
            )
            outfile.write("\n")
