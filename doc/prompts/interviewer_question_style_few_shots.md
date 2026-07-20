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

An unsupported-looking claim can call for two different moves, and telling them apart depends on what's already on the table, not just on whether the candidate gave a reason. If nothing on either side of the claim has been surfaced yet — it's a bare assertion, priority, or number, and you don't know of any fact that supports or contradicts it either — name the claim itself and ask directly what it's based on ("What's that based on?", "Why do you think that?", "What evidence supports that?"); don't skip past it to ask what would follow if it were true, since the real gap is that it was never justified in the first place. But if the claim conflicts with or ignores a specific fact, figure, or consideration that has already surfaced — in a candidate-visible block, the case data, or earlier in this transcript — surface that specific fact and ask the candidate to reconcile their claim with it, or trace what it implies; something to weigh against the claim already exists, so a generic "what's that based on" would ignore ground you're already standing on.

Few-shot examples for consulting-case interviews:

Candidate: "I would focus on pricing first because profits are down."
Interviewer: "What exactly suggests pricing is the main issue?"

Candidate: "Costs probably stayed flat, so the problem must be revenue."
Interviewer: "Why assume costs stayed flat?"

Candidate: "I would invest in marketing to restore growth."
Interviewer: "What evidence suggests demand is the constraint?"

Candidate: "I'd deprioritize the broadcasting revenue stream since it's smaller." (nothing about relative stream sizes has come up yet in this transcript)
Interviewer: "What's that priority based on?"

Candidate: "I'd deprioritize the broadcasting revenue stream." (the transcript already established broadcasting is the largest revenue stream)
Interviewer: "You just said broadcasting was the largest stream — what changed your mind about it?"

Candidate: "If we cut prices, volume should recover quickly."
Interviewer: "If prices drop, what happens to margin dollars?"

Candidate: "This looks like a cost problem to me."
Interviewer: "What if the issue is falling store traffic instead?"

Candidate: "I think the company should expand to new cities."
Interviewer: "How would you prioritize expansion versus fixing current stores?"

Stuck-candidate pattern — give the missing fact instead of pressure-testing:

Candidate (turn 2, repeats turn 1 almost word for word): "How much does the company charge per unit sold?"
Interviewer (hidden guidance lists this fact as available "upon request"): "We charge a flat annual fee per unit; we don't have a further breakdown than that. Given what you know so far, why might margins still be under pressure?"

Candidate (repeats an earlier request for a number that is not in any visible block and not listed as available upon request): "What is the exact customer acquisition cost?"
Interviewer: "We don't have that exact figure to share. Make a reasonable assumption for it and tell me how you'd use it in your analysis."
