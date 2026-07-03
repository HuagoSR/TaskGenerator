import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_motif_graph_grammar import MotifGraphGrammarBuilder  # noqa: E402


DEFAULT_OUTPUT_PATH = ROOT / "SkillRegistry" / "v3_motif_graph_grammar.experimental.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build deterministic experimental motif graph grammar records."
    )
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    builder = MotifGraphGrammarBuilder()
    artifact = builder.build()
    written_path = builder.write_output(artifact, args.output_path)
    print(
        json.dumps(
            {
                "output_path": written_path,
                "grammar_count": artifact.diagnostics.grammar_count,
                "motif_types": artifact.diagnostics.motif_types,
                "warning_codes": artifact.diagnostics.warning_codes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
