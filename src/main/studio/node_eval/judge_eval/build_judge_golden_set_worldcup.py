"""Build a 50-row judge golden set (CSV) for the World Cup case, using the *actual*
rendered judge prompt as input.

Unlike build_judge_golden_set.py (which stores the raw AgenticGraphState fields
judge_node reads, for a harness to assemble at call time), this script captures the
exact SystemMessage text `judge_node`'s main decision call sends to `judge_llm` --
`JUDGE_GRAPH_SYSTEM_PROMPT` + situation + guide navigation rules + case-guide
excerpts (node.py:444-457) -- by running the real `judge_node` function with
`judge_llm` mocked and `retrieve_case_guide_context` forced empty (no live
vectorstore call; the scouting call always returns an empty `case_guide_query`, so
the excerpts section renders as "None.", same as any real round where the judge
decides it doesn't need the guide). That prompt string is what a harness should feed
to the LLM under test, and its `enough_evidence`/`focus_areas` response is what gets
compared against `expected_enough_evidence` below.

All 50 items use `judge_round=0` for the same reason as the JSON golden set: at
`judge_round + 1 >= MAX_JUDGE_ROUNDS` (2), node.py:462-464 force-overrides
`enough_evidence=True` regardless of the LLM's answer, and that deterministic
cutoff already has unit-test coverage (test_judge_max_rounds). This golden set
targets the judge LLM's genuine reasoning, so it never exercises that override.

Case: 04-worldcup-test (IWFC), the only case in synthetic-dataset/ with both a math
block and a creative block, letting every category below apply to a single case.

Category taxonomy (same "coverage, not quality" principle as the 3-case JSON golden
set -- enough_evidence asks whether every case-applicable stage has *something* on
the record for eval_case_performance/eval_dialog_quality to score, not whether the
candidate performed well):

    OPENING_ONLY                 False  Opening prompt + one unfounded reaction only.
    STRUCTURED_NO_DATA            False  Opening + structure proposed, but the data
                                         block was never revealed.
    DATA_MID_SYNTHESIS_NO_REC     False  Data revealed and correctly interpreted, but
                                         no math/creative/recommendation reached.
    PREMATURE_RECOMMENDATION      False  Recommendation given cold, no structure/data.
    MATH_SKIPPED                  False  Full run to a grounded recommendation, but
                                         the case's math exchange was never asked.
    CREATIVE_SKIPPED              False  Full run incl. math, but the creative
                                         (hydration-break) exchange was never asked.
    BOTH_EXHIBITS_SKIPPED         False  Straight from synthesis to recommendation;
                                         neither math nor creative ever asked.
    MATH_STARTED_NOT_FINISHED     False  Candidate begins the calculation, stalls,
                                         never reaches usable numbers or beyond.
    RECOMMENDATION_ASKED_NOT_ANSWERED False  Interviewer asks for the recommendation;
                                         transcript ends before the candidate answers.
    OFF_TOPIC_CIRCULAR_LONG       False  Many turns, but circular/generic -- never
                                         progresses past the opening framing.
    KEY_FACT_MISUNDERSTOOD_INCOMPLETE False  Candidate misreads the fixed-broadcasting
                                         fact, isn't corrected, and the interview stops
                                         before recommendation.
    FULL_COVERAGE_STRONG          True   Every stage, closely mirroring the case's own
                                         expected analysis and ideal recommendation.
    FULL_COVERAGE_WEAK            True   Every stage touched, but generic/thin.
    FULL_COVERAGE_WITH_REDIRECT   True   Every stage touched, after 1-2 interviewer
                                         nudges off an unproductive tangent.
    FULL_COVERAGE_VERY_SHORT_EFFICIENT True   Every stage touched, compressed into very
                                         few turns.
    FULL_COVERAGE_MATH_WRONG_BUT_ATTEMPTED True   Every stage touched; the math answer
                                         itself is wrong -- a scoring problem, not a
                                         coverage problem.
    FULL_COVERAGE_CREATIVE_OVERSOLD_BUT_ATTEMPTED True   Every stage touched; the
                                         creative answer oversells the lever instead of
                                         sizing it -- again a scoring, not coverage, gap.
    FULL_COVERAGE_HALLUCINATED_DATA True   Every stage touched; the candidate invents
                                         an unsupported fact along the way -- a
                                         groundedness problem, not a coverage gap.
    FULL_COVERAGE_LONG_ITERATIVE_MANY_REDIRECTS True   Long, non-linear path (multiple
                                         tangents/redirects) that still reaches full
                                         coverage.
    FULL_COVERAGE_RECOMMENDATION_NO_RISKS True   Every stage touched; the final
                                         recommendation itself skips risks/next steps.

Usage (from repo root, with the project venv active):
    python -m src.main.studio.node_eval.judge_eval.build_judge_golden_set_worldcup
"""
from __future__ import annotations

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

