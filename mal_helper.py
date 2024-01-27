"""
MyAnimeList helper module.

This module includes the following features:
- Date Fixer: Console interface to review and fix missing start/finish dates in
your anime/manga list using historical episode/chapter updates

This module would not be possible without the official MAL API. My thanks go
out to the API's developers and maintainers.
https://myanimelist.net/apiconfig/references/api/v2

As a safety precaution, I would recommend taking a backup of your anime and
manga lists before running.
https://myanimelist.net/panel.php?go=export
"""

import json
import requests
import time

import pandas as pd
from bs4 import BeautifulSoup


class MALUser:
    def __init__(self, user_name: str, headers: dict):
        self.user_name = user_name
        self.headers = headers

    def _get_list(self, list_type: str, limit: int):
        """Request user list from MAL and return it."""
        assert list_type in ("anime", "manga"), (
            f"Invalid list type {list_type}."
            "List type must be 'anime' or 'manga'"
        )

        url = (
            f"https://api.myanimelist.net/v2/users/{self.user_name}/"
            f"{list_type}list?fields=list_status&limit={limit}"
        )
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

        my_list = response.json()
        response.close()

        return my_list

    def get_anime_list(self, limit: int = 1000, overwrite: bool = False):
        """Request user's anime list if needed, then return it."""
        if (not hasattr(self, "my_anime_list")) or (overwrite):
            self.my_anime_list = self._get_list("anime", limit)
        return self.my_anime_list

    def get_manga_list(self, limit: int = 1000, overwrite: bool = False):
        """Request user's manga list if needed, then return it."""
        if (not hasattr(self, "my_manga_list")) or (overwrite):
            self.my_manga_list = self._get_list("manga", limit)
        return self.my_manga_list


