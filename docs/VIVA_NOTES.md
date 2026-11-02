# Viva notes — 20 short Q&As

Prepared 2026-11-03 from current code and saved aggregate results. All syllabus
topics are **UNVERIFIED**. Answers describe this educational virtual system only.

1. **What does Raah do?** Estimates synthetic congestion/future queue wait and
   compares constrained virtual controllers; it does not operate real signals.

2. **Is this live GPS?** No. Speeds are noisy synthetic GPS-like aggregates;
   counts, queues and waits come from simulator truth.

3. **What is one dataset row?** One run, timestamp, junction and approach snapshot
   on a 10-second grid. There are 14,520 labeled rows from 30 runs.

4. **What are the two supervised targets?** LOW/MEDIUM/HIGH congestion at t, and
   mean queue wait at the exact same run/junction/approach at t+60 seconds.

5. **Why warn about label leakage?** Current congestion is defined by speed/count/
   queue/wait rules. Learning those same inputs could merely reproduce the rule.

6. **Which features does classification actually use?** Incoming/outgoing counts,
   current phase, seconds in phase and synthetic time of day. Direct rule inputs,
   GPS sample-count proxy, identifiers and targets are excluded.

7. **Why split by run?** Neighboring windows/approaches are correlated. Whole runs
   stay together: 18 train, six validation, six test, with zero group overlap.

8. **How is preprocessing isolated?** Imputers, encoders, scaling and polynomial
   expansion fit training data only during comparisons. Unknown phase categories
   are ignored with a fixed output width; missing speeds remain schema-valid nulls.

9. **Why select KNN instead of the most accurate classifier?** KNN had validation
   macro-F1 0.537601; SVC had higher accuracy but zero MEDIUM recall. Macro-F1
   weights classes equally. The frozen choice uses recall/latency for exact ties.

10. **What does KNN mean here?** Fifteen neighbors, distance weighting and Euclidean
    distance after train-fitted scaling; its settings were fixed, not tuned on test.

11. **What is the regression baseline and winner?** Predict current mean wait as
    the future wait. Validation MAE: baseline 10.102998 s versus polynomial-degree-2
    linear regression 6.139516 s; linear regression gives 7.017311 s.

12. **What do MAE, RMSE and R2 tell us?** MAE is average absolute error in seconds;
    RMSE penalizes large errors more; R2 measures variance explained relative to a
    mean baseline. High R2 under persistent synthetic waits is not real-world proof.

13. **Was the final test used to choose models?** No. Choice was frozen first,
    selected full pipelines refit on 24 development groups, then six test groups
    scored once. Saved receipt counters are one read and one batch per model.

14. **What are the saved final results and weaknesses?** KNN accuracy 0.684229,
    macro-F1 0.503522, MEDIUM recall 0.055363. Regression MAE 5.973365 s,
    RMSE 8.190121 s, with 441 negative outputs retained and flagged.

15. **What does unsupervised analysis establish?** Training-only clustering/PCA
    describes synthetic structure, not supervised accuracy or truth. PCA's first
    two components explain 0.563375 of saved training variance. IQR/z-score are
    SKIPPED_UNVERIFIED; DBSCAN silhouette is undefined with one non-noise cluster.

16. **How do the three controllers differ?** Fixed-time uses 30-second greens;
    rule-only extends from queue pressure; ML-assisted adds bounded congestion/
    wait pressure. All share the same deterministic safety state machine.

17. **How are conflicts and starvation constrained?** Green axes alternate through
    3-second yellow and 1-second all-red. Green is 15–60 seconds, extensions <=5 s,
    axis red <=75 s, with WALK/clearance protected. This does not bound every
    vehicle's delay under overload or certify physical pedestrian safety.

18. **What happens if models or the API fail?** Missing artifacts yield explicit
    unavailable/503, invalid input 422, stale mutation 409. ML queue-only fallback
    requires API opt-in. The client pauses on errors and displays no random substitute.

19. **Did adaptive control always improve traffic?** No. The saved 75-rollout
    benchmark has zero constraint violations but 30/50 adverse mean-wait pairs;
    both adaptive policies are worse in medium/high/incident. Results are synthetic
    and right-censored; five runs/scenario give limited uncertainty evidence.

20. **What is reproducible or still unverified?** Seed 57, grouped manifests,
    version/hash records and tests support repeatability; 116 benchmark artifacts
    matched byte-for-byte in QA. Timing/platform differences remain. Official
    syllabus, SUMO runtime and real-browser visual verification are not established.

Sources: [README comparisons and architecture](../README.md),
[final test audit](FINAL_TEST_AUDIT.md), [QA evidence](FINAL_QA_REPORT.md),
[syllabus evidence map](SYLLABUS_COVERAGE_REPORT.md).
