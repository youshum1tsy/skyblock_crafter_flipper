def format(amount):
    formats = {"b": 1000000000, "m": 1000000, "k": 1000}

    for key, value in formats.items():
        if amount >= value:
            amount /= value
            return f"{amount:.2f}{key}"
    return f"{amount:.2f}"


def printPrettyStats(name, stats):
    print("-" * 30)
    if not stats:
        print(f"Data for {name} not found")
        return
    print(f"Targeted check {name}")
    print(
        f"Sell price {format(stats.targetItemPrice)} | Volume {format(stats.targetItemVolume)}"
    )
    print(f"Net Profit: {format(stats.profit)} | ROI: {stats.roi:.2f}%")
    print(f"Velocity: {stats.profitPerHours:.2f} coins/hour")
