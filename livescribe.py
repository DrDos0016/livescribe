from journal import Journal


def main():
    journal = Journal()
    journal.login()

    if journal.logged_in:
        journal.set_journal()
        journal.archive()

        # 2017
        #journal.download_post("http://dr-dos.livejournal.com/411146.html")
        #journal.download_post("http://dr-dos.livejournal.com/408872.html")

        journal.save(journal.journal, "dr-dos", "complete.json", pretty=True)
    return True

if __name__ == "__main__":
    main()