# ---------------------------------------------------------------------------
# Reusable, fact-exact building blocks (copied verbatim from
# src/synthetic-dataset/04-worldcup-test.json so every transcript stays
# consistent with the case's own numbers and wording).
# ---------------------------------------------------------------------------

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

CREATIVE_Q = (
    "The Secretary General mentions that in-stadium hydration breaks - mandated by player "
    "welfare rules in high-heat matches - currently carry no commercial value: they're a "
    "broadcast dead zone with no ads, no branding, and no fan engagement content. She asks "
    "whether monetizing hydration breaks could meaningfully help close the new margin gap. "
    "What would you tell her?"
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

CREATIVE_STRONG = (
    "I'd size it before getting excited. Hydration breaks only happen in high-heat "
    "matches, not all 104, and each break is short, so the ad inventory is limited - think "
    "sponsor billboards, a named hydration partner category, screen takeovers. It's "
    "high-margin since the broadcast infrastructure already exists, but the margin gap "
    "here is roughly EUR 340M or more in absolute EBITDA terms. Hydration breaks won't "
    "move that needle meaningfully - I'd frame it to her as a nice incremental sponsorship "
    "line, not a structural fix."
)

REC_STRONG = (
    "Renegotiate future broadcasting deals so value scales more with match count rather "
    "than a flat tournament package - that's the revenue-side fix. Set explicit "
    "cost-sharing and shared-infrastructure targets with host countries before agreeing to "
    "any future expansion, since the tri-host cost base is the biggest driver of the gap. "
    "And treat incremental in-match inventory like hydration breaks as a secondary, "
    "low-risk revenue add-on, not the fix. The main risks are that broadcasters may prefer "
    "the certainty of a fixed package, and that cost-sharing runs into host-country "
    "politics. Next steps: commission a per-match value analysis on the broadcasting "
    "portfolio, set country-specific cost targets ahead of the next bidding cycle, and "
    "pilot a scoped hydration-break sponsorship program."
)


def _t(*lines: str) -> list[str]:
    """Small readability helper: pass alternating role-prefixed strings."""
    return list(lines)


ITEMS: list[dict[str, Any]] = [
    # ================================================================= FALSE (25)
    {
        "id": "WC_01",
        "category": "OPENING_ONLY",
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
        "category": "OPENING_ONLY",
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
        "category": "OPENING_ONLY",
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
        "category": "STRUCTURED_NO_DATA",
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
        "category": "STRUCTURED_NO_DATA",
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
        "category": "STRUCTURED_NO_DATA",
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
        "category": "DATA_MID_SYNTHESIS_NO_REC",
        "expected_enough_evidence": False,
        "rationale": (
            "Structure and data-driven synthesis are both strong, but the interview stops "
            "before the quantification step or the recommendation ask -- case_math_answer, "
            "case_creative_answer, and final_recommendation all remain untested."
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
        "category": "DATA_MID_SYNTHESIS_NO_REC",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_07: correct qualitative synthesis, but stops before math/creative/recommendation.",
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
        "category": "DATA_MID_SYNTHESIS_NO_REC",
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
        "category": "PREMATURE_RECOMMENDATION",
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
        "category": "PREMATURE_RECOMMENDATION",
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
        "category": "PREMATURE_RECOMMENDATION",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_10/WC_11: recommendation given before any case fact has been exchanged.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Honestly, they should just monetize the hydration breaks and "
            "other unused ad space - that would close the gap.",
        ),
    },
    {
        "id": "WC_13",
        "category": "MATH_SKIPPED",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate reaches a well-grounded recommendation and even handles the "
            "creative sizing question, but the interviewer never asked the case's "
            "quantified per-match math question, so case_math_answer has nothing to be "
            "scored against despite the case having a dedicated math exhibit ready to "
            "test."
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_14",
        "category": "MATH_SKIPPED",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_13: creative and recommendation both reached, but the math exchange is missing.",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_15",
        "category": "CREATIVE_SKIPPED",
        "expected_enough_evidence": False,
        "rationale": (
            "Math is handled well and the recommendation is grounded, but the creative "
            "hydration-break question -- one of this case's required exchanges -- was "
            "never asked, so case_creative_answer remains untested even though the case "
            "has that exhibit ready."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is this a one-off diagnosis, or does the Committee want a "
            "repeatable model for future editions?",
            "Interviewer: A repeatable model.",
            "Candidate: I'd split revenue streams from the incremental cost of the "
            "expansion and look at per-match economics. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So fixed broadcasting revenue is being diluted across more "
            "matches, while tripled host-country costs and new travel costs are pushing "
            "per-match cost up.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_16",
        "category": "CREATIVE_SKIPPED",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_15: math and recommendation both reached, but the creative question is missing.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should I anchor on EBITDA margin specifically, or also free cash "
            "flow?",
            "Interviewer: EBITDA margin.",
            "Candidate: I'll split revenue from the incremental cost base of expansion, "
            "and look at per-match economics given matches jumped from 64 to 104. What's "
            "changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: This is a structural mismatch: revenue is largely fixed-package "
            "and cost is largely linear-to-triplicated with host-country count.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_17",
        "category": "BOTH_EXHIBITS_SKIPPED",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate reaches a directionally sound recommendation straight after "
            "the qualitative synthesis, but neither of this case's two required "
            "exhibits -- the per-match math question and the hydration-break creative "
            "question -- was ever raised, leaving case_math_answer and "
            "case_creative_answer both untested."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is the objective a diagnosis only, or also a path to making the "
            "expansion pay for itself?",
            "Interviewer: Both.",
            "Candidate: I'd split revenue streams from the incremental cost base of the "
            "expansion, and look at per-match economics. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So broadcasting is fixed and gets diluted as matches grow, while "
            "three host countries roughly triple infrastructure cost instead of scaling "
            "with match count.",
            f"Interviewer: {REC_ASK}",
            "Candidate: Renegotiate the broadcasting deal to scale better with matches, "
            "and get the host countries to share more of the infrastructure cost.",
        ),
    },
    {
        "id": "WC_18",
        "category": "BOTH_EXHIBITS_SKIPPED",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_17: structure and data covered, recommendation reached, but neither math nor creative was ever raised.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Before structuring - is there a hard deadline tied to the next "
            "bid cycle?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion and "
            "look at per-match figures. What's changed on each side?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So the growth story is really sponsorship and licensing, while "
            "the cost story is the tri-host infrastructure and new travel costs "
            "outpacing the match-count increase.",
            f"Interviewer: {REC_ASK}",
            "Candidate: I'd push broadcasters toward a structure that captures more "
            "value per match, and negotiate cost-sharing with host countries before any "
            "further expansion.",
        ),
    },
    {
        "id": "WC_19",
        "category": "MATH_STARTED_NOT_FINISHED",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate begins the calculation but never reaches a usable answer, and "
            "the conversation stops there -- no creative question, no recommendation. "
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
        "category": "MATH_STARTED_NOT_FINISHED",
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
        "category": "RECOMMENDATION_ASKED_NOT_ANSWERED",
        "expected_enough_evidence": False,
        "rationale": (
            "Every earlier stage -- structure, data, math, and the creative question -- "
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
        ),
    },
    {
        "id": "WC_22",
        "category": "RECOMMENDATION_ASKED_NOT_ANSWERED",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
        ),
    },
    {
        "id": "WC_23",
        "category": "OFF_TOPIC_CIRCULAR_LONG",
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
        "category": "OFF_TOPIC_CIRCULAR_LONG",
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
        "category": "KEY_FACT_MISUNDERSTOOD_INCOMPLETE",
        "expected_enough_evidence": False,
        "rationale": (
            "The candidate misreads the central case fact -- broadcasting is explicitly "
            "a fixed package, not sold per match -- and even after a direct interviewer "
            "correction, doesn't recover the insight or move on to quantification, the "
            "creative question, or a recommendation."
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
    # ================================================================= TRUE (25)
    {
        "id": "WC_26",
        "category": "FULL_COVERAGE_STRONG",
        "expected_enough_evidence": True,
        "rationale": (
            "Every stage -- objective clarification, MECE structure, data-grounded "
            "synthesis, correct quantification, a well-sized creative answer, and a "
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_27",
        "category": "FULL_COVERAGE_STRONG",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_28",
        "category": "FULL_COVERAGE_STRONG",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_29",
        "category": "FULL_COVERAGE_STRONG",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_30",
        "category": "FULL_COVERAGE_WEAK",
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
            f"Interviewer: {CREATIVE_Q}",
            "Candidate: Maybe it helps a little bit with the gap.",
            f"Interviewer: {REC_ASK}",
            "Candidate: Renegotiate broadcasting and manage the host-country costs "
            "better.",
        ),
    },
    {
        "id": "WC_31",
        "category": "FULL_COVERAGE_WEAK",
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
            f"Interviewer: {CREATIVE_Q}",
            "Candidate: Could be worth trying, not sure how much it really helps.",
            f"Interviewer: {REC_ASK}",
            "Candidate: Fix the broadcasting deal and try to cut some of the host-"
            "country costs.",
        ),
    },
    {
        "id": "WC_32",
        "category": "FULL_COVERAGE_WEAK",
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
            f"Interviewer: {CREATIVE_Q}",
            "Candidate: Probably a small help, not a huge one.",
            f"Interviewer: {REC_ASK}",
            "Candidate: Try to fix the broadcasting side and control costs in the host "
            "countries.",
        ),
    },
    {
        "id": "WC_33",
        "category": "FULL_COVERAGE_WITH_REDIRECT",
        "expected_enough_evidence": True,
        "rationale": (
            "Needed one direct nudge to move off an unhelpful ticket-pricing tangent, "
            "but the transcript still reaches full coverage -- structure, data, math, "
            "creative sizing, and a risk-aware recommendation -- so there is enough "
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_34",
        "category": "FULL_COVERAGE_WITH_REDIRECT",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_35",
        "category": "FULL_COVERAGE_WITH_REDIRECT",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_36",
        "category": "FULL_COVERAGE_VERY_SHORT_EFFICIENT",
        "expected_enough_evidence": True,
        "rationale": (
            "Even compressed into very few turns, the candidate covers objective, "
            "structure, hypothesis, correct quantification, a well-sized creative "
            "answer, and a complete recommendation -- brevity doesn't reduce evidence "
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
            "29.1M to EUR 31.8M. On hydration breaks - real incremental sponsorship, but "
            "a rounding error against a roughly EUR 340M absolute EBITDA gap, so it's a "
            "nice-to-have, not a fix. My recommendation: renegotiate broadcasting toward "
            "per-match or tiered value, lock in cost-sharing with future host countries "
            "before any more expansion, and treat hydration breaks and similar inventory "
            "as a small add-on.",
            "Interviewer: That's right on the money.",
        ),
    },
    {
        "id": "WC_37",
        "category": "FULL_COVERAGE_VERY_SHORT_EFFICIENT",
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
            "11%. Cost per match: EUR 29.1M to EUR 31.8M, up about 9%. Hydration-break "
            "monetization is real but tiny against a roughly EUR 340M absolute EBITDA "
            "gap - a nice-to-have, not the fix. Recommendation: renegotiate broadcasting "
            "toward per-match value, lock in host-country cost-sharing before further "
            "expansion, and treat in-match inventory like hydration breaks as a small "
            "secondary revenue line.",
            "Interviewer: Good, that covers it.",
        ),
    },
    {
        "id": "WC_38",
        "category": "FULL_COVERAGE_VERY_SHORT_EFFICIENT",
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
            "31.8M. Hydration-break monetization is genuine but far too small against a "
            "roughly EUR 340M absolute gap. I'd renegotiate broadcasting toward per-"
            "match value, agree cost-sharing with host countries up front, and treat "
            "hydration breaks as a minor add-on, not the fix.",
        ),
    },
    {
        "id": "WC_39",
        "category": "FULL_COVERAGE_MATH_WRONG_BUT_ATTEMPTED",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            "Candidate: Given revenue per match is actually holding up, I'd focus mainly "
            "on containing the host-country cost side - tighter cost-sharing "
            "agreements before any further expansion, and treat hydration breaks as a "
            "small incremental add-on.",
        ),
    },
    {
        "id": "WC_40",
        "category": "FULL_COVERAGE_MATH_WRONG_BUT_ATTEMPTED",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            "Candidate: Since the cost side looks more controlled than I expected, I'd "
            "focus the recommendation on capturing more broadcasting value per match, "
            "and treat hydration breaks as a small additional lever.",
        ),
    },
    {
        "id": "WC_41",
        "category": "FULL_COVERAGE_MATH_WRONG_BUT_ATTEMPTED",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_42",
        "category": "FULL_COVERAGE_CREATIVE_OVERSOLD_BUT_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": (
            "The candidate answers the creative question but oversells it without "
            "sizing the opportunity against the roughly EUR 340M gap -- a "
            "case_creative_answer quality problem, not a coverage gap, since every "
            "stage still has an answer on the record."
        ),
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is this a repeatable-model ask, or just this edition?",
            "Interviewer: Repeatable model.",
            "Candidate: I'll split revenue from the incremental cost of expansion and "
            "look at per-match economics. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Fixed-package broadcasting dilution plus tripled host-country "
            "costs explain the gap.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {CREATIVE_Q}",
            "Candidate: I think that's a great idea - they should definitely sell "
            "sponsorships for the hydration breaks, put a partner's logo on the water "
            "bottles and the big screens, and that extra revenue should help close the "
            "margin gap significantly.",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_43",
        "category": "FULL_COVERAGE_CREATIVE_OVERSOLD_BUT_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_42: creative answer oversold, but every stage still has content to score.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is margin recovery the top priority?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion and "
            "look per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Fixed broadcasting dilution and tripled host-country costs are "
            "the two drivers.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {CREATIVE_Q}",
            "Candidate: Absolutely, monetizing hydration breaks sounds like a strong "
            "lever - sponsor branding, on-screen ads, maybe even a dedicated hydration "
            "partner - I'd expect that to make a real dent in the margin gap.",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_46",
        "category": "FULL_COVERAGE_LONG_ITERATIVE_MANY_REDIRECTS",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_47",
        "category": "FULL_COVERAGE_LONG_ITERATIVE_MANY_REDIRECTS",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_48",
        "category": "FULL_COVERAGE_LONG_ITERATIVE_MANY_REDIRECTS",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_49",
        "category": "FULL_COVERAGE_RECOMMENDATION_NO_RISKS",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            "Candidate: I'd renegotiate the broadcasting contracts to scale more with "
            "match count, and get the host countries to share more of the "
            "infrastructure cost.",
        ),
    },
    {
        "id": "WC_50",
        "category": "FULL_COVERAGE_RECOMMENDATION_NO_RISKS",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            "Candidate: Push broadcasters toward per-match value capture, and set "
            "cost-sharing agreements with host countries.",
        ),
    },
    # ------------------------------------------------------- Second batch: more depth on weak categories
    {
        "id": "WC_51",
        "category": "MATH_SKIPPED",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_13/WC_14: creative and recommendation reached, but the math exchange is missing.",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_52",
        "category": "MATH_SKIPPED",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_53",
        "category": "CREATIVE_SKIPPED",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_15/WC_16: math and recommendation reached, but the creative question is missing.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Is there a specific deadline the Secretary General has in mind "
            "for a fix, like the next hosting bid cycle?",
            "Interviewer: Ideally before the next hosting bid cycle.",
            "Candidate: Got it. I'd separate revenue streams from the incremental cost "
            "of the expansion, and look at per-match economics rather than totals.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: This points to a two-sided problem: fixed broadcasting revenue "
            "diluting per match, and host-country costs roughly tripling instead of "
            "scaling with the match count.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_54",
        "category": "CREATIVE_SKIPPED",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_53: everything but the creative question is present.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should I focus purely on EBITDA margin, or is cash flow also "
            "part of the brief?",
            "Interviewer: Focus on EBITDA margin.",
            "Candidate: I'll split revenue streams from the incremental cost of the "
            "expansion, and check this on a per-match basis.",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: So the fixed-package broadcasting deal is being diluted by the "
            "extra matches, while the tri-host format multiplies infrastructure and "
            "security cost well beyond a simple match-count scale-up.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_55",
        "category": "BOTH_EXHIBITS_SKIPPED",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_17/WC_18: structure and data covered, recommendation reached, but neither math nor creative was ever raised.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Just to confirm, are we diagnosing only, or also expected to "
            "propose a fix?",
            "Interviewer: Both.",
            "Candidate: I'd split revenue from the incremental cost of the expansion "
            "and look at this per match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Fixed-package broadcasting is losing value per match, and the "
            "three-country format is multiplying costs well beyond what a simple "
            "match-count increase would explain.",
            f"Interviewer: {REC_ASK}",
            "Candidate: I'd push for a broadcasting structure that scales with match "
            "count, and negotiate shared infrastructure costs with the host countries.",
        ),
    },
    {
        "id": "WC_56",
        "category": "MATH_STARTED_NOT_FINISHED",
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
        "category": "RECOMMENDATION_ASKED_NOT_ANSWERED",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
        ),
    },
    {
        "id": "WC_58",
        "category": "RECOMMENDATION_ASKED_NOT_ANSWERED",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
        ),
    },
    {
        "id": "WC_59",
        "category": "OFF_TOPIC_CIRCULAR_LONG",
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
        "category": "KEY_FACT_MISUNDERSTOOD_INCOMPLETE",
        "expected_enough_evidence": False,
        "rationale": "Same pattern as WC_25: the candidate misreads a central case fact -- here, assuming broadcasting scales with host-country count -- isn't corrected even after a direct interviewer prompt, and the interview stops before quantification, the creative question, or a recommendation.",
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
        "category": "FULL_COVERAGE_WEAK",
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
            f"Interviewer: {CREATIVE_Q}",
            "Candidate: Might help some, hard to say how much.",
            f"Interviewer: {REC_ASK}",
            "Candidate: Fix the broadcasting deal and try to control the host-country "
            "costs.",
        ),
    },
    {
        "id": "WC_62",
        "category": "FULL_COVERAGE_WITH_REDIRECT",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_63",
        "category": "FULL_COVERAGE_VERY_SHORT_EFFICIENT",
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
            "31.8M. Hydration-break monetization is real but tiny against a roughly EUR "
            "340M absolute gap. I'd renegotiate broadcasting toward per-match value, "
            "agree cost-sharing with host countries up front, and treat in-match "
            "inventory like hydration breaks as a minor add-on.",
        ),
    },
    {
        "id": "WC_64",
        "category": "FULL_COVERAGE_MATH_WRONG_BUT_ATTEMPTED",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_65",
        "category": "FULL_COVERAGE_CREATIVE_OVERSOLD_BUT_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_42/WC_43: creative answer oversold (and here also factually loose about which matches qualify), but every stage still has content to score.",
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
            f"Interviewer: {CREATIVE_Q}",
            "Candidate: Definitely worth doing - selling hydration-break sponsorships "
            "across all 104 matches, with a dedicated partner brand, should generate "
            "meaningful revenue and go a long way toward closing the margin gap.",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_66",
        "category": "FULL_COVERAGE_CREATIVE_OVERSOLD_BUT_ATTEMPTED",
        "expected_enough_evidence": True,
        "rationale": "Same pattern as WC_65: creative answer oversold, full coverage otherwise.",
        "transcript": _t(
            f"Interviewer: {OPENING}",
            "Candidate: Should I anchor on EBITDA margin specifically?",
            "Interviewer: Yes.",
            "Candidate: I'll split revenue from the incremental cost of expansion, per "
            "match. What's changed?",
            f"Interviewer reveal: {DATA_REVEAL}",
            "Candidate: Fixed broadcasting dilution and tripled host-country costs are "
            "the two drivers.",
            f"Interviewer: {MATH_Q}",
            f"Candidate: {MATH_CORRECT}",
            f"Interviewer: {CREATIVE_Q}",
            "Candidate: I'd say monetizing hydration breaks could be one of the "
            "biggest levers here - branded content, sponsor takeovers, maybe even "
            "ticketed fan experiences tied to the break - it seems like a natural place "
            "to recover a lot of the lost margin.",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_69",
        "category": "FULL_COVERAGE_LONG_ITERATIVE_MANY_REDIRECTS",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            f"Candidate: {REC_STRONG}",
        ),
    },
    {
        "id": "WC_70",
        "category": "FULL_COVERAGE_RECOMMENDATION_NO_RISKS",
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
            f"Interviewer: {CREATIVE_Q}",
            f"Candidate: {CREATIVE_STRONG}",
            f"Interviewer: {REC_ASK}",
            "Candidate: I'd move broadcasting toward a per-match pricing structure and "
            "agree cost-sharing with host countries for future editions.",
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
    """Run the real judge_node with judge_llm mocked, capturing the exact
    SystemMessage content of the main decision call (the second of the two calls
    judge_node makes -- the first is the case-guide scouting decision, forced empty
    here since there's no live vectorstore in this offline builder)."""
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
