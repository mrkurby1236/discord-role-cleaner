import os
import time
import urllib.parse
import requests

API_BASE = "https://discord.com/api/v10"

TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = os.environ["DISCORD_GUILD_ID"]
ROLE_ID = os.environ["DISCORD_ROLE_ID"]

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
SKIP_BOTS = os.getenv("SKIP_BOTS", "true").lower() == "true"

BASE_HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "User-Agent": "discord-weekly-role-cleaner"
}


def api_request(method, url, **kwargs):
    extra_headers = kwargs.pop("headers", {})
    headers = {**BASE_HEADERS, **extra_headers}

    while True:
        response = requests.request(method, url, headers=headers, **kwargs)

        if response.status_code == 429:
            retry_after = response.json().get("retry_after", 1)
            print(f"Rate limited. Waiting {retry_after} seconds...")
            time.sleep(float(retry_after) + 0.25)
            continue

        return response


def get_all_members():
    after = "0"

    while True:
        response = api_request(
            "GET",
            f"{API_BASE}/guilds/{GUILD_ID}/members",
            params={"limit": 1000, "after": after}
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to list members: {response.status_code} {response.text}"
            )

        members = response.json()

        if not members:
            break

        for member in members:
            yield member

        after = members[-1]["user"]["id"]

        if len(members) < 1000:
            break


def remove_role_from_member(user_id):
    reason = urllib.parse.quote("Scheduled weekly role cleanup")

    return api_request(
        "DELETE",
        f"{API_BASE}/guilds/{GUILD_ID}/members/{user_id}/roles/{ROLE_ID}",
        headers={"X-Audit-Log-Reason": reason}
    )


def main():
    targets = []

    for member in get_all_members():
        user = member.get("user", {})

        if SKIP_BOTS and user.get("bot"):
            continue

        if ROLE_ID in member.get("roles", []):
            targets.append(member)

    print(f"Found {len(targets)} member(s) with role {ROLE_ID}.")
    print(f"Dry run: {DRY_RUN}")

    removed = 0
    failed = 0

    for member in targets:
        user = member["user"]
        user_id = user["id"]
        username = user.get("username", user_id)

        if DRY_RUN:
            print(f"[DRY RUN] Would remove role from {username} ({user_id})")
            continue

        response = remove_role_from_member(user_id)

        if response.status_code == 204:
            removed += 1
            print(f"Removed role from {username} ({user_id})")
        else:
            failed += 1
            print(
                f"Failed for {username} ({user_id}): "
                f"{response.status_code} {response.text}"
            )

    print(f"Done. Removed: {removed}. Failed: {failed}.")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
