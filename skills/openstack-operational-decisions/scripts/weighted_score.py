#!/usr/bin/env python3
"""Weighted decision model from 'OpenStack, the Day After Tomorrow' (App. A, Ch. 18).

Computes option scores and a simple sensitivity analysis: which single score
change (by 1 or 2 points, staying within 1..5) would flip the order of two
adjacent options. The model is a conversation tool; it never overrides a gate.

Usage: python3 weighted_score.py options.json
"""

import json
import sys

SCALE = (1, 5)
WEIGHT_TOLERANCE = 1e-6  # weights should sum to 1; allow float rounding


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    weights = data.get("weights")
    options = data.get("options")
    if not isinstance(weights, dict) or not weights:
        sys.exit("error: 'weights' must be a non-empty object of dimension -> weight")
    if not isinstance(options, dict) or len(options) < 1:
        sys.exit("error: 'options' must be a non-empty object of option -> scores")
    total = sum(weights.values())
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        sys.exit(f"error: weights sum to {total:.4f}, expected 1.0")
    for name, scores in options.items():
        missing = set(weights) - set(scores)
        extra = set(scores) - set(weights)
        if missing:
            sys.exit(f"error: option '{name}' has no score for: {', '.join(sorted(missing))}")
        if extra:
            sys.exit(f"error: option '{name}' scores unknown dimensions: {', '.join(sorted(extra))}")
        for dim, s in scores.items():
            if not isinstance(s, (int, float)) or not SCALE[0] <= s <= SCALE[1]:
                sys.exit(f"error: option '{name}' dimension '{dim}' score {s!r} outside {SCALE[0]}..{SCALE[1]}")
    return weights, options


def score(weights, scores):
    return sum(weights[d] * scores[d] for d in weights)


def flips(weights, upper, lower, s_upper, s_lower):
    """Single-score changes that would make `lower` rank at or above `upper`."""
    gap = score(weights, s_upper) - score(weights, s_lower)
    found = []
    for dim, w in weights.items():
        # report only the smallest sufficient change per dimension and direction
        for delta in (1, 2):
            if s_lower[dim] + delta <= SCALE[1] and w * delta >= gap - 1e-9:
                found.append(f"{lower}.{dim} +{delta} ({s_lower[dim]}->{s_lower[dim] + delta})")
                break
        for delta in (1, 2):
            if s_upper[dim] - delta >= SCALE[0] and w * delta >= gap - 1e-9:
                found.append(f"{upper}.{dim} -{delta} ({s_upper[dim]}->{s_upper[dim] - delta})")
                break
    return gap, found


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    weights, options = load(sys.argv[1])
    ranked = sorted(options, key=lambda o: score(weights, options[o]), reverse=True)

    print("Scores (5 = preferable on every dimension):")
    for name in ranked:
        print(f"  {name:<30} {score(weights, options[name]):.2f}")

    print("\nSensitivity (single-score changes that would flip adjacent options):")
    for upper, lower in zip(ranked, ranked[1:]):
        gap, found = flips(weights, upper, lower, options[upper], options[lower])
        print(f"  {upper} vs {lower}: gap {gap:.2f}")
        if found:
            for f in found:
                print(f"    - {f}")
        else:
            print("    - no single change of 1 or 2 points flips this pair")
    print("\nReminder: scores only compare options that passed every gate.")


if __name__ == "__main__":
    main()
