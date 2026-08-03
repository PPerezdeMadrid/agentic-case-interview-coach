import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

STUDIO_DIR = Path(__file__).resolve().parents[2]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

import loader  # noqa: E402
import node  # noqa: E402
import utils  # noqa: E402
from adapter import get_opening_prompt  # noqa: E402

CASE_ID = "04-worldcup-test"
OUTPUT_PATH = (
    Path(__file__).resolve().parents[4]
    / "database"
    / "node_eval"
    / "judge_eval"
    / "judge_golden_set_worldcup.csv"
)

# Reusable building blocks, copied verbatim from src/synthetic-dataset/04-worldcup-test.json.

OPENING = (
    "Your client is the Interconta World Football Cup Organizing Committee (IWFC), the "
    "commercial body responsible for the quadrennial global football tournament. For the "
    "upcoming edition, the tournament is expanding from 32 to 48 national teams, played "
    "across three co-host countries. Total tournament revenue is projected to grow 45% "
    "versus the last edition, but the Organizing Committee's own financial model shows "
    "EBITDA margin falling from 38% to roughly 24% over the same period. The Committee's "
    "Secretary General has brought you in to explain why profitability is deteriorating "
    "despite the growth, and to recommend whether - and how - the expansion can be made to "
    "pay for itself."
)

DATA_REVEAL = (
    "Previous edition: 32 teams, 64 matches, single host country. Upcoming edition: 48 "
    "teams, 104 matches, three co-host countries. Broadcasting rights are sold "
    "predominantly as a fixed package per tournament, not per match. Sponsorship and "
    "licensing revenue, tied to global reach, drove most of the 45% revenue growth. On the "
    "cost side, three host countries mean roughly triplicated venue, security, and "
    "logistics infrastructure instead of a 62.5% scale-up, team travel and accommodation "
    "costs have risen because delegations move between host countries during the group "
    "stage, and prize money scales directly with the number of qualifying teams."
)

MATH_Q = (
    "The interviewer now provides the following numbers: previous edition total revenue "
    "was EUR 3.0B with total costs of EUR 1.86B across 64 matches - that's a 38% EBITDA "
    "margin. The upcoming edition is projected at EUR 4.35B revenue, a 24% EBITDA margin, "
    "across 104 matches. Can you work out revenue per match and cost per match for both "
    "editions, and tell me how they've changed?"
)

REC_ASK = "Based on your analysis, what recommendation would you give the Secretary General?"

MATH_CORRECT = (
    "Previous edition: revenue per match is EUR 3.0B divided by 64, about EUR 46.9M, and "
    "cost per match is EUR 1.86B divided by 64, about EUR 29.1M. For the upcoming edition, "
    "total cost is 76% of EUR 4.35B, so about EUR 3.31B. Revenue per match is EUR 4.35B "
    "divided by 104, about EUR 41.8M, and cost per match is EUR 3.31B divided by 104, about "
    "EUR 31.8M. So revenue per match is down roughly 11%, and cost per match is up roughly "
    "9%."
)

REC_STRONG = (
    "Renegotiate future broadcasting deals so value scales more with match count rather "
    "than a flat tournament package - that's the revenue-side fix. Set explicit "
    "cost-sharing and shared-infrastructure targets with host countries before agreeing to "
    "any future expansion, since the tri-host cost base is the biggest driver of the gap. "
    "The main risks are that broadcasters may prefer "
    "the certainty of a fixed package, and that cost-sharing runs into host-country "
    "politics. Next steps: commission a per-match value analysis on the broadcasting "
    "portfolio, and set country-specific cost targets ahead of the next bidding cycle."
)


def _t(*lines: str) -> list[str]:
    """Small readability helper: pass alternating role-prefixed strings."""
    return list(lines)

