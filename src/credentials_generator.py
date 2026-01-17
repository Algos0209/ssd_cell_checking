def generate_credentials(num):
    """
    Generate hostname, username, and password based on the given number.
    :param num: int or str, the number to use (will be zero-padded to 3 digits)
    :return: tuple (hostname, username, password)
    """
    try:
        n = int(num)
    except Exception:
        raise ValueError("Input must be an integer or string representing an integer.")
    xxx = f"{n:03d}"
    hostname = f"css01sth{xxx}ts01"
    username = f"uss01sth{xxx}ts01"
    password = f"sth@TS{xxx}"
    return hostname, username, password