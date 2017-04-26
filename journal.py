import getpass
import json
import os
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup


class Journal(object):
    def __init__(self):
        self.user = None
        self.password = None
        self.logged_in = False
        self.session = requests.Session()
        self.journal = {
            "meta": {},
            "journal": {
                "profile": None,
                "friends": [],
                "posts": []
            }
        }

    def login(self, username=None, password=None):
        if username is None:
            self.user = input("LJ Username: ")
        else:
            self.user = username
        if password is None:
            self.password = getpass.getpass()
        else:
            self.password = password

        login_url = "http://www.livejournal.com/login.bml"
        data = {

            "user": self.user,
            "password": self.password,
            "action:login": "",
        }

        print("Logging in...")
        resp = self.session.post(login_url, data=data)

        if resp.status_code == 200:
            print("Logged in as {}.".format(self.user))
            self.logged_in = True
        return True

    def set_journal(self, name=None):
        if name is None:
            self.journal_name = input(
                "Journal to archive (leave blank for {}): ".format(self.user)
            )
        else:
            self.journal_name = name

        self.urls = {
            "root": "http://www.livejournal.com/",
            "journal": "http://{}.livejournal.com/".format(self.journal_name),
            "profile": (
                "http://www.livejournal.com/"
                "userinfo.bml?user={}&comms=access".format(self.journal_name)
            ),
            "calendar": (
                "http://{}.livejournal.com/calendar".format(self.journal_name)
            ),
            "userpics": "http://l-userpic.livejournal.com",
        }

        print("Set journal to {}.".format(self.journal_name))
        return True

    def archive(self):
        print("BEGIN ARCHIVAL")
        print("Preparing data structure...")
        self.journal["meta"] = {
            "archived_by": self.user,
            "archived_on": str(datetime.now(timezone.utc)),
            "journal": self.journal_name,
            "type": "unknown",  # Journal/Community
        }

        print("Acquiring profile info...")
        resp = requests.get(self.urls["profile"], cookies=self.session.cookies)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Journal/Community?
        tag = soup.find("img", class_="i-ljuser-userhead")
        if tag and ("userinfo" in tag.attrs.get("src", "")):
            self.journal["meta"]["type"] = "journal"
        elif tag and "community" in tag.attrs.get("src", ""):
            self.journal["meta"]["type"] = "community"

        # Profile
        tag = soup.find("div", class_="l-profile")
        self.journal["journal"]["profile"] = tag.text

        print("Discovering first post...")
        resp = requests.get(self.urls["calendar"],
                            cookies=self.session.cookies)
        soup = BeautifulSoup(resp.text, "html.parser")
        tags = soup.find_all("a")

        first_month = tags[-2]  # Second to last link

        # Month overview
        resp = requests.get(first_month.attrs["href"],
                            cookies=self.session.cookies)
        soup = BeautifulSoup(resp.text, "html.parser")
        tags = soup.find_all("a")

        first_post = None
        for tag in tags:
            if (tag.attrs.get("href", "").startswith(self.urls["journal"]) and
                    tag.attrs["href"].endswith(".html")):
                first_post = tag.attrs["href"]
                break

        if not first_post:
            print("COULD NOT FIND FIRST POST")
            return False

        print("Found!")
        self.download_from(first_post)

        print("All posts archived!")
        return True

    def download_from(self, url, capture_source=False):

        while True:
            # Download post
            next_url = self.download_post(url, capture_source)
            time.sleep(3)

            # Next post
            if next_url:
                url = next_url

            """
            # DEBUG
            if len(self.journal["journal"]["posts"]) >= 10:
                break
            """
        return True

    def download_post(self, url, capture_source=False):
        resp = self.session.get(url, cookies=self.session.cookies)
        soup = BeautifulSoup(resp.text, "html.parser")

        # DEBUG
        #  with open("temp.html", "w") as fh:
        #    fh.write(soup.prettify())

        # Obtain the post link
        post_link = url
        for history in resp.history:
            if history.url.startswith(self.urls["journal"]):
                post_link = history.url
                break
        post = {
            "id": post_link.replace(
                self.urls["journal"], ""
            ).replace(".html", ""),
            "url": url,
            "author": "",
            "time": "",
            "userpic": "",
            "privacy": "public",
            "subject": "",
            "location": "",
            "mood": "",
            "mood_image": "",
            "music": "",
            "content": "",
            "comments": [],
        }

        if capture_source:
            post["html"] = soup.prettify()

        # Author
        author_tag = soup.find("span", class_="ljuser")
        post["author"] = author_tag.attrs["data-ljuser"]

        # Time
        post["time"] = soup.find("time").text

        # Userpic
        images = soup.find_all("img")
        for image in images:
            if (image.has_attr("src") and
                    image.attrs["src"].startswith(self.urls["userpics"])):
                post["userpic"] = image.attrs["src"]
                break

        # Privacy / Subject
        subject_tag = soup.find("h1", class_="b-singlepost-title")
        if subject_tag:
            privacy = subject_tag.find("span")
            if privacy and privacy.has_attr("class"):
                if "i-posticon-private" in privacy.attrs["class"]:
                    post["privacy"] = "private"
                elif "i-posticon-protected" in privacy.attrs["class"]:
                    post["privacy"] = "friends-only"
            post["subject"] = subject_tag.text.strip()

        # Location / Mood / Music
        location_tag = soup.find("li",
                                 class_="b-singlepost-meta-item-location")
        if location_tag:
            post["location"] = location_tag.find("span").text

        mood_tag = soup.find("li", class_="b-singlepost-meta-item-mood")
        if mood_tag:
            post["mood"] = mood_tag.find("span").text
            image_tag = mood_tag.find("img")
            if image_tag:
                post["mood_image"] = image_tag.attrs["src"]

        music_tag = soup.find("li", class_="b-singlepost-meta-item-music")
        if music_tag:
            post["music"] = music_tag.find("span").text

        # Content
        post["content"] = str(soup.find("div",
                              class_="b-singlepost-bodywrapper"))

        # Post is complete
        print(post["time"], post["subject"])

        # Comments
        post["comments"] = self.get_comments(post["id"])

        # Next url
        next_url = None
        next_tag = soup.find("a", class_="b-controls-next")
        if next_tag:
            next_url = next_tag.attrs["href"]

        self.journal["journal"]["posts"].append(post)

        # Save individual JSON file
        self.save(post, self.journal_name, post["time"], pretty=True)

        return next_url

    def save(self, data, directory, filename, pretty=False):
        if pretty:
            json_str = json.dumps(data, sort_keys=True, indent=4)
        else:
            json_str = json.dumps(data)

        # Make the directory if it doesn't exist
        os.makedirs(os.path.join("journals", directory), exist_ok=True)

        # Save the file
        # TODO: Handle name conflicts
        filepath = os.path.join("journals", directory, filename + ".json")
        with open(filepath, "w") as fh:
            fh.write(json_str)
        print("Saved", filename)

    def get_comments(self, post_id):
        comments = []
        base_url = ("http://{}.livejournal.com/{}/__rpc_get_thread"
                    "?journal={}&itemid={}&flat={}&skip=&media=&page={}&_={}")
        page = 1
        ts = int(time.time() * 1000)
        total_comments = None

        # Download flat comment info
        # Flatly to have all content available
        print("\tDownloading comments")
        while True:
            url = base_url.format(self.journal_name, self.journal_name,
                                  self.journal_name, post_id, 1, page, ts)

            resp = self.session.get(url, cookies=self.session.cookies)
            # print(resp.content)
            comments_data = resp.json()
            if total_comments is None:
                total_comments = comments_data.get("replycount", 0)

            # Handle 0 comment posts
            if total_comments == 0:
                return []

            for comment in comments_data["comments"]:
                c = {
                    "id": comment.get("dtalkid", 0),
                    "author": comment.get("poster", ""),
                    "userpic": comment.get("userpic", ""),
                    "time": comment.get("ctime_ts", 0),
                    "article": comment.get("article", "")
                }

                if c["time"] != "":
                    c["time"] = str(datetime.utcfromtimestamp(c["time"]))

                comments.append(c)

            if total_comments is None or len(comments) == total_comments:
                break
            else:
                page += 1

        # Download comment thread info
        print("\tDownloading comment threading...")
        thread_info = {}
        comment_count = 0
        page = 1
        while True:
            url = base_url.format(self.journal_name, self.journal_name,
                                  self.journal_name, post_id, 0, page, ts)

            resp = self.session.get(url, cookies=self.session.cookies)
            comments_data = resp.json()
            for comment in comments_data["comments"]:
                c = {
                    "id": comment.get("dtalkid", 0),
                    "above": comment.get("above", 0),
                    "below": comment.get("below", 0),
                    "parent": comment.get("parent", 0)
                }
                thread_info[c["id"]] = c
                comment_count += 1

            if comment_count >= total_comments:
                break
            else:
                page += 1

        # Stitch the comments
        for comment in comments:
            comment["above"] = thread_info[comment["id"]]["above"]
            comment["below"] = thread_info[comment["id"]]["below"]
            comment["parent"] = thread_info[comment["id"]]["parent"]
        return comments