# Handwritten case
ITEMS: list[dict[str, Any]] = [
    # FALSE (25)
    {
        "id": "WC_01",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": (
            "Single unfounded guess after the opening prompt; no recap, no clarifying "
            "question, no structure, no data requested. Nothing beyond a very weak "
            "case_opening has any material to score."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: This is probably just because ticket prices didn't go up enough "
            "with the bigger stadiums.",
        ),
    },
    {
        "id": "WC_02",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_01: an unfounded first reaction with no recap, structure, or data.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd guess player salaries went up a lot because there are more "
            "teams now, so that's probably eating the margin.",
        ),
    },
    {
        "id": "WC_03",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_01/WC_02: a generic reaction with no structure or data exchanged.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Sounds like a classic case of costs growing faster than revenue - "
            "I'd just tell them to cut spending across the board.",
        ),
    },
    {
        "id": "WC_04",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": (
            "Opening and a clean MECE structure are in place, but the interviewer hasn't "
            "revealed any of the tournament/cost data yet, so there's nothing to test the "
            "candidate's diagnosis against -- final_recommendation and "
            "overall_problem_solving remain untested."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Let me play that back: revenue's up 45% but EBITDA margin fell "
            "from 38% to 24%, driven by going from 32 to 48 teams across three host "
            "countries instead of one. Before I structure this - is the Committee looking "
            "for a one-off explanation for this edition, or a repeatable model for future "
            "expansions?",
            "Interviewer: They want a repeatable model - this can't happen again next "
            "cycle.",
            "Candidate: Understood. I'd split this into revenue streams - broadcasting, "
            "sponsorship, ticketing, hospitality, licensing - versus the incremental cost "
            "base from expanding to three host countries: venues, logistics, travel, "
            "security, prize money. I'd also want to compare per-match economics between "
            "the two editions rather than just totals, since match count itself has "
            "changed a lot. Could you share how each revenue stream and cost category has "
            "moved?",
        ),
    },
    {
        "id": "WC_05",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_04: solid structure proposed, but the data block was never revealed.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Before structuring, is margin recovery the hard priority, or is "
            "some dilution acceptable as the price of global growth?",
            "Interviewer: Margin recovery is the priority.",
            "Candidate: Then I'd look at this as revenue streams versus the incremental "
            "cost of expansion, and specifically at per-match economics rather than "
            "totals, since the match count itself has jumped. What's changed on the "
            "revenue side, stream by stream?",
        ),
    },
    {
        "id": "WC_06",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_04/WC_05: structure proposed but interviewer defers the data reveal.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd like to split revenue from the incremental cost base created "
            "by hosting in three countries, and look at per-match figures given the jump "
            "from 64 to 104 matches. What's driving the cost side specifically?",
            "Interviewer: Good instinct - we'll get to the specific numbers, keep going "
            "with your structure first.",
            "Candidate: Sure - within costs I'd separate venue and security "
            "infrastructure, team travel and accommodation, and prize money, since each "
            "could scale differently with teams versus host countries.",
        ),
    },
    {
        "id": "WC_07",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": (
            "Structure and data-driven synthesis are both strong, but the interview stops "
            "before the quantification step or the recommendation ask -- case_math_answer "
            "and final_recommendation both remain untested."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Before I structure this, is the Committee after a one-off "
            "diagnosis or a repeatable model for future editions?",
            "Interviewer: A repeatable model.",
            "Candidate: I'd split revenue streams from the incremental cost base of "
            "expansion, and look at per-match economics rather than totals, since match "
            "count jumped a lot. Could you share how revenue and costs have moved?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That's a strong signal - if broadcasting is sold as a fixed "
            "package, jumping from 64 to 104 matches barely moves broadcasting revenue, "
            "so revenue per match must be falling. Meanwhile three host countries "
            "roughly triples fixed infrastructure costs instead of scaling 62.5%, and "
            "travel plus prize money add further cost. So this looks like a structural "
            "mismatch between a flat revenue model and a cost model that scales - and "
            "sometimes triplicates - with the format change.",
        ),
    },
    {
        "id": "WC_08",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_07: correct qualitative synthesis, but stops before math/recommendation.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Quick question first - should I anchor on EBITDA margin "
            "specifically, or is free cash flow also part of the ask?",
            "Interviewer: Anchor on EBITDA margin.",
            "Candidate: I'll split this into revenue streams versus the incremental cost "
            "of the three-host-country format, and compare per-match economics across "
            "editions. What's changed on each side?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So the revenue growth is really coming from sponsorship and "
            "licensing, not from the format itself monetizing well, since broadcasting is "
            "a flat package. And the cost side is the bigger story: three host countries "
            "instead of one means infrastructure, security, and travel costs are scaling "
            "much faster than the 62.5% increase in matches.",
            "Interviewer: What does that imply about where the fix should focus?",
            "Candidate: It suggests the fix has to touch both sides - how broadcasting "
            "value is captured, and how host-country costs are shared - rather than just "
            "one lever.",
        ),
    },
    {
        "id": "WC_09",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_07/WC_08: solid diagnosis reached, but the interview ends before quantification or a recommendation.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Before I dive in - is there a hard deadline for the "
            "recommendation, like the next hosting bid cycle?",
            "Interviewer: Yes, ideally before the next bid cycle.",
            "Candidate: Got it. I'll separate revenue streams from the incremental cost "
            "base of the expansion, and look at this on a per-match basis given matches "
            "went from 64 to 104. What's the picture on each side?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Okay - so broadcasting, the biggest stream, is fixed per "
            "tournament, meaning more matches dilutes it per match. Sponsorship and "
            "licensing explain the actual 45% growth. On costs, tripling the host "
            "countries is doing more damage than the extra matches themselves, plus new "
            "travel costs between host countries that didn't exist before.",
        ),
    },
    {
        "id": "WC_10",
        "category": "PREMATURE_CONCLUSION",
        "expected_enough_evidence": False,
        "rationale": (
            "A recommendation-shaped line exists, but it was given cold, with no "
            "structure or data exchanged -- ungrounded, not evidence."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd recommend they scale back to a single host country next time "
            "- three countries is clearly too expensive.",
        ),
    },
    {
        "id": "WC_11",
        "category": "PREMATURE_CONCLUSION",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_10: an ungrounded recommendation with no preceding structure or data.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: My recommendation is to renegotiate the broadcasting contract - "
            "that should fix the margin problem.",
        ),
    },
    {
        "id": "WC_12",
        "category": "PREMATURE_CONCLUSION",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_10/WC_11: recommendation given before any case fact has been exchanged.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Honestly, they should just sell more sponsorships and unused ad "
            "space around the stadiums - that would close the gap.",
        ),
    },
    {
        "id": "WC_13",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate reaches a well-grounded recommendation, but the interviewer "
            "never asked the case's quantified per-match math question, so "
            "case_math_answer has nothing to be scored against despite the case having a "
            "dedicated math exhibit ready to test."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis only, or also a recommendation on making "
            "the expansion pay for itself?",
            "Interviewer: Both.",
            "Candidate: I'd split revenue streams from the incremental cost base of the "
            "three-host expansion, and look at per-match economics. What's changed on "
            "each side?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So a fixed broadcasting package dilutes per-match revenue as "
            "matches grow, while tripled host-country infrastructure, added travel, and "
            "team-linked prize money push per-match cost up - a structural mismatch, not "
            "weak demand.",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_14",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_13: the recommendation is reached, but the math exchange is missing.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Before structuring - is margin recovery the priority, even if it "
            "means slower future expansion?",
            "Interviewer: Yes, margin recovery is the priority.",
            "Candidate: I'll split this into revenue streams versus the incremental cost "
            "of the expansion, and look at per-match figures. What's the picture?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: This points to a fixed-revenue, scaling-cost mismatch: "
            "broadcasting barely grows with match count, while the tri-host format "
            "roughly triples infrastructure cost and adds new travel costs.",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_19",
        "category": "UNFINISHED_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate begins the calculation but never reaches a usable answer, and "
            "the conversation stops there -- no recommendation. "
            "There isn't a complete answer to score case_math_answer against, and none of "
            "the later-stage dimensions have been reached either."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the goal a repeatable model for future editions?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion and "
            "look at per-match economics. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So fixed broadcasting revenue is being diluted while tri-host "
            "costs are scaling faster than matches.",
            f"Interviewer: {MATH_Q}",
            "Candidate: Okay, let me try... revenue per match before is 3 billion over... "
            "sorry, how many matches was that again?",
            "Interviewer: 64 matches.",
            "Candidate: Right, so that's... give me a second, the numbers are quite "
            "large. I think I'd need a calculator to get this exactly right, but roughly "
            "it would be revenue divided by matches on both sides.",
        ),
    },
    {
        "id": "WC_20",
        "category": "UNFINISHED_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_19: the math attempt stalls before producing usable numbers, and nothing later is reached.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should I anchor on EBITDA margin recovery specifically?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue streams from the incremental cost base and "
            "look at per-match figures. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So broadcasting dilution plus tripled host-country costs look "
            "like the two drivers.",
            f"Interviewer: {MATH_Q}",
            "Candidate: Let's see - 4.35 billion at 24% margin... I need to work out the "
            "cost figure first, but I'm getting a bit turned around on whether the "
            "margin applies to revenue or to costs. Can you remind me how EBITDA margin "
            "is defined here?",
            "Interviewer: EBITDA margin is EBITDA over revenue.",
            "Candidate: Right - I think I still need another moment to get the exact "
            "euro figures right rather than guess.",
        ),
    },
    {
        "id": "WC_21",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": (
            "Every earlier stage -- structure, data, and math -- "
            "is fully covered, but the transcript ends the moment the interviewer asks "
            "for a recommendation, before the candidate answers. final_recommendation, "
            "the single most decision-relevant dimension, has no candidate content to "
            "score."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a repeatable model going forward, or just this "
            "edition?",
            "Interviewer: A repeatable model.",
            "Candidate: I'll split revenue from the incremental cost base of expansion "
            "and look at per-match economics. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So fixed broadcasting revenue is diluted as matches grow, while "
            "tripled host-country costs and new travel costs push per-match cost up - a "
            "structural mismatch, not weak demand.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
        ),
    },
    {
        "id": "WC_22",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_21: everything up to and including the recommendation ask is covered, but the candidate's answer is missing.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is margin recovery the hard priority here?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue streams from the incremental cost base and "
            "look at this per match given matches went from 64 to 104. What's the "
            "picture?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: This is a fixed-revenue, scaling-cost problem: broadcasting "
            "barely grows with match count while the tri-host format multiplies "
            "infrastructure cost.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
        ),
    },
    {
        "id": "WC_23",
        "category": "NON_RESPONSIVE",
        "expected_enough_evidence": False,
        "rationale": (
            "Despite several turns of back-and-forth, the candidate keeps restating the "
            "same generic revenue-vs-cost framing without ever requesting the case's "
            "specific data, so nothing progresses past the opening -- length alone "
            "doesn't create evidence."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: So basically revenue went up but margin went down, so costs must "
            "have gone up more than revenue.",
            "Interviewer: Can you be more specific about what you'd want to look at?",
            "Candidate: Sure, I'd look at revenue and I'd look at costs.",
            "Interviewer: What specifically within revenue and costs?",
            "Candidate: Well, on revenue side, revenue things, and on the cost side, cost "
            "things - basically anything that could be driving the numbers.",
            "Interviewer: Can you name specific revenue streams or cost categories for a "
            "tournament like this?",
            "Candidate: I mean, tournaments have revenue and they have expenses, so I'd "
            "want to see both broken down generally.",
            "Interviewer: Broken down how, specifically?",
            "Candidate: Just generally by category, so we can see where the money is "
            "going and where it's coming from.",
        ),
    },
    {
        "id": "WC_24",
        "category": "NON_RESPONSIVE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_23: many turns of restated generic framing, never reaching real data or a recommendation.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: This is a classic profitability problem - profit is revenue "
            "minus cost, so something on one of those sides must be off.",
            "Interviewer: Which side would you like to start with?",
            "Candidate: Let's start broad and look at the overall numbers first.",
            "Interviewer: The overall numbers are in the prompt - 45% revenue growth, "
            "margin down from 38% to 24%. What would you like to know beyond that?",
            "Candidate: I'd want to understand the overall trend a bit more before "
            "narrowing in.",
            "Interviewer: Can you propose a specific structure to narrow in with?",
            "Candidate: I think the key is really just understanding revenue and cost at "
            "a high level first, then going from there.",
            "Interviewer: We've been at a high level for a while now - what's your first "
            "concrete question?",
            "Candidate: Maybe just, generally, what's been happening with the business "
            "overall.",
        ),
    },
    {
        "id": "WC_25",
        "category": "EVIDENCE_MISREAD",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate misreads the central case fact -- broadcasting is explicitly "
            "a fixed package, not sold per match -- and even after a direct interviewer "
            "correction, doesn't recover the insight or move on to quantification or a "
            "recommendation."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue streams from the incremental cost of "
            "expansion and look at this per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Okay, so broadcasting is sold per match, which means with 104 "
            "matches instead of 64, broadcasting revenue should have gone up a lot - "
            "that's probably most of the 45% growth.",
            "Interviewer: Take another look at how broadcasting is actually sold here.",
            "Candidate: Right, either way I think the bigger issue is just that they "
            "added too many teams overall.",
        ),
    },
    # TRUE (25)
    {
        "id": "WC_26",
        "category": "FULL_COVERAGE_CLEAN",
        "expected_enough_evidence": True,
        "rationale": (
            "Every stage -- objective clarification, MECE structure, data-grounded "
            "synthesis, correct quantification, and a "
            "risk-aware recommendation -- closely mirrors the case's own expected "
            "analysis and ideal answer, giving the eval nodes clean material to score "
            "every dimension highly."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Let me play that back: revenue up 45%, margin down from 38% to "
            "24%, driven by going from 32 to 48 teams across three host countries. "
            "Before I structure this - does the Committee want a repeatable model for "
            "future editions, or just an explanation for this one, and is margin "
            "recovery the hard priority?",
            "Interviewer: They want a repeatable model, and yes, margin recovery is the "
            "priority - this can't happen again next cycle.",
            "Candidate: Understood. I'd split this into revenue streams - broadcasting, "
            "sponsorship, ticketing, hospitality, licensing - versus the incremental "
            "cost base of expansion - venues, logistics, travel, security, prize money - "
            "and look at per-match economics rather than totals, since matches went from "
            "64 to 104. My working hypothesis is that a lot of this revenue is priced as "
            "a flat package, so more matches could be diluting revenue per match, even "
            "as total revenue grows.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That confirms it. Broadcasting, the largest stream, is sold as a "
            "fixed package, so jumping from 64 to 104 matches barely moves it, meaning "
            "revenue per match falls. Sponsorship and licensing, tied to global reach, "
            "explain the actual 45% growth. On costs, three host countries roughly "
            "triples fixed infrastructure instead of scaling 62.5%, and travel between "
            "host countries plus team-linked prize money add further cost. This is a "
            "structural mismatch between a flat revenue model and a triplicating cost "
            "model, not weak demand.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_27",
        "category": "FULL_COVERAGE_CLEAN",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_26: a complete, well-grounded run through every stage, closely tracking the case's ideal solution.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Before structuring, I want to make sure I've got the ask right: "
            "is this purely a diagnosis, or do you also want a concrete recommendation "
            "on making the expansion self-sustaining?",
            "Interviewer: Both - diagnosis and recommendation.",
            "Candidate: Understood. I'd start with the cost side, since three host "
            "countries instead of one is the structural change that jumps out at me, "
            "then look at revenue streams, then compare per-match economics across "
            "editions.",
            "Interviewer: Go ahead.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That reshapes the picture: tripling host-country infrastructure, "
            "adding cross-country travel, and prize money scaling with 48 teams explains "
            "the cost side, while a fixed broadcasting package explains why revenue per "
            "match is falling even as total revenue and sponsorship both grow.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_28",
        "category": "FULL_COVERAGE_CLEAN",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_26/WC_27: full, strong coverage of every stage.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: One clarifying question before I structure this: is there a "
            "specific timeline the Secretary General has in mind, like the next hosting "
            "bid cycle?",
            "Interviewer: Yes, ideally ready before the next bid cycle.",
            "Candidate: Understood. I'll split revenue streams from the incremental cost "
            "base of the three-host expansion, and anchor on per-match economics rather "
            "than totals, since matches nearly doubled. My hypothesis is that a "
            "fixed-package revenue model isn't scaling with match count the way costs "
            "are.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Confirmed - broadcasting's fixed-package structure dilutes "
            "revenue per match, sponsorship and licensing are the real growth drivers, "
            "and the tri-host format roughly triples infrastructure cost plus adds new "
            "travel cost and team-linked prize money.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_29",
        "category": "FULL_COVERAGE_CLEAN",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_26-28: complete, strong-quality coverage of every applicable stage.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Let me recap first: revenue is up 45%, but EBITDA margin fell "
            "from 38% to 24%, tied to expanding from 32 to 48 teams across three host "
            "countries. Is margin recovery non-negotiable, or is some dilution "
            "acceptable if it funds long-term growth?",
            "Interviewer: Margin recovery is non-negotiable this time.",
            "Candidate: Then I'd separate revenue streams from the incremental cost of "
            "the expansion, and compare per-match economics across editions, since match "
            "count jumped 62.5%. I suspect the revenue side isn't built to monetize more "
            "matches the way the cost side is built to multiply with host countries.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Right - fixed-package broadcasting means more matches dilutes "
            "revenue per match, sponsorship/licensing drove the real growth, and the "
            "tri-host setup roughly triples infrastructure cost while adding new travel "
            "and team-linked prize-money costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_30",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": (
            "Every stage is touched, so there's transcript material for every rubric "
            "dimension, but execution is generic and under-quantified throughout, which "
            "should drive low -- not missing -- scores."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd look at revenue and costs separately.",
            "Interviewer: Go ahead.",
            "Candidate: What changed on each side?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So broadcasting didn't grow much and the three countries cost "
            "more.",
            f"Interviewer: {MATH_Q}",
            "Candidate: Roughly revenue per match went down a bit and cost per match "
            "went up a bit.",
            f"Interviewer: {REC_ASK}",
            "Candidate: Renegotiate broadcasting and manage the host-country costs "
            "better.",
        ),
    },
    {
        "id": "WC_31",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_30: full stage coverage, but thin and generic throughout.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Okay, so revenue is up but margin is down, meaning costs grew "
            "faster.",
            "Interviewer: What would you want to look at to confirm that?",
            "Candidate: Just the revenue and cost breakdown I guess.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Right, so the broadcasting deal is fixed and the three countries "
            "add a lot of cost.",
            f"Interviewer: {MATH_Q}",
            "Candidate: I think revenue per match goes down and cost per match goes up, "
            "somewhere around ten percent each way.",
            f"Interviewer: {REC_ASK}",
            "Candidate: Fix the broadcasting deal and try to cut some of the host-"
            "country costs.",
        ),
    },
    {
        "id": "WC_32",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_30/WC_31: every stage present, quality thin throughout.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'll check revenue first, then costs.",
            "Interviewer: Sure.",
            "Candidate: What's the breakdown look like?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So it sounds like broadcasting isn't really growing and the "
            "extra countries are expensive.",
            f"Interviewer: {MATH_Q}",
            "Candidate: I'd say per match revenue is down and per match cost is up, "
            "roughly.",
            f"Interviewer: {REC_ASK}",
            "Candidate: Try to fix the broadcasting side and control costs in the host "
            "countries.",
        ),
    },
    {
        "id": "WC_33",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": (
            "Needed one direct nudge to move off an unhelpful ticket-pricing tangent, "
            "but the transcript still reaches full coverage -- structure, data, math, "
            "and a risk-aware recommendation -- so there is enough "
            "evidence to evaluate, including how the candidate handled redirection."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd start by looking at ticket pricing strategy across the three "
            "host countries.",
            "Interviewer: What happens to the value of the broadcasting deal when it's "
            "spread across 104 matches instead of 64?",
            "Candidate: Good point - let's look at broadcasting and the rest of revenue "
            "first, then costs.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That confirms it - fixed-package broadcasting dilutes per-match "
            "revenue as matches grow, while the tri-host format triples infrastructure "
            "cost and adds new travel costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_34",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_33: one redirect needed, but full coverage still reached.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd want to look at overall administrative overhead first.",
            "Interviewer: Would it help to look at revenue streams versus the "
            "incremental cost of the three-host format instead?",
            "Candidate: Yes, that's a better starting point - let's split it that way.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So fixed-package broadcasting is being diluted by the extra "
            "matches, while three host countries roughly triple infrastructure cost and "
            "add new travel costs on top.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_35",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_33/WC_34: after a nudge back on track, the transcript reaches full coverage.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd first check whether player salaries have gone up "
            "disproportionately.",
            "Interviewer: What happens to the value of the broadcasting deal when it's "
            "spread across 104 matches instead of 64?",
            "Candidate: Fair - let's look at broadcasting and revenue overall before "
            "costs.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Right, so a fixed broadcasting package means revenue per match "
            "falls as matches increase, while the tri-host setup roughly triples "
            "infrastructure cost and adds travel costs that didn't exist before.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_36",
        "category": "FULL_COVERAGE_CLEAN",
        "expected_enough_evidence": True,
        "rationale": (
            "Even compressed into very few turns, the candidate covers objective, "
            "structure, hypothesis, correct quantification, "
            "and a complete recommendation -- brevity doesn't reduce evidence "
            "when every stage is genuinely covered."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Quick clarifying question - are we optimizing for this edition "
            "only, or the model going forward?",
            "Interviewer: Going forward.",
            "Candidate: Then I'd split revenue streams from the incremental cost base of "
            "expansion and look at per-match economics rather than totals. Two things "
            "I'd check: is broadcasting sold per match or as a fixed package, and how do "
            "venue/security costs scale with host-country count versus match count?",
            "Interviewer: Broadcasting is a fixed package. Three host countries roughly "
            "triples venue and security infrastructure.",
            "Candidate: Then that's the whole story: a 62.5% jump in matches barely "
            "moves fixed broadcasting revenue, so revenue per match falls, while "
            "tripling infrastructure plus travel and prize money scaling with team count "
            "pushes cost per match up. On the numbers, that's revenue per match down "
            "from about EUR 46.9M to EUR 41.8M, and cost per match up from about EUR "
            "29.1M to EUR 31.8M. My recommendation: renegotiate broadcasting toward "
            "per-match or tiered value, and lock in cost-sharing with future host countries "
            "before any more expansion.",
            "Interviewer: That's right on the money.",
        ),
    },
    {
        "id": "WC_37",
        "category": "FULL_COVERAGE_CLEAN",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_36: concise, but every stage is genuinely covered.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is margin recovery the priority, or is some dilution acceptable "
            "for global growth?",
            "Interviewer: Margin recovery is the priority.",
            "Candidate: Then split revenue from the incremental cost of expansion, "
            "per-match. My hypothesis: fixed-package broadcasting dilutes per-match "
            "revenue as matches grow, while three host countries triple infrastructure "
            "cost. What does the data show?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Confirmed. Revenue per match: EUR 46.9M to EUR 41.8M, down about "
            "11%. Cost per match: EUR 29.1M to EUR 31.8M, up about 9%. Recommendation: "
            "renegotiate broadcasting toward per-match value, and lock in host-country "
            "cost-sharing before further expansion.",
            "Interviewer: Good, that covers it.",
        ),
    },
    {
        "id": "WC_38",
        "category": "FULL_COVERAGE_CLEAN",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_36/WC_37: brief but complete coverage of every stage.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: One question first - repeatable model, or one-off diagnosis?",
            "Interviewer: Repeatable model.",
            "Candidate: Then I'd separate revenue streams from the incremental cost of "
            "the three-host expansion, on a per-match basis. My hypothesis is that fixed "
            "broadcasting pricing means more matches dilutes revenue per match while "
            "tripled host-country infrastructure raises cost per match. Can you confirm "
            "how broadcasting is sold and how costs scale by host country?",
            "Interviewer: Broadcasting is a fixed package, and yes, three host countries "
            "roughly triples infrastructure and security cost.",
            "Candidate: That's consistent with revenue per match falling from about EUR "
            "46.9M to EUR 41.8M and cost per match rising from about EUR 29.1M to EUR "
            "31.8M. I'd renegotiate broadcasting toward per-"
            "match value, agree cost-sharing with host countries up front.",
        ),
    },
    {
        "id": "WC_39",
        "category": "FULL_COVERAGE_CONTENT_FLAW_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": (
            "The candidate reaches every stage, including an attempt at the math, but "
            "arrives at an incorrect per-match conclusion. That's a case_math_answer "
            "scoring problem, not a coverage problem -- there is a complete answer on "
            "the record for the eval node to grade, even though it's wrong."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion and "
            "look at per-match economics. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So broadcasting dilution and tripled host-country costs both "
            "seem to be at play.",
            f"Interviewer: {MATH_Q}",
            "Candidate: Previous edition: revenue per match is 3.0 billion over 64, "
            "about 46.9 million. For the upcoming edition, revenue per match is 4.35 "
            "billion over... let me use 64 again for consistency - that gives about 68 "
            "million, so actually revenue per match went up, not down, which is "
            "interesting.",
            f"Interviewer: {REC_ASK}",
            "Candidate: Given revenue per match is actually holding up, I'd focus mainly "
            "on containing the host-country cost side - tighter cost-sharing "
            "agreements before any further expansion.",
        ),
    },
    {
        "id": "WC_40",
        "category": "FULL_COVERAGE_CONTENT_FLAW_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_39: full coverage, but the math conclusion is wrong -- a scoring issue, not a coverage gap.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should I anchor on EBITDA margin specifically?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion and "
            "look at per-match figures. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Fixed broadcasting and tripled host-country costs look like the "
            "two drivers.",
            f"Interviewer: {MATH_Q}",
            "Candidate: Okay - previous edition cost per match is 1.86 billion over 64, "
            "about 29.1 million. For the new edition, I'll take 24% of 4.35 billion as "
            "the cost directly, so that's about 1.04 billion, divided by 104 matches, "
            "about 10 million per match - so cost per match actually looks like it's "
            "gone down a lot.",
            f"Interviewer: {REC_ASK}",
            "Candidate: Since the cost side looks more controlled than I expected, I'd "
            "focus the recommendation on capturing more broadcasting value per match.",
        ),
    },
    {
        "id": "WC_41",
        "category": "FULL_COVERAGE_CONTENT_FLAW_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_39/WC_40: complete run, incorrect math result, still evaluable end to end.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is there a hard deadline tied to the next bid cycle?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per-match. What's the picture?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Sounds like a fixed-revenue, scaling-cost mismatch.",
            f"Interviewer: {MATH_Q}",
            "Candidate: Revenue per match previously: 3.0 billion over 64 matches, about "
            "46.9 million. This edition: 4.35 billion over 48 teams - so about 90 "
            "million per team, which suggests things are actually much healthier per "
            "unit than the margin numbers imply.",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_44",
        "category": "FULL_COVERAGE_HALLUCINATED_DATA",
        "expected_enough_evidence": True,
        "rationale": (
            "The candidate invents an unsupported ticketing statistic not present "
            "anywhere in the case materials, which should hurt groundedness scoring, "
            "but every stage of the interview is still covered end to end, so there is "
            "enough transcript to evaluate every dimension -- enough_evidence tracks "
            "coverage, not factual accuracy."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion and "
            "look at per-match economics. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Right, and I understand ticketing revenue actually fell about "
            "15% this edition because of capacity constraints in the new stadiums, on "
            "top of the fixed-broadcasting dilution and the tripled host-country "
            "costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_45",
        "category": "FULL_COVERAGE_HALLUCINATED_DATA",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_44: an invented fact appears mid-analysis, but full stage coverage is still reached.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is margin recovery non-negotiable this cycle?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per-match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That lines up with what I'd heard - I believe security costs "
            "specifically are up around EUR 200M this edition given the three-country "
            "footprint, on top of the broadcasting dilution point.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_46",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": (
            "The path is long and non-linear -- two tangents, two interviewer "
            "redirects -- but the transcript still ends up covering every stage the "
            "case requires, so there is enough evidence to evaluate, including a real "
            "signal on how the candidate handles being redirected repeatedly."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd want to look at sponsor churn first - maybe some big "
            "sponsors dropped out.",
            "Interviewer: There's no indication of sponsor churn here. What about the "
            "format change itself - 32 to 48 teams, one host to three?",
            "Candidate: Fair, let's look at that. I'd split revenue from the "
            "incremental cost of the expansion.",
            "Interviewer: Go ahead.",
            "Candidate: On the cost side, I'd guess player accommodation is the biggest "
            "new cost.",
            "Interviewer: What happens to the value of the broadcasting deal when it's "
            "spread across 104 matches instead of 64?",
            "Candidate: Good redirect - let's look at broadcasting specifically before "
            "anything else.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Okay, now it's clear: fixed-package broadcasting means revenue "
            "per match falls as matches grow, while three host countries roughly "
            "triples infrastructure cost and adds new travel costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_47",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_46: several tangents and redirects, but full coverage is eventually reached.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: My first thought is currency exchange-rate exposure across "
            "three countries.",
            "Interviewer: That's not the driver here - think about the format change "
            "itself.",
            "Candidate: Understood. I'd split revenue streams from the incremental cost "
            "of expansion, then.",
            "Interviewer: Go ahead.",
            "Candidate: On revenue, I'd guess ticket pricing is the main issue.",
            "Interviewer: What happens to the value of the broadcasting deal when it's "
            "spread across 104 matches instead of 64?",
            "Candidate: Right, let's focus there instead.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That clarifies it - fixed broadcasting dilutes per-match "
            "revenue as matches increase, while the tri-host format roughly triples "
            "infrastructure cost and adds travel and prize-money costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_48",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_46/WC_47: a winding path that still lands on full coverage.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd first want to check if there was a one-off write-off this "
            "edition, like an insurance claim or a legal settlement.",
            "Interviewer: No such write-off - this is about the format change itself.",
            "Candidate: Okay, I'll split revenue from the incremental cost of "
            "expansion, then, and look at per-match economics.",
            "Interviewer: Go ahead.",
            "Candidate: I'd guess merchandising is the main revenue swing factor.",
            "Interviewer: What happens to the value of the broadcasting deal when it's "
            "spread across 104 matches instead of 64?",
            "Candidate: Let's dig into broadcasting specifically then.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That resolves it - fixed-package broadcasting dilutes revenue "
            "per match as matches grow, and the tri-host setup roughly triples "
            "infrastructure cost, plus new travel and prize-money costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_49",
        "category": "FULL_COVERAGE_CONTENT_FLAW_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": (
            "The recommendation is directionally correct and grounded in the analysis, "
            "but stops short of naming risks or next steps. That's a "
            "final_recommendation quality gap, not a coverage gap -- every stage, "
            "including this one, has content for the eval node to score."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion and "
            "look at per-match economics. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So fixed-package broadcasting dilutes revenue per match as "
            "matches grow, while the tri-host format roughly triples infrastructure "
            "cost.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            "Candidate: I'd renegotiate the broadcasting contracts to scale more with "
            "match count, and get the host countries to share more of the "
            "infrastructure cost.",
        ),
    },
    {
        "id": "WC_50",
        "category": "FULL_COVERAGE_CONTENT_FLAW_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_49: full coverage reached, but the recommendation itself skips risks/next steps.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should I anchor on EBITDA margin specifically?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per-match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Fixed broadcasting dilution and tripled host-country costs "
            "explain the gap.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            "Candidate: Push broadcasters toward per-match value capture, and set "
            "cost-sharing agreements with host countries.",
        ),
    },
    # Second batch: more depth on weak categories
    {
        "id": "WC_51",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_13/WC_14: the recommendation is reached, but the math exchange is missing.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should we treat this as a one-off issue for this edition, or "
            "design something repeatable for future expansions?",
            "Interviewer: Something repeatable, please.",
            "Candidate: Then I'd separate revenue streams from the incremental cost of "
            "expanding to three host countries, and look at this on a per-match basis "
            "rather than in aggregate.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That tells me broadcasting revenue is essentially frozen per "
            "tournament, so spreading it over more matches dilutes it, while the extra "
            "host countries add roughly triple the fixed infrastructure cost instead of "
            "a proportional increase.",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_52",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_51: everything but the math exchange is present.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd like to know whether the priority is protecting margin or "
            "protecting growth, if the two are in tension.",
            "Interviewer: Protecting margin is the priority here.",
            "Candidate: Understood. I'll split this into revenue streams versus the "
            "incremental cost of the three-host format, and check per-match economics "
            "rather than totals.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So the structural story is a fixed-package broadcasting deal "
            "losing value per match as the tournament grows, combined with host-country "
            "costs that roughly triple instead of scaling with matches.",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_56",
        "category": "UNFINISHED_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_19/WC_20: the math attempt stalls before producing usable numbers, and nothing later is reached.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should I treat this purely as a diagnosis, or also come up with "
            "a fix?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue streams from the incremental cost base, and "
            "look at per-match economics. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So broadcasting is diluting per match while host-country costs "
            "are multiplying.",
            f"Interviewer: {MATH_Q}",
            "Candidate: Okay - previous revenue per match is 3 billion divided by... "
            "sorry, was it 64 or 104 matches for the old edition?",
            "Interviewer: 64 matches for the previous edition.",
            "Candidate: Right, so roughly 47 million per match then. For the new "
            "edition I'd need to redo the cost side too, and I want to make sure I "
            "don't mix up the two editions - let me take a moment to lay the numbers "
            "out properly rather than rush it.",
        ),
    },
    {
        "id": "WC_57",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_21/WC_22: everything up to and including the recommendation ask is covered, but the candidate's answer is missing.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the goal purely diagnosis, or also a fix the Committee can "
            "act on?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So fixed-package broadcasting is being diluted while "
            "host-country costs are roughly tripling.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
        ),
    },
    {
        "id": "WC_58",
        "category": "INCOMPLETE_COVERAGE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_57: the transcript ends the moment the recommendation is asked for.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should I anchor purely on EBITDA margin recovery?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue streams from the incremental cost of "
            "expansion, per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So the fixed-package broadcasting deal loses value per match as "
            "the tournament grows, while the tri-host format multiplies infrastructure "
            "cost.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
        ),
    },
    {
        "id": "WC_59",
        "category": "NON_RESPONSIVE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_23/WC_24: many turns of restated generic framing, never reaching real data or a recommendation.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: So there's clearly something going on with either revenue or "
            "costs.",
            "Interviewer: Which would you like to look at first?",
            "Candidate: Let's just look at the numbers broadly first.",
            "Interviewer: Which numbers specifically?",
            "Candidate: Whatever's driving the margin change, generally speaking.",
            "Interviewer: Can you propose a structure to look at this with?",
            "Candidate: I think the main thing is to understand what's happening at a "
            "high level before going deeper.",
            "Interviewer: We've been at a high level for several turns now - what's one "
            "concrete thing you'd ask for?",
            "Candidate: Maybe just an overview of how the tournament has changed "
            "recently.",
        ),
    },
    {
        "id": "WC_60",
        "category": "EVIDENCE_MISREAD",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_25: the candidate misreads a central case fact -- here, assuming broadcasting scales with host-country count -- isn't corrected even after a direct interviewer prompt, and the interview stops before quantification or a recommendation.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is this purely a diagnosis, or also a recommendation?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Since the tournament now has three host countries instead of "
            "one, I'd expect broadcasting revenue to have roughly tripled too, which "
            "should be helping margin, not hurting it.",
            "Interviewer: Broadcasting isn't tied to the number of host countries - "
            "look again at how it's actually sold.",
            "Candidate: Fair, but I still think the extra host countries are probably "
            "the main upside here, so the issue must be elsewhere, maybe sponsorship "
            "contracts.",
        ),
    },
    {
        "id": "WC_61",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_30-32: full stage coverage, but thin and generic throughout.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd check what changed with revenue and costs.",
            "Interviewer: Go ahead.",
            "Candidate: Can you break that down for me?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Okay so broadcasting isn't really growing and the extra "
            "countries cost a lot more.",
            f"Interviewer: {MATH_Q}",
            "Candidate: I think revenue per match drops a bit and cost per match goes "
            "up a bit, roughly.",
            f"Interviewer: {REC_ASK}",
            "Candidate: Fix the broadcasting deal and try to control the host-country "
            "costs.",
        ),
    },
    {
        "id": "WC_62",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_33-35: one redirect needed, but full coverage still reached.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd want to check whether player transfer fees have changed.",
            "Interviewer: What happens to the value of the broadcasting deal when it's "
            "spread across 104 matches instead of 64?",
            "Candidate: Good redirect - let's start with broadcasting and revenue "
            "overall.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So fixed-package broadcasting dilutes per match as matches "
            "grow, while the tri-host format multiplies infrastructure cost.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_63",
        "category": "FULL_COVERAGE_CLEAN",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_36-38: concise, but every stage is genuinely covered.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: One question before I structure this - is the priority margin "
            "recovery even if it slows expansion, or is some dilution acceptable?",
            "Interviewer: Margin recovery is the priority.",
            "Candidate: Then I'll split revenue from the incremental cost of expansion, "
            "per match, and check two things: how broadcasting is sold, and how "
            "host-country count drives cost.",
            "Interviewer: Broadcasting is a fixed package, and three host countries "
            "roughly triples infrastructure and security cost.",
            "Candidate: That explains it - revenue per match falls from about EUR "
            "46.9M to EUR 41.8M while cost per match rises from about EUR 29.1M to EUR "
            "31.8M. I'd renegotiate broadcasting toward per-match value, "
            "agree cost-sharing with host countries up front.",
        ),
    },
    {
        "id": "WC_64",
        "category": "FULL_COVERAGE_CONTENT_FLAW_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_39-41: full coverage, but the math conclusion is wrong -- a scoring issue, not a coverage gap.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should I focus on this edition only, or the model going "
            "forward?",
            "Interviewer: Going forward.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Fixed broadcasting dilution and tripled host-country costs "
            "look like the drivers.",
            f"Interviewer: {MATH_Q}",
            "Candidate: Cost per match previously was 1.86 billion over 64 matches, "
            "about 29 million. For the new edition, 24% margin on 4.35 billion means "
            "EBITDA is about 1.04 billion, so cost must be about 3.3 billion - divided "
            "across 48 teams instead of matches, that's roughly 69 million per team, "
            "which suggests things are actually in decent shape per team.",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_67",
        "category": "FULL_COVERAGE_HALLUCINATED_DATA",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_44/WC_45: an invented fact appears mid-analysis, but full stage coverage is still reached.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Right, and I recall that merchandising revenue is also down "
            "about 20% this edition due to licensing disputes in one of the host "
            "countries, on top of the broadcasting dilution and tripled host-country "
            "costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_68",
        "category": "FULL_COVERAGE_HALLUCINATED_DATA",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_67: a different invented fact, full coverage otherwise.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should I anchor purely on EBITDA margin?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That's consistent with what I'd expect - I believe one of the "
            "three host countries also imposed a special hosting tax of around EUR "
            "150M on the Committee this edition, which would add to the cost pressure "
            "alongside the broadcasting dilution.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_69",
        "category": "FULL_COVERAGE_MESSY_PROCESS",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_46-48: several tangents and redirects, but full coverage is eventually reached.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd first check whether the tournament changed its ticket "
            "pricing tiers this edition.",
            "Interviewer: That's not the driver - think about the format change "
            "itself.",
            "Candidate: Okay, I'll split revenue from the incremental cost of "
            "expansion then.",
            "Interviewer: Go ahead.",
            "Candidate: I'd guess sponsorship contracts have penalty clauses tied to "
            "match count.",
            "Interviewer: What happens to the value of the broadcasting deal when it's "
            "spread across 104 matches instead of 64?",
            "Candidate: Right, let's focus on broadcasting specifically.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That clarifies it - fixed-package broadcasting dilutes revenue "
            "per match as matches grow, and the tri-host format roughly triples "
            "infrastructure cost, plus new travel and prize-money costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_70",
        "category": "FULL_COVERAGE_CONTENT_FLAW_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_49/WC_50: full coverage reached, but the recommendation itself skips risks/next steps.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Fixed-package broadcasting dilution and tripled host-country "
            "costs explain the gap.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            "Candidate: I'd move broadcasting toward a per-match pricing structure and "
            "agree cost-sharing with host countries for future editions.",
        ),
    },
    {
        "id": "WC_71",
        "category": "PREMATURE_CONCLUSION",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_10-12: a cold recommendation with no structure or data behind it, this time aimed at prize money specifically.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd just cut the prize money pool - that's obviously where the "
            "excess is.",
        ),
    },
    {
        "id": "WC_72",
        "category": "PREMATURE_CONCLUSION",
        "expected_enough_evidence": False,
        "rationale": "A confident demand-side verdict delivered cold -- sounding plausible doesn't substitute for structure or data.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: This is clearly a demand problem - fewer fans are showing up "
            "despite the bigger format, so I'd put more into marketing and fan "
            "engagement.",
        ),
    },
    {
        "id": "WC_73",
        "category": "PREMATURE_CONCLUSION",
        "expected_enough_evidence": False,
        "rationale": "One clarifying question doesn't turn this into real analysis -- the candidate still jumps straight to a recommendation with no structure and no data exchanged.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is margin recovery the priority?",
            "Interviewer: Yes.",
            "Candidate: Then I'd recommend raising ticket prices across all three host "
            "countries - that directly improves margin.",
        ),
    },
    {
        "id": "WC_74",
        "category": "PREMATURE_CONCLUSION",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_10-12/WC_73: a confident operational-efficiency verdict with no structure or data behind it.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: My honest take is the Committee just needs to run a leaner "
            "operation - cut overhead and administrative costs across the board.",
        ),
    },
    {
        "id": "WC_75",
        "category": "UNFINISHED_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": (
            "The revenue-per-match half of the calculation lands cleanly, but the "
            "candidate visibly stalls trying to back cost per match out of the margin "
            "percentage and never produces a usable cost figure -- an analysis genuinely "
            "begun, not one that was skipped."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is this meant to be a repeatable model for future editions?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion and "
            "look at per-match figures. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So a fixed broadcasting package plus tripled host-country costs "
            "looks like the core story.",
            f"Interviewer: {MATH_Q}",
            "Candidate: Revenue per match is straightforward - 4.35 billion over 104, so "
            "a bit over 41 million. For cost per match I need total cost first, and I'm "
            "working out 24% of 4.35 billion as EBITDA, so cost would be revenue minus "
            "EBITDA... let me redo that, I want to make sure I'm not mixing up margin "
            "and cost.",
            "Interviewer: Take your time.",
            "Candidate: Give me another moment - I keep second-guessing whether the 24% "
            "is of revenue or of something else.",
        ),
    },
    {
        "id": "WC_76",
        "category": "UNFINISHED_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate visibly attempts to build a structure but trails off before "
            "ever stating one cleanly, and the conversation ends there -- a structure "
            "genuinely started, not a case where nothing was attempted at all."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd want to split this into a few pieces - starting with, well, "
            "the revenue side, and then... actually, let me think about how best to "
            "break down the cost side too, since there's a lot going on there with the "
            "three countries and everything that comes with that, and I want to make "
            "sure I'm not missing a piece before I lay it all out...",
            "Interviewer: Take your time, but I'd like to hear the actual structure.",
            "Candidate: Right, sorry - give me a second to organize this properly, "
            "there's a few ways I could cut it and I want to pick the right one.",
        ),
    },
    {
        "id": "WC_77",
        "category": "UNFINISHED_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate begins interpreting the data reveal but the synthesis trails "
            "off before landing on an actual conclusion, and the conversation stops "
            "there -- an analysis started, not one that was never attempted."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Before anything else - is margin recovery the hard priority, "
            "even at the cost of slower future growth?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue streams from the incremental cost base of "
            "the expansion and look at this per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Okay, so broadcasting being a fixed package means... and then "
            "with the three host countries, the costs are... there's definitely a "
            "connection between those two things, I just need a second to put it "
            "together properly rather than guess at how they interact.",
            "Interviewer: Go ahead whenever you're ready.",
            "Candidate: Right - give me a moment, I want to state this precisely rather "
            "than hand-wave it.",
        ),
    },
    {
        "id": "WC_78",
        "category": "UNFINISHED_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate correctly gets both raw per-match figures but stalls "
            "specifically on converting them into percentage changes, and the "
            "conversation ends before a usable answer -- the calculation was started, "
            "not skipped."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Just to confirm - is the ask a repeatable model for future "
            "editions?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So the fixed-package broadcasting deal plus tripled "
            "host-country costs are the two drivers.",
            f"Interviewer: {MATH_Q}",
            "Candidate: Revenue per match before was about 46.9 million, and this "
            "edition it's about 41.8 million. Cost per match before was about 29.1 "
            "million, and I've got roughly 31.8 million for this edition. Now let me "
            "work out the percentage change on each... that's going to take a second, "
            "I don't want to round it wrong.",
            "Interviewer: Go ahead.",
            "Candidate: Sorry, I keep losing track of which direction I'm dividing - "
            "give me another moment to get the percentages right rather than guess.",
        ),
    },
    {
        "id": "WC_79",
        "category": "NON_RESPONSIVE",
        "expected_enough_evidence": False,
        "rationale": (
            "The interviewer asks about costs three separate times and the candidate "
            "answers about revenue every time -- not vague or circular, just "
            "consistently answering a different question than the one asked."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd look at what's driving this.",
            "Interviewer: Let's start with costs specifically - what do you think is "
            "driving the cost side?",
            "Candidate: Well, on revenue, I'd guess sponsorship and ticketing are "
            "probably both up given the bigger format.",
            "Interviewer: I asked about costs, not revenue - what's driving costs "
            "specifically?",
            "Candidate: Right, and I think broadcasting revenue is probably being "
            "under-monetized too, which would explain a lot of this.",
            "Interviewer: I need your view on the cost side specifically, not revenue.",
            "Candidate: Sure - I think revenue overall is probably not keeping pace "
            "with how big the tournament has gotten.",
        ),
    },
    {
        "id": "WC_80",
        "category": "NON_RESPONSIVE",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate keeps steering into tangents about format legitimacy and "
            "fan sentiment instead of engaging with the profitability structure the "
            "interviewer is asking for, even after two direct redirects."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Honestly, my first thought is whether a 48-team format even "
            "makes sense for the sport - some fans think it dilutes the quality of "
            "play compared to a smaller field.",
            "Interviewer: That's not something we have data on here - can you propose "
            "a structure for looking at the profitability question?",
            "Candidate: Sure, but I do think the competitive-balance angle matters, "
            "since weaker matchups might be part of why this feels different from "
            "prior editions.",
            "Interviewer: Let's stay on the financials - revenue streams versus costs. "
            "Where would you start?",
            "Candidate: Fair - though I'd note that fan sentiment about the format "
            "could indirectly matter for sponsorship appetite down the line, which is "
            "worth keeping in mind.",
        ),
    },
    {
        "id": "WC_81",
        "category": "NON_RESPONSIVE",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate never proposes a structure of their own, repeatedly asking "
            "the interviewer to supply the answer instead, even after being told "
            "directly that's not how this works."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: What would you say is the biggest piece of this, if you had to "
            "guess?",
            "Interviewer: I'd like your view first - how would you approach this?",
            "Candidate: Sure, but is it more of a cost issue or a revenue issue in "
            "your experience with cases like this?",
            "Interviewer: I can't steer you toward an answer - propose your own "
            "structure.",
            "Candidate: Understood - though if you had to point me somewhere, would "
            "you start with the revenue side or the cost side?",
            "Interviewer: That's for you to decide - what's your structure?",
            "Candidate: Okay, one more check - is there usually a pattern in these "
            "cases I should be aware of?",
        ),
    },
    {
        "id": "WC_82",
        "category": "NON_RESPONSIVE",
        "expected_enough_evidence": False,
        "rationale": (
            "The interviewer asks directly for the recommendation twice and the "
            "candidate answers both times by re-summarizing the diagnosis instead of "
            "ever stating what they'd actually recommend -- present and talking, but "
            "never responsive to the actual question."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'll split revenue streams from the incremental cost base and "
            "look at this per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So fixed-package broadcasting is diluting per-match revenue "
            "while tripled host-country costs and new travel costs push per-match cost "
            "up.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            "Candidate: So just to recap where we've landed - revenue's up 45%, "
            "margin's down from 38% to 24%, and it traces back to the fixed-package "
            "broadcasting deal plus the tripled host-country cost base.",
            "Interviewer: Right, and given that - what's your recommendation?",
            "Candidate: Yeah, so the core issue really is that revenue model versus "
            "cost model mismatch I mentioned - fixed revenue, scaling costs.",
        ),
    },
    {
        "id": "WC_83",
        "category": "EVIDENCE_MISREAD",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate misattributes the 45% revenue growth to broadcasting when "
            "the data explicitly says sponsorship and licensing drove it -- and after "
            "a direct correction, doesn't recover the point or move on to "
            "quantification or a recommendation."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue streams from the incremental cost of "
            "expansion and look at this per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So broadcasting is clearly the growth engine here - with 104 "
            "matches instead of 64, broadcasting revenue must be what's driving most "
            "of that 45% growth.",
            "Interviewer: Take another look at what's actually driving the 45% growth "
            "in the data.",
            "Candidate: Sure, but either way I think the bigger lever is probably just "
            "negotiating a better overall broadcasting number for next time.",
        ),
    },
    {
        "id": "WC_84",
        "category": "EVIDENCE_MISREAD",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate reads the host-country cost increase as scaling with the "
            "62.5% match-count jump, when the data says it's roughly triplicated by "
            "having three host countries specifically -- and doesn't correct the "
            "misread even after being pointed back to it."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is margin recovery the priority here?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Okay, so since matches went up 62.5%, I'd expect host-country "
            "costs to have scaled roughly in line with that, maybe a bit more - so "
            "that's probably a fairly proportionate increase, not really the core "
            "issue.",
            "Interviewer: Look again at how the host-country costs actually scaled "
            "here.",
            "Candidate: Right, but I still think the costs are roughly proportionate "
            "to the extra matches, so I'd focus more on the revenue side being the "
            "real driver.",
        ),
    },
    {
        "id": "WC_85",
        "category": "EVIDENCE_MISREAD",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate reads prize money as scaling with match count, when the "
            "data ties it directly to the number of qualifying teams -- and after a "
            "direct correction, keeps using the wrong driver instead of adopting the "
            "right one."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is this a one-time diagnosis or a repeatable model?",
            "Interviewer: A repeatable model.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: On prize money, since matches nearly doubled, I'd expect that "
            "pool to have roughly doubled too, which would explain a good chunk of "
            "the cost increase on its own.",
            "Interviewer: Prize money doesn't scale with matches here - look again at "
            "what it's actually tied to.",
            "Candidate: Understood, but I still think match count is the more useful "
            "lens for the cost side generally, so I'd keep sizing things that way.",
        ),
    },
    {
        "id": "WC_86",
        "category": "EVIDENCE_MISREAD",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate reads the margin change backwards -- as an improvement "
            "rather than the 38%-to-24% decline the case states -- and even after a "
            "direct correction, keeps framing the situation as fundamentally healthy "
            "rather than revisiting the diagnosis."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So if I've got this right, EBITDA margin actually improved "
            "this edition, from 24% up to 38%, which is a good sign given how much "
            "bigger the tournament got.",
            "Interviewer: You have that backwards - margin fell from 38% to 24%, not "
            "the other way round.",
            "Candidate: Got it, but either way I think the underlying story is still "
            "that the expansion is working well financially, just needs a bit of "
            "fine-tuning.",
        ),
    },
    {
        "id": "WC_87",
        "category": "EVIDENCE_MISREAD",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate misreads total revenue as flat when the case states it's "
            "up 45%, building a wrong 'demand problem' narrative from that error -- "
            "and after a direct correction, keeps the same wrong frame instead of "
            "revisiting it."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is margin recovery the priority?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So it sounds like total revenue has basically stayed flat "
            "despite the bigger format, which would make sense if the new matches "
            "aren't bringing in much at all.",
            "Interviewer: Total revenue is actually up 45% - it's not flat, and "
            "that's an important part of the story.",
            "Candidate: Okay, but I still think the core narrative is a demand "
            "shortfall from the expansion not resonating with fans the way it was "
            "expected to.",
        ),
    },
    {
        "id": "WC_88",
        "category": "FULL_COVERAGE_HALLUCINATED_DATA",
        "expected_enough_evidence": True,
        "rationale": (
            "The candidate invents a specific principal-sponsor deal value that "
            "appears nowhere in the case materials, which should hurt groundedness "
            "scoring, but every stage of the interview is still covered end to end."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion and "
            "look at per-match economics. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That tracks with what I recall - I believe the new principal "
            "sponsor deal alone is worth somewhere around EUR 180M a year, on top of "
            "the fixed-broadcasting dilution and the tripled host-country costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_89",
        "category": "FULL_COVERAGE_HALLUCINATED_DATA",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_88: an invented fact (here, a stadium-utilization figure) appears mid-analysis, but full stage coverage is still reached.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is margin recovery the hard priority this cycle?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Right, and I recall stadium utilization actually dropped to "
            "around 70% this edition because of the expanded match schedule spreading "
            "demand thinner, alongside the fixed-broadcasting and host-country cost "
            "points.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_90",
        "category": "FULL_COVERAGE_HALLUCINATED_DATA",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_88/WC_89: an invented fact (here, a broadcasting-contract length and signing date) appears mid-analysis, but full stage coverage is still reached.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is this a one-off diagnosis or a repeatable model for future "
            "editions?",
            "Interviewer: A repeatable model.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That's consistent with what I understood - I believe this "
            "broadcasting contract is an eight-year deal signed back in 2019, which "
            "would explain why it's locked into a fixed-package structure regardless "
            "of match count.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    # Third batch: balance small categories to 10 rows each
    {
        "id": "WC_91",
        "category": "FULL_COVERAGE_CLEAN",
        "expected_enough_evidence": True,
        "rationale": (
            "Every stage -- objective clarification, MECE structure, data-grounded "
            "synthesis, correct quantification, and a risk-aware recommendation -- is "
            "covered end to end, this time anchored on whether the margin decline is a "
            "one-off or a recurring pattern."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Let me recap: revenue up 45%, margin down from 38% to 24%, "
            "tied to going from 32 to 48 teams across three host countries. Before I "
            "structure this - is this margin decline expected to be a one-off for this "
            "edition, or does the Committee expect it to recur at future expansions "
            "too?",
            "Interviewer: They expect it to recur unless something structural changes.",
            "Candidate: Understood. Then I'd split revenue streams from the incremental "
            "cost base of the three-host expansion, and compare per-match economics "
            "rather than totals, since match count nearly doubled. My hypothesis is "
            "that a flat-package revenue model isn't scaling with match count the way "
            "the cost base is.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That confirms it - broadcasting's fixed-package structure "
            "dilutes revenue per match as matches grow, sponsorship and licensing "
            "explain the actual 45% growth, and the tri-host format roughly triples "
            "infrastructure cost while adding new travel and team-linked prize-money "
            "costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_92",
        "category": "FULL_COVERAGE_CLEAN",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_36-38/WC_63: compressed into a handful of turns, but every stage is genuinely covered.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Quick check first - is the Committee prioritizing margin "
            "recovery even if it slows future expansion, or is some dilution "
            "acceptable?",
            "Interviewer: Margin recovery is the priority.",
            "Candidate: Then I'd split revenue from the incremental cost of the "
            "three-host expansion, per match, and check two things: how broadcasting "
            "is sold, and how host-country count drives cost versus match count.",
            "Interviewer: Broadcasting is a fixed package, and yes, three host "
            "countries roughly triples infrastructure and security cost.",
            "Candidate: That's the whole story then - revenue per match falls from "
            "about EUR 46.9M to EUR 41.8M, cost per match rises from about EUR 29.1M "
            "to EUR 31.8M. I'd renegotiate broadcasting toward per-match value, and "
            "lock in cost-sharing with future host countries before further "
            "expansion.",
            "Interviewer: That covers everything I needed.",
        ),
    },
    {
        "id": "WC_93",
        "category": "PREMATURE_CONCLUSION",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_10-12/WC_71-74: a confident revenue-side verdict delivered cold, with no structure or data behind it.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'd just go after a bigger global sponsorship deal with a "
            "major tech brand - that alone should cover the margin gap.",
        ),
    },
    {
        "id": "WC_94",
        "category": "PREMATURE_CONCLUSION",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_10-12/WC_71-74: an immediate pricing verdict with no preceding structure or data exchanged.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Honestly the simplest fix is to push for a much higher "
            "broadcasting rights price at the next renegotiation - that solves it.",
        ),
    },
    {
        "id": "WC_95",
        "category": "PREMATURE_CONCLUSION",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_73: one clarifying question doesn't turn this into real analysis -- the candidate still jumps straight to a recommendation with no structure and no data exchanged.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is this urgent enough that we're looking for a quick fix "
            "rather than a full redesign?",
            "Interviewer: We'd like a quick fix if one exists.",
            "Candidate: Then I'd recommend dropping back to a single host country next "
            "time - fewer host countries means fewer costs, plain and simple.",
        ),
    },
    {
        "id": "WC_96",
        "category": "UNFINISHED_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": (
            "Structure, data, and math are all correctly covered, but the candidate "
            "visibly starts the final recommendation and trails off mid-sentence "
            "without ever completing it -- a recommendation genuinely begun, not one "
            "that was skipped."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis only, or also a recommendation on "
            "making the expansion pay for itself?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue streams from the incremental cost base of "
            "the three-host expansion, and look at per-match economics. What's changed "
            "on each side?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So a fixed broadcasting package dilutes per-match revenue as "
            "matches grow, while tripled host-country infrastructure and added travel "
            "push per-match cost up.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            "Candidate: Given all that, I'd say the priority has to be renegotiating "
            "the broadcasting side, and then, well, on the cost side there's probably "
            "a few different ways to approach the host-country piece, so let me think "
            "about which one actually makes the most sense before I commit to...",
        ),
    },
    {
        "id": "WC_97",
        "category": "UNFINISHED_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate correctly works out both per-match figures but stalls "
            "trying to tie them into a single structural conclusion, and the "
            "conversation ends before a recommendation -- an interpretation genuinely "
            "begun, not skipped."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is margin recovery the hard priority here?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So fixed-package broadcasting and tripled host-country costs "
            "both look relevant.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            "Candidate: So revenue per match is down about 11% and cost per match is "
            "up about 9% - I want to make sure I state the combined margin effect of "
            "those two correctly rather than just eyeballing it, give me a second to "
            "work through how they net out together...",
            "Interviewer: Take your time.",
            "Candidate: Right, I keep going back and forth on whether to express this "
            "as a margin-point impact or a euro impact - let me settle that before I "
            "give you the full picture.",
        ),
    },
    {
        "id": "WC_98",
        "category": "UNFINISHED_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate builds out the cost side of the structure in real detail "
            "but trails off before ever stating the revenue side, and the "
            "conversation stops there -- half a structure genuinely attempted, not "
            "one that was never started."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: I'll start on the cost side - venue and security "
            "infrastructure across three host countries, team travel and "
            "accommodation between host countries, and prize money tied to team "
            "count. On the revenue side, I'd want to look at... actually, let me make "
            "sure I've got the cost buckets exhaustive first before I move to "
            "revenue, since I don't want to double-count anything across the two.",
            "Interviewer: Go ahead and give me the revenue side whenever you're "
            "ready.",
            "Candidate: Right, sorry - let me just double check I haven't missed a "
            "cost bucket first, there might be one more I'm forgetting related to "
            "logistics specifically...",
        ),
    },
    {
        "id": "WC_99",
        "category": "NON_RESPONSIVE",
        "expected_enough_evidence": False,
        "rationale": (
            "Asked repeatedly for a concrete structure, the candidate keeps offering "
            "surface-level predictions instead of ever stating a MECE breakdown -- "
            "present and talking, but never actually responsive to the ask."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: My gut says this is mostly a cost story.",
            "Interviewer: Can you lay out a structure for how you'd confirm that?",
            "Candidate: Sure, I'd guess venues and security are probably the biggest "
            "piece of it.",
            "Interviewer: That's a guess at an answer, not a structure - how would "
            "you organize the analysis?",
            "Candidate: Fair, I think travel costs are probably up a lot too given "
            "three countries.",
            "Interviewer: I need an actual framework before we go further - how would "
            "you break this problem down?",
            "Candidate: I'd say prize money is worth a look as well, given more teams "
            "qualify now.",
        ),
    },
    {
        "id": "WC_100",
        "category": "NON_RESPONSIVE",
        "expected_enough_evidence": False,
        "rationale": (
            "Every time the interviewer asks the candidate to commit to a number or a "
            "structure, the candidate deflects the question back to the interviewer "
            "instead of answering it, even after being told directly to commit."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Before I say anything - roughly how big would you say the "
            "cost increase is?",
            "Interviewer: I'd like your estimate, not mine - how would you structure "
            "this?",
            "Candidate: Fair enough, but what would you say is the biggest cost "
            "bucket, just so I calibrate?",
            "Interviewer: That's for you to work out - propose your own structure.",
            "Candidate: Understood - though if you had to rank the cost categories, "
            "which would you put first?",
            "Interviewer: I can't answer that for you - what's your structure?",
            "Candidate: Okay, one last check - is there a standard way these "
            "profitability cases are usually cut?",
        ),
    },
    {
        "id": "WC_101",
        "category": "NON_RESPONSIVE",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate responds to every prompt with rapport-building filler -- "
            "praising the question, promising to get there -- without ever "
            "contributing a structure, a data request, or a conclusion."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Great setup - this is exactly the kind of case I enjoy "
            "digging into.",
            "Interviewer: How would you like to structure the analysis?",
            "Candidate: Love that question - let's definitely make sure we get to "
            "the bottom of this properly.",
            "Interviewer: What specifically would you look at first?",
            "Candidate: Good instinct to push on that - I want to make sure I cover "
            "this the right way rather than rush it.",
            "Interviewer: I need something concrete - what's your first question for "
            "me?",
            "Candidate: Appreciate the nudge - let's make sure we're thorough as we "
            "get into it.",
        ),
    },
    {
        "id": "WC_102",
        "category": "EVIDENCE_MISREAD",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate conflates the team-count jump (32 to 48) with the "
            "match-count jump (64 to 104), treating them as the same figure, and "
            "doesn't correct the conflation even after being pointed back to it."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Okay, so since the team count only went from 32 to 48, "
            "that's the same increase I should use for the match count too, which "
            "keeps the per-match math fairly simple.",
            "Interviewer: Look again at the match counts specifically - they didn't "
            "move the same amount as the team count.",
            "Candidate: Sure, but I think using the team-count increase as the "
            "stand-in for everything keeps this cleaner, so I'd stick with that.",
        ),
    },
    {
        "id": "WC_103",
        "category": "EVIDENCE_MISREAD",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate assumes the previous, single-host edition was the more "
            "expensive one, backwards from the data, and doesn't correct the "
            "misread even after a direct correction."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is margin recovery the priority here?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So it sounds like the single-host previous edition was "
            "actually the pricier one to run, and this upcoming edition should be "
            "cheaper per match given the shared infrastructure across three "
            "countries.",
            "Interviewer: That's backwards - the upcoming, three-host edition is the "
            "more cost-heavy one, not the previous edition.",
            "Candidate: Got it, but either way I still think the single-host format "
            "was the more expensive setup, so I'd focus on what made that one costly.",
        ),
    },
    {
        "id": "WC_104",
        "category": "EVIDENCE_MISREAD",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate attributes the 45% revenue growth to ticketing and "
            "hospitality, when the data says sponsorship and licensing drove it, and "
            "keeps the wrong attribution even after a direct correction."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is this a one-off diagnosis or a repeatable model?",
            "Interviewer: A repeatable model.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So with more matches and more host countries, ticketing and "
            "hospitality sales must be what's driving most of that 45% revenue "
            "growth.",
            "Interviewer: Look again at what the data says actually drove the 45% "
            "growth.",
            "Candidate: Fair, but I still think ticketing is the more reliable "
            "growth lever here, so I'd keep building the story around that.",
        ),
    },
    {
        "id": "WC_105",
        "category": "FULL_COVERAGE_CONTENT_FLAW_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_39-41/WC_64: full coverage reached, but this time the candidate divides the new edition's cost by team count instead of match count, producing a wrong but complete answer.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Fixed broadcasting dilution and tripled host-country costs "
            "look like the two drivers.",
            f"Interviewer: {MATH_Q}",
            "Candidate: For the new edition, 24% margin on EUR 4.35B means EBITDA is "
            "about EUR 1.04B, so cost is about EUR 3.31B - I'll divide that by the 48 "
            "teams instead of matches, so cost per team is about EUR 69M, which "
            "looks quite manageable.",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_106",
        "category": "FULL_COVERAGE_CONTENT_FLAW_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_49/WC_50/WC_70: full coverage reached, but the recommendation itself skips risks and next steps.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is margin recovery non-negotiable this cycle?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Fixed-package broadcasting dilution and tripled host-country "
            "costs explain the gap.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            "Candidate: I'd renegotiate broadcasting toward per-match value and "
            "agree cost-sharing targets with future host countries.",
        ),
    },
    {
        "id": "WC_107",
        "category": "FULL_COVERAGE_CONTENT_FLAW_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": (
            "Structure, data, and math are all correct and fully covered, but the "
            "final recommendation only addresses the cost side even though the "
            "candidate's own diagnosis clearly implicated both revenue and cost -- a "
            "recommendation inconsistent with the candidate's own analysis, not a "
            "coverage gap."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So a fixed broadcasting package dilutes per-match revenue as "
            "matches grow, while tripled host-country infrastructure and added "
            "travel push per-match cost up - it's a mismatch on both sides.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            "Candidate: Given that, I'd focus entirely on tightening host-country "
            "cost-sharing agreements before any future expansion.",
        ),
    },
    {
        "id": "WC_108",
        "category": "FULL_COVERAGE_HALLUCINATED_DATA",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_44/WC_45/WC_67/WC_68/WC_88-90: an invented fact (here, a broadcaster viewership penalty clause) appears mid-analysis, but full stage coverage is still reached.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the ask a diagnosis, a recommendation, or both?",
            "Interviewer: Both.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Right, and I believe the broadcasting contract has a "
            "viewership penalty clause that cuts the fee by roughly EUR 100M if global "
            "audience share drops below a threshold, which adds downside risk on top "
            "of the fixed-package dilution and tripled host-country costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_109",
        "category": "FULL_COVERAGE_HALLUCINATED_DATA",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_108: a different invented fact (a host-country government subsidy), full coverage otherwise.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should I anchor purely on EBITDA margin recovery?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That's consistent with what I recall - I believe one host "
            "country is providing a government infrastructure subsidy of around EUR "
            "120M that partly offsets the tripled venue costs, on top of the "
            "broadcasting dilution point.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_110",
        "category": "FULL_COVERAGE_HALLUCINATED_DATA",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_108/WC_109: a different invented fact (a specific total-attendance figure), full coverage otherwise.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is this a one-off diagnosis or a repeatable model for future "
            "editions?",
            "Interviewer: A repeatable model.",
            "Candidate: I'll split revenue from the incremental cost of expansion, "
            "per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: That tracks with what I understood - I believe total "
            "in-stadium attendance is projected at around 6.5 million across the "
            "tournament, which would support the sponsorship and licensing growth "
            "story alongside the broadcasting dilution and tripled host-country "
            "costs.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
]


