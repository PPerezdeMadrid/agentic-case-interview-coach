import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output" / "harvard_casebook_probitability"


def block(block_id, block_type, title, visible, source_page, content):
    return {
        "block_id": block_id,
        "block_type": block_type,
        "title": title,
        "visible_to_candidate": visible,
        "image": None,
        "source_page": source_page,
        "content": content,
    }


CASES = {
    "harvard_beer_brew_05_clean_raw.json": {
        "case_content": [
            block(
                "beer_brew_prompt_001",
                "prompt",
                "Prompt #1 - Beer Brew",
                True,
                10,
                "Beer Brew, a major US beer company, entered the UK market two years ago and is still losing money. Despite high per-capita beer consumption, sales have been disappointing and management wants to know why.\n\n"
                "• Beer Brew is currently selling two products in the UK: a strong beer and a light beer.\n\n"
                "• The company has spent heavily on marketing and made its products broadly available through normal distribution channels.",
            ),
            block(
                "beer_brew_guidance_001",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                10,
                "High Level Plan of Attack: determine whether the problem comes from product mix, customer preferences, pricing, or marketing.\n\n"
                "• Use the profitability framework and focus on the revenue side of the problem.\n\n"
                "• Evaluate the product mix of Beer Brew and compare it with what is selling well in the UK.\n\n"
                "• Understand consumer behavior and tastes in the market.\n\n"
                "• Analyze whether pricing, placement, and marketing reinforce or weaken the brand.",
            ),
            block(
                "beer_brew_guidance_002",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                10,
                "Lay out your thoughts. Ask questions such as:\n\n"
                "• What kinds of beers are currently the best sellers in the UK?\n\n"
                "• How are Beer Brew's strong and light beers performing?\n\n"
                "• Is the market highly competitive, and are there any distribution problems?\n\n"
                "• How does Beer Brew's price compare with other premium brands?",
            ),
            block(
                "beer_brew_expected_analysis_001",
                "expected_analysis",
                "Expected Analysis - Prompt #1",
                False,
                11,
                "Dig Deeper: Gather Facts / Make Calculations\n\n"
                "• The best-selling beers in the UK are generally dark, strong tasting, and moderate to high in alcohol content.\n\n"
                "• Beer Brew's strong beer is only selling slightly below average, but the light beer is not selling at all.\n\n"
                "• UK consumers associate dark beer with strength, masculinity, and value; Beer Brew's products are relatively light in color.\n\n"
                "• The light beer category is underdeveloped in the UK because the health trend that drove growth in the US has not translated to Europe.\n\n"
                "• Beer Brew also undercut the market on price, which makes the product look like a low-quality 'American beer' rather than a premium offering.\n\n"
                "• Distribution is not the issue: the beer is sold wherever competing brands are sold.",
            ),
            block(
                "beer_brew_key_findings_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                11,
                "Key findings:\n\n"
                "• Beer Brew's product mix is misaligned with UK consumer preferences.\n\n"
                "• The light beer offering has little market fit in the UK.\n\n"
                "• Low pricing dilutes the brand and reinforces the perception of inferior quality.",
            ),
            block(
                "beer_brew_final_recommendation_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                11,
                "Based on your analysis, what recommendation would you give the client?",
            ),
            block(
                "beer_brew_guidance_003",
                "guidance",
                "Interviewer Guidance - Final Recommendation",
                False,
                11,
                "• Change the color and positioning of the stronger beer so it better matches what UK consumers associate with premium, strong beer.\n\n"
                "• Drop the light beer product line because the UK market is not ready for it.\n\n"
                "• Raise price points to match premium competitors rather than signaling low quality.",
            ),
        ]
    },
    "harvard_chemical_manufacturer_03_clean_raw.json": {
        "case_content": [
            block(
                "chemical_manufacturer_prompt_001",
                "prompt",
                "Prompt #1 - Chemical Manufacturer",
                True,
                6,
                "A chemical manufacturer that produces preservatives for packaged foods has increased market share, yet profits have declined. The CEO has asked you to investigate why profitability is falling and what the company should do next.\n\n"
                "• Management believes market share has improved, but the company is still under profit pressure.\n\n"
                "• The key question is whether the problem is driven by industry demand, pricing, or costs.",
            ),
            block(
                "chemical_manufacturer_guidance_001",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                6,
                "High Level Plan of Attack: clarify what the apparent market-share gain really means, then test what is happening to price, volume, demand, and costs.\n\n"
                "• Use the profitability framework and pull in relevant ideas from the value chain, 4Cs, and 4Ps.\n\n"
                "• Determine whether industry demand is rising or falling.\n\n"
                "• Assess substitutes, competition, and the overall health of the market.\n\n"
                "• Understand whether the company is gaining share through stronger positioning or simply through lower prices.",
            ),
            block(
                "chemical_manufacturer_guidance_002",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                6,
                "Lay out your thoughts. Ask questions such as:\n\n"
                "• Are preservative products still being used at the same level as before?\n\n"
                "• Have competitors entered or exited the market?\n\n"
                "• Has the client's volume actually increased, and by how much?\n\n"
                "• Have costs changed materially, or is price the main pressure point?",
            ),
            block(
                "chemical_manufacturer_expected_analysis_001",
                "expected_analysis",
                "Expected Analysis - Prompt #1",
                False,
                7,
                "Dig Deeper: Gather Facts\n\n"
                "• The preservatives industry is shrinking because consumers increasingly prefer fresher food and use fewer preservatives.\n\n"
                "• Several competitors have exited the market because the industry became saturated and unattractive.\n\n"
                "• The client's sales volume is only slightly higher than before, and the gain in market share is mostly a byproduct of competitor exits.\n\n"
                "• The company has been forced to lower prices in order to survive and retain volume in a shrinking market.\n\n"
                "• Costs have stayed broadly stable, so the decline in profit is mainly a margin problem rather than a cost problem.\n\n"
                "• Management is trying to renegotiate raw-material prices, but that alone will not solve the structural issue.",
            ),
            block(
                "chemical_manufacturer_key_findings_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                7,
                "Key findings:\n\n"
                "• The industry is shrinking, so higher market share does not translate into healthier economics.\n\n"
                "• The client is effectively buying share through lower prices.\n\n"
                "• Costs are not falling fast enough to offset the decline in price and margin.",
            ),
            block(
                "chemical_manufacturer_final_recommendation_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                7,
                "Based on your analysis, what recommendation would you give the client?",
            ),
            block(
                "chemical_manufacturer_guidance_003",
                "guidance",
                "Interviewer Guidance - Final Recommendation",
                False,
                7,
                "• Diversify into other chemicals with healthier demand so the company is less exposed to this declining market.\n\n"
                "• Reduce costs aggressively if price remains the only competitive lever.\n\n"
                "• Explore collaboration or joint purchasing approaches that improve raw-material negotiating leverage.",
            ),
        ]
    },
    "harvard_fast_food_restaurant_10_clean_raw.json": {
        "case_content": [
            block(
                "fast_food_restaurant_prompt_001",
                "prompt",
                "Prompt #1 - Fast Food Restaurant",
                True,
                23,
                "A classmate who bought a fast-food burger restaurant says the business has been steadily losing money for the last three months. Diagnose the issue, decide where to investigate first, and recommend what the owner should do next.",
            ),
            block(
                "fast_food_restaurant_guidance_001",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                23,
                "High Level Plan of Attack: first determine whether the issue is revenue, costs, or both, and then test whether the driver is internal or external.\n\n"
                "• Was the store making money three months ago? What changed?\n\n"
                "• Have revenues decreased, costs increased, or both?\n\n"
                "• Was there a major event such as a health-code issue, crime incident, or economic shock in the area?\n\n"
                "• Is there new competition nearby?",
            ),
            block(
                "fast_food_restaurant_guidance_002",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                23,
                "Lay out your thoughts.\n\n"
                "• If revenues are down, determine whether there are fewer customers or lower spend per visit.\n\n"
                "• If the problem is external, evaluate the competitor's value proposition and local market changes.\n\n"
                "• If the problem is internal, review food quality, pricing, service, cleanliness, facility layout, and overall experience.",
            ),
            block(
                "fast_food_restaurant_expected_analysis_001",
                "expected_analysis",
                "Expected Analysis - Prompt #1",
                False,
                24,
                "Dig Deeper: Gather Facts\n\n"
                "• Revenues have decreased and profits have declined; the problem is not a sudden cost spike.\n\n"
                "• The immediate driver is lower traffic: there are fewer customers coming to the restaurant.\n\n"
                "• The issue is external and tied to a new competitor that opened across the street.\n\n"
                "• A strong next step is primary research: visit both locations, compare product quality, pricing, service, layout, parking, accessibility, and overall experience.\n\n"
                "• Customer interviews should test how diners perceive the burger restaurant versus the new chicken competitor.\n\n"
                "• Once the value-proposition gap is clear, management can generate options and prioritize the highest-impact improvements.",
            ),
            block(
                "fast_food_restaurant_key_findings_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                25,
                "Key findings:\n\n"
                "• The problem is primarily a traffic decline, not a cost issue.\n\n"
                "• The decline is being driven by a nearby competitor with a stronger value proposition.\n\n"
                "• The right answer starts with diagnosing what customers value before choosing operational fixes.",
            ),
            block(
                "fast_food_restaurant_final_recommendation_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                25,
                "Based on your diagnosis, what should the burger restaurant do next?",
            ),
            block(
                "fast_food_restaurant_guidance_003",
                "guidance",
                "Interviewer Guidance - Final Recommendation",
                False,
                25,
                "• Recommend a structured field-study effort: customer interviews, competitor visits, and direct comparison of food, price, service, and convenience.\n\n"
                "• Build a menu of improvement options such as menu changes, quality upgrades, facility or service improvements, and clearer value positioning.\n\n"
                "• Prioritize actions based on expected traffic recovery, return on investment, and speed of execution.",
            ),
        ]
    },
    "harvard_hospital_08_clean_raw.json": {
        "case_content": [
            block(
                "hospital_prompt_001",
                "prompt",
                "Prompt #1 - Hospital",
                True,
                16,
                "A 350-bed hospital that had historically generated a 1 to 3 percent operating gain is now projecting a $12 million operating loss and could run out of cash within five years. The client wants to identify the source of the downturn and restore the hospital to break-even without layoffs.",
            ),
            block(
                "hospital_guidance_001",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                16,
                "High Level Plan of Attack: frame the case as profitability equals revenue minus costs, then determine whether the problem is falling revenue, excess fixed cost, inefficient variable cost, or some combination.\n\n"
                "• Layoffs are not an available solution.\n\n"
                "• Investigate how managed-care contracts, admissions, and length of stay are affecting revenue.\n\n"
                "• Test whether the hospital is carrying too much fixed capacity for current demand.",
            ),
            block(
                "hospital_guidance_002",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                16,
                "Lay out your thoughts.\n\n"
                "• Separate fixed versus variable costs.\n\n"
                "• Examine occupancy, staffing levels, physician behavior, and utilization of services.\n\n"
                "• Explore revenue levers such as insurer contracts, physician affiliations, and differentiated service lines.\n\n"
                "• Consider whether the local market has structural overcapacity.",
            ),
            block(
                "hospital_expected_analysis_001",
                "expected_analysis",
                "Expected Analysis - Prompt #1",
                False,
                17,
                "Dig Deeper: Gather Facts\n\n"
                "• Revenues have dropped by roughly 15 percent because of aggressive capitated managed-care pricing and declining admissions / length of stay in fee-for-service contracts.\n\n"
                "• Contracts are binding for three years, so the hospital cannot quickly renegotiate its revenue base.\n\n"
                "• Occupancy is about 70 percent, but the hospital is staffed for about 80 percent occupancy, creating high fixed-cost pressure.\n\n"
                "• Utilization of diagnostic and therapeutic services is about 15 percent higher than expected when contracts were priced.\n\n"
                "• Variable-cost improvement should focus on physician-driven resource use, purchasing discipline, formulary choices, and vendor concentration.\n\n"
                "• Revenue-side options include signing additional insurer contracts, employing or affiliating physicians, and marketing Centers of Excellence.\n\n"
                "• The market is also oversupplied: there are two other 350-bed hospitals nearby, admissions are down 5 percent, and patient days are down 10 percent.",
            ),
            block(
                "hospital_key_findings_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                18,
                "Key findings:\n\n"
                "• The hospital faces both revenue pressure and excess fixed capacity.\n\n"
                "• Physician-driven utilization is too high relative to how contracts were priced.\n\n"
                "• The local market appears to have structural overcapacity, which limits standalone recovery options.",
            ),
            block(
                "hospital_final_recommendation_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                18,
                "What would you recommend to restore the hospital to break-even?",
            ),
            block(
                "hospital_guidance_003",
                "guidance",
                "Interviewer Guidance - Final Recommendation",
                False,
                18,
                "• Improve variable costs by aligning physician incentives, reducing unnecessary utilization, tightening purchasing, and simplifying the vendor / formulary base.\n\n"
                "• Pursue revenue growth through additional insurer relationships, physician alignment, and differentiated specialty programs.\n\n"
                "• Consider strategic affiliation with a competitor to rationalize capacity in an overbuilt market.\n\n"
                "• A strong candidate should discuss both revenue maximization and cost minimization, while showing a clear understanding of fixed versus variable costs.",
            ),
        ]
    },
    "harvard_juice_producer_02_clean_raw.json": {
        "case_content": [
            block(
                "juice_producer_prompt_001",
                "prompt",
                "Prompt #1 - Juice Producer",
                True,
                4,
                "A juice producer historically sold 18-ounce cartons, then introduced 36-ounce plastic gallons. Sales have continued to grow by roughly 20 percent per year, but profits have steadily declined. Diagnose the issue and recommend what the owner should do.\n\n"
                "• The new gallon format was introduced to meet customer demand.\n\n"
                "• The business is experiencing a classic sales-up / profit-down problem.",
            ),
            block(
                "juice_producer_guidance_001",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                4,
                "High Level Plan of Attack: determine whether the issue is really on the revenue side or whether the new packaging format has introduced hidden cost problems.\n\n"
                "• Use the profitability framework, but focus mostly on costs rather than volume.\n\n"
                "• Compare the carton and gallon formats on price, packaging cost, labor, and overhead allocation.\n\n"
                "• Understand how the cost of new equipment has been incorporated into pricing.",
            ),
            block(
                "juice_producer_guidance_002",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                4,
                "Lay out your thoughts.\n\n"
                "• Sales are growing, so revenue volume is not the core issue.\n\n"
                "• Test whether gallons are being priced correctly on a per-unit and per-ounce basis.\n\n"
                "• Ask how packaging, labor, equipment, and overhead are assigned across products.",
            ),
            block(
                "juice_producer_expected_analysis_001",
                "expected_analysis",
                "Expected Analysis - Prompt #1",
                False,
                5,
                "Dig Deeper: Gather Facts / Make Calculations\n\n"
                "• Plastic gallons cost more to package than cartons, and they also require more skilled labor to run the machine.\n\n"
                "• The producer raised prices broadly across both cartons and gallons rather than allocating the incremental gallon costs to the gallon product itself.\n\n"
                "• Factory overhead is pooled and divided by unit volume, which further masks the true economics of the gallon format.\n\n"
                "• Gallons have grown to roughly 60 percent of sales volume.\n\n"
                "• On a per-ounce basis, the gallon product is effectively underpriced relative to its cost structure.\n\n"
                "• The more gallons the company sells under the current pricing approach, the more profit it gives away.",
            ),
            block(
                "juice_producer_key_findings_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                5,
                "Key findings:\n\n"
                "• The business has a cost-allocation problem rather than a demand problem.\n\n"
                "• The gallon product is underpriced given its higher direct and indirect costs.\n\n"
                "• Higher gallon mix is worsening profitability instead of helping it.",
            ),
            block(
                "juice_producer_final_recommendation_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                5,
                "Based on your analysis, what recommendation would you give the client?",
            ),
            block(
                "juice_producer_guidance_003",
                "guidance",
                "Interviewer Guidance - Final Recommendation",
                False,
                5,
                "• Conduct a proper activity-based costing exercise to separate the economics of cartons and gallons.\n\n"
                "• Reprice the gallon product based on its true packaging, labor, and overhead cost.\n\n"
                "• Stop averaging gallon-related costs across the full product line.",
            ),
        ]
    },
    "harvard_the_video_store_09_clean_raw.json": {
        "case_content": [
            block(
                "the_video_store_prompt_001",
                "prompt",
                "Prompt #1 - The Video Store",
                True,
                19,
                "Two entrepreneurs opened a video rental store near HBS and enjoyed strong initial growth, but after about a year profits fell sharply. Diagnose what happened and determine what the owners should do.",
            ),
            block(
                "the_video_store_guidance_001",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                19,
                "High Level Plan of Attack: first diagnose whether the problem sits in revenue or cost, and then determine whether the revenue problem is traffic or share of wallet.\n\n"
                "• Have revenues declined, have costs increased, or both?\n\n"
                "• Are fewer customers coming to the store, or are existing customers renting fewer videos?\n\n"
                "• Have prices changed?\n\n"
                "• Have new competitors or substitute entertainment options appeared?",
            ),
            block(
                "the_video_store_guidance_002",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                19,
                "Lay out your thoughts.\n\n"
                "• Use store traffic data and register receipts to distinguish a traffic problem from a spend-per-customer problem.\n\n"
                "• Do not define competition too narrowly: the client is in the home-entertainment business, not just the video-store business.\n\n"
                "• Once the demand problem is clear, develop and test a hypothesis about what substitute is taking share.",
            ),
            block(
                "the_video_store_expected_analysis_001",
                "expected_analysis",
                "Expected Analysis - Prompt #1",
                False,
                21,
                "Dig Deeper: Gather Facts\n\n"
                "• Revenues have decreased; the case is not primarily about rising costs.\n\n"
                "• Prices have not changed.\n\n"
                "• Traffic has fallen, which means the problem is customer visits rather than number of rentals per visit.\n\n"
                "• There are no new video stores or movie theaters driving the decline, so the competitive set must be defined more broadly.\n\n"
                "• The right frame is home entertainment: cable, pay-per-view, video on demand, delivery, and other in-home movie options are likely shrinking the store's market.\n\n"
                "• A strong candidate should explicitly broaden the definition of the business before concluding what is happening.",
            ),
            block(
                "the_video_store_key_findings_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                22,
                "Key findings:\n\n"
                "• The core problem is lower traffic, not higher cost or lower price.\n\n"
                "• The market is being disrupted by substitute forms of home entertainment.\n\n"
                "• The owners must redefine the competitive set before choosing a response.",
            ),
            block(
                "the_video_store_final_recommendation_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                22,
                "Based on your diagnosis, what should the video store owners do next?",
            ),
            block(
                "the_video_store_guidance_003",
                "guidance",
                "Interviewer Guidance - Final Recommendation",
                False,
                22,
                "• Recommend a response only after clearly diagnosing the revenue problem and the substitute threat.\n\n"
                "• A strong answer should show a structured diagnostic flow, share hypotheses explicitly, and connect the recommendation to the broader shift in home entertainment.\n\n"
                "• The candidate should drive toward a practical answer rather than staying only at the brainstorming stage.",
            ),
        ]
    },
    "harvard_travel_agency_07_clean_raw.json": {
        "case_content": [
            block(
                "travel_agency_prompt_001",
                "prompt",
                "Prompt #1 - Travel Agency",
                True,
                14,
                "A travel agency earns a 10 percent commission on bookings and generates about $1 million of profit before tax, while comparable agencies earn $2 million to $3.5 million. Identify why this agency is underperforming on profitability.\n\n"
                "• The agency processes about one million transactions per year.\n\n"
                "• The key issue is whether both customer segments contribute equally to profit.",
            ),
            block(
                "travel_agency_guidance_001",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                14,
                "High Level Plan of Attack: understand how each transaction contributes to the bottom line and separate the economics of business versus leisure customers.\n\n"
                "• Use the profitability framework, with emphasis on the cost side.\n\n"
                "• Ask about segment mix, total volume, revenue, and transaction cost.\n\n"
                "• Test whether the agency's issue is too little revenue per transaction, too much cost per transaction, or both.",
            ),
            block(
                "travel_agency_guidance_002",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                14,
                "Lay out your thoughts.\n\n"
                "• Break the analysis into business and leisure travelers.\n\n"
                "• Compare revenue per transaction versus cost per transaction for each segment.\n\n"
                "• Check whether the agency offers any additional products that could improve average revenue per booking.",
            ),
            block(
                "travel_agency_expected_analysis_001",
                "expected_analysis",
                "Expected Analysis - Prompt #1",
                False,
                15,
                "Dig Deeper: Gather Facts / Make Calculations\n\n"
                "• The agency has roughly 300,000 business transactions and 700,000 leisure transactions.\n\n"
                "• Business travel generates about $6 million of revenue, or roughly $20 per transaction, against a $9 transaction cost.\n\n"
                "• Leisure travel generates about $4 million of revenue, or roughly $5.71 per transaction, against the same $9 transaction cost.\n\n"
                "• That means business transactions are strongly profitable, while leisure transactions lose money on each booking.\n\n"
                "• Overall revenue is not dramatically out of line with peers; the problem is segment mix and poor leisure economics.\n\n"
                "• The leisure segment is the main drag on profitability.",
            ),
            block(
                "travel_agency_key_findings_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                15,
                "Key findings:\n\n"
                "• Business travelers are profitable; leisure travelers are not.\n\n"
                "• The agency's transaction cost is too high relative to leisure revenue per booking.\n\n"
                "• Comparable revenue to peers does not matter if the economics by segment are fundamentally broken.",
            ),
            block(
                "travel_agency_final_recommendation_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                15,
                "Based on your analysis, what recommendation would you give the client?",
            ),
            block(
                "travel_agency_guidance_003",
                "guidance",
                "Interviewer Guidance - Final Recommendation",
                False,
                15,
                "• Negotiate with airlines or customers so the agency captures more revenue on leisure transactions.\n\n"
                "• Reduce the cost per transaction for leisure bookings.\n\n"
                "• Consider focusing the business more heavily on business travelers.\n\n"
                "• Increase leisure revenue per customer through add-ons such as hotels, packages, and related travel products.",
            ),
        ]
    },
    "harvard_wheeler_dealer_06_clean_raw.json": {
        "case_content": [
            block(
                "wheeler_dealer_prompt_001",
                "prompt",
                "Prompt #1 - Wheeler Dealer",
                True,
                12,
                "Wheeler Dealer, an auto service chain, expanded aggressively by opening 15 additional stores. For the first time in more than a decade, profits have turned negative. Diagnose why the expansion hurt returns and recommend next steps.\n\n"
                "• Historically the business operated a healthy 30-store network.\n\n"
                "• Management believed it needed to expand because its original geographies were becoming saturated.",
            ),
            block(
                "wheeler_dealer_guidance_001",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                12,
                "High Level Plan of Attack: understand what changed with the expansion by looking at customer mix, geography, and the economics of Wheeler Dealer's two business lines.\n\n"
                "• Focus on customer segmentation and whether the new stores are serving the same type of customer as before.\n\n"
                "• Understand the nature of the business and the profit structure of the different offerings.\n\n"
                "• Use the profitability framework with emphasis on how revenue mix has changed.",
            ),
            block(
                "wheeler_dealer_guidance_002",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                12,
                "Lay out your thoughts.\n\n"
                "• Ask where the company expanded and whether the new stores operate in the same environment as the legacy stores.\n\n"
                "• Distinguish between the off-the-shelf auto-parts business and the garage-service business.\n\n"
                "• Test whether both businesses have similar margins and whether pricing has changed.",
            ),
            block(
                "wheeler_dealer_expected_analysis_001",
                "expected_analysis",
                "Expected Analysis - Prompt #1",
                False,
                13,
                "Dig Deeper: Gather Facts / Make Calculations\n\n"
                "• Wheeler Dealer traditionally operated in or near suburban areas.\n\n"
                "• The new expansion went more heavily into inner-city areas because those locations were cheaper.\n\n"
                "• The company has two businesses under one roof: garage mechanical service and retail auto parts.\n\n"
                "• Garage services carry about twice the profit margin of the off-the-shelf retail business.\n\n"
                "• Inner-city locations attract more lower-income, do-it-yourself customers who buy parts but do not use the higher-margin service offering.\n\n"
                "• Prices did not increase to offset this shift in mix, so the business ended up with more low-margin sales and fewer high-margin ones.",
            ),
            block(
                "wheeler_dealer_key_findings_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                13,
                "Key findings:\n\n"
                "• Garage service is the real economic engine of the business.\n\n"
                "• The expansion attracted the wrong customer mix for Wheeler Dealer's model.\n\n"
                "• Off-the-shelf parts alone do not generate enough margin to support healthy returns.",
            ),
            block(
                "wheeler_dealer_final_recommendation_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                13,
                "Based on your analysis, what recommendation would you give the client?",
            ),
            block(
                "wheeler_dealer_guidance_003",
                "guidance",
                "Interviewer Guidance - Final Recommendation",
                False,
                13,
                "• Where appropriate, drop the garage-service component in underperforming areas and focus on the retail end of the business.\n\n"
                "• Scale back from urban areas that do not attract the profitable suburban service customer.\n\n"
                "• Re-focus future expansion on geographies that support the higher-margin service offering.",
            ),
        ]
    },
    "harvard_world_view_04_clean_raw.json": {
        "case_content": [
            block(
                "world_view_prompt_001",
                "prompt",
                "Prompt #1 - World View",
                True,
                8,
                "World View, a Canadian cable TV company, entered the US Northeast expecting to capture a large and weakly contested market. Despite that opportunity, the business has failed to make a profit. Determine why and advise management on the next move.\n\n"
                "• The addressable market was estimated at roughly 4 million consumers.\n\n"
                "• Direct cable competition is limited, yet the business still struggles to convert enough paying customers.",
            ),
            block(
                "world_view_guidance_001",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                8,
                "High Level Plan of Attack: determine why a seemingly attractive, low-competition market is not producing enough profitable demand.\n\n"
                "• Analyze both the revenue and cost sides of the problem.\n\n"
                "• Focus heavily on the consumer rather than assuming the issue is direct cable competition.\n\n"
                "• Compare viewing behavior and income levels in the US Northeast versus Canada.",
            ),
            block(
                "world_view_guidance_002",
                "guidance",
                "Interviewer Guidance - Prompt #1",
                False,
                8,
                "Lay out your thoughts.\n\n"
                "• Ask how many of the 4 million potential customers actually subscribed.\n\n"
                "• Test whether costs per customer are materially different in the new market.\n\n"
                "• Evaluate local TV stations and other substitutes.\n\n"
                "• Determine whether consumers see enough added value to pay for cable.",
            ),
            block(
                "world_view_expected_analysis_001",
                "expected_analysis",
                "Expected Analysis - Prompt #1",
                False,
                9,
                "Dig Deeper: Gather Facts / Make Calculations\n\n"
                "• Only about 2.1 million of the 4 million potential customers have signed up.\n\n"
                "• Costs per customer are not materially higher than expected; the problem is mainly on the demand side.\n\n"
                "• The Northeast has many local stations with strong reception that consumers can watch for free.\n\n"
                "• Consumers in the region are less willing to pay roughly $40 per month for cable when local TV already covers much of what they want.\n\n"
                "• World View does offer some differentiated programming, but consumers do not value it enough.\n\n"
                "• The average consumer in the Northeast watches regular TV more than cable compared with Canadian consumers, and average incomes are lower.",
            ),
            block(
                "world_view_key_findings_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                9,
                "Key findings:\n\n"
                "• The main competition is from substitutes such as free local TV, not from other cable players.\n\n"
                "• Management misread consumer willingness to pay and viewing habits in the new market.\n\n"
                "• A market that looks structurally open can still be unattractive if customers do not perceive enough value.",
            ),
            block(
                "world_view_final_recommendation_001",
                "final_recommendation",
                "Final Recommendation",
                True,
                9,
                "Based on your analysis, what recommendation would you give the client?",
            ),
            block(
                "world_view_guidance_003",
                "guidance",
                "Interviewer Guidance - Final Recommendation",
                False,
                9,
                "• Educate consumers on the additional value of the cable offering and consider a lower or more targeted price point.\n\n"
                "• Scale back operations to the regions where demand is strongest.\n\n"
                "• Consider offering a smaller package for customers who do not want a full cable bundle.\n\n"
                "• If these strategies fail, exit the market.",
            ),
        ]
    },
}


def main():
    for filename, payload in CASES.items():
        path = OUTPUT_DIR / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Rewrote {path}")


if __name__ == "__main__":
    main()
