"""
Batch Runner for Sequential Wikipedia Translation Pipeline.

Purpose:
- Executes sequential translation of multiple articles from a text file queue with safe rate-limit pacing.
- Reads a file containing article titles (one per line, ignoring empty lines and `#` comments).
- Option for custom pause interval (default: 3 seconds between articles).
- Executes translation pipeline for each title.
- Tracks summary statistics: total articles, succeeded, failed, total tokens saved, total elapsed time.
- Generates batch completion report dict.
"""

from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, Union

from .token_saver import default_tracker, TokenTracker


@dataclass
class ArticleBatchItemResult:
    """Result of an individual article translation inside a batch run."""
    title: str
    success: bool
    elapsed_seconds: float = 0.0
    tokens_saved: int = 0
    error: Optional[str] = None
    output_files: Dict[str, str] = field(default_factory=dict)


@dataclass
class BatchReport:
    """Summary report of a batch execution."""
    total_articles: int
    succeeded: int
    failed: int
    total_tokens_saved: int
    total_elapsed_seconds: float
    items: List[ArticleBatchItemResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_articles": self.total_articles,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "total_tokens_saved": self.total_tokens_saved,
            "total_elapsed_seconds": round(self.total_elapsed_seconds, 2),
            "items": [
                {
                    "title": it.title,
                    "success": it.success,
                    "elapsed_seconds": round(it.elapsed_seconds, 2),
                    "tokens_saved": it.tokens_saved,
                    "error": it.error,
                    "output_files": it.output_files,
                }
                for it in self.items
            ],
        }


class BatchRunner:
    """Orchestrates batch queue reading and sequential translation execution."""

    def __init__(
        self,
        pause_interval: float = 3.0,
        token_tracker: Optional[TokenTracker] = None,
    ):
        self.pause_interval = pause_interval
        self.token_tracker = token_tracker or default_tracker

    @staticmethod
    def parse_queue_file(queue_file_path: Union[str, Path]) -> List[str]:
        """
        Reads a queue text file containing article titles:
        - One per line
        - Ignores blank / empty lines
        - Ignores lines starting with '#' comments
        """
        path = Path(queue_file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Queue file not found: {path}")

        titles: List[str] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                titles.append(stripped)
        return titles

    def run_batch_from_file(
        self,
        queue_file_path: Union[str, Path],
        translate_fn: Callable[[str], Dict[str, Any]],
        pause_interval: Optional[float] = None,
        on_progress: Optional[Callable[[int, int, str, ArticleBatchItemResult], None]] = None,
    ) -> BatchReport:
        """Convenience method to execute batch translation from a text file queue."""
        return self.run_batch(
            queue=queue_file_path,
            translate_fn=translate_fn,
            pause_interval=pause_interval,
            on_progress=on_progress,
        )

    def run_batch(
        self,
        queue: Union[str, Path, List[str]],
        translate_fn: Callable[[str], Dict[str, Any]],
        pause_interval: Optional[float] = None,
        on_progress: Optional[Callable[[int, int, str, ArticleBatchItemResult], None]] = None,
    ) -> BatchReport:
        """
        Executes sequential translation over a list of titles or from a queue file.

        Args:
            queue: Either a Path/str to a queue file or a list of article titles.
            translate_fn: A callable taking `title: str` and returning a dict with keys
                          such as `{"success": bool, "error": str, "tokens_saved": int, "output_files": dict}`.
            pause_interval: Optional override for pause duration (in seconds) between articles.
            on_progress: Optional callback invoked after each article: `callback(index, total, title, item_result)`.

        Returns:
            BatchReport containing comprehensive statistics.
        """
        if isinstance(queue, (str, Path)):
            titles = self.parse_queue_file(queue)
        else:
            # List of titles provided directly
            titles = [t.strip() for t in queue if t.strip() and not t.strip().startswith("#")]

        interval = self.pause_interval if pause_interval is None else pause_interval

        total = len(titles)
        item_results: List[ArticleBatchItemResult] = []
        succeeded_count = 0
        failed_count = 0
        total_tokens_saved = 0

        start_time_all = time.perf_counter()

        for idx, title in enumerate(titles, start=1):
            start_item = time.perf_counter()
            err_msg: Optional[str] = None
            success = False
            item_tokens_saved = 0
            output_files: Dict[str, str] = {}

            # Record tracker tokens before run
            tokens_before = getattr(self.token_tracker, "total_saved_tokens", 0)

            try:
                fn_result = translate_fn(title)
                if isinstance(fn_result, dict):
                    # A batch callback must explicitly report its outcome.  Treating a
                    # missing flag as success hides cancelled/partial CLI runs.
                    if "success" not in fn_result:
                        success = False
                        err_msg = "translate_fn returned no explicit success status"
                    else:
                        success = bool(fn_result["success"])
                        err_msg = fn_result.get("error")
                    raw_output_files = fn_result.get("output_files", {})
                    output_files = raw_output_files if isinstance(raw_output_files, dict) else {}
                    # If translate_fn provided tokens_saved explicitly, use it
                    if "tokens_saved" in fn_result:
                        item_tokens_saved = int(fn_result["tokens_saved"])
                    else:
                        tokens_after = getattr(self.token_tracker, "total_saved_tokens", 0)
                        item_tokens_saved = max(0, tokens_after - tokens_before)
                else:
                    success = False
                    err_msg = "translate_fn must return a result dictionary"
            except Exception as exc:
                success = False
                err_msg = str(exc)

            elapsed_item = time.perf_counter() - start_item

            if success:
                succeeded_count += 1
            else:
                failed_count += 1

            total_tokens_saved += item_tokens_saved

            item_res = ArticleBatchItemResult(
                title=title,
                success=success,
                elapsed_seconds=elapsed_item,
                tokens_saved=item_tokens_saved,
                error=err_msg,
                output_files=output_files,
            )
            item_results.append(item_res)

            if on_progress:
                try:
                    on_progress(idx, total, title, item_res)
                except Exception:
                    pass

            # Safe rate-limit pause between articles (except after the final article)
            if idx < total and interval > 0:
                time.sleep(interval)

        total_elapsed = time.perf_counter() - start_time_all

        report = BatchReport(
            total_articles=total,
            succeeded=succeeded_count,
            failed=failed_count,
            total_tokens_saved=total_tokens_saved,
            total_elapsed_seconds=total_elapsed,
            items=item_results,
        )
        return report


default_batch_runner = BatchRunner()