def build_case() -> dict[str, Any]:
    raw_case = loader.load_case(CASE_ID)
    case_data = loader.adapt_case(raw_case)
    opening = get_opening_prompt(case_data)
    return {
        "case_prompt": opening["content"] if opening else "None.",
        "case_guidance": utils.extract_case_guidance(case_data),
        "case_data": case_data,
        "case_recommendation": utils.extract_case_recommendation(case_data),
    }


def capture_judge_prompt(state: dict[str, Any]) -> str:
    """Mock judge_llm and capture the SystemMessage from judge_node's second (main
    decision) call; the first, case-guide scouting, call is forced empty (no live vectorstore here)."""
    captured: dict[str, str] = {}
    call_count = {"n": 0}

    def fake_invoke(messages):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return SimpleNamespace(content=json.dumps({"case_guide_query": ""}))
        captured["prompt"] = messages[0].content
        return SimpleNamespace(content=json.dumps({"enough_evidence": True, "focus_areas": []}))

    mock_llm = Mock()
    mock_llm.bind.return_value = mock_llm
    mock_llm.invoke.side_effect = fake_invoke
    node.judge_llm = mock_llm
    node.retrieve_case_guide_context = Mock(return_value=[])

    node.judge_node(state)
    return captured["prompt"]


def main() -> None:
    case = build_case()
    rubric_data = loader.adapt_rubric(loader.load_rubric())

    expected_true = sum(1 for item in ITEMS if item["expected_enough_evidence"])
    expected_false = len(ITEMS) - expected_true
    print(
        f"{len(ITEMS)} items built for case '{CASE_ID}' "
        f"({expected_true} expected True / {expected_false} expected False)."
    )

    rows = []
    for item in ITEMS:
        state = {
            "judge_round": 0,
            "transcript": item["transcript"],
            "rubric_data": rubric_data,
            "case_prompt": case["case_prompt"],
            "case_guidance": case["case_guidance"],
            "case_data": case["case_data"],
            "case_recommendation": case["case_recommendation"],
        }
        judge_input = capture_judge_prompt(state)
        rows.append(
            {
                "conversation_id": item["id"],
                "category": item["category"],
                "expected_enough_evidence": item["expected_enough_evidence"],
                "judge_input": judge_input,
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "conversation_id",
        "category",
        "expected_enough_evidence",
        "judge_input",
    ]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
