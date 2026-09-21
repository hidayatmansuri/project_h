document.addEventListener('DOMContentLoaded', () => {
    const startYear = 2024;
    const currentYear = new Date().getFullYear();
    const yearSpan = document.getElementById('copyright-year');

    if (yearSpan) {
        if (currentYear > startYear) {
            yearSpan.textContent = `${startYear} - ${currentYear}`;
        } else {
            yearSpan.textContent = `${startYear}`;
        }
    }
});
