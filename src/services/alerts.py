from core.config import get_settings


def glucose_warning_text(mmol: float) -> str:
    s = get_settings()
    if mmol < s.glucose_low_mmol:
        return (
            "Warning: low glucose reading. Please verify and monitor closely. "
            "If symptoms are severe, contact emergency services."
        )
    if mmol > s.glucose_high_mmol:
        return (
            "Warning: high glucose reading. Please follow your care plan. "
            "If symptoms worsen, contact emergency services."
        )
    return ""


def bp_warning_text(systolic: int, diastolic: int) -> str:
    s = get_settings()
    if systolic >= s.bp_urgent_sys or diastolic >= s.bp_urgent_dia:
        return (
            "Urgent warning: blood pressure is in dangerous range. "
            "Seek urgent medical help now."
        )
    if systolic >= s.bp_high_sys or diastolic >= s.bp_high_dia:
        return "Warning: blood pressure is elevated. Follow your care plan and re-check soon."
    return ""
