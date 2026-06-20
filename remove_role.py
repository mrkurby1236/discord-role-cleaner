import os
import re
import time
import urllib.parse
import requests

API_BASE = "https://discord.com/api/v10"

TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = os.environ["DISCORD_GUILD_ID"]

RAW_ROLE_IDS = os.getenv("DISCORD_ROLE_IDS") or os.getenv("DISCORD_ROLE_ID")

if not RAW_ROLE_IDS:
    raise RuntimeError("Missing DISCORD_ROLE_IDS secret.")

ROLE_IDS = set(
    role_id.strip()
    for role_id in re.split(r"[,\s]+", RAW_ROLE_IDS)
    if role_id.strip()
)

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


def remove_role_from_member(user_id, role_id):
    reason = urllib.parse.quote("Scheduled weekly role cleanup")

    return api_request(
        "DELETE",
        f"{API_BASE}/guilds/{GUILD_ID}/members/{user_id}/roles/{role_id}",
        headers={"X-Audit-Log-Reason": reason}
    )


def main():
    print(f"Target role IDs: {', '.join(ROLE_IDS)}")
    print(f"Dry run: {DRY_RUN}")

    targets = []

    for member in get_all_members():
        user = member.get("user", {})

        if SKIP_BOTS and user.get("bot"):
            continue

        member_roles = set(member.get("roles", []))
        roles_to_remove = member_roles.intersection(ROLE_IDS)

        if roles_to_remove:
            targets.append((member, roles_to_remove))

    print(f"Found {len(targets)} member(s) with at least one target role.")

    removed = 0
    failed = 0

    for member, roles_to_remove in targets:
        user = member["user"]
        user_id = user["id"]
        username = user.get("username", user_id)

        for role_id in roles_to_remove:
            if DRY_RUN:
                print(f"[DRY RUN] Would remove role {role_id} from {username} ({user_id})")
                continue

            response = remove_role_from_member(user_id, role_id)

            if response.status_code == 204:
                removed += 1
                print(f"Removed role {role_id} from {username} ({user_id})")
            else:
                failed += 1
                print(
                    f"Failed to remove role {role_id} from {username} ({user_id}): "
                    f"{response.status_code} {response.text}"
                )

    print(f"Done. Removed role assignments: {removed}. Failed: {failed}.")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
