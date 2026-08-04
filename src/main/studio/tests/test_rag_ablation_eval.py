import sys
import unittest
from pathlib import Path


STUDIO_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = STUDIO_DIR.parents[1]
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    import rag_ablation_eval
except ModuleNotFoundError as exc:
    raise unittest.SkipTest(f"Studio test dependencies are not installed: {exc.name}") from exc


class RagAblationEvalTests(unittest.TestCase):
    def test_transcript_before_eval_drops_post_eval_lines(self) -> None:
        record = {
            "transcript": [
                "Interviewer: Walk me through your approach.",
                "Candidate: I would split revenue and cost.",
                "Eval Case Performance: structured case-performance assessment completed.",
                "Eval Dialog Quality: structured interaction-quality assessment completed.",
                "Give Feedback: Nice structure.",
            ]
        }

        self.assertEqual(
            rag_ablation_eval._transcript_before_eval(record),
            [
                "Interviewer: Walk me through your approach.",
                "Candidate: I would split revenue and cost.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
