from datetime import date, timedelta

class Scheduler:
    FULL_CYCLE = [1, 2, 4, 7, 15, 30]
    SHORT_CYCLE = [1, 3, 7]

    def schedule_new_item(self, today: date) -> dict:
        return {
            "status": "learning",
            "current_stage": 1,
            "cycle_type": "full",
            "cycle_start_date": today,
            "next_review_date": today + timedelta(days=1)
        }
