from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import logger
from .config import load_config
from .throttle import StatusThrottle
from .tts import speak

cfg = load_config()
logger.configure(cfg.log_path)
throttle = StatusThrottle(cfg.status_throttle_seconds)

mcp = FastMCP("readless")


@mcp.tool()
async def speak_summary(headline: str, details: str = "") -> str:
    """Announce a completed, user-visible task out loud.

    Call when a task the user will care about is done: code written, tests passed,
    bug fixed, research concluded. Don't call for trivial back-and-forth.

    Args:
        headline: Spoken aloud. Keep to <= 15 words. No code, no paths.
                  Use the user's main language (Chinese for this user).
        details: Not spoken. Appended to the log for later reference.

    Returns a short status string (e.g. "spoken", "tts_no_key_logged",
    "suppressed_quiet_hours", "tool_disabled"). Not an error on suppression.
    """
    logger.log_event("summary", headline, details)
    if not cfg.tools.speak_summary:
        return "tool_disabled"
    if cfg.in_quiet_hours():
        return "suppressed_quiet_hours"
    return await speak(headline, cfg)


@mcp.tool()
async def speak_status(message: str) -> str:
    """Heartbeat update during a long-running task.

    Use for progress pings on tasks expected to take > 2 minutes. The server
    throttles to at most one spoken status per minute; extra calls return
    "throttled" (not an error) — that is expected and fine.

    Args:
        message: Spoken aloud. Keep to <= 10 words.

    Returns "spoken", "throttled", "tts_no_key_logged", "suppressed_quiet_hours",
    or "tool_disabled".
    """
    logger.log_event("status", message)
    if not cfg.tools.speak_status:
        return "tool_disabled"
    if not throttle.allow():
        return "throttled"
    if cfg.in_quiet_hours():
        return "suppressed_quiet_hours"
    return await speak(message, cfg)


@mcp.tool()
async def speak_blocker(question: str) -> str:
    """Agent is blocked — needs user input to continue. Highest priority.

    Use when you cannot proceed without a decision (destructive op confirmation,
    missing credential, ambiguous requirement). Bypasses quiet hours and
    interrupts any in-progress speech.

    Args:
        question: Spoken aloud. Keep to <= 20 words. Say clearly what you need.

    Returns "spoken", "tts_no_key_logged", "tts_failed_but_logged", or
    "tool_disabled".
    """
    logger.log_event("blocker", question)
    if not cfg.tools.speak_blocker:
        return "tool_disabled"
    return await speak(question, cfg, interrupt=True)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
