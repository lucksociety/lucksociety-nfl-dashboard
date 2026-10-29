"""NFL season labels span September through the following winter."""
from datetime import datetime
from zoneinfo import ZoneInfo

def current_season(now=None):
    now = now or datetime.now(ZoneInfo('America/New_York'))
    return now.year if now.month >= 9 else now.year - 1
