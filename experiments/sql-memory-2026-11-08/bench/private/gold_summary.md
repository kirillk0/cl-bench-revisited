# Private gold summary

Seed SHA-256: `05050f81e4783c9ac99eefec5785dc1441bc4452f246ffd2ba80aa8787f690b9` (seed itself stays private).

## W1
```json
{
  "services": [
    {
      "attempts": 2300,
      "failed_attempts": 350,
      "operations": 2000,
      "physical_pools": 2,
      "retried_operations": 250,
      "service_code": "ledger-sync",
      "terminal_failure_pct": 2.5,
      "terminal_failures": 50
    },
    {
      "attempts": 2300,
      "failed_attempts": 350,
      "operations": 2000,
      "physical_pools": 2,
      "retried_operations": 250,
      "service_code": "parcel-index",
      "terminal_failure_pct": 2.5,
      "terminal_failures": 50
    }
  ],
  "totals": {
    "attempts": 4600,
    "failed_attempts": 700,
    "operations": 4000,
    "retried_operations": 500,
    "terminal_failures": 100
  }
}
```

## W2
```json
{
  "assessment": "idx-north rises from 2.5% to 21.0% (+18.5 pp), while idx-south stays at 2.5%. The applied deadline falls from 250 to 80 ms; upstream p95 stays 118 ms, queue depth 4, workers 16. A tighter client deadline is the strongest supported proximal explanation, not an observed upstream slowdown. Temporal coincidence plus mechanism is not controlled causal proof.",
  "changes": [
    {
      "after_json": "{\"deadline_ms\": 80}",
      "before_json": "{\"deadline_ms\": 250}",
      "effective_at_ms": 1777719600000,
      "kind_code": "deadline_policy",
      "pool_code": "idx-north"
    }
  ],
  "pool_metrics": [
    {
      "attempt_failure_pct": 51.23456790123457,
      "attempts": 1620,
      "failed_attempts": 830,
      "max_deadline_ms": 80,
      "min_deadline_ms": 80,
      "operations": 1000,
      "period": "incident",
      "pool_code": "idx-north",
      "retried_operations": 410,
      "terminal_failure_pct": 21.0,
      "terminal_failures": 210
    },
    {
      "attempt_failure_pct": 15.217391304347826,
      "attempts": 1150,
      "failed_attempts": 175,
      "max_deadline_ms": 250,
      "min_deadline_ms": 250,
      "operations": 1000,
      "period": "incident",
      "pool_code": "idx-south",
      "retried_operations": 125,
      "terminal_failure_pct": 2.5,
      "terminal_failures": 25
    },
    {
      "attempt_failure_pct": 15.217391304347826,
      "attempts": 1150,
      "failed_attempts": 175,
      "max_deadline_ms": 250,
      "min_deadline_ms": 250,
      "operations": 1000,
      "period": "reference",
      "pool_code": "idx-north",
      "retried_operations": 125,
      "terminal_failure_pct": 2.5,
      "terminal_failures": 25
    },
    {
      "attempt_failure_pct": 15.217391304347826,
      "attempts": 1150,
      "failed_attempts": 175,
      "max_deadline_ms": 250,
      "min_deadline_ms": 250,
      "operations": 1000,
      "period": "reference",
      "pool_code": "idx-south",
      "retried_operations": 125,
      "terminal_failure_pct": 2.5,
      "terminal_failures": 25
    }
  ],
  "telemetry": [
    {
      "mean_value": 16.0,
      "period": "incident",
      "pool_code": "idx-north",
      "signal_code": "available_workers",
      "unit": "workers"
    },
    {
      "mean_value": 0.42,
      "period": "incident",
      "pool_code": "idx-north",
      "signal_code": "cpu_utilization",
      "unit": "fraction"
    },
    {
      "mean_value": 4.0,
      "period": "incident",
      "pool_code": "idx-north",
      "signal_code": "queue_depth",
      "unit": "operations"
    },
    {
      "mean_value": 118.0,
      "period": "incident",
      "pool_code": "idx-north",
      "signal_code": "upstream_latency_p95",
      "unit": "ms"
    },
    {
      "mean_value": 16.0,
      "period": "incident",
      "pool_code": "idx-south",
      "signal_code": "available_workers",
      "unit": "workers"
    },
    {
      "mean_value": 0.42,
      "period": "incident",
      "pool_code": "idx-south",
      "signal_code": "cpu_utilization",
      "unit": "fraction"
    },
    {
      "mean_value": 4.0,
      "period": "incident",
      "pool_code": "idx-south",
      "signal_code": "queue_depth",
      "unit": "operations"
    },
    {
      "mean_value": 118.0,
      "period": "incident",
      "pool_code": "idx-south",
      "signal_code": "upstream_latency_p95",
      "unit": "ms"
    },
    {
      "mean_value": 16.0,
      "period": "reference",
      "pool_code": "idx-north",
      "signal_code": "available_workers",
      "unit": "workers"
    },
    {
      "mean_value": 0.42,
      "period": "reference",
      "pool_code": "idx-north",
      "signal_code": "cpu_utilization",
      "unit": "fraction"
    },
    {
      "mean_value": 4.0,
      "period": "reference",
      "pool_code": "idx-north",
      "signal_code": "queue_depth",
      "unit": "operations"
    },
    {
      "mean_value": 118.0,
      "period": "reference",
      "pool_code": "idx-north",
      "signal_code": "upstream_latency_p95",
      "unit": "ms"
    },
    {
      "mean_value": 16.0,
      "period": "reference",
      "pool_code": "idx-south",
      "signal_code": "available_workers",
      "unit": "workers"
    },
    {
      "mean_value": 0.42,
      "period": "reference",
      "pool_code": "idx-south",
      "signal_code": "cpu_utilization",
      "unit": "fraction"
    },
    {
      "mean_value": 4.0,
      "period": "reference",
      "pool_code": "idx-south",
      "signal_code": "queue_depth",
      "unit": "operations"
    },
    {
      "mean_value": 118.0,
      "period": "reference",
      "pool_code": "idx-south",
      "signal_code": "upstream_latency_p95",
      "unit": "ms"
    }
  ]
}
```

