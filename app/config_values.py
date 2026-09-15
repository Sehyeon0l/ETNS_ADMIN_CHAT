"""Tunable settings that aren't secrets and don't need a database row.

Change ADMIN_STATUS_THRESHOLD here (not in the view/route code) to adjust
what counts as 여유/보통/바쁨 for every admin.
"""

ADMIN_STATUS_THRESHOLD = {
    "GREEN_MAX": 2,  # 0..GREEN_MAX waiting inquiries -> 여유
    "YELLOW_MAX": 5,  # GREEN_MAX+1..YELLOW_MAX -> 보통, above that -> 바쁨
}

STATUS_GREEN = "GREEN"
STATUS_YELLOW = "YELLOW"
STATUS_RED = "RED"

STATUS_LABELS = {
    STATUS_GREEN: "여유",
    STATUS_YELLOW: "보통",
    STATUS_RED: "바쁨",
}

STATUS_DOTS = {
    STATUS_GREEN: "🟢",
    STATUS_YELLOW: "🟡",
    STATUS_RED: "🔴",
}


def compute_admin_status(waiting_count):
    if waiting_count <= ADMIN_STATUS_THRESHOLD["GREEN_MAX"]:
        return STATUS_GREEN
    if waiting_count <= ADMIN_STATUS_THRESHOLD["YELLOW_MAX"]:
        return STATUS_YELLOW
    return STATUS_RED
