def format(amount):
    if amount is None:
        return "N/A"

    abs_amount = abs(amount)
    formats = {"b": 1000000000, "m": 1000000, "k": 1000}

    for key, value in formats.items():
        if abs_amount >= value:
            val = amount / value
            return f"{val:.2f}{key}"

    # Если цена очень маленькая (меньше 0.05), выводим до 4 знаков
    if 0 < abs_amount < 0.05:
        return f"{amount:.4f}"

    return f"{amount:.2f}"


def printPrettyStats(name, stats):
    print("-" * 30)
    if not stats:
        print(f"Data for {name} not found")
        return

    craftType = getattr(stats, "craftType", "crafting").upper()
    print(f"Targeted check: {name} [{craftType}]")

    sellPrice = getattr(stats, "targetItemPrice", None) or getattr(
        stats, "unitSellPrice", 0
    )
    volume = getattr(stats, "targetItemVolume", 0)
    profit = getattr(stats, "profit", 0)
    roi = getattr(stats, "roi", 0.0)
    velocity = getattr(stats, "realProfitPerHour", None) or getattr(
        stats, "profitPerHours", 0
    )

    print(f"Sell price: {format(sellPrice)} | Volume: {format(volume)}")
    print(f"Net Profit: {format(profit)} | ROI: {roi:.2f}%")
    print(f"Velocity: {format(velocity)} coins/hour")

    # Вывод времени Forge
    forgeTotalSec = getattr(stats, "totalForgeDurationSec", 0)
    if forgeTotalSec > 0:
        parallelSec = forgeTotalSec / 5.0
        print(
            f"⏱ Время Forge (5 слотов): {format_time(parallelSec)} (в 1 слот: {format_time(forgeTotalSec)})"
        )


def format_time(seconds: float) -> str:
    """Переводит секунды в читаемый формат (дни, часы, минуты)."""
    if seconds <= 0:
        return "0с"

    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if days > 0:
        parts.append(f"{days}д")
    if hours > 0:
        parts.append(f"{hours}ч")
    if minutes > 0 and days == 0:
        parts.append(f"{minutes}м")
    if secs > 0 and days == 0 and hours == 0:
        parts.append(f"{secs}с")

    return " ".join(parts) if parts else "0с"
