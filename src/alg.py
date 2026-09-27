# Standalone, console-only version of the climbing simulation (no GUI).
# Kept in sync with the animation logic in animation.py: one random active
# climber advances per step; with `alarm_probability` a "vulnerable" climber
# (progress > 0) falls back a level; reaching 12 levels marks a climber as done.

import random


class AlarmRandomizer:
    # Better alarm randomizer than a raw Bernoulli draw (`random() < p`):
    # a trickle/leaky-bucket pattern that fires alarms at exactly the configured
    # rate on average while spreading them evenly in time. Raw Bernoulli draws
    # can produce pathological streaks (bursts of alarms or long silent runs);
    # this keeps the timing realistic without distorting the average rate.
    def __init__(self, probability=0.35):
        self.probability = probability
        self._position = 0.0

    def trigger(self):
        # Each step adds a uniform [0, 1) increment; an alarm fires every time
        # the accumulator crosses the threshold calibrated to `probability`.
        self._position += random.random()
        threshold = 0.5 / max(self.probability, 1e-9)
        if self._position >= threshold:
            self._position -= threshold
            return True
        return False


def pick_alarm_victim(active_climbers, climbing_progress):
    # Weight the victim draw by current height: the higher a climber is, the
    # more likely an alarm knocks them back (realistic climbing risk).
    vulnerable_climbers = [c for c in active_climbers if climbing_progress[c] > 0]
    if not vulnerable_climbers:
        return None
    weights = [climbing_progress[c] for c in vulnerable_climbers]
    return random.choices(vulnerable_climbers, weights=weights, k=1)[0]


def step_simulation(climbing_progress, finished_status, active_climbers,
                    alarm_probability, alarm_randomizer=None):
    # Advance the simulation by a single step and return a dict describing the
    # event that happened (used for logging / animations).
    if not active_climbers:
        return {"event": "ALL_FINISHED", "climber_id": None}

    # Pick a random climber that is still climbing
    climber_id = random.choice(list(active_climbers))
    climbing_progress[climber_id] += 1

    # Reached the top of the wall
    if climbing_progress[climber_id] >= 12:
        active_climbers.remove(climber_id)
        finished_status[climber_id] = 1
        return {"event": "CLIMBER_FINISHED", "climber_id": climber_id}

    # Random alarm: knock a vulnerable climber back one level
    if alarm_randomizer is None:
        alarm_randomizer = AlarmRandomizer(alarm_probability)
    if alarm_randomizer.trigger():
        alarm_climber_id = pick_alarm_victim(active_climbers, climbing_progress)
        if alarm_climber_id is not None:
            climbing_progress[alarm_climber_id] -= 1
            return {
                "event": "ALARM_PENALTY",
                "climber_id": alarm_climber_id,
                "advanced_climber": climber_id
            }

    # Ordinary climb step
    return {"event": "PROGRESS", "climber_id": climber_id}


# --- Simulation settings and state ---
NUM_CLIMBERS = 10
climbing_progress = [0] * NUM_CLIMBERS    # levels reached by each climber
finished_status = [0] * NUM_CLIMBERS      # 1 once a climber reaches the top
active_climbers = set(range(NUM_CLIMBERS))  # climbers still climbing
alarm_probability = 0.35                   # chance of an alarm each step
alarm_randomizer = AlarmRandomizer(alarm_probability)

# Run until every climber has finished
while active_climbers:
    result = step_simulation(climbing_progress, finished_status, active_climbers,
                             alarm_probability, alarm_randomizer)

# Report the final results
print("Simulation finished.")
print(f"Climbers finished: {[i+1 for i, status in enumerate(finished_status) if status]}")
print(f"Final progress: {climbing_progress}")