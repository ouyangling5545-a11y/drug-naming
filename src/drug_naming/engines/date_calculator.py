"""Date calculator for project pipeline milestones.

Handles calendar-day projection from working-day durations,
skipping weekends. Working days = calendar days minus Saturdays and Sundays.
"""

from __future__ import annotations

from datetime import date, timedelta


def working_days_to_calendar_days(working_days: int) -> int:
    """Convert working days to approximate calendar days.

    Rough estimate: 5 working days per 7 calendar days.
    Used for initial projection before exact date calculation.
    """
    return int(working_days * 7 / 5) + 1


def add_working_days(start: date, working_days: int) -> date:
    """Add working days to a date, skipping weekends.

    If working_days is 0, returns start.
    Each full working day increments the date by 1, skipping Sat/Sun.
    """
    if working_days <= 0:
        return start
    current = start
    remaining = working_days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 ... Fri=4
            remaining -= 1
    return current


def recalculate_milestone_dates(milestones: list, start_date: date | None = None) -> None:
    """Recalculate fastest_start/fastest_end and slowest_start/slowest_end
    for an ordered list of milestones.

    Handles dependency chains: a milestone that depends_on another
    starts after the dependency's end date.

    Args:
        milestones: List of Milestone objects (mutated in place).
        start_date: Override start date for the first milestone.
                    Defaults to today.
    """
    if not milestones:
        return

    # Build lookup by milestone id
    by_id = {m.id: m for m in milestones}

    base = start_date or date.today()

    for m in sorted(milestones, key=lambda x: x.order):
        # Determine fastest start
        fastest_start = base
        if m.depends_on:
            candidates = []
            for dep_id in m.depends_on:
                dep = by_id.get(dep_id)
                if dep and dep.fastest_end:
                    candidates.append(dep.fastest_end)
            if candidates:
                fastest_start = max(candidates) + timedelta(days=1)

        # Skip weekends for start date
        while fastest_start.weekday() >= 5:
            fastest_start += timedelta(days=1)

        m.fastest_start = fastest_start
        m.fastest_end = add_working_days(fastest_start, m.fastest_days)

        # Slowest path
        slowest_start = base
        if m.depends_on:
            candidates = []
            for dep_id in m.depends_on:
                dep = by_id.get(dep_id)
                if dep and dep.slowest_end:
                    candidates.append(dep.slowest_end)
            if candidates:
                slowest_start = max(candidates) + timedelta(days=1)

        while slowest_start.weekday() >= 5:
            slowest_start += timedelta(days=1)

        m.slowest_start = slowest_start
        m.slowest_end = add_working_days(slowest_start, m.slowest_days)


def recalculate_project_dates(project) -> None:
    """Recalculate all milestone dates for a project.

    Respects phase ordering and parallel phases.
    First non-parallel phase starts from today.
    Parallel phases can start after their parallel_trigger milestone completes.
    """
    from datetime import date as dt_date

    phases_sorted = sorted(project.phases, key=lambda p: p.order)
    base_date = dt_date.today()

    for phase in phases_sorted:
        if phase.is_parallel and phase.parallel_trigger:
            # Find the trigger milestone in another phase
            trigger_end = None
            for other_phase in phases_sorted:
                for m in other_phase.milestones:
                    if m.id == phase.parallel_trigger and m.fastest_end:
                        trigger_end = m.fastest_end
                        break
                if trigger_end:
                    break
            if trigger_end:
                recalculate_milestone_dates(phase.milestones, start_date=trigger_end)
                continue

        recalculate_milestone_dates(phase.milestones, start_date=base_date)
        # Next non-parallel phase starts after the last milestone of this phase
        if phase.milestones:
            last = phase.milestones[-1]
            if last.fastest_end:
                base_date = last.fastest_end
