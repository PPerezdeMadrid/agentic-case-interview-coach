"""Build a synthetic golden set for evaluating the judge node's `enough_evidence` decision.

Each item's `case_prompt`/`case_guidance`/`case_data`/`case_recommendation`/`rubric_data`
are derived through the same `loader`/`utils` functions the real graph uses, and
`assemble_state(item, cases, rubric_data)` reconstitutes the exact per-call judge_node
input. All items use judge_round=0 to target the judge LLM's own reasoning rather than
the deterministic MAX_JUDGE_ROUNDS override.

Category taxonomy -- `enough_evidence` measures stage coverage, not performance quality:

    OPENING_ONLY                False  Opening + unfounded reaction only.
    STRUCTURED_MID_ANALYSIS     False  Structure + data, no recommendation yet.
    PREMATURE_RECOMMENDATION    False  Recommendation given cold, ungrounded.
    REQUIRED_EXHIBIT_SKIPPED    False  Recommendation reached but a required math/
                                        creative exhibit was never touched.
    FULL_COVERAGE_WEAK          True   All stages touched, thin execution.
    FULL_COVERAGE_STRONG        True   All stages touched, closely mirrors expected answer.
    FULL_COVERAGE_WITH_REDIRECT True   All stages touched after an interviewer redirect.

Usage (from repo root, with the project venv active):
    python -m src.main.studio.node_eval.judge_eval.build_judge_golden_set
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

STUDIO_DIR = Path(__file__).resolve().parents[2]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

import loader  # noqa: E402
import utils  # noqa: E402
from adapter import get_opening_prompt  # noqa: E402

OUTPUT_PATH = (
    Path(__file__).resolve().parents[4] / "database" / "node_eval" / "judge_eval" / "judge_golden_set.json"
)

CASE_IDS = ["01-energy-company", "02-football-team", "03-agriculture-company"]


ITEMS: list[dict[str, Any]] = [
    # ---------------------------------------------------------------- Case 1: Solventus Energy (no math/creative block)
    {
        "id": "JUDGE_C1_01",
        "case_id": "01-energy-company",
        "category": "OPENING_ONLY",
        "expected_enough_evidence": False,
        "rationale": (
            "Candidate reacted with an unfounded guess after a single prompt, without "
            "recapping the situation, clarifying the objective, or proposing a structure. "
            "No case fact has been exchanged yet, so essentially every rubric dimension "
            "beyond a very weak case_opening has nothing to score against."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Solventus Energy, a Spanish renewable energy company "
            "operating three business units: onshore wind generation, residential electricity "
            "retail (B2C), and large-scale battery storage construction. Over the past two years, "
            "group EBITDA has fallen 34% even though total revenue has grown 18%. The CEO has "
            "brought you in to find out what is driving the profit decline and to recommend a "
            "path forward.",
            "Candidate: That sounds like it's probably a pricing problem. I'd guess the company "
            "needs to raise prices.",
        ],
    },
    {
        "id": "JUDGE_C1_02",
        "case_id": "01-energy-company",
        "category": "STRUCTURED_MID_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": (
            "Opening, MECE unit-level structure, and a correct read of the revealed data are all "
            "present, but the interviewer has not yet asked for a recommendation -- "
            "final_recommendation and the overall_* synthesis dimensions have no transcript to "
            "draw on yet."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Solventus Energy, a Spanish renewable energy company "
            "operating three business units: onshore wind generation, residential electricity "
            "retail (B2C), and large-scale battery storage construction. Over the past two years, "
            "group EBITDA has fallen 34% even though total revenue has grown 18%. The CEO has "
            "brought you in to find out what is driving the profit decline and to recommend a "
            "path forward.",
            "Candidate: Before I dive in, let me recap: group EBITDA is down 34% over two years "
            "while revenue is up 18%, across the three business units - wind generation, B2C "
            "retail, and battery storage. Is the goal here purely a diagnosis, or are you also "
            "looking for a turnaround plan, and is there a specific timeframe in mind?",
            "Interviewer: Let's start with a diagnosis of what's driving the decline.",
            "Candidate: Understood. Rather than looking at Solventus as one blended P&L, I'd like "
            "to break profitability down unit by unit, since a healthy consolidated revenue trend "
            "can hide a struggling business line underneath it. Could you share how each of the "
            "three units is performing individually?",
            "Interviewer reveal: Revenue and margin by business unit: wind generation has a 41% "
            "EBITDA margin and is operationally healthy. B2C retail has a -8% EBITDA margin with "
            "28% annual customer churn. Battery storage has no revenue yet, is running at 3x "
            "original CAPEX, and is delayed by 22 months.",
            "Candidate: Okay, so wind looks like the profitable core, B2C retail is clearly "
            "bleeding money given that negative margin and high churn, and battery storage is a "
            "pre-revenue project that's badly over budget and behind schedule.",
        ],
    },
    {
        "id": "JUDGE_C1_03",
        "case_id": "01-energy-company",
        "category": "PREMATURE_RECOMMENDATION",
        "expected_enough_evidence": False,
        "rationale": (
            "A recommendation-shaped utterance exists, but it was given cold, without the "
            "candidate ever recapping the case, proposing a structure, or asking for the "
            "unit-level data that actually explains the profit decline. It is not grounded in "
            "anything exchanged in the transcript, so it cannot be scored against the case's "
            "expected recommendation, and case_structure/overall_problem_solving still have no "
            "material at all."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Solventus Energy, a Spanish renewable energy company "
            "operating three business units: onshore wind generation, residential electricity "
            "retail (B2C), and large-scale battery storage construction. Over the past two years, "
            "group EBITDA has fallen 34% even though total revenue has grown 18%. The CEO has "
            "brought you in to find out what is driving the profit decline and to recommend a "
            "path forward.",
            "Candidate: My recommendation would be to shut down the battery storage unit "
            "entirely and put everything into wind generation.",
        ],
    },
    {
        "id": "JUDGE_C1_04",
        "case_id": "01-energy-company",
        "category": "FULL_COVERAGE_WEAK",
        "expected_enough_evidence": True,
        "rationale": (
            "Every case-applicable stage -- unit-level structure, data-driven diagnosis, and a "
            "final recommendation -- has been touched, so eval_case_performance and "
            "eval_dialog_quality now have transcript material for every rubric dimension. "
            "Execution is generic and under-quantified throughout, which should drive low "
            "scores, but that is a scoring-quality question for the eval nodes, not a reason to "
            "withhold enough_evidence."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Solventus Energy, a Spanish renewable energy company "
            "operating three business units: onshore wind generation, residential electricity "
            "retail (B2C), and large-scale battery storage construction. Over the past two years, "
            "group EBITDA has fallen 34% even though total revenue has grown 18%. The CEO has "
            "brought you in to find out what is driving the profit decline and to recommend a "
            "path forward.",
            "Candidate: I'd want to look at this business unit by business unit rather than as "
            "one company.",
            "Interviewer: Go ahead.",
            "Candidate: Can you tell me how each of the three units is doing?",
            "Interviewer reveal: Revenue and margin by business unit: wind generation has a 41% "
            "EBITDA margin and is operationally healthy. B2C retail has a -8% EBITDA margin with "
            "28% annual customer churn. Battery storage has no revenue yet, is running at 3x "
            "original CAPEX, and is delayed by 22 months.",
            "Candidate: So wind is fine, retail is losing money, and battery storage has no "
            "revenue yet.",
            "Interviewer: Based on your analysis, what recommendation would you give the CEO?",
            "Candidate: I'd keep investing in wind, try to improve retail, and keep an eye on "
            "battery storage.",
        ],
    },
    {
        "id": "JUDGE_C1_05",
        "case_id": "01-energy-company",
        "category": "FULL_COVERAGE_STRONG",
        "expected_enough_evidence": True,
        "rationale": (
            "The transcript closely mirrors the case's expected analysis and ideal final "
            "recommendation -- opening, hypothesis-driven structure, data-grounded synthesis, "
            "and a recommendation with risks and next steps are all present, giving the eval "
            "nodes clean, well-grounded material to score every dimension highly."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Solventus Energy, a Spanish renewable energy company "
            "operating three business units: onshore wind generation, residential electricity "
            "retail (B2C), and large-scale battery storage construction. Over the past two years, "
            "group EBITDA has fallen 34% even though total revenue has grown 18%. The CEO has "
            "brought you in to find out what is driving the profit decline and to recommend a "
            "path forward.",
            "Candidate: Let me quickly recap: group EBITDA is down 34% over two years despite "
            "revenue growing 18%, across wind generation, B2C retail, and battery storage. "
            "Before I structure this, is the objective a root-cause diagnosis, a turnaround "
            "plan, or both, and is there a time horizon the CEO has in mind?",
            "Interviewer: Focus on diagnosis first, then we can talk about a path forward.",
            "Candidate: Given that revenue is growing but EBITDA is falling, my working "
            "hypothesis is that one or both of the newer, faster-growing units are unprofitable "
            "and are dragging down group EBITDA even as they add to the top line. I'd like to "
            "test that by looking at profitability separately for each of the three business "
            "units.",
            "Interviewer reveal: Revenue and margin by business unit: wind generation has a 41% "
            "EBITDA margin and is operationally healthy. B2C retail has a -8% EBITDA margin with "
            "28% annual customer churn. Battery storage has no revenue yet, is running at 3x "
            "original CAPEX, and is delayed by 22 months.",
            "Candidate: That confirms the hypothesis. Wind, at a 41% margin, is the healthy core "
            "and isn't the source of the decline. B2C retail has structurally negative unit "
            "economics - a -8% margin combined with 28% churn means the company is paying "
            "heavily to acquire customers it can't keep. Battery storage isn't an operating loss "
            "so much as a distressed capital project: zero revenue, 3x CAPEX, and a 22-month "
            "delay mean fixed and financing costs are piling up with nothing to offset them. "
            "Since all of the revenue growth came from these two units, the blended P&L is "
            "masking just how serious the problem is.",
            "Interviewer: Based on your analysis, what recommendation would you give the CEO?",
            "Candidate: I'd stop managing Solventus as one blended P&L and separate reporting "
            "and decision-making by business unit immediately. Protect and keep reinvesting in "
            "wind generation, since its 41% margin is funding the group. On B2C retail, set a "
            "short, explicit deadline to fix pricing and churn, or exit if it can't improve fast "
            "enough. On battery storage, commission an independent technical and financial "
            "review to decide between restructuring, bringing in a partner, or writing down the "
            "investment. The main risk is that exiting retail has reputational consequences, and "
            "writing down battery storage means acknowledging sunk losses without a permanent "
            "CFO in place, so I'd sequence the wind protection and retail deadline first while "
            "that review is underway.",
        ],
    },
    {
        "id": "JUDGE_C1_06",
        "case_id": "01-energy-company",
        "category": "FULL_COVERAGE_WITH_REDIRECT",
        "expected_enough_evidence": True,
        "rationale": (
            "Even though the candidate needed an interviewer nudge to reach the right structure "
            "and got a follow-up probe on retail's margin, the transcript still reaches full "
            "coverage -- structure, data, root-cause reasoning, and a recommendation are all "
            "present -- so there is enough evidence to evaluate, including how well the "
            "candidate adapted to redirection."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Solventus Energy, a Spanish renewable energy company "
            "operating three business units: onshore wind generation, residential electricity "
            "retail (B2C), and large-scale battery storage construction. Over the past two years, "
            "group EBITDA has fallen 34% even though total revenue has grown 18%. The CEO has "
            "brought you in to find out what is driving the profit decline and to recommend a "
            "path forward.",
            "Candidate: I'd like to start by looking at overall cost trends across the company "
            "before going anywhere else.",
            "Interviewer: Would it help to look at margins separately for each of the three "
            "business units instead?",
            "Candidate: Yes, that's a better starting point - let's break profitability down by "
            "wind generation, B2C retail, and battery storage.",
            "Interviewer reveal: Revenue and margin by business unit: wind generation has a 41% "
            "EBITDA margin and is operationally healthy. B2C retail has a -8% EBITDA margin with "
            "28% annual customer churn. Battery storage has no revenue yet, is running at 3x "
            "original CAPEX, and is delayed by 22 months.",
            "Candidate: Wind is healthy at 41% margin, B2C retail is losing money at -8% margin "
            "with heavy churn, and battery storage has no revenue yet and is over budget and "
            "behind schedule.",
            "Interviewer: What's actually driving retail's negative margin specifically?",
            "Candidate: High customer acquisition costs combined with 28% annual churn mean the "
            "company keeps paying to replace customers it can't retain, so it's destroying value "
            "on a per-customer basis.",
            "Interviewer: Based on your analysis, what recommendation would you give the CEO?",
            "Candidate: Protect wind generation as the core profit engine, put retail on a short "
            "clock to fix its unit economics or exit, and get an independent review of the "
            "battery project given how far over budget and behind schedule it is.",
        ],
    },
    # ---------------------------------------------------------------- Case 2: CF Baluarte Levante (has a math block)
    {
        "id": "JUDGE_C2_01",
        "case_id": "02-football-team",
        "category": "OPENING_ONLY",
        "expected_enough_evidence": False,
        "rationale": (
            "Same pattern as JUDGE_C1_01: a single unfounded guess after the opening prompt, "
            "with no recap, structure, or data exchanged."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is CF Baluarte Levante, a mid-sized Spanish football club. "
            "After being promoted to La Liga in 2019, the club took on significant debt to fund "
            "player signings and was relegated back to Segunda Division in 2023. Since "
            "relegation, profitability has deteriorated sharply. The majority owner, a US "
            "private equity fund, wants a clear diagnosis of why profitability has deteriorated "
            "and a set of concrete levers to improve performance within the next 18 months.",
            "Candidate: I'd guess ticket prices are too low for a Segunda Division club.",
        ],
    },
    {
        "id": "JUDGE_C2_02",
        "case_id": "02-football-team",
        "category": "STRUCTURED_MID_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": (
            "Opening, a MECE revenue/cost structure, and the qualitative unit data have all "
            "been covered, but the interview stops before the quantified wage-restructuring "
            "question and before any recommendation is requested -- case_math_answer and "
            "final_recommendation both remain completely untested."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is CF Baluarte Levante, a mid-sized Spanish football club. "
            "After being promoted to La Liga in 2019, the club took on significant debt to fund "
            "player signings and was relegated back to Segunda Division in 2023. Since "
            "relegation, profitability has deteriorated sharply. The majority owner, a US "
            "private equity fund, wants a clear diagnosis of why profitability has deteriorated "
            "and a set of concrete levers to improve performance within the next 18 months.",
            "Candidate: Let me recap: the club was promoted in 2019, took on debt for signings, "
            "got relegated back to Segunda in 2023, and profitability has deteriorated sharply "
            "since. Is the 18-month improvement window fixed given the private equity owner's "
            "horizon, and should I focus on EBITDA, cash flow, or both?",
            "Interviewer: Focus on EBITDA for now, and yes, treat 18 months as a real "
            "constraint.",
            "Candidate: I'd like to split this into revenue streams - broadcasting, matchday, "
            "merchandising, sponsorship, transfers - versus the cost base, mainly wages and "
            "other contracted obligations, and separate immediate cash levers from longer-term "
            "value creation. Given relegation, my working hypothesis is that broadcasting "
            "revenue dropped sharply while wage costs, set for a top-division revenue base, "
            "haven't come down as fast.",
            "Interviewer reveal: Broadcasting revenue is down approximately 52% after relegation, "
            "the single largest driver of the decline. Matchday revenue is down too, partly "
            "because Segunda attendance is lower and partly because stadium hospitality is "
            "unavailable during an ongoing renovation. Merchandising is actually up 40% "
            "year-on-year, but it's too small to offset the broadcasting decline. Player wages "
            "were contracted for a top-division revenue base and haven't been reduced enough "
            "since relegation.",
            "Candidate: That confirms it - broadcasting is the dominant revenue shock, and the "
            "cost side hasn't caught up with the new reality yet.",
        ],
    },
    {
        "id": "JUDGE_C2_03",
        "case_id": "02-football-team",
        "category": "PREMATURE_RECOMMENDATION",
        "expected_enough_evidence": False,
        "rationale": (
            "Same pattern as JUDGE_C1_03: an ungrounded recommendation given before any "
            "structure or data was exchanged."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is CF Baluarte Levante, a mid-sized Spanish football club. "
            "After being promoted to La Liga in 2019, the club took on significant debt to fund "
            "player signings and was relegated back to Segunda Division in 2023. Since "
            "relegation, profitability has deteriorated sharply. The majority owner, a US "
            "private equity fund, wants a clear diagnosis of why profitability has deteriorated "
            "and a set of concrete levers to improve performance within the next 18 months.",
            "Candidate: I'd recommend cutting the wage bill immediately and selling some of the "
            "academy players.",
        ],
    },
    {
        "id": "JUDGE_C2_04",
        "case_id": "02-football-team",
        "category": "REQUIRED_EXHIBIT_SKIPPED",
        "expected_enough_evidence": False,
        "rationale": (
            "This transcript reaches a full, well-grounded recommendation, but the interviewer "
            "never asked the case's quantified wage-restructuring question, so the candidate "
            "never worked through the numbers (pre-relegation wage bill, current wage bill, the "
            "EUR16.25M reduction needed). Because this case includes a dedicated math exchange "
            "as one of its required blocks, case_math_answer would have to be marked "
            "not_tested despite the case having a quantitative component ready to test -- the "
            "interview was ended one exchange too early rather than genuinely lacking a math "
            "step."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is CF Baluarte Levante, a mid-sized Spanish football club. "
            "After being promoted to La Liga in 2019, the club took on significant debt to fund "
            "player signings and was relegated back to Segunda Division in 2023. Since "
            "relegation, profitability has deteriorated sharply. The majority owner, a US "
            "private equity fund, wants a clear diagnosis of why profitability has deteriorated "
            "and a set of concrete levers to improve performance within the next 18 months.",
            "Candidate: Let me recap: the club was promoted in 2019, took on debt for signings, "
            "got relegated back to Segunda in 2023, and profitability has deteriorated sharply "
            "since. Is the 18-month improvement window fixed given the private equity owner's "
            "horizon, and should I focus on EBITDA, cash flow, or both?",
            "Interviewer: Focus on EBITDA, and treat 18 months as a real constraint.",
            "Candidate: I'd split revenue streams versus the cost base, and separate immediate "
            "cash levers from longer-term value creation. My hypothesis is that broadcasting "
            "revenue collapsed after relegation while wage costs, built for a top-division "
            "revenue base, are lagging behind.",
            "Interviewer reveal: Broadcasting revenue is down approximately 52% after relegation "
            "- the single largest driver. Matchday revenue is down due to lower Segunda "
            "attendance and an ongoing stadium renovation that's cut off hospitality revenue. "
            "Merchandising is up 40% year-on-year but far too small to offset the broadcasting "
            "decline. Sponsorship is down modestly on La Liga relegation clauses. Net debt "
            "stands at EUR47M, and player wages, contracted for top-division revenue, haven't "
            "been reduced enough. The club has a cantera valued at over EUR25M across three "
            "players, a loyal abonado base, and a rejected stadium naming-rights offer.",
            "Candidate: So the two-layer story is a structural revenue shock from relegation "
            "plus a wage bill that's still sized for La Liga income.",
            "Interviewer: Based on your analysis, what recommendation would you give the "
            "ownership group?",
            "Candidate: Restructure the wage bill to match Segunda Division economics, monetize "
            "a cantera player for liquidity, and reconsider the naming-rights offer, while "
            "treating promotion as the real structural fix. The main risk is that selling too "
            "much talent or cutting costs too aggressively could hurt the team's competitiveness "
            "and the very promotion chances the plan depends on.",
        ],
    },
    {
        "id": "JUDGE_C2_05",
        "case_id": "02-football-team",
        "category": "FULL_COVERAGE_WEAK",
        "expected_enough_evidence": True,
        "rationale": (
            "Opening, structure, data, the math exchange, and a recommendation are all present "
            "-- full stage coverage -- even though the recommendation itself is generic and "
            "skips risks/next steps and the math talk-through is thin; there is enough "
            "transcript to score every dimension, just not highly."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is CF Baluarte Levante, a mid-sized Spanish football club. "
            "After being promoted to La Liga in 2019, the club took on significant debt to fund "
            "player signings and was relegated back to Segunda Division in 2023. Since "
            "relegation, profitability has deteriorated sharply. The majority owner, a US "
            "private equity fund, wants a clear diagnosis of why profitability has deteriorated "
            "and a set of concrete levers to improve performance within the next 18 months.",
            "Candidate: I'd look at revenue and costs separately.",
            "Interviewer: Go ahead.",
            "Candidate: What's happened to revenue and costs since relegation?",
            "Interviewer reveal: Broadcasting revenue is down approximately 52% after relegation. "
            "Merchandising is up 40% year-on-year but too small to matter much. Player wages "
            "were contracted for a top-division revenue base and haven't been reduced enough.",
            "Candidate: So broadcasting is way down and wages haven't been cut enough.",
            "Interviewer: The interviewer now provides the following numbers: before relegation, "
            "the club generated EUR100M of annual revenue and had a wage bill equal to 65% of "
            "revenue. After relegation, revenue fell by 35% to EUR65M, but the wage bill only "
            "fell by 10% because most player contracts were fixed. If the club wants to return "
            "to a 65% wage-to-revenue ratio, by how many euros does the wage bill need to be "
            "reduced from its current level?",
            "Candidate: Let me try... pre-relegation wages were 65 million, and if they only "
            "fell 10 percent that's about 58.5 million now. To get back to 65 percent of the "
            "new 65 million revenue, that's around 42 million, so they need to cut a bit more "
            "than 16 million.",
            "Interviewer: Based on your analysis, what recommendation would you give the "
            "ownership group?",
            "Candidate: Cut the wage bill and maybe sell a player.",
        ],
    },
    {
        "id": "JUDGE_C2_06",
        "case_id": "02-football-team",
        "category": "FULL_COVERAGE_STRONG",
        "expected_enough_evidence": True,
        "rationale": (
            "The transcript mirrors the case's own math setup and ideal final recommendation -- "
            "opening, hypothesis-driven structure, data-grounded synthesis, the wage-"
            "restructuring calculation, and a recommendation with risks and next steps are all "
            "present."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is CF Baluarte Levante, a mid-sized Spanish football club. "
            "After being promoted to La Liga in 2019, the club took on significant debt to fund "
            "player signings and was relegated back to Segunda Division in 2023. Since "
            "relegation, profitability has deteriorated sharply. The majority owner, a US "
            "private equity fund, wants a clear diagnosis of why profitability has deteriorated "
            "and a set of concrete levers to improve performance within the next 18 months.",
            "Candidate: Let me recap: promoted in 2019, took on debt for signings, relegated "
            "back to Segunda in 2023, and profitability has deteriorated sharply since. Given "
            "the private equity owner's ask, is the 18-month window a hard constraint, and "
            "should I anchor on EBITDA, free cash flow, or both?",
            "Interviewer: Anchor on EBITDA, and yes, treat 18 months as real.",
            "Candidate: I'll split revenue into broadcasting, matchday, merchandising, "
            "sponsorship, and transfers, and costs into wages versus other contracted "
            "obligations, then separate immediate cash levers from longer-term value creation. "
            "My hypothesis is that relegation caused an immediate structural drop in "
            "broadcasting revenue, while wage commitments set for a top-division revenue base "
            "haven't adjusted down as fast.",
            "Interviewer reveal: Broadcasting revenue is down approximately 52% after relegation "
            "- the single largest driver. Matchday revenue is down due to lower Segunda "
            "attendance and an ongoing stadium renovation that's cut off hospitality revenue. "
            "Merchandising is up 40% year-on-year but far too small to offset the broadcasting "
            "decline. Sponsorship is down modestly on La Liga relegation clauses. Net debt "
            "stands at EUR47M, and player wages, contracted for top-division revenue, haven't "
            "been reduced enough. The club has a cantera valued at over EUR25M across three "
            "players, a loyal abonado base, and a rejected stadium naming-rights offer.",
            "Candidate: That confirms a two-layer problem: a structural revenue shock from "
            "relegation, mainly broadcasting, and a cost base, mainly wages, that's misaligned "
            "with the new Segunda-level revenue.",
            "Interviewer: The interviewer now provides the following numbers: before relegation, "
            "the club generated EUR100M of annual revenue and had a wage bill equal to 65% of "
            "revenue. After relegation, revenue fell by 35% to EUR65M, but the wage bill only "
            "fell by 10% because most player contracts were fixed. If the club wants to return "
            "to a 65% wage-to-revenue ratio, by how many euros does the wage bill need to be "
            "reduced from its current level?",
            "Candidate: Setting it up: the pre-relegation wage bill was 65% of EUR100M, so "
            "EUR65M. It's only fallen 10% since, so the current wage bill is EUR65M times 0.9, "
            "which is EUR58.5M. The target is 65% of the new EUR65M revenue base, which is "
            "EUR42.25M. So the further reduction needed is EUR58.5M minus EUR42.25M, which is "
            "EUR16.25M. That confirms the core issue isn't just revenue - it's a cost base still "
            "built for a La Liga income level, and EUR16.25M is the scale of restructuring "
            "needed before other levers even matter.",
            "Interviewer: Based on your analysis, what recommendation would you give the "
            "ownership group?",
            "Candidate: Restructure the wage bill by roughly EUR16.25M to match Segunda "
            "Division economics, and fund the transition with selective asset monetization - at "
            "least one cantera player, given the combined value of over EUR25M - rather than "
            "fully depleting the pipeline. I'd also reopen the naming-rights discussion as a "
            "liquidity lever, since it doesn't depend on league position. The key risks are that "
            "selling too much talent could hurt competitiveness and the promotion chances this "
            "plan depends on, and that aggressive cost cuts could erode support among the loyal "
            "abonado base. Next steps: set a timeline for the wage restructuring and identify "
            "which contracts to renegotiate first, decide which cantera player to monetize based "
            "on sporting importance versus liquidity need, and bring the naming-rights proposal "
            "back to the board.",
        ],
    },
    {
        "id": "JUDGE_C2_07",
        "case_id": "02-football-team",
        "category": "FULL_COVERAGE_WITH_REDIRECT",
        "expected_enough_evidence": True,
        "rationale": (
            "Needed one redirect to get past an unhelpful pricing tangent, but the transcript "
            "still reaches full coverage -- two-layer structure, data, the wage-restructuring "
            "math, and a risk-aware recommendation -- so there is enough evidence to evaluate."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is CF Baluarte Levante, a mid-sized Spanish football club. "
            "After being promoted to La Liga in 2019, the club took on significant debt to fund "
            "player signings and was relegated back to Segunda Division in 2023. Since "
            "relegation, profitability has deteriorated sharply. The majority owner, a US "
            "private equity fund, wants a clear diagnosis of why profitability has deteriorated "
            "and a set of concrete levers to improve performance within the next 18 months.",
            "Candidate: I'd start by looking at ticket pricing strategy.",
            "Interviewer: What happened to broadcasting revenue specifically after relegation?",
            "Candidate: Good point - let's look at broadcasting first, then the rest of "
            "revenue, then costs.",
            "Interviewer reveal: Broadcasting revenue is down approximately 52% after relegation "
            "- the single largest driver. Player wages were contracted for a top-division "
            "revenue base and haven't been reduced enough since relegation.",
            "Candidate: So broadcasting collapsed roughly 52%, which is the dominant driver, "
            "while wages haven't come down enough given they were set for La Liga revenue.",
            "Interviewer: The interviewer now provides the following numbers: before relegation, "
            "revenue was EUR100M with wages at 65% of revenue; after relegation revenue fell 35% "
            "to EUR65M but wages only fell 10%. How much further does the wage bill need to fall "
            "to get back to a 65% ratio?",
            "Candidate: Pre-relegation wages were EUR65M, now at EUR58.5M after the 10% cut. "
            "Target at 65% of EUR65M revenue is EUR42.25M, so they need a further EUR16.25M cut.",
            "Interviewer: Based on your analysis, what recommendation would you give the "
            "ownership group?",
            "Candidate: Restructure the wage bill by about EUR16.25M, monetize a cantera player "
            "to fund the transition, and revisit the naming-rights offer, while accepting that "
            "only promotion truly fixes the broadcasting shortfall. The main risk is hurting "
            "squad quality and, with it, promotion chances.",
        ],
    },
    # ---------------------------------------------------------------- Case 3: Verdex AI (no math/creative block)
    {
        "id": "JUDGE_C3_01",
        "case_id": "03-agriculture-company",
        "category": "OPENING_ONLY",
        "expected_enough_evidence": False,
        "rationale": (
            "Same pattern as JUDGE_C1_01/JUDGE_C2_01: a single unfounded guess after the "
            "opening prompt, with no recap, structure, or data exchanged."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Verdex AI, a Spanish agri-tech startup that offers an "
            "AI-powered crop disease detection system for olive groves and vineyard farms in "
            "Spain and Portugal. Its early traction has been especially strong in areas such as "
            "Candeleda, Talavera de la Reina, the Sierra de Gredos corridor, and parts of "
            "Extremadura and Alentejo. Annual recurring revenue has grown 60% per year for the "
            "last two years and the company now serves 340 agricultural cooperative clients. "
            "Despite this growth, losses have widened each quarter and burn has accelerated in "
            "the last two periods. The founders want to understand the source of the "
            "profitability problem and identify a path to financial sustainability.",
            "Candidate: Sounds like they're probably just spending too much on marketing.",
        ],
    },
    {
        "id": "JUDGE_C3_02",
        "case_id": "03-agriculture-company",
        "category": "STRUCTURED_MID_ANALYSIS",
        "expected_enough_evidence": False,
        "rationale": (
            "Opening, the acquisition-vs-servicing structure, and the unit-economics data are "
            "all covered, but the final recommendation has not been reached yet -- "
            "final_recommendation remains untested."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Verdex AI, a Spanish agri-tech startup that offers an "
            "AI-powered crop disease detection system for olive groves and vineyard farms in "
            "Spain and Portugal. Its early traction has been especially strong in areas such as "
            "Candeleda, Talavera de la Reina, the Sierra de Gredos corridor, and parts of "
            "Extremadura and Alentejo. Annual recurring revenue has grown 60% per year for the "
            "last two years and the company now serves 340 agricultural cooperative clients. "
            "Despite this growth, losses have widened each quarter and burn has accelerated in "
            "the last two periods. The founders want to understand the source of the "
            "profitability problem and identify a path to financial sustainability.",
            "Candidate: Let me recap: ARR has grown 60% a year for two years, they now serve 340 "
            "cooperatives, but losses are widening and burn is accelerating. Is the founders' "
            "ask a diagnosis only, or a concrete sustainability plan, and how much runway do we "
            "have to work with?",
            "Interviewer: Good questions - let's diagnose first. I'll tell you the runway is "
            "limited, more on that shortly.",
            "Candidate: Since this is positioned as an AI software company, I'd expect "
            "software-like margins. If margins are thin despite fast growth, my hypothesis is "
            "the delivery model is more hardware- and service-heavy than the positioning "
            "suggests, so growth may be adding cost as fast as revenue. I'd like to split this "
            "into acquisition economics - cost to win a customer - versus servicing economics - "
            "cost to keep serving them.",
            "Interviewer reveal: Current gross margin is approximately 18%, very low for a "
            "company positioned as AI software, because the product needs physical field "
            "sensors, technician installation, and ongoing maintenance. Customer acquisition "
            "cost payback is 38 months. Pricing was set low to drive penetration among "
            "price-sensitive cooperatives. Large cooperatives are more profitable than small "
            "ones because fixed onboarding and installation costs are spread over more hectares; "
            "small cooperatives are loss-making per account. Remaining runway is approximately "
            "14 months.",
            "Candidate: That confirms it - this isn't really a software margin profile, it's "
            "hardware-and-service-heavy, and with a 38-month payback against only 14 months of "
            "runway, growth is currently burning cash rather than building operating leverage.",
        ],
    },
    {
        "id": "JUDGE_C3_03",
        "case_id": "03-agriculture-company",
        "category": "PREMATURE_RECOMMENDATION",
        "expected_enough_evidence": False,
        "rationale": (
            "Same pattern as JUDGE_C1_03/JUDGE_C2_03: an ungrounded recommendation given before "
            "any structure or data was exchanged."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Verdex AI, a Spanish agri-tech startup that offers an "
            "AI-powered crop disease detection system for olive groves and vineyard farms in "
            "Spain and Portugal. Its early traction has been especially strong in areas such as "
            "Candeleda, Talavera de la Reina, the Sierra de Gredos corridor, and parts of "
            "Extremadura and Alentejo. Annual recurring revenue has grown 60% per year for the "
            "last two years and the company now serves 340 agricultural cooperative clients. "
            "Despite this growth, losses have widened each quarter and burn has accelerated in "
            "the last two periods. The founders want to understand the source of the "
            "profitability problem and identify a path to financial sustainability.",
            "Candidate: I'd recommend they just raise prices across the board.",
        ],
    },
    {
        "id": "JUDGE_C3_05",
        "case_id": "03-agriculture-company",
        "category": "FULL_COVERAGE_WEAK",
        "expected_enough_evidence": True,
        "rationale": (
            "Opening, structure, data, and a recommendation are all present, so every rubric "
            "dimension has some transcript to draw on, even though the recommendation stays "
            "generic and never quantifies the runway/payback tradeoff."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Verdex AI, a Spanish agri-tech startup that offers an "
            "AI-powered crop disease detection system for olive groves and vineyard farms in "
            "Spain and Portugal. Its early traction has been especially strong in areas such as "
            "Candeleda, Talavera de la Reina, the Sierra de Gredos corridor, and parts of "
            "Extremadura and Alentejo. Annual recurring revenue has grown 60% per year for the "
            "last two years and the company now serves 340 agricultural cooperative clients. "
            "Despite this growth, losses have widened each quarter and burn has accelerated in "
            "the last two periods. The founders want to understand the source of the "
            "profitability problem and identify a path to financial sustainability.",
            "Candidate: I'd look at costs versus revenue for a typical customer.",
            "Interviewer: Go ahead.",
            "Candidate: What does it cost to serve a customer versus what we charge them?",
            "Interviewer reveal: Current gross margin is approximately 18%. Customer "
            "acquisition cost payback is 38 months. Large cooperatives are more profitable than "
            "small ones. Remaining runway is approximately 14 months.",
            "Candidate: So margins are low because of the hardware costs, and payback takes a "
            "long time.",
            "Interviewer: Based on your analysis, what recommendation would you give the "
            "founders?",
            "Candidate: Focus more on bigger customers and adjust pricing.",
        ],
    },
    {
        "id": "JUDGE_C3_06",
        "case_id": "03-agriculture-company",
        "category": "FULL_COVERAGE_STRONG",
        "expected_enough_evidence": True,
        "rationale": (
            "The transcript mirrors the case's own ideal final recommendation -- opening, "
            "hypothesis-driven structure, data-grounded synthesis, and a risk-aware "
            "recommendation are all present."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Verdex AI, a Spanish agri-tech startup that offers an "
            "AI-powered crop disease detection system for olive groves and vineyard farms in "
            "Spain and Portugal. Its early traction has been especially strong in areas such as "
            "Candeleda, Talavera de la Reina, the Sierra de Gredos corridor, and parts of "
            "Extremadura and Alentejo. Annual recurring revenue has grown 60% per year for the "
            "last two years and the company now serves 340 agricultural cooperative clients. "
            "Despite this growth, losses have widened each quarter and burn has accelerated in "
            "the last two periods. The founders want to understand the source of the "
            "profitability problem and identify a path to financial sustainability.",
            "Candidate: Let me recap: ARR has grown 60% a year for two years across 340 "
            "cooperatives, but losses are widening and burn is accelerating, and the founders "
            "want to understand the root cause and a path to sustainability. Is there a "
            "specific runway or timeline I should be aware of before I structure this?",
            "Interviewer: Yes - I'll give you the runway figure shortly, keep going.",
            "Candidate: Since this is sold as AI software, I'd expect software-like margins; if "
            "they're thin despite fast growth, my hypothesis is that the delivery model is more "
            "hardware- and service-heavy than the positioning suggests. I'd like to split the "
            "analysis into acquisition economics, what it costs to win a customer, versus "
            "servicing economics, what it costs to keep serving them, and look at whether that "
            "differs by cooperative size.",
            "Interviewer reveal: Gross margin is approximately 18%, low for an \"AI software\" "
            "business, driven by physical field sensors, technician installation, and "
            "maintenance - not the AI itself. CAC payback is 38 months. Pricing was set low to "
            "drive penetration among price-sensitive cooperatives, especially smaller ones. "
            "Large cooperatives are meaningfully more profitable than small ones, since fixed "
            "onboarding and installation costs spread over more hectares; small cooperatives are "
            "loss-making per account. Runway is approximately 14 months. A software-only "
            "satellite model could remove sensor costs but needs 9 more months of development "
            "and capital.",
            "Candidate: That confirms the hypothesis - this is a structural unit-economics "
            "problem, not a growth problem. An 18% margin is far below what software should look "
            "like, and with a 38-month CAC payback against only 14 months of runway, faster "
            "growth is actually accelerating cash burn rather than building leverage. The weak "
            "economics are concentrated in small cooperatives specifically, while large ones "
            "are already healthy.",
            "Interviewer: Based on your analysis, what recommendation would you give the "
            "founders?",
            "Candidate: Stop or sharply limit acquisition of small, unprofitable cooperatives, "
            "shift commercial focus to larger accounts, and restructure pricing so hardware and "
            "installation costs are recovered explicitly, while treating the software-only "
            "satellite model as the structural fix once financed. The main risks are that "
            "unbundling fees could slow the 60%-growth narrative in the short term, and that the "
            "satellite model still needs 9 more months of development and capital that may "
            "require external financing. Next steps: implement the pricing and segmentation "
            "changes within 6 months given the runway constraint, pursue bridge financing or a "
            "partner specifically for the satellite development gap, and track gross margin and "
            "CAC payback by segment monthly.",
        ],
    },
    {
        "id": "JUDGE_C3_07",
        "case_id": "03-agriculture-company",
        "category": "FULL_COVERAGE_WITH_REDIRECT",
        "expected_enough_evidence": True,
        "rationale": (
            "Needed one redirect away from a generic sales-spend framing, but the transcript "
            "still reaches full coverage -- structure, data, and a recommendation -- so there "
            "is enough evidence to evaluate."
        ),
        "judge_round": 0,
        "transcript": [
            "Interviewer: Your client is Verdex AI, a Spanish agri-tech startup that offers an "
            "AI-powered crop disease detection system for olive groves and vineyard farms in "
            "Spain and Portugal. Its early traction has been especially strong in areas such as "
            "Candeleda, Talavera de la Reina, the Sierra de Gredos corridor, and parts of "
            "Extremadura and Alentejo. Annual recurring revenue has grown 60% per year for the "
            "last two years and the company now serves 340 agricultural cooperative clients. "
            "Despite this growth, losses have widened each quarter and burn has accelerated in "
            "the last two periods. The founders want to understand the source of the "
            "profitability problem and identify a path to financial sustainability.",
            "Candidate: I'd start by looking at how sales and marketing spend has scaled with "
            "revenue.",
            "Interviewer: What does it actually take to deliver this product to a customer?",
            "Candidate: Good redirect - let's look at delivery cost. I'd split this into "
            "acquisition economics versus servicing economics.",
            "Interviewer reveal: Gross margin is approximately 18%, driven by physical field "
            "sensors, technician installation, and maintenance. CAC payback is 38 months. Large "
            "cooperatives are more profitable than small ones. Runway is approximately 14 "
            "months.",
            "Candidate: So the low 18% margin comes from physical sensors, installation, and "
            "maintenance, not the AI itself, and with a 38-month CAC payback against 14 months "
            "of runway, growth is currently burning cash.",
            "Interviewer: Based on your analysis, what recommendation would you give the "
            "founders?",
            "Candidate: Limit acquisition of small cooperatives, refocus on larger accounts, "
            "unbundle hardware/installation pricing, and prioritize the satellite, software-only "
            "model as the real structural fix, while accepting it needs further financing and "
            "about 9 more months to build.",
        ],
    },
]


def build_case_library() -> dict[str, dict[str, Any]]:
    """Derive case_prompt/case_guidance/case_data/case_recommendation for each case_id
    using the exact same loader/utils functions judge_node's real callers use, so this
    golden set can never silently drift from what production actually feeds the judge."""
    cases: dict[str, dict[str, Any]] = {}
    for case_id in CASE_IDS:
        raw_case = loader.load_case(case_id)
        case_data = loader.adapt_case(raw_case)
        opening = get_opening_prompt(case_data)
        cases[case_id] = {
            "case_prompt": opening["content"] if opening else "None.",
            "case_guidance": utils.extract_case_guidance(case_data),
            "case_data": case_data,
            "case_recommendation": utils.extract_case_recommendation(case_data),
        }
    return cases


def assemble_state(
    item: dict[str, Any], cases: dict[str, dict[str, Any]], rubric_data: dict[str, Any]
) -> dict[str, Any]:
    """Reconstitute the exact AgenticGraphState slice judge_node(state) reads for one
    golden-set item -- this is what a harness should pass to judge_node/agentic.judge_node."""
    case = cases[item["case_id"]]
    return {
        "judge_round": item["judge_round"],
        "transcript": item["transcript"],
        "rubric_data": rubric_data,
        "case_prompt": case["case_prompt"],
        "case_guidance": case["case_guidance"],
        "case_data": case["case_data"],
        "case_recommendation": case["case_recommendation"],
    }


def main() -> None:
    cases = build_case_library()
    rubric_data = loader.adapt_rubric(loader.load_rubric())

    expected_true = sum(1 for item in ITEMS if item["expected_enough_evidence"])
    expected_false = len(ITEMS) - expected_true
    print(f"{len(ITEMS)} items built across {len(cases)} cases "
          f"({expected_true} expected True / {expected_false} expected False).")

    # Sanity check: every item must assemble into a valid judge_node input.
    for item in ITEMS:
        assemble_state(item, cases, rubric_data)

    payload = {
        "_schema_notes": (
            "Each item + its case_id's entry under 'cases', combined with 'rubric_data', is "
            "exactly the AgenticGraphState slice judge_node(state) reads (case_prompt, "
            "case_guidance, case_data, case_recommendation, rubric_data, transcript, "
            "judge_round). See assemble_state() in build_judge_golden_set.py for how to "
            "reconstitute it before calling judge_node/agentic.judge_node directly."
        ),
        "rubric_data": rubric_data,
        "cases": cases,
        "items": ITEMS,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
    print(f"Wrote golden set to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