## T1
```json
{
  "assessment": "Overall failure falls 15%\u21928.153846%, and the pooled candidate appears better (9.333333% versus 14.6%). But idx-r19 is worse in all eight matched slices: +2 pp for small and +4 pp for large. Equal-slice standardization gives 14% versus 11%, +3 pp. Small-workload share rises from 33.333333% to 76.923077%. The observed trend and pooled comparison are confounded by workload and exposure composition, not evidence that rollout improved reliability. Candidate-associated regression is the strongest measured adverse association conditional on the specified strata; non-random assignment and unmeasured factors prevent identifying the build itself as a proven cause.",
  "builds": [
    {
      "build_code": "idx-r18",
      "operations": 5000,
      "terminal_failure_pct": 14.6,
      "terminal_failures": 730
    },
    {
      "build_code": "idx-r19",
      "operations": 7500,
      "terminal_failure_pct": 9.333333333333334,
      "terminal_failures": 700
    }
  ],
  "matched_cells": [
    {
      "build_code": "idx-r18",
      "class_code": "large",
      "operations": 1500,
      "period": "early",
      "region_code": "north",
      "terminal_failure_pct": 20.0,
      "terminal_failures": 300
    },
    {
      "build_code": "idx-r19",
      "class_code": "large",
      "operations": 500,
      "period": "early",
      "region_code": "north",
      "terminal_failure_pct": 24.0,
      "terminal_failures": 120
    },
    {
      "build_code": "idx-r18",
      "class_code": "small",
      "operations": 500,
      "period": "early",
      "region_code": "north",
      "terminal_failure_pct": 2.0,
      "terminal_failures": 10
    },
    {
      "build_code": "idx-r19",
      "class_code": "small",
      "operations": 500,
      "period": "early",
      "region_code": "north",
      "terminal_failure_pct": 4.0,
      "terminal_failures": 20
    },
    {
      "build_code": "idx-r18",
      "class_code": "large",
      "operations": 1500,
      "period": "early",
      "region_code": "south",
      "terminal_failure_pct": 20.0,
      "terminal_failures": 300
    },
    {
      "build_code": "idx-r19",
      "class_code": "large",
      "operations": 500,
      "period": "early",
      "region_code": "south",
      "terminal_failure_pct": 24.0,
      "terminal_failures": 120
    },
    {
      "build_code": "idx-r18",
      "class_code": "small",
      "operations": 500,
      "period": "early",
      "region_code": "south",
      "terminal_failure_pct": 2.0,
      "terminal_failures": 10
    },
    {
      "build_code": "idx-r19",
      "class_code": "small",
      "operations": 500,
      "period": "early",
      "region_code": "south",
      "terminal_failure_pct": 4.0,
      "terminal_failures": 20
    },
    {
      "build_code": "idx-r18",
      "class_code": "large",
      "operations": 250,
      "period": "late",
      "region_code": "north",
      "terminal_failure_pct": 20.0,
      "terminal_failures": 50
    },
    {
      "build_code": "idx-r19",
      "class_code": "large",
      "operations": 500,
      "period": "late",
      "region_code": "north",
      "terminal_failure_pct": 24.0,
      "terminal_failures": 120
    },
    {
      "build_code": "idx-r18",
      "class_code": "small",
      "operations": 250,
      "period": "late",
      "region_code": "north",
      "terminal_failure_pct": 2.0,
      "terminal_failures": 5
    },
    {
      "build_code": "idx-r19",
      "class_code": "small",
      "operations": 2250,
      "period": "late",
      "region_code": "north",
      "terminal_failure_pct": 4.0,
      "terminal_failures": 90
    },
    {
      "build_code": "idx-r18",
      "class_code": "large",
      "operations": 250,
      "period": "late",
      "region_code": "south",
      "terminal_failure_pct": 20.0,
      "terminal_failures": 50
    },
    {
      "build_code": "idx-r19",
      "class_code": "large",
      "operations": 500,
      "period": "late",
      "region_code": "south",
      "terminal_failure_pct": 24.0,
      "terminal_failures": 120
    },
    {
      "build_code": "idx-r18",
      "class_code": "small",
      "operations": 250,
      "period": "late",
      "region_code": "south",
      "terminal_failure_pct": 2.0,
      "terminal_failures": 5
    },
    {
      "build_code": "idx-r19",
      "class_code": "small",
      "operations": 2250,
      "period": "late",
      "region_code": "south",
      "terminal_failure_pct": 4.0,
      "terminal_failures": 90
    }
  ],
  "periods": [
    {
      "candidate_traffic_pct": 33.333333333333336,
      "operations": 6000,
      "period": "early",
      "terminal_failure_pct": 15.0,
      "terminal_failures": 900
    },
    {
      "candidate_traffic_pct": 84.61538461538461,
      "operations": 6500,
      "period": "late",
      "terminal_failure_pct": 8.153846153846153,
      "terminal_failures": 530
    }
  ],
  "standardized": {
    "candidate_failure_pct": 14.0,
    "candidate_minus_reference_pp": 3.0,
    "candidate_worse_slices": 8,
    "matched_slices": 8,
    "reference_failure_pct": 11.0
  },
  "workload_mix": [
    {
      "class_code": "large",
      "operations": 4000,
      "period": "early",
      "terminal_failure_pct": 21.0,
      "traffic_pct": 66.66666666666667
    },
    {
      "class_code": "small",
      "operations": 2000,
      "period": "early",
      "terminal_failure_pct": 3.0,
      "traffic_pct": 33.333333333333336
    },
    {
      "class_code": "large",
      "operations": 1500,
      "period": "late",
      "terminal_failure_pct": 22.666666666666668,
      "traffic_pct": 23.076923076923077
    },
    {
      "class_code": "small",
      "operations": 5000,
      "period": "late",
      "terminal_failure_pct": 3.8,
      "traffic_pct": 76.92307692307692
    }
  ]
}
```

