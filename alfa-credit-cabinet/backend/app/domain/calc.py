def annuity_payment(amount: float, annual_rate_pct: float, months: int) -> float:
    """Аннуитетный платёж в месяц."""
    if months <= 0:
        raise ValueError("months must be positive")
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return amount / months
    return amount * r / (1 - (1 + r) ** -months)
