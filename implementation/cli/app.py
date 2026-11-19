"""Command-line front end for the Control Plane vertical slice.

Every command delegates to the existing Register and StateMachine. No transition rule is
re-implemented here; the CLI only parses arguments and renders results.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from typing import Optional, Sequence, TextIO

from schema.db import connect, initialize
from services.register import Register, WorkItem
from services.state_machine import ROLES, Actor, StateMachine, TransitionResult

DEFAULT_DB = "control_plane.db"
EXIT_ACCEPTED = 0
EXIT_REJECTED = 1
EXIT_ERROR = 2


def derive_display(item: WorkItem) -> str:
    """Display-only derived state. Stores nothing; see status/derive.py for the Stream C model."""
    if item.state in ("Complete", "Archived"):
        return "Done"
    if item.assigned_to is None:
        return "Ownership Gap"
    if item.state == "Blocked":
        return f"Blocked: {item.block_reason}"
    if item.state == "Claimed Complete":
        return "Awaiting verification (T5)"
    return item.state


def _render_item(item: WorkItem, out: TextIO) -> None:
    out.write(f"work_id:        {item.work_id}\n")
    out.write(f"item_type:      {item.item_type or '(none)'}\n")
    out.write(f"project_id:     {item.project_id}\n")
    out.write(f"state:          {item.state}\n")
    out.write(f"assigned_to:    {item.assigned_to or '(none)'}\n")
    out.write(f"derived:        {derive_display(item)}\n")
    out.write(f"done_criterion: {item.done_criterion}\n")
    out.write(f"evidence_refs:  {', '.join(item.evidence_refs) or '(none)'}\n")


def _render_summary(item: WorkItem, out: TextIO) -> None:
    out.write(
        f"{item.work_id:<10} {item.item_type or '(none)':<12} {item.state:<18} "
        f"{item.assigned_to or '(none)':<14} {derive_display(item)}\n")


def _render_result(result: TransitionResult, out: TextIO) -> None:
    if result.accepted:
        out.write(f"ACCEPTED {result.work_id}: -> {result.new_state} (audit {result.audit_id})\n")
    else:
        out.write(f"REJECTED {result.work_id}: {result.reason_code} - {result.detail}\n")


def cmd_create(args: argparse.Namespace, reg: Register, sm: StateMachine, out: TextIO) -> int:
    item = reg.create(
        args.work_id, args.project_id, args.done_criterion, args.actor,
        assigned_to=args.assigned_to or None, required=args.required,
        item_type=args.item_type)
    out.write(f"CREATED {item.work_id} ({item.item_type}) in state {item.state}\n")
    return EXIT_ACCEPTED


def cmd_assign(args: argparse.Namespace, reg: Register, sm: StateMachine, out: TextIO) -> int:
    item = reg.assign(args.work_id, args.assigned_to or None, args.actor)
    out.write(f"ASSIGNED {item.work_id} to {item.assigned_to or '(none - Ownership Gap)'}\n")
    return EXIT_ACCEPTED


def cmd_transition(args: argparse.Namespace, reg: Register, sm: StateMachine, out: TextIO) -> int:
    result = sm.transition(
        args.work_id, args.to, Actor(args.actor, args.role), args.evidence or None)
    _render_result(result, out)
    return EXIT_ACCEPTED if result.accepted else EXIT_REJECTED


def cmd_query(args: argparse.Namespace, reg: Register, sm: StateMachine, out: TextIO) -> int:
    items = reg.query(
        work_id=args.work_id, state=args.state, assigned_to=args.assigned_to,
        project_id=args.project_id)
    for item in items:
        _render_summary(item, out)
    if not items:
        out.write("(no matching work items)\n")
    return EXIT_ACCEPTED


def cmd_show(args: argparse.Namespace, reg: Register, sm: StateMachine, out: TextIO) -> int:
    item = reg.get(args.work_id)
    if item is None:
        out.write(f"ERROR: work item {args.work_id!r} does not exist\n")
        return EXIT_ERROR
    _render_item(item, out)
    out.write("audit:\n")
    for row in reg.audit_entries(args.work_id):
        _render_audit(row, out)
    return EXIT_ACCEPTED


def _render_audit(row: sqlite3.Row, out: TextIO) -> None:
    out.write(
        f"  #{row['audit_id']} {row['event_type']} {row['old_state'] or '-'} -> "
        f"{row['new_state']} by {row['actor']} at {row['timestamp']}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli", description="Control Plane vertical slice (Register + State Machine T1-T7).")
    db_opts = argparse.ArgumentParser(add_help=False)
    db_opts.add_argument("--db", default=DEFAULT_DB, help=f"SQLite file (default {DEFAULT_DB})")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create", parents=[db_opts], help="create a work item (Assigned)")
    p.add_argument("--work-id", required=True)
    p.add_argument("--project-id", required=True)
    p.add_argument("--done-criterion", required=True)
    p.add_argument("--item-type", required=True,
                   help="Decision, Validation, Execution, Observation or Exception")
    p.add_argument("--assigned-to", default=None)
    p.add_argument("--required", action="store_true")
    p.add_argument("--actor", required=True)
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("assign", parents=[db_opts], help="set the owner (empty clears it)")
    p.add_argument("--work-id", required=True)
    p.add_argument("--assigned-to", default="")
    p.add_argument("--actor", required=True)
    p.set_defaults(func=cmd_assign)

    p = sub.add_parser("transition", parents=[db_opts],
                       help="attempt a state transition (exit 0 accepted, 1 rejected)")
    p.add_argument("--work-id", required=True)
    p.add_argument("--to", required=True, help="target state, e.g. Active")
    p.add_argument("--actor", required=True, help="actor identity")
    p.add_argument("--role", required=True, choices=ROLES)
    p.add_argument("--evidence", action="append", default=[],
                   help="evidence reference (repeatable)")
    p.set_defaults(func=cmd_transition)

    p = sub.add_parser("query", parents=[db_opts], help="list work items")
    p.add_argument("--work-id")
    p.add_argument("--state")
    p.add_argument("--assigned-to")
    p.add_argument("--project-id")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("show", parents=[db_opts], help="show one item with its audit trail")
    p.add_argument("--work-id", required=True)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("demo", parents=[db_opts],
                       help="run the end-to-end slice (use a new DB file)")
    p.set_defaults(func=cmd_demo)
    return parser


def _step(out: TextIO, title: str) -> None:
    out.write(f"\n== {title}\n")


def cmd_demo(args: argparse.Namespace, reg: Register, sm: StateMachine, out: TextIO) -> int:
    """Walks the vertical slice and the T7 demonstration; each step uses the CLI commands' code path."""
    _step(out, "1. Create Execution item W-1 and assign to worker-1")
    reg.create("W-1", "DEMO", "Migration script runs clean on staging", "pm-office",
               item_type="Execution")
    reg.assign("W-1", "worker-1", "pm-office")
    _render_item(reg.get("W-1"), out)

    _step(out, "2. Illegal attempt: T1 by a non-owner worker (owner is worker-1)")
    _render_result(sm.transition(
        "W-1", "Active", Actor("worker-2", "worker"), ["branch feat/other"]), out)

    _step(out, "3. Legal transition T1 (Assigned -> Active) by the owner")
    _render_result(sm.transition(
        "W-1", "Active", Actor("worker-1", "worker"), ["branch feat/migration"]), out)

    _step(out, "4. Show W-1 with audit trail")
    _render_item(reg.get("W-1"), out)
    for row in reg.audit_entries("W-1"):
        _render_audit(row, out)

    _step(out, "5. Decision item D-1 created and assigned to the Intent Owner (lucien)")
    reg.create("D-1", "DEMO", "Intent Owner records the scope decision", "pm-office",
               item_type="Decision")
    reg.assign("D-1", "lucien", "pm-office")
    _render_item(reg.get("D-1"), out)

    _step(out, "6. Illegal attempt: T7 by a worker (T7 is Intent Owner only)")
    _render_result(sm.transition(
        "D-1", "Claimed Complete", Actor("worker-1", "worker"), ["Decision recorded"]), out)

    _step(out, "7. T7 (Assigned -> Claimed Complete) by lucien, evidence 'Decision recorded'")
    _render_result(sm.transition(
        "D-1", "Claimed Complete", Actor("lucien", "intent_owner"), ["Decision recorded"]), out)

    _step(out, "8. Attempt Complete by the Intent Owner: rejected, T5 still required")
    _render_result(sm.transition(
        "D-1", "Complete", Actor("lucien", "intent_owner"), ["Decision recorded"]), out)

    _step(out, "9. T5 (Claimed Complete -> Complete) by the verifier")
    _render_result(sm.transition(
        "D-1", "Complete", Actor("verifier-1", "verifier"),
        ["done criterion satisfied: decision recorded"]), out)

    _step(out, "10. Show D-1 with audit trail")
    _render_item(reg.get("D-1"), out)
    for row in reg.audit_entries("D-1"):
        _render_audit(row, out)

    _step(out, "11. Register summary")
    for item in reg.query():
        _render_summary(item, out)
    return EXIT_ACCEPTED


def main(argv: Optional[Sequence[str]] = None, out: Optional[TextIO] = None) -> int:
    out = out or sys.stdout
    args = _build_parser().parse_args(argv)
    conn = connect(args.db)
    try:
        initialize(conn)
        return args.func(args, Register(conn), StateMachine(conn), out)
    except (ValueError, KeyError, sqlite3.Error) as exc:
        out.write(f"ERROR: {exc}\n")
        return EXIT_ERROR
    finally:
        conn.close()
