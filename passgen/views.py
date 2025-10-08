from django.shortcuts import render
import random
import string


def passgen(request):
    
    # Empty Array
    password=""
    desire_password=""
    error_message=""
    
    if request.method == 'POST':
        length = int(request.POST.get('length',12))
        
        # Checkboxes
        includeUpper = request.POST.get('upper') == 'on'
        includeLower = request.POST.get('lower') == 'on'
        includeNumbers = request.POST.get('numbs') == 'on'
        includeSymbols = request.POST.get('symbols') == 'on'
        
        desire_password = request.POST.get("desired", "")
        
        special_chars = "!£$%^&*+#~@"
        # Collect password characters based on check boxes
        characters = ""
        if includeUpper:
            characters += string.ascii_uppercase
        if includeLower:
            characters += string.ascii_lowercase
        if includeNumbers:
            characters += string.digits
        if includeSymbols:
            characters += special_chars

        uppercase_chars = string.ascii_uppercase if includeUpper else ""
        
        # Makingsure that at-least once checkbox is checked
        if not characters:
            error_message = "Please select at least one of the following password type."
        else:
            apply_uppercase_limit = includeUpper and includeLower
            max_uppercase = 2 if length <= 10 else 5
            # If password provided transform
            if desire_password:
                subs = {
                    "a": "@",
                    "e": "3",
                    "i": "!",
                    "o": "*",
                    "u": "#",
                    "s": "$",
                    "t": "+",
                    "g": "9",
                    "b": "&",
                    "5": "%",
                    "f": "?",
                    "n": "~",
                    "v": "^"
                }
                password = ""
                for char in desire_password:
                    if char.lower() in subs and random.choice([True, False]):
                        password += subs[char.lower()]
                    else:
                        if char.isalpha():
                            password += char.upper() if random.choice([True, False]) else char.lower()
                        else:
                            password += char
                            
                while len(password) < length:
                    password += random.choice(characters + uppercase_chars)
            else:
                password = ''.join(random.choice(characters) for _ in range(length))
                
            if apply_uppercase_limit:
                uppercase_indices = [i for i, c in enumerate(password) if c.isupper()]
                if len(uppercase_indices) > max_uppercase:
                    random.shuffle(uppercase_indices)
                    keep = set(uppercase_indices[:max_uppercase])
                    password = ''.join(
                        c.lower() if (i not in keep and c.isupper()) else c
                        for i, c in enumerate(password)
                    )

    return render(request, 'passgen.html',{
        'password':password,
        'desire_password':desire_password,
        'error_message':error_message,
        }
    )


