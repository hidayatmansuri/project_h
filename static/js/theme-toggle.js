// theme-toggle.js
document.addEventListener('DOMContentLoaded', function() {
    const toggleCheckbox = document.getElementById('theme-toggle');
    const backToTop = document.getElementById("backToTop");
    const htmlElement = document.documentElement;

    // Load saved theme
    const storedTheme = localStorage.getItem('theme');
    if (storedTheme) {
        htmlElement.classList.remove('light', 'dark');
        htmlElement.classList.add(storedTheme);
        toggleCheckbox.checked = storedTheme === 'dark';
    }

    // Toggle on checkbox change
    toggleCheckbox.addEventListener('change', function () {
        const newTheme = toggleCheckbox.checked ? 'dark' : 'light';
        htmlElement.classList.remove('light', 'dark');
        htmlElement.classList.add(newTheme);
        localStorage.setItem('theme', newTheme);
    });

    window.addEventListener("scroll", () => {
        if(window.scrollY > 10) {
            backToTop.style.display = "flex";
        } else {
            backToTop.style.display = "none";
        }
    });
});


