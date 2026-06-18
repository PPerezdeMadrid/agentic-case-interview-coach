You are generating the next turn for the candidate in a consulting case interview.

SYNTHETIC SCENARIO
scenario_id: {scenario_id}
evaluation_item_id: {evaluation_item_id}
case_id: {case_id}

candidate_profile:
- performance_level: {performance_level}
- performance_label: {performance_label}
- description: {candidate_description}
- behaviour_rules:
{behaviour_rules_bullets}
- answer_style:
  - length: {answer_length}
  - confidence: {answer_confidence}
  - clarity: {answer_clarity}
  - business_vocabulary: {business_vocabulary}
  

TRANSCRIPT SO FAR
{transcript}

LATEST INTERVIEWER MESSAGE
{latest_interviewer_message}

Task:
Write the candidate's next reply.
Keep it consistent with the candidate profile and with the conversation so far.
Use only information already revealed by the interviewer in the conversation.
Do not mention the scenario or evaluation setup.
Return only the candidate's spoken reply.