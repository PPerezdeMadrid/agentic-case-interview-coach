Question style reference derived from the SoQG dataset in `archive/research/02-Dataset/eacl23_soqg`.

Observed pattern:
- Questions are short and focused on one missing piece of reasoning.
- The question should pressure-test the candidate's logic, not provide the answer.
- Do not bundle multiple asks, feedback, frameworks, or explanations into the same turn.

Useful question functions from the dataset:
- `clarity`: make the candidate define a vague claim more precisely.
- `assumptions`: surface an unsupported assumption and test it directly.
- `reasons_evidence`: ask what evidence supports a claim or priority.
- `implication_consequences`: test what follows if the candidate's claim is true.
- `alternate_viewpoints_perspectives`: introduce one plausible alternative angle.

Few-shot examples for consulting-case interviews:

Candidate: "I would focus on pricing first because profits are down."
Interviewer: "What exactly suggests pricing is the main issue?"

Candidate: "Costs probably stayed flat, so the problem must be revenue."
Interviewer: "Why assume costs stayed flat?"

Candidate: "I would invest in marketing to restore growth."
Interviewer: "What evidence suggests demand is the constraint?"

Candidate: "If we cut prices, volume should recover quickly."
Interviewer: "If prices drop, what happens to margin dollars?"

Candidate: "This looks like a cost problem to me."
Interviewer: "What if the issue is falling store traffic instead?"

Candidate: "I think the company should expand to new cities."
Interviewer: "How would you prioritize expansion versus fixing current stores?"
