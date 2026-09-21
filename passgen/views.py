from django.shortcuts import render
import string
import secrets

# Map characters to their possible symbol/number substitutions
LEET_SUBS = {
    "a": {"symbols": ["@"], "numbers": ["4"]},
    "b": {"symbols": ["&"], "numbers": ["8"]},
    "e": {"symbols": [], "numbers": ["3"]},
    "f": {"symbols": ["?"], "numbers": []},
    "g": {"symbols": [], "numbers": ["9"]},
    "i": {"symbols": ["!"], "numbers": ["1"]},
    "l": {"symbols": ["!", "|"], "numbers": ["1"]},
    "o": {"symbols": ["*"], "numbers": ["0"]},
    "s": {"symbols": ["$"], "numbers": ["5"]},
    "t": {"symbols": ["+"], "numbers": ["7"]},
    "u": {"symbols": ["#"], "numbers": []},
    "z": {"symbols": [], "numbers": ["2"]},
}

def passgen(request):
    
    password = ""
    desire_password = ""
    error_message = ""
    
    # Defaults for state persistence
    length = 12
    includeUpper = True
    includeLower = True
    includeNumbers = True
    includeSymbols = True
    
    if request.method == 'POST':
        length = int(request.POST.get('length', 12))
        
        includeUpper = request.POST.get('upper') == 'on'
        includeLower = request.POST.get('lower') == 'on'
        includeNumbers = request.POST.get('numbs') == 'on'
        includeSymbols = request.POST.get('symbols') == 'on'
        
        desire_password = request.POST.get("desired", "")
        
        special_chars = "!£$%^&*+#~@"
        
        # Build character pools
        pools = []
        if includeUpper:
            pools.append(string.ascii_uppercase)
        if includeLower:
            pools.append(string.ascii_lowercase)
        if includeNumbers:
            pools.append(string.digits)
        if includeSymbols:
            pools.append(special_chars)

        # Validate selection
        if not pools:
            error_message = "Please select at least one password type."
        
        else:
            # ------------------ DESIRED PASSWORD ------------------
            if desire_password:
                password_chars = []

                for char in desire_password:
                    lower_char = char.lower()
                    choices = []
                    
                    # Always allow the character itself (or its case variations)
                    if char.isalpha():
                        if includeUpper and includeLower:
                            choices.extend([char.upper(), char.lower()])
                        elif includeUpper:
                            choices.append(char.upper())
                        elif includeLower:
                            choices.append(char.lower())
                        else:
                            choices.append(char) # Fallback if neither selected
                    else:
                        choices.append(char)

                    # Add substitution options if the user allowed them
                    if lower_char in LEET_SUBS:
                        if includeSymbols:
                            choices.extend(LEET_SUBS[lower_char]["symbols"])
                        if includeNumbers:
                            choices.extend(LEET_SUBS[lower_char]["numbers"])
                    
                    # Pick one randomly
                    password_chars.append(secrets.choice(choices))

                # Randomly place padding around the desired word
                if len(password_chars) < length:
                    all_chars = "".join(pools)
                    padding_length = length - len(password_chars)
                    padding = [secrets.choice(all_chars) for _ in range(padding_length)]
                    offset = secrets.randbelow(padding_length + 1)
                    password_chars = padding[:offset] + password_chars + padding[offset:]

                password = "".join(password_chars)

            # ------------------ RANDOM PASSWORD ------------------
            else:
                password_chars = []
                # Ensure at least one character from each selected pool
                for pool in pools:
                    password_chars.append(secrets.choice(pool))
                
                # Fill the rest
                all_chars = "".join(pools)
                while len(password_chars) < length:
                    password_chars.append(secrets.choice(all_chars))
                
                # Shuffle the result
                secrets.SystemRandom().shuffle(password_chars)
                password = "".join(password_chars)

    return render(request, 'passgen.html', {
        'password': password,
        'desired': desire_password,
        'error_message': error_message,
        'length': length,
        'upper': includeUpper,
        'lower': includeLower,
        'numbs': includeNumbers,
        'symbols': includeSymbols,
    })