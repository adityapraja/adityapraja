import os
import datetime as dt
import requests
from dateutil import relativedelta

USER = os.environ["USER_NAME"]
TOKEN = os.environ["ACCESS_TOKEN"]          # PAT with read:user (+ repo for private contributions)
BIRTHDAY = os.environ.get("BIRTHDAY", "2000-01-01")  # YYYY-MM-DD, used for "Uptime"
WIDTH = 46                                   # chars between label start and value end

API = "https://api.github.com/graphql"
HEADERS = {"Authorization": f"bearer {TOKEN}"}


def gql(query, variables):
    r = requests.post(API, json={"query": query, "variables": variables}, headers=HEADERS, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def profile_stats():
    q = """
    query($login:String!, $cursor:String){
      user(login:$login){
        createdAt
        followers{ totalCount }
        repositoriesContributedTo(first:1, contributionTypes:[COMMIT,PULL_REQUEST,ISSUE,REPOSITORY]){ totalCount }
        repositories(ownerAffiliations:OWNER, first:100, after:$cursor){
          totalCount
          nodes{ stargazerCount }
          pageInfo{ hasNextPage endCursor }
        }
      }
    }"""
    cursor, stars, first = None, 0, None
    while True:
        u = gql(q, {"login": USER, "cursor": cursor})["user"]
        first = first or u
        stars += sum(n["stargazerCount"] for n in u["repositories"]["nodes"])
        if not u["repositories"]["pageInfo"]["hasNextPage"]:
            break
        cursor = u["repositories"]["pageInfo"]["endCursor"]
    return {
        "created": first["createdAt"],
        "followers": first["followers"]["totalCount"],
        "repos": first["repositories"]["totalCount"],
        "contrib": first["repositoriesContributedTo"]["totalCount"],
        "stars": stars,
    }


def contribution_history(created_iso):
    """Per-year calendars -> list of (date, count), plus total commits."""
    q = """
    query($login:String!, $from:DateTime!, $to:DateTime!){
      user(login:$login){
        contributionsCollection(from:$from, to:$to){
          totalCommitContributions
          restrictedContributionsCount
          contributionCalendar{ weeks{ contributionDays{ date contributionCount } } }
        }
      }
    }"""
    start_year = int(created_iso[:4])
    now = dt.datetime.now(dt.timezone.utc)
    days, commits = {}, 0
    for year in range(start_year, now.year + 1):
        frm = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        to = min(dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc), now)
        c = gql(q, {"login": USER, "from": frm.isoformat(), "to": to.isoformat()})[
            "user"]["contributionsCollection"]
        commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]
        for w in c["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
    return sorted(days.items()), commits


def streaks(days):
    today = dt.date.today().isoformat()
    longest = run = 0
    for date, count in days:
        if date > today:
            continue
        run = run + 1 if count > 0 else 0
        longest = max(longest, run)
    # current streak: walk back from today (today may still be empty)
    cur, seen = 0, [(d, c) for d, c in days if d <= today]
    for i, (d, c) in enumerate(reversed(seen)):
        if c > 0:
            cur += 1
        elif i == 0:
            continue
        else:
            break
    return cur, longest


def uptime():
    b = dt.datetime.strptime(BIRTHDAY, "%Y-%m-%d")
    d = relativedelta.relativedelta(dt.datetime.now(), b)
    return f"{d.years} years, {d.months} months, {d.days} days"


def main():
    p = profile_stats()
    days, commits = contribution_history(p["created"])
    cur, longest = streaks(days)
    total = sum(c for _, c in days)

    values = {
        "uptime": uptime(),
        "repos": f"{p['repos']:,}",
        "contrib": f"{p['contrib']:,}",
        "stars": f"{p['stars']:,}",
        "followers": f"{p['followers']:,}",
        "commits": f"{commits:,}",
        "total": f"{total:,}",
        "streak": f"{cur} days",
        "longest": f"{longest} days",
    }
    labels = {
        "uptime": "Uptime", "repos": "Repos", "contrib": "Contributed", "stars": "Stars",
        "followers": "Followers", "commits": "Commits", "total": "Total Contributions",
        "streak": "Current Streak", "longest": "Longest Streak",
    }

    svg = open("template.svg", encoding="utf-8").read()
    svg = svg.replace("{{USERNAME}}", USER)
    svg = svg.replace("{{updated}}", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    for key, val in values.items():
        n = max(WIDTH - len(labels[key]) - len(val), 3)
        svg = svg.replace("{{%s_dots}}" % key, " " + "." * n + " ")
        svg = svg.replace("{{%s}}" % key, val)

    open("stats.svg", "w", encoding="utf-8").write(svg)
    print("stats.svg written:", values)


if __name__ == "__main__":
    main()