class MALHelper:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}
        self.user_lists = {}

    def _get_entry_history(self, entry_id: str, list_type: str):
        """Get history for an anime/manga entry and clean it."""
        if list_type == "anime":
            list_modifier = "a"
        elif list_type == "manga":
            list_modifier = "m"

        url = (
            "https://myanimelist.net/ajaxtb.php?keepThis=true&detailed"
            f"{list_modifier}id={entry_id}&TB_iframe=true&height=420&width=390"
        )
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

        parsed_html = BeautifulSoup(response.content, features="lxml")
        response.close()

        history = parsed_html.body.find_all(
            "div",
            attrs={"class": "spaceit_pad"}
        )

        cleaned_history = []
        for h in history:
            line = h.text
            parts = line.split(" ")

            wdate = parts[4]
            wtime = parts[6]
            wcount = parts[1][:-1]

            converted_wdate = wdate[6:] + "-" + wdate[:2] + "-" + wdate[3:5]

            cleaned_history.append((wcount, converted_wdate, wtime))

        return cleaned_history

    def _determine_dates(self, history: list):
        """Determine start and finish dates for an entry using its history."""
        # Reverse order of history so earliest watch date is first
        history = history[::-1]

        earliest_ep = min(history, key=lambda x: int(x[0]))[0]
        latest_ep = max(history, key=lambda x: int(x[0]))[0]

        # Set start date to earliest date with earliest_ep
        for i, h1 in enumerate(history):
            if h1[0] == earliest_ep:
                start_date = h1[1]
                start_time = h1[2]
                start_date_index = i
                break
        print(
            f"<<< Earliest episode/chapter {earliest_ep} was first "
            f"watched/read at {start_date} {start_time}"
        )

        # Set finish date to earliest date with latest_ep that occurs after the
        # start date
        for j, h2 in enumerate(history):
            if j < start_date_index:
                continue
            # For a series to be completed, the history MUST contain the final
            # episode as the last history entry. Possible edge case: Currently
            # rewatching series?
            if h2[0] == latest_ep:
                finish_date = h2[1]
                finish_time = h2[2]
                break
        print(
            f"<<< Last episode/chapter {latest_ep} was first "
            f"watched/read at {finish_date} {finish_time}"
        )

        return start_date, finish_date

    def add_user(self, user_name: str):
        """Create new User for given user_name if one doesn't already exist."""
        if self.user_lists.get(user_name) is None:
            User = MALUser(user_name, self.headers)
            self.user_lists[user_name] = User

    def update_entry(self, entry_id: str, list_type: str, updates: dict):
        """Send update request via MAL API using given updates."""
        url = (
            "https://api.myanimelist.net/v2/"
            f"{list_type}/{entry_id}/my_list_status"
        )
        response = requests.put(url, data=updates, headers=self.headers)
        return response

    def date_fixer(self, list_type: str, wait_time: int = 1, auto_skip: bool = False, start_from: str = None):
        """Simple command line interface to assist with manual fixing of start
        and end dates in current user's anime or manga list.

        This method will run on the list of the owner of the OAuth Access
        Token. This is a requirement to send update requests to MAL.

        Caveats:
        - Missing history is common, especially if you have not frequently been
        using the episode/chapter count feature in MAL.
        - The API is limited to getting at most 1000 entries from a user's
        anime or manga list. This may be possible to resolve using pagination
        with the offset parameter.

        Args:
            list_type (str): Either 'anime' or 'manga' corresponding to which
                user list to fix.
            wait_time (int, optional): Time to sleep between every entry in
                user list. Defaults to 1.
            auto_skip (bool, optional): Option to auto-skip any entries with a
                status that is not completed or already has a start and finish
                date. Defaults to False.
            start_from (str, optional): Option to start from a specific manga
                entry to simulate pagination. Use the exact entry title, e.g.
                'Akira'. Defaults to None.
        """
        assert list_type in ("anime", "manga"), (
            f"Invalid list type {list_type}."
            "List type must be 'anime' or 'manga'"
        )

        self.add_user("@me")

        if list_type == "anime":
            user_list = self.user_lists["@me"].get_anime_list()
        elif list_type == "manga":
            user_list = self.user_lists["@me"].get_manga_list()

        entry_count = len(user_list["data"])

        start_from_triggered = False
        if start_from is None:
            start_from_triggered = True

        # Iterate through every entry in user's list
        for index, entry in enumerate(user_list["data"]):
            entry_id = entry["node"]["id"]
            entry_title = entry["node"]["title"]
            entry_status = entry["list_status"]["status"]

            entry_start_date = entry["list_status"].get("start_date", "UNKNOWN")
            entry_finish_date = entry["list_status"].get("finish_date", "UNKNOWN")

            # If start_from is given, skip entries until start_from is reached
            if not start_from_triggered:
                if entry_title != start_from:
                    print(f"Skipped {index+1}")
                    continue
                else:
                    start_from_triggered = True

            # Print relevant info for entry
            print(
                f"{index+1}/{entry_count} [{entry_status.upper()}] "
                f"{entry_title} ({entry_id}). "
                f"Current start date: {entry_start_date}. "
                f"Current finish date: {entry_finish_date}."
            )

            # Sanity check that start date is not after finish date. Dates are
            # in YYYY-MM-DD format which string compare correctly
            if (entry_start_date != "UNKNOWN") and (entry_finish_date != "UNKNOWN"):
                if (entry_start_date > entry_finish_date):
                    print("<<< Found an issue. Start date is after finish date")
                    input("This will require a manual fix. Type anything in to continue: \n<<< ")
                    print("==========================================================")
                    continue

            # If auto_skip is toggled, skip entry if it is completed or both
            # the start and finish date are already populated
            if auto_skip:
                if entry_status != "completed":
                    print("<<< Skipping entry as the status is not completed")
                    print("==========================================================")
                    continue
                elif (entry_start_date != "UNKNOWN") and (entry_finish_date != "UNKNOWN"):
                    print("<<< Skipping entry as the start and end date are already populated")
                    print("==========================================================")
                    continue

            # Retrieve history for entry via MAL endpoint
            history = self._get_entry_history(entry_id, list_type)
            for h in history:
                wcount, wdate, wtime = h
                if list_type == "anime":
                    print(f"[{wdate} {wtime}] Watched episode {wcount}")
                elif list_type == "manga":
                    print(f"[{wdate} {wtime}] Read chapter {wcount}")

            time.sleep(wait_time)

            # Determine best action and propose change to user
            skip_flag = False
            if entry_status != "completed":
                print("<<< Proposed change: Skip entry as the status is not completed")
                skip_flag = True
            else:
                if (entry_start_date != "UNKNOWN") and (entry_finish_date != "UNKNOWN"):
                    print("<<< Proposed change: Skip entry as the start and end date are already populated")
                    skip_flag = True
                elif len(history) == 0:
                    print("<<< Found an issue. No history available")
                    input("This will require a manual fix. Type anything in to continue: \n<<< ")
                    print("==========================================================")
                    continue
                # Status is completed and at least one of start or finish date
                # are not populated
                else:
                    start_date, finish_date = self._determine_dates(history)
                    print(f"<<< Proposed change: Set start date to {start_date}. Set finish date to {finish_date}")

            # Await user choice
            while True:
                user_choice = input(
                    "Type 'Y' if you wish to proceed with the proposed change. "
                    "Type 'S' to skip the entry. "
                    "Type 'F' to just add the final date. "
                    "Type 'X' to exit:"
                    "\n<<< "
                )
                if user_choice.upper() in ("Y", "S", "F", "X"):
                    break
                print(f"<<< Did not understand input '{user_choice}'. Please try again")

            # Action user choice
            if user_choice.upper() == "Y":
                if skip_flag:
                    print("<<< Skipping current entry as proposed change")
                    print("==========================================================")
                    continue
                else:
                    updates = {
                        "start_date": start_date,
                        "finish_date": finish_date,
                    }
            elif user_choice.upper() == "F":
                updates = {
                    "finish_date": finish_date,
                }
            elif user_choice.upper() == "S":
                print("<<< Skipping current entry on user request")
                print("==========================================================")
                continue
            elif user_choice.upper() == "X":
                print("<<< Exiting date_fixer function")
                print("==========================================================")
                break

            response = self.update_entry(entry_id, list_type, updates)
            print(updates)
            print(f"<<< Sent proposed change as update request to MAL and received response code {response}")
            print("==========================================================")

        print("All done!")


# %%

if __name__ == "__main__":
    with open("token.json", "r") as file:
        token = json.load(file)

    access_token = token["access_token"]
    Helper = MALHelper(access_token)

    # Helper.date_fixer("anime", auto_skip=True)

    # Helper.date_fixer("manga", auto_skip=True)
