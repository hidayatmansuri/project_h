from django.shortcuts import render
import string
import secrets
import random  # only used for shuffle


def passgen(request):
    
    password = ""
    desire_password = ""
    error_message = ""
    
    if request.method == 'POST':
        length = int(request.POST.get('length', 12))
        
        includeUpper = request.POST.get('upper') == 'on'
        includeLower = request.POST.get('lower') == 'on'
        includeNumbers = request.POST.get('numbs') == 'on'
        includeSymbols = request.POST.get('symbols') == 'on'
        
        desire_password = request.POST.get("desired", "")
        
        special_chars = "!£$%^&*+#~@"
        
        # Build character pool
        characters = ""
        if includeUpper:
            characters += string.ascii_uppercase
        if includeLower:
            characters += string.ascii_lowercase
        if includeNumbers:
            characters += string.digits
        if includeSymbols:
            characters += special_chars

        # Validate selection
        if not characters:
            error_message = "Please select at least one password type."
        
        else:
            apply_uppercase_limit = includeUpper and includeLower
            max_uppercase = 2 if length <= 10 else (4 if length <= 20 else 5)

            # ------------------ DESIRED PASSWORD ------------------
            if desire_password:
                subs = {
                    "a": "@", "i": "!", "o": "*", "u": "#",
                    "s": "$", "t": "+", "g": "9", "b": "&",
                    "5": "%", "f": "?"
                }

                password = ""

                for char in desire_password:
                    if char.lower() in subs and secrets.choice([True, False]):
                        password += subs[char.lower()]
                    else:
                        if char.isalpha():
                            password += char.upper() if secrets.choice([True, False]) else char.lower()
                        else:
                            password += char

                while len(password) < length:
                    password += secrets.choice(characters)

            # ------------------ RANDOM PASSWORD ------------------
            else:
                password = ''.join(secrets.choice(characters) for _ in range(length))

            # ------------------ APPLY UPPERCASE LIMIT ------------------
            if apply_uppercase_limit:
                uppercase_indices = [i for i, c in enumerate(password) if c.isupper()]

                if len(uppercase_indices) > max_uppercase:
                    random.shuffle(uppercase_indices)
                    keep = set(uppercase_indices[:max_uppercase])

                    password = ''.join(
                        c.lower() if (i not in keep and c.isupper()) else c
                        for i, c in enumerate(password)
                    )

    return render(request, 'passgen.html', {
        'password': password,
        'desire_password': desire_password,
        'error_message': error_message,
    })