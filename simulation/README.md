# Virtual simulation (planned)

This directory reserves the synthetic scenario generator and rule-based virtual signal simulator.
No simulator/controller is implemented in Phase 1. No physical traffic control is allowed.

Future implementation must use seed 57, independent scenario/run groups, explicit aggregate
units, and group-separated evaluation with train-only preprocessing. The virtual controller
must enforce minimum/maximum green, yellow/all-red clearance, movement exclusion, bounded
changes, starvation limits, invalid-input fallback and rejection of infeasible configurations.
Test these invariants and compare against a fixed-time virtual baseline before reporting results.