## T2
```json
{
  "assessment": "sync-south rises 2.5%\u219217.5% (+15 pp); sync-north remains 2.5%. Deadline stays 250 ms. South available workers fall 16\u21924, queue depth rises 4\u2192180, failed terminal queue time 5\u2192235 ms and execution time 245\u219215 ms; upstream p95 stays 118 ms. An applied worker-limit reduction with queue starvation is the strongest proximal explanation; there is no observed deadline-policy tightening. This is convergent observational evidence, not an intervention proving exclusivity.",
  "changes": [
    {
      "after_json": "{\"worker_limit\": 4}",
      "before_json": "{\"worker_limit\": 16}",
      "effective_at_ms": 1778151600000,
      "kind_code": "worker_limit",
      "pool_code": "sync-south"
    }
  ],
  "pool_metrics": [
    {
      "attempt_failure_pct": 15.217391304347826,
      "attempts": 1150,
      "failed_attempts": 175,
      "failed_terminal_execution_mean_ms": 245.0,
      "failed_terminal_queue_mean_ms": 5.0,
      "max_deadline_ms": 250,
      "min_deadline_ms": 250,
      "operations": 1000,
      "period": "incident",
      "pool_code": "sync-north",
      "retried_operations": 125,
      "terminal_failure_pct": 2.5,
      "terminal_failures": 25
    },
    {
      "attempt_failure_pct": 46.774193548387096,
      "attempts": 1550,
      "failed_attempts": 725,
      "failed_terminal_execution_mean_ms": 15.0,
      "failed_terminal_queue_mean_ms": 235.0,
      "max_deadline_ms": 250,
      "min_deadline_ms": 250,
      "operations": 1000,
      "period": "incident",
      "pool_code": "sync-south",
      "retried_operations": 375,
      "terminal_failure_pct": 17.5,
      "terminal_failures": 175
    },
    {
      "attempt_failure_pct": 15.217391304347826,
      "attempts": 1150,
      "failed_attempts": 175,
      "failed_terminal_execution_mean_ms": 245.0,
      "failed_terminal_queue_mean_ms": 5.0,
      "max_deadline_ms": 250,
      "min_deadline_ms": 250,
      "operations": 1000,
      "period": "reference",
      "pool_code": "sync-north",
      "retried_operations": 125,
      "terminal_failure_pct": 2.5,
      "terminal_failures": 25
    },
    {
      "attempt_failure_pct": 15.217391304347826,
      "attempts": 1150,
      "failed_attempts": 175,
      "failed_terminal_execution_mean_ms": 245.0,
      "failed_terminal_queue_mean_ms": 5.0,
      "max_deadline_ms": 250,
      "min_deadline_ms": 250,
      "operations": 1000,
      "period": "reference",
      "pool_code": "sync-south",
      "retried_operations": 125,
      "terminal_failure_pct": 2.5,
      "terminal_failures": 25
    }
  ],
  "telemetry": [
    {
      "mean_value": 16.0,
      "period": "incident",
      "pool_code": "sync-north",
      "signal_code": "available_workers",
      "unit": "workers"
    },
    {
      "mean_value": 0.42,
      "period": "incident",
      "pool_code": "sync-north",
      "signal_code": "cpu_utilization",
      "unit": "fraction"
    },
    {
      "mean_value": 4.0,
      "period": "incident",
      "pool_code": "sync-north",
      "signal_code": "queue_depth",
      "unit": "operations"
    },
    {
      "mean_value": 118.0,
      "period": "incident",
      "pool_code": "sync-north",
      "signal_code": "upstream_latency_p95",
      "unit": "ms"
    },
    {
      "mean_value": 4.0,
      "period": "incident",
      "pool_code": "sync-south",
      "signal_code": "available_workers",
      "unit": "workers"
    },
    {
      "mean_value": 0.42,
      "period": "incident",
      "pool_code": "sync-south",
      "signal_code": "cpu_utilization",
      "unit": "fraction"
    },
    {
      "mean_value": 180.0,
      "period": "incident",
      "pool_code": "sync-south",
      "signal_code": "queue_depth",
      "unit": "operations"
    },
    {
      "mean_value": 118.0,
      "period": "incident",
      "pool_code": "sync-south",
      "signal_code": "upstream_latency_p95",
      "unit": "ms"
    },
    {
      "mean_value": 16.0,
      "period": "reference",
      "pool_code": "sync-north",
      "signal_code": "available_workers",
      "unit": "workers"
    },
    {
      "mean_value": 0.42,
      "period": "reference",
      "pool_code": "sync-north",
      "signal_code": "cpu_utilization",
      "unit": "fraction"
    },
    {
      "mean_value": 4.0,
      "period": "reference",
      "pool_code": "sync-north",
      "signal_code": "queue_depth",
      "unit": "operations"
    },
    {
      "mean_value": 118.0,
      "period": "reference",
      "pool_code": "sync-north",
      "signal_code": "upstream_latency_p95",
      "unit": "ms"
    },
    {
      "mean_value": 16.0,
      "period": "reference",
      "pool_code": "sync-south",
      "signal_code": "available_workers",
      "unit": "workers"
    },
    {
      "mean_value": 0.42,
      "period": "reference",
      "pool_code": "sync-south",
      "signal_code": "cpu_utilization",
      "unit": "fraction"
    },
    {
      "mean_value": 4.0,
      "period": "reference",
      "pool_code": "sync-south",
      "signal_code": "queue_depth",
      "unit": "operations"
    },
    {
      "mean_value": 118.0,
      "period": "reference",
      "pool_code": "sync-south",
      "signal_code": "upstream_latency_p95",
      "unit": "ms"
    }
  ]
}
```

