# Scenarios

Scenario files follow this pattern:

- `scenario_<case_number>_<level>.json`
- case `001` = `duke_activist_action`
- case `002` = `harvard_01_retailer`

Performance ladder: `very_weak` | `weak` | `good` | `very_good` | `excellent`

## Duke - Activist Action (001)

These scenarios all use `duke_activist_action` and differ only in candidate quality.

- `scenario_001_very_weak.json`
  - very weak candidate
  - generic, vague, weak recommendation

- `scenario_001_weak.json`
  - weak candidate
  - some understanding, but shallow structure and incomplete reasoning

- `scenario_001_good.json`
  - good candidate
  - mostly correct logic, but limited sharpness and synthesis

- `scenario_001_very_good.json`
  - very good candidate
  - strong structure, strong business reasoning, slightly below top-tier polish

- `scenario_001_excellent.json`
  - excellent candidate
  - correct prioritization, strong exhibit interpretation, decisive recommendation

## Harvard - Retailer (002)

- `scenario_002_very_weak.json`
  - very weak candidate
  - misses the revenue-side diagnosis, store segmentation, and product-mix mismatch

- `scenario_002_weak.json`
  - weak candidate
  - notices some revenue-side issues, but stays generic and weakly prioritized

- `scenario_002_good.json`
  - good candidate
  - mostly correct diagnosis of customer behavior and assortment mismatch

- `scenario_002_very_good.json`
  - very good candidate
  - strong segmentation logic, strong diagnosis, slightly less polished than top-tier

- `scenario_002_excellent.json`
  - excellent candidate
  - sharp revenue-side framing, precise segmentation, and decisive recommendation

## AGSM - Chilled Beverages (003)

- `scenario_003_very_weak.json`
  - very weak candidate
  - jumps to selling the business and misses cost, pricing, and synergy logic

- `scenario_003_weak.json`
  - weak candidate
  - notices some structural issues but stays tentative and underdeveloped

- `scenario_003_good.json`
  - good candidate
  - reaches the right answer and identifies the main economics, with moderate synthesis

- `scenario_003_very_good.json`
  - very good candidate
  - strong commercial diagnosis and strong recommendation, slightly below top-tier polish

- `scenario_003_excellent.json`
  - excellent candidate
  - sharp economic diagnosis, strong synergy awareness, decisive keep-and-fix recommendation

## Harvard - Juice Producer (004)

- `scenario_004_very_weak.json`
  - very weak candidate
  - misses the cost-side diagnosis and the pricing/allocation problem

- `scenario_004_weak.json`
  - weak candidate
  - suspects a cost issue, but explains the gallon economics only partially

- `scenario_004_good.json`
  - good candidate
  - identifies underpriced gallons and incorrect cost allocation

- `scenario_004_very_good.json`
  - very good candidate
  - strong diagnosis of gallon unit economics and product-mix deterioration

- `scenario_004_excellent.json`
  - excellent candidate
  - crisp activity-based costing diagnosis and decisive repricing recommendation

## AGSM - Distilled Spirits (005)

- `scenario_005_very_weak.json`
  - very weak candidate
  - misses the state/channel mix shift and stays generic

- `scenario_005_weak.json`
  - weak candidate
  - notices some distribution issues, but underdevelops the channel economics

- `scenario_005_good.json`
  - good candidate
  - identifies the open-state mix shift as the main profitability issue

- `scenario_005_very_good.json`
  - very good candidate
  - strong channel-economics diagnosis and strong recommendation

- `scenario_005_excellent.json`
  - excellent candidate
  - crisp elimination of false leads and decisive channel-mix conclusion

## Duke - Cackalacky Construction (006)

- `scenario_006_very_weak.json`
  - very weak candidate
  - misses the market-sizing logic and gives a weak entry recommendation

- `scenario_006_weak.json`
  - weak candidate
  - partial math and partial market-entry logic, but underdeveloped synthesis

- `scenario_006_good.json`
  - good candidate
  - correct market sizing and sensible Texas recommendation

- `scenario_006_very_good.json`
  - very good candidate
  - strong market selection, strong entry logic, strong risks and mitigations

- `scenario_006_excellent.json`
  - excellent candidate
  - sharp quantification, strong Texas rationale, and disciplined entry recommendation

## Harvard - Chemical Manufacturer (007)

- `scenario_007_very_weak.json`
  - very weak candidate
  - misreads market share and misses the shrinking-market price pressure story

- `scenario_007_weak.json`
  - weak candidate
  - notices some pricing pressure, but underdevelops the industry-decline logic

- `scenario_007_good.json`
  - good candidate
  - correctly links shrinking demand, competitor exits, and lower margins

- `scenario_007_very_good.json`
  - very good candidate
  - strong diagnosis of market-share optics and revenue-quality deterioration

- `scenario_007_excellent.json`
  - excellent candidate
  - crisp interpretation of shrinking-market economics and decisive strategic recommendation

## Duke - Dealer Jack's (008)

- `scenario_008_very_weak.json`
  - very weak candidate
  - misses the private label mix story and fails the core math

- `scenario_008_weak.json`
  - weak candidate
  - sees part of the mix logic, but under-explains the math and risks

- `scenario_008_good.json`
  - good candidate
  - validates the hypothesis and recommends private label focus

- `scenario_008_very_good.json`
  - very good candidate
  - strong diagnosis, strong math, and strong implementation caution

- `scenario_008_excellent.json`
  - excellent candidate
  - crisp private-label economics, clean math, and disciplined recommendation

## AGSM - Airline Expansion (009)

- `scenario_009_very_weak.json`
  - very weak candidate
  - fails to structure the route as a profitability and cannibalization decision

- `scenario_009_weak.json`
  - weak candidate
  - sees some demand and cost drivers, but underweights cannibalization

- `scenario_009_good.json`
  - good candidate
  - correctly frames route economics and includes cannibalization

- `scenario_009_very_good.json`
  - very good candidate
  - strong route-profitability logic and strong strategic treatment of cannibalization

- `scenario_009_excellent.json`
  - excellent candidate
  - crisp incremental-profit framework and disciplined decision rule

Note for Harvard retailer:

- `case_math_answer` is marked as `not_tested`
- `case_creative_answer` is marked as `not_tested`

This is intentional because the case is primarily diagnostic and recommendation-based, not a true math or brainstorming case in the MVP flow.
