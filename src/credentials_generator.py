def generate_credentials(num):
    """
    Generate hostname, username, and password based on the given number.
    For 1-9: Returns single credential set with 00x format
    For 10-99: Returns TWO credential sets - one with 0xx format and one with xx format for hostname
               (username and password always use 0xx format)
    :param num: int or str, the number to use
    :return: list of tuples [(hostname, username, password), ...]
    """
    try:
        n = int(num)
    except Exception:
        raise ValueError("Input must be an integer or string representing an integer.")
    
    # Always use 3-digit format for username and password
    xxx_3digit = f"{n:03d}"
    username = f"uss01sth{xxx_3digit}ts01"
    password = f"sth@TS{xxx_3digit}"
    
    if 1 <= n <= 9:
        # For 1-9: use 00x format for hostname
        hostname = f"css01sth{xxx_3digit}ts01"
        return [(hostname, username, password)]
    elif 10 <= n <= 99:
        # For 10-99: return BOTH 0xx and xx format hostnames
        hostname_3digit = f"css01sth{xxx_3digit}ts01"
        hostname_2digit = f"css01sth{n}ts01"
        return [
            (hostname_3digit, username, password),
            (hostname_2digit, username, password)
        ]
    else:
        # For 100+: use the number as-is
        hostname = f"css01sth{n}ts01"
        return [(hostname, username, password)]