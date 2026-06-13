"""
spider_eval.py — Lightweight benchmark runner using curated NL-to-SQL test queries
against the local ecommerce DB (mirrors Spider dataset style).
"""
import sys
import os
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent  import run_agent
from logger import CorrectionLogger

# ── Hand-crafted benchmark queries (ecommerce domain) ────────────────────────
BENCHMARK_QUERIES = [
    # Simple SELECTs
    {"id": 1,  "question": "List all users from New York", "difficulty": "easy"},
    {"id": 2,  "question": "Show all products in the Electronics category", "difficulty": "easy"},
    {"id": 3,  "question": "How many orders are there in total?", "difficulty": "easy"},
    {"id": 4,  "question": "What is the average product price?", "difficulty": "easy"},
    {"id": 5,  "question": "Show the 5 most expensive products", "difficulty": "easy"},
    # Aggregations
    {"id": 6,  "question": "What is the total revenue from all delivered orders?", "difficulty": "medium"},
    {"id": 7,  "question": "How many orders does each user have? Show top 10.", "difficulty": "medium"},
    {"id": 8,  "question": "What is the average rating per product?", "difficulty": "medium"},
    {"id": 9,  "question": "Which product category has the highest total revenue?", "difficulty": "medium"},
    {"id": 10, "question": "How many products are in each category?", "difficulty": "medium"},
    # JOINs
    {"id": 11, "question": "Show order details with customer names for the 5 most recent orders", "difficulty": "medium"},
    {"id": 12, "question": "List products that have never been reviewed", "difficulty": "medium"},
    {"id": 13, "question": "Show users who have placed more than 5 orders", "difficulty": "hard"},
    {"id": 14, "question": "What are the top 5 customers by total spending?", "difficulty": "hard"},
    {"id": 15, "question": "Which products have an average rating above 4?", "difficulty": "hard"},
    # Complex
    {"id": 16, "question": "Show monthly revenue for 2024", "difficulty": "hard"},
    {"id": 17, "question": "Find users who bought Electronics but never bought Books", "difficulty": "hard"},
    {"id": 18, "question": "What is the cancellation rate by product category?", "difficulty": "hard"},
    {"id": 19, "question": "Show the top 3 most reviewed products with their average rating", "difficulty": "hard"},
    {"id": 20, "question": "Find the customer who has spent the most money overall", "difficulty": "hard"},
]


def run_benchmark(
    model: str = "gpt-3.5-turbo",
    max_queries: int = 20,
    verbose: bool = True,
) -> dict:
    """Run the benchmark and return aggregated metrics."""
    logger  = CorrectionLogger()
    results = []
    queries = BENCHMARK_QUERIES[:max_queries]

    print(f"\n{'='*65}")
    print(f"  SQL Agent Benchmark — {len(queries)} queries — model: {model}")
    print(f"{'='*65}\n")

    for q in queries:
        qid  = q["id"]
        text = q["question"]
        diff = q["difficulty"]

        if verbose:
            print(f"[{qid:02d}/{len(queries)}] ({diff.upper():6s}) {text}")

        try:
            res = run_agent(text, model=model, logger=logger)
            status = "✓" if res["success"] else "✗"
            n_att  = len(res["attempts"])
            if verbose:
                print(f"       {status}  {n_att} attempt(s) | {res['total_time_ms']:.0f}ms\n")

            results.append({
                "id":            qid,
                "question":      text,
                "difficulty":    diff,
                "success":       res["success"],
                "attempts":      n_att,
                "first_try":     res["success"] and n_att == 1,
                "time_ms":       res["total_time_ms"],
            })
        except Exception as exc:
            if verbose:
                print(f"       ERROR: {exc}\n")
            results.append({
                "id": qid, "question": text, "difficulty": diff,
                "success": False, "attempts": 0, "first_try": False, "time_ms": 0,
            })

    # ── Aggregate metrics ─────────────────────────────────────────────────────
    total      = len(results)
    succeeded  = sum(1 for r in results if r["success"])
    first_tries= sum(1 for r in results if r["first_try"])
    avg_att    = sum(r["attempts"] for r in results) / total if total else 0
    avg_time   = sum(r["time_ms"]  for r in results) / total if total else 0

    by_diff = {}
    for diff in ["easy", "medium", "hard"]:
        subset   = [r for r in results if r["difficulty"] == diff]
        if subset:
            by_diff[diff] = round(sum(1 for r in subset if r["success"]) / len(subset) * 100, 1)

    metrics = {
        "total":              total,
        "success_count":      succeeded,
        "success_rate":       round(succeeded / total * 100, 1) if total else 0,
        "first_try_rate":     round(first_tries / total * 100, 1) if total else 0,
        "avg_attempts":       round(avg_att, 2),
        "avg_time_ms":        round(avg_time, 1),
        "success_by_difficulty": by_diff,
        "results":            results,
    }

    print(f"\n{'='*65}")
    print(f"  RESULTS")
    print(f"  Final success rate : {metrics['success_rate']}%  (target >87%)")
    print(f"  First-try rate     : {metrics['first_try_rate']}%  (target >60%)")
    print(f"  Avg attempts       : {metrics['avg_attempts']}     (target <1.5)")
    print(f"  Avg latency        : {metrics['avg_time_ms']}ms")
    print(f"  By difficulty      : {by_diff}")
    print(f"{'='*65}\n")

    return metrics


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SQL Agent Benchmark")
    parser.add_argument("--model",  default="gpt-3.5-turbo")
    parser.add_argument("--n",      type=int, default=20)
    args = parser.parse_args()
    run_benchmark(model=args.model, max_queries=args.n)
