# Agentic Case Interview Coach

This project explores the use of agentic AI to support consulting case interview practice.

The system is designed as a multi-agent architecture where an Interviewer Agent conducts a case interview, a Judge Agent evaluates the candidate's reasoning using a structured rubric, and a Feedback Agent generates personalised coaching based on the interview transcript and case knowledge.

The project focuses on reducing the dependency on large labelled datasets by using consulting casebooks, retrieval-augmented generation, and structured evaluation criteria. The goal is not to replace human coaching, but to provide an accessible tool that can help students practise case interviews and receive more consistent feedback.

## Main Features

- Case interview simulation through an LLM-based interviewer
- Follow-up questioning based on the candidate's answers
- Rubric-based evaluation of the interview transcript
- Retrieval-augmented feedback using consulting frameworks and casebook material
- Multi-agent orchestration using LangGraph

## Repository Structure

- `src/main`: active MVP implementation
- `src/scenarios`: interview scenarios and rubric configuration
- `src/synthetic-dataset`: synthetic case material used by the active MVP
- `src/database`: structured case database in JSON
- `src/schemas`: shared JSON schemas
- `doc/`: project documentation and diagrams
- `archive/`: legacy code and research material kept out of the active project structure
