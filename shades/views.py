from django.shortcuts import render


def shades(request):
    """
    Renders the Colour Shades app displaying shades from #000000 to #FFFFFF
    in ascending order with hex and RGB values.
    """
    # Generate 256 baseline grayscale shades from #000000 to #FFFFFF in ascending order
    initial_shades = []
    for i in range(256):
        hex_code = f"#{i:02X}{i:02X}{i:02X}"
        rgb_code = f"rgb({i}, {i}, {i})"
        initial_shades.append({
            'hex': hex_code,
            'rgb': rgb_code,
            'r': i,
            'g': i,
            'b': i,
        })

    return render(request, 'shades.html', {
        'initial_shades': initial_shades,
    })
