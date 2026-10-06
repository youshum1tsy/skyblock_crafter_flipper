def format(amount):
    formats = {"b": 1000000000, "m": 1000000, "k": 1000}

    for key, value in formats.items():
        if amount >= value:
            amount /= value
            return f"{amount:.2f}{key}"
    return f"{amount:.0f}"
