# Eval

## Case performance

Rubric-based

The case-performance component evaluates the quality of the candidate's case-solving output, focusing on how well they open the case, structure the problem, handle any math or creative task, and deliver a final recommendation.
It is assessed through the rubric dimensions `case_opening`, `case_structure`, `case_math_answer`, `case_creative_answer`, `final_recommendation`, `overall_structure`, `overall_problem_solving`, and `overall_communication`.

## Dialogue Quality
The interaction-quality component is informed by ACUTE-Eval, which argues that dialogue evaluation should consider complete multi-turn conversations rather than isolated single-turn responses. Following this idea, the proposed rubric evaluates the candidate as a specific participant in the interview dialogue, focusing on whether their communication remains clear, responsive, grounded, calibrated, and coherent across the interaction.

https://arxiv.org/abs/1909.03087

| Dimension | What it evaluates |
|---|---|
| `clarity_and_concision` | Whether the candidate explains ideas clearly, avoids unnecessary repetition, and keeps answers focused without losing important reasoning. |
| `responsiveness_and_adaptation` | Whether the candidate answers the interviewer’s prompt directly, incorporates new information, and adjusts their reasoning when guided or challenged. |
| `groundedness` | Whether the candidate avoids inventing facts, numbers, or external context, and keeps assumptions explicit and tied to the information provided in the case. |
| `confidence_calibration` | Whether the candidate expresses conclusions with appropriate confidence, acknowledges uncertainty, and avoids overclaiming beyond the available evidence. |
| `multi_turn_coherence` | Whether the candidate maintains a logically connected reasoning thread across the whole interview, rather than producing disconnected answers. |

### `clarity_and_concision`

| Score | Description |
|---|---|
| `1` | The candidate is hard to follow, rambling, repetitive, or consistently inefficient in how they communicate ideas. |
| `2` | The candidate is understandable but uneven, with some unnecessary verbosity, repetition, or loosely expressed reasoning. |
| `3` | The candidate is generally clear and concise, with only minor inefficiencies or occasional repetition that do not materially reduce understanding. |
| `4` | The candidate is consistently clear, crisp, and efficient, communicating enough reasoning to be useful without wasting words. |

### `responsiveness_and_adaptation`

| Score | Description |
|---|---|
| `1` | The candidate often misses the interviewer’s question, ignores cues, or continues on the wrong path even after being redirected. |
| `2` | The candidate responds to some prompts appropriately but is slow or inconsistent in incorporating guidance or new information. |
| `3` | The candidate usually answers the actual question and adapts reasonably well when new facts or redirection are introduced. |
| `4` | The candidate directly addresses prompts, integrates new information quickly, and adjusts their reasoning smoothly when guided or challenged. |

### `groundedness`

| Score | Description |
|---|---|
| `1` | The candidate frequently invents facts, numbers, or business context, or makes unsupported claims without signaling them as assumptions. |
| `2` | The candidate is partly grounded in the case but occasionally introduces weakly supported assumptions or stretches beyond the evidence. |
| `3` | The candidate is mostly grounded in the case, with assumptions kept limited and usually signposted. |
| `4` | The candidate stays tightly anchored to the case materials, avoids invented details, and makes any necessary assumptions explicit and controlled. |

### `confidence_calibration`

| Score | Description |
|---|---|
| `1` | The candidate is badly calibrated, either overstating weak conclusions or showing uncertainty even when the evidence is clear. |
| `2` | The candidate shows mixed calibration, with some reasonable judgment but noticeable overclaiming or hesitation at key moments. |
| `3` | The candidate is generally well calibrated, with confidence that usually matches the available evidence. |
| `4` | The candidate is consistently well calibrated, expressing strong conclusions when supported and explicitly acknowledging uncertainty when the evidence is incomplete. |

### `multi_turn_coherence`

| Score | Description |
|---|---|
| `1` | The conversation feels fragmented; answers are disconnected, internally inconsistent, or fail to build on earlier reasoning. |
| `2` | The candidate shows some continuity, but the overall reasoning thread is uneven, partially disconnected, or weakly integrated across turns. |
| `3` | The candidate maintains a mostly coherent line of reasoning across the interview, with only minor breaks or rough transitions. |
| `4` | The candidate maintains a strong, logically connected reasoning thread across the full interaction, with each turn building naturally on the previous ones. |
