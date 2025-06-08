// theme-toggle.js
document.addEventListener('DOMContentLoaded', function() {
    const toggleButton = document.getElementById('theme-toggle');
    const htmlElement = document.documentElement;

    // Load saved theme
    const storedTheme = localStorage.getItem('theme');
    if (storedTheme) {
        htmlElement.classList.remove('light', 'dark');
        htmlElement.classList.add(storedTheme);
    }

    // Toggle on button click
    if (toggleButton) {
        toggleButton.addEventListener('click', function() {
            if (htmlElement.classList.contains('dark')) {
                htmlElement.classList.remove('dark');
                htmlElement.classList.add('light');
                localStorage.setItem('theme', 'light');
            } else {
                htmlElement.classList.remove('light');
                htmlElement.classList.add('dark');
                localStorage.setItem('theme', 'dark');
            }
        });
    }
});
