"""Command-Line Interface for PerturbMat-Agent."""

import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.evaluation.benchmark_runner import PerturbMatBenchmarkRunner
from src.ingestion.pdf_extractor import PDFPaperIngestor, SI_PATTERNS


def main():
    parser = argparse.ArgumentParser(
        description="PerturbMat-Agent: Literature Gap Analyzer & Counterfactual Experiment Predictor"
    )
    parser.add_argument(
        "--mode",
        choices=["status", "run-ablation", "predict-custom"],
        default="status",
        help="Action to execute: 'status' checks uploaded PDFs, 'run-ablation' runs the full Gap + Held-Out Prediction benchmark, 'predict-custom' answers a custom perturbation query.",
    )
    parser.add_argument(
        "--model",
        default="gemini-3.8-flash",
        help="Gemini model to use (default: gemini-3.8-flash; or gemini-3.1-pro-preview)",
    )
    parser.add_argument(
        "--max-snowball",
        type=int,
        default=10,
        help="Maximum number of missing foundational/mechanistic papers to fetch via OpenAlex/EuropePMC snowballing",
    )
    parser.add_argument(
        "--baseline-protocol",
        type=str,
        default="Standard seed-mediated gold nanobipyramid synthesis in CTAB (100 mM), HAuCl4 (0.5 mM), AgNO3 (0.08 mM), HCl, ascorbic acid, and pentatwinned gold seeds at 30 °C.",
        help="Baseline protocol for --mode predict-custom",
    )
    parser.add_argument(
        "--question",
        type=str,
        default=None,
        help="Custom perturbation question for --mode predict-custom (e.g., 'What happens to gold bipyramid volume and aspect ratio when [AgNO3] or [HCl] is increased?')",
    )

    args = parser.parse_args()
    console = Console()
    root = Path(__file__).resolve().parents[1]
    seed_dir = root / "data" / "seed_papers"
    held_out_dir = root / "data" / "held_out_papers"

    paired_seeds = PDFPaperIngestor.pair_main_and_si_pdfs(seed_dir)
    held_out_pdfs = [
        p for p in sorted(held_out_dir.glob("*.pdf")) if not SI_PATTERNS.search(p.stem)
    ]

    if args.mode == "status":
        table = Table(title="PerturbMat-Agent Dataset Status")
        table.add_column("Folder", style="cyan")
        table.add_column("Detected Main PDFs", style="green")
        table.add_column("Paired SI PDFs", style="yellow")

        for m_pdf, si_list in paired_seeds:
            table.add_row(
                "data/seed_papers/",
                m_pdf.name,
                ", ".join(p.name for p in si_list) if si_list else "(none)",
            )
        if not paired_seeds:
            table.add_row("data/seed_papers/", "[red]No PDFs uploaded yet[/red]", "-")

        for h_pdf in held_out_pdfs:
            table.add_row("data/held_out_papers/", h_pdf.name, "Auto-detected on run")
        if not held_out_pdfs:
            table.add_row("data/held_out_papers/", "[red]No held-out PDFs uploaded yet[/red]", "-")

        console.print(table)
        console.print(
            Panel(
                "1. Drop your 9–20 seed papers into [bold cyan]data/seed_papers/[/bold cyan] and their SIs into [bold cyan]data/seed_papers/supplementary_info/[/bold cyan].\n"
                "2. Drop your held-out test paper into [bold cyan]data/held_out_papers/[/bold cyan].\n"
                "3. Run [bold green]uv run python -m src.cli --mode run-ablation[/bold green] to run the full Gap + Prediction Ablation Study!",
                title="Next Steps",
            )
        )
        return

    runner = PerturbMatBenchmarkRunner(workspace_root=root, model_name=args.model)

    if args.mode == "run-ablation":
        console.print("[bold cyan]Running Full PerturbMat-Agent Ablation Study...[/bold cyan]")
        results = runner.run_full_ablation_study(max_snowball_papers=args.max_snowball)
        console.print(
            f"[bold green]Done![/bold green] Full report written to: [underline]{root / 'outputs' / 'ablation_report.md'}[/underline]"
        )
        console.print(f"Total papers in KB: {results['num_seed_and_expanded_papers']} | CMO Edges: {results['num_cmo_edges']}")

    elif args.mode == "predict-custom":
        if not args.question:
            console.print("[bold red]Please provide --question '...' when using --mode predict-custom[/bold red]")
            return
        held_out_cases = runner.prepare_held_out_cases()
        kb, snowball = runner.build_knowledge_base(
            held_out_cases=held_out_cases,
            enable_snowball_expansion=True,
            max_snowball_papers=args.max_snowball,
        )
        from src.agents.experiment_predictor import ExperimentPredictorEngine

        predictor = ExperimentPredictorEngine(runner.llm, kb, snowball)
        pred, cycle, search_logs = predictor.predict_with_mechanistic_cross_questioning(
            args.baseline_protocol, args.question
        )
        console.print(Panel(pred.primary_prediction_summary, title="Final Calibrated Prediction"))
        console.print("[bold yellow]Cross-Questioning Challenges Raised:[/bold yellow]")
        for ch in cycle.challenges:
            console.print(f"- [{ch.failure_mode_targeted}] {ch.sharp_question}")


if __name__ == "__main__":
    main()
