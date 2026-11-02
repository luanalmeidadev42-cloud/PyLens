"""A small, bounded CPU workload for trying the PyLens executor."""

import argparse
from time import monotonic


def main() -> None:
    """### O que faz
    Lê a duração solicitada e executa uma carga de CPU limitada a 15 segundos.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seconds",
        type=float,
        default=2.0,
        help="how long to run the CPU workload (default: 2, maximum: 15)",
    )
    args = parser.parse_args()

    if not 0 < args.seconds <= 15:
        parser.error("--seconds must be greater than 0 and at most 15")

    deadline = monotonic() + args.seconds
    value = 0
    iterations = 0

    while monotonic() < deadline:
        value = (value * 1664525 + 1013904223) & 0xFFFFFFFF
        iterations += 1

    print(f"Completed {iterations:,} iterations; checksum: {value}")


if __name__ == "__main__":
    main()
