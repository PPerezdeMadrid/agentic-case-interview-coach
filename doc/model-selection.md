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

To ensure the system remains practical, reproducible, and cost-effective, the implementation now runs entirely on hosted or local inference instead of the HPC GPU allocation. As currently configured in `.env`:

* **Interviewer**: Qwen3-14B (OpenRouter, `qwen/qwen3-14b`)
* **Candidate**: Mistral-Small-24B-Instruct (OpenRouter, `mistralai/mistral-small-24b-instruct-2501`)
* **Judge**: Llama-3.3-70B-Instruct (OpenRouter, `meta-llama/llama-3.3-70b-instruct`)
* **Feedback**: GPT-4o-mini (OpenRouter, `openai/gpt-4o-mini`)


The GPU-hosted configuration (`localhost:18401`/`18402` via `server.bash` on the HPC cluster) is kept commented out in `llm_server.py` in case the project reverts to self-hosted inference; it still targets the smaller Mistral-Nemo/Llama-3.3-70B pair, since it remains constrained by the single-GPU allocation.

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