## T3
```json
{
  "assessment": "Registry v2 outcome_events is operation-grain current instrumentation. Aggregate execution cells to actual physical pools, not intended routes, and do not deduplicate by cells. sync-south rises from 3% to 18%, +15 pp; sync-north stays 3%. The old attempt feed is legitimate retained history, not current coverage. Counting outcomes once and using attempt_count for retries produces the report; counts alone do not establish a root cause.",
  "largest_increase": {
    "incident_failure_pct": 18.0,
    "increase_pp": 15.0,
    "pool_code": "sync-south",
    "reference_failure_pct": 3.0
  },
  "pool_metrics": [
    {
      "mean_latency_ms": 108.87,
      "operations": 1000,
      "period": "incident",
      "pool_code": "sync-north",
      "retried_operations": 130,
      "retry_pct": 13.0,
      "terminal_failure_pct": 3.0,
      "terminal_failures": 30
    },
    {
      "mean_latency_ms": 261.8,
      "operations": 1000,
      "period": "incident",
      "pool_code": "sync-south",
      "retried_operations": 380,
      "retry_pct": 38.0,
      "terminal_failure_pct": 18.0,
      "terminal_failures": 180
    },
    {
      "mean_latency_ms": 108.87,
      "operations": 1000,
      "period": "reference",
      "pool_code": "sync-north",
      "retried_operations": 130,
      "retry_pct": 13.0,
      "terminal_failure_pct": 3.0,
      "terminal_failures": 30
    },
    {
      "mean_latency_ms": 108.9,
      "operations": 1000,
      "period": "reference",
      "pool_code": "sync-south",
      "retried_operations": 130,
      "retry_pct": 13.0,
      "terminal_failure_pct": 3.0,
      "terminal_failures": 30
    }
  ],
  "source": {
    "effective_from_ms": 1778284800000,
    "event_grain": "operation",
    "event_table": "outcome_events",
    "version": 2
  },
  "totals": [
    {
      "operations": 2000,
      "period": "incident",
      "terminal_failure_pct": 10.5,
      "terminal_failures": 210
    },
    {
      "operations": 2000,
      "period": "reference",
      "terminal_failure_pct": 3.0,
      "terminal_failures": 60
    }
  ]
}
```
