# Services

## State machine: `StateMachine.transition`

```python
from services.state_machine import StateMachine, Actor

sm = StateMachine(connection)
result = sm.transition(work_id, to_state, actor, evidence)
```

- `work_id`: str. `to_state`: one of the register states.
- `actor`: `Actor(identity, role)`, role in `worker`, `manager`, `system`, `verifier`.
- `evidence`: `None`, a string, or a list of strings. Each non-blank string is appended, in order, as one evidence record in `WorkItem.evidence_refs` (T4 attaches the list; a done criterion may need several records). Blank or missing evidence is `EVIDENCE_MISSING`.
- Returns `TransitionResult(accepted, work_id, new_state, audit_id, reason_code, detail)`.
- Rejections never mutate the register and write no audit entry. `reason_code` is one of `NOT_FOUND`, `ILLEGAL_TRANSITION`, `ACTOR_NOT_PERMITTED`, `EVIDENCE_MISSING`.
- Accepted transitions write exactly one `TRANSITION` audit row in the same transaction as the state change.
- Transitions are the only supported way to change `state`. Direct writes are blocked by a trigger unless the state machine has set its guard inside its own transaction.

Transition table (`TRANSITIONS` in `state_machine.py`): T1-T6, see the State Machine Spec. Claimed Complete -> Active is not in the table and is rejected as `ILLEGAL_TRANSITION`.

### Failed verification: `StateMachine.verification_failed`

```python
result = sm.verification_failed(work_id, actor, evidence)
```

- Verifier-only (`actor.role == "verifier"`). The item must be in `Claimed Complete`, otherwise `ILLEGAL_TRANSITION`.
- The state stays `Claimed Complete`. The item is not moved to `Active`. The worker's completion claim is preserved.
- `evidence` is required (`EVIDENCE_MISSING` otherwise). It is appended to `evidence_refs`.
- Accepted results return `reason_code="VERIFICATION_FAILURE"`, `new_state="Claimed Complete"`. This writes one `VERIFICATION_FAILURE` audit row in the same transaction. This is the only accepted operation that does not change state.
- Rejections mutate nothing and write no audit row, as for `transition`.
- Stream C reads the `VERIFICATION_FAILURE` exception from `audit_entries` and `WorkItem.evidence_refs`.

## Work Register: `Register` (read and write API)

```python
from services.register import Register

reg = Register(connection)
reg.create(work_id, project_id, done_criterion, actor, assigned_to=None, required=False)  # writes a CREATE audit entry
reg.assign(work_id, assigned_to, actor)   # writes an ASSIGNMENT audit entry; KeyError if unknown
reg.get(work_id)                          # WorkItem or None
reg.query(work_id=, assigned_to=, state=, project_id=, last_update_ts_from=, last_update_ts_to=)  # list of WorkItem, read-only
reg.audit_entries(work_id)                            # audit rows, oldest first
```

`WorkItem.evidence_refs` is a tuple of evidence ids in attachment order (empty if none).

Stream C reads work items through `Register.get` and `Register.query` only. `WorkItem` is a frozen dataclass and does not contain a status field; status is derived by Stream C.
