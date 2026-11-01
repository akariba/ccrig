"""Read-only validation harness for CCRIG's analytical outputs.

Nothing in this package is imported by the application (`app/`), and it is
not vendored into the static Pyodide build. It exists to (a) measure how the
current relationship ranking behaves against independent, falsifiable
checks, and (b) pin the application's analytical outputs so that unrelated
changes (input validation, CORS, dependency hygiene, ...) can be proven not
to have moved a single score.

    python -m validation.run                  # print the validation report
    python -m validation.run --check          # compare against stored baselines
    python -m validation.run --write-baseline # re-record baselines (intentional only)
"""
