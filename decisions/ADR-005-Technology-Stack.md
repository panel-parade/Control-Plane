# ADR-005: Technology Stack

Status: Accepted

## Decision
Control Plane v1 uses Python 3.12, sqlite3, and pytest.

## Reason
Fastest path to validating the Control Plane architecture while minimising infrastructure complexity.

## Consequences
Future revisions may replace sqlite3 if operational evidence demonstrates a need.
