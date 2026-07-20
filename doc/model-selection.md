# Model Selection

## Based on the papers
### Interviewer: Llama-3.1-70B

Source: LLM-as-an-interviewer: Beyond static testing through dynamic LLM evaluation (Kim et al., 2025, Section 4.1)

Best-performing open-source model for dynamic interview generation, providing question modification, constructive feedback, and follow-up question generation. Demonstrated robustness across reasoning and factuality tasks with multi-turn interactions.

### Candidate: Mixtral-8x7B-Instruct-v0.1

Source: A survey on LLM-as-a-judge (Gu et al., 2026, Model Selection section)

Mixture of Experts architecture recognized as top-performing open-source model. Architectural heterogeneity relative to other components reduces systematic evaluation biases and prevents model-to-model correlation artifacts.


### Judge: Qwen2-72B-Instruct

Source: A survey on LLM-as-a-judge (Gu et al., 2026, Results section)

The 72B variant provides sufficient computational capacity for sophisticated scoring, calibration analysis, and bias detection. Maintains the evaluation excellence demonstrated by the Qwen family while offering parameter scale comparable to other system components.


### Comparative Specification

| Model | Role | Architecture | Parameters | VRAM | Reference |
|-------|------|--------------|-----------|------|-----------|
| Llama-3.1-70B | Interviewer | Transformer | 70B | ~140GB | Kim et al. (2025) §4.1 |
| Mixtral-8x7B | Candidate | MoE | 46.7B | ~46GB | Gu et al. (2026) |
| Qwen2-72B | Judge | Transformer | 72B | ~144GB | Gu et al. (2026) |

## Computational Constraints
The project is being developed using computational resources provided by the University of St Andrews HPC cluster, where access is currently limited to a single GPU per job allocation. Running the 70B and 72B models locally would require substantially more GPU memory and computational resources than are available under this allocation, and job queue wait times made the GPU-hosted setup impractical for iterative experimentation.

To ensure the system remains practical, reproducible, and cost-effective, the implementation now runs entirely on hosted/local inference instead of the HPC GPU allocation:

* **Interviewer**: Qwen2.5-32B-Instruct (OpenRouter — `qwen/qwen-2.5-32b-instruct`)
* **Candidate**: Mixtral-8x7B-Instruct-v0.1 (OpenRouter — `mistralai/mixtral-8x7b-instruct`)
* **Judge**: Llama-3.1-70B-Instruct (OpenRouter — `meta-llama/llama-3.1-70b-instruct`)
* **Feedback**: local model served via LM Studio (`LMSTUDIO_MODEL`, currently `phi-4`)

This preserves architectural diversity between agent roles (transformer vs. MoE vs. dense variants across three different model families) while removing the dependency on HPC job scheduling. The judge keeps a full 70B-class model since it drives scoring/calibration, matching the reference literature's model choice for that role.

The interviewer and candidate were originally downsized further, to Qwen2.5-7B-Instruct and Mistral-Nemo-Instruct (12B), purely to fit the single-GPU HPC allocation described above. Both have since been raised back up within the same model family now that inference runs on OpenRouter rather than the HPC cluster:

* The candidate move to Mixtral-8x7B-Instruct-v0.1 restores the original Gu et al. (2026) choice for that role (see above) rather than being a new selection.
* The interviewer move to Qwen2.5-32B-Instruct is a middle-ground scale-up: large enough to give richer question generation and follow-ups than the 7B variant, while staying a different family from the Llama-3.1-70B judge to preserve architectural diversity. Nguyen et al. (2025, SimInterview) is a relevant data point here but cuts the other way — they report that a smaller model (Gemma 3) produced *more* engaging interviewer conversations than larger alternatives (OpenAI o3, Llama 4 Maverick) in their setup, so parameter count alone is not assumed to track interview quality; the upgrade here is motivated by compute headroom rather than a claim that bigger strictly means better. EZInterviewer (Li et al., 2023) similarly does not mandate a specific interviewer scale, but its retrieval-augmented mock-interview generator is consistent with keeping the interviewer role on a moderately sized, low-latency model rather than the largest available one.

The GPU-hosted configuration (`localhost:18401`/`18402` via `server.bash` on the HPC cluster) is kept commented out in `llm_server.py` in case the project reverts to self-hosted inference; it still targets the smaller Mistral-Nemo/Llama-3.3-70B pair since it remains constrained by the single-GPU allocation.

See `src/main/studio/llm_server.py` for the concrete `ChatOpenAI` wiring and `.env` for the `OPENROUTER_MODEL_INTERVIEWER` / `OPENROUTER_MODEL_CANDIDATE` / `OPENROUTER_MODEL_JUDGE` / `LMSTUDIO_MODEL` variables that control these role assignments.


## References

```bibtex
@misc{kim2025interviewer,
  author = {Kim, Eunsu and Suk, Juyoung and Kim, Seungone and Muennighoff, Niklas and Kim, Dongkwan and Oh, Alice},
  title = {LLM-as-an-interviewer: Beyond static testing through dynamic LLM evaluation},
  year = {2025},
  booktitle = {Findings of the Association for Computational Linguistics: ACL 2025}
}

@misc{li2023ezinterviewer,
  author = {Li, Mingzhe and Chen, Xiuying and Liao, Weiheng and Song, Yang and Zhang, Tao and Zhao, Dongyan and Yan, Rui},
  title = {EZInterviewer: To improve job interview performance with mock interview generator},
  year = {2023},
  eprint = {2301.00972},
  archivePrefix = {arXiv}
}

@misc{nguyen2025siminterview,
  author = {Nguyen, Hung Truong Thanh and Nguyen, Tran Diem Quynh and Cao, Hoang Loc},
  title = {SimInterview: Transforming business education through large language model-based simulated multilingual interview training system},
  year = {2025},
  eprint = {2508.11873},
  archivePrefix = {arXiv}
}

@article{gu2026judge,
  author = {Gu, Jiawei and others},
  title = {A survey on LLM-as-a-judge},
  year = {2026},
  journal = {Computers and Electrical Engineering},
  doi = {10.1016/j.compeleceng.2025.110456}
}
```

