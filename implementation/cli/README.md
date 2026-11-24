# Control Plane CLI (vertical slice)

A thin command-line wrapper over the unchanged `Register` and `StateMachine` services. No GUI.

Run from the repository root:

```
python implementation\cli <command> [options] --db control_plane.db
```

`--db` defaults to `control_plane.db`. Each run initialises the schema (idempotent).

## Commands

| Command | Purpose |
| --- | --- |
| `create --work-id ID --project-id P --done-criterion TEXT --item-type TYPE --actor A [--assigned-to A] [--required]` | Create a work item with an explicit item type. |
| `assign --work-id ID --assigned-to A --actor A` | Assign a work item (audited). |
| `transition --work-id ID --to STATE --actor A --role ROLE [--evidence TEXT]...` | Attempt a state transition. `--evidence` may be repeated. |
| `query [--work-id ID] [--state S] [--assigned-to A] [--project-id P]` | List work items. |
| `show --work-id ID` | Show one item, its derived display state and audit trail. |
| `demo` | Run the end-to-end scripted flow (T1 and T7 -> T5). |

Item types: `Decision`, `Validation`, `Execution`, `Observation`, `Exception`.

## Exit codes

- `0`: success, or transition accepted.
- `1`: transition rejected by the state machine (reason code printed, e.g. `ACTOR_NOT_PERMITTED`, `ILLEGAL_TRANSITION`, `EVIDENCE_MISSING`).
- `2`: error (e.g. `TYPE_MISSING`, unknown item, database error).

Rejections write no audit entry.

## Example

```
python implementation\cli create --work-id W-1 --project-id DEMO --done-criterion "Migration runs" --item-type Execution --assigned-to worker-1 --actor pm-office
python implementation\cli transition --work-id W-1 --to Active --actor worker-1 --role worker --evidence "branch feat/migration"
python implementation\cli show --work-id W-1
python implementation\cli demo --db demo.db
```

## Notes and assumptions

- Actor identity and role are supplied as flags. There is no authentication.
- `derive_display` is display-only and does not change stored state.
- Evidence supplied on T1 is required but not stored in `evidence_refs`. Only T4 and T7 attach evidence in the current services (existing behaviour, unchanged here).
