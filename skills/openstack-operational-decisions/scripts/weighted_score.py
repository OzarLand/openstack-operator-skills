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
TIE_TOLERANCE = 1e-9  # score differences below this are float noise, i.e. a tie


def is_number(value):
    # bool is a subclass of int in Python; true/false are not scores or weights
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        sys.exit("error: the top level must be an object with 'weights' and 'options'")
    weights = data.get("weights")
    options = data.get("options")
    if not isinstance(weights, dict) or not weights:
        sys.exit("error: 'weights' must be a non-empty object of dimension -> weight")
    if not isinstance(options, dict) or len(options) < 1:
        sys.exit("error: 'options' must be a non-empty object of option -> scores")
    for dim, w in weights.items():
        if not is_number(w) or w < 0:
            sys.exit(f"error: weight for '{dim}' must be a number >= 0, got {w!r}")
    total = sum(weights.values())
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        sys.exit(f"error: weights sum to {total:.4f}, expected 1.0")
    for name, scores in options.items():
        if not isinstance(scores, dict):
            sys.exit(f"error: option '{name}' must be an object of dimension -> score")
        missing = set(weights) - set(scores)
        extra = set(scores) - set(weights)
        if missing:
            sys.exit(f"error: option '{name}' has no score for: {', '.join(sorted(missing))}")
        if extra:
            sys.exit(f"error: option '{name}' scores unknown dimensions: {', '.join(sorted(extra))}")
        for dim, s in scores.items():
            if not is_number(s) or not SCALE[0] <= s <= SCALE[1]:
                sys.exit(f"error: option '{name}' dimension '{dim}' score {s!r} outside {SCALE[0]}..{SCALE[1]}")
    return weights, options


def score(weights, scores):
    return sum(weights[d] * scores[d] for d in weights)


def flips(weights, upper, lower, s_upper, s_lower):
    """Single-score changes that would make `lower` rank at or above `upper`."""
    gap = score(weights, s_upper) - score(weights, s_lower)
    found = []
    if gap < TIE_TOLERANCE:
        return gap, None  # tied: any change to a weighted dimension separates them
    for dim, w in weights.items():
        if w == 0:
            continue  # a zero-weight dimension cannot change the ranking
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
        if found is None:
            print("    - tied: any change to a weighted dimension separates them")
        elif found:
            for f in found:
                print(f"    - {f}")
        else:
            print("    - no single change of 1 or 2 points flips this pair")
    print("\nReminder: scores only compare options that passed every gate.")


if __name__ == "__main__":
    main()
