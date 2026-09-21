document.addEventListener('DOMContentLoaded', () => {
    const menuToggle = document.getElementById('menuToggle');
    const closeMenu = document.getElementById('closeMenu');
    const mainNav = document.getElementById('mainNav');
    const navOverlay = document.getElementById('navOverlay');

    function openSidebar() {
        mainNav.classList.add('open');
        navOverlay.classList.add('open');
        document.body.style.overflow = 'hidden';
    }

    function closeSidebar() {
        mainNav.classList.remove('open');
        navOverlay.classList.remove('open');
        document.body.style.overflow = 'auto';
    }

    if (menuToggle) menuToggle.addEventListener('click', openSidebar);
    if (closeMenu) closeMenu.addEventListener('click', closeSidebar);
    if (navOverlay) navOverlay.addEventListener('click', closeSidebar);
});
