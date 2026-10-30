const currentPath = window.location.pathname;

document.querySelectorAll('.home-nav .nav-link').forEach(link => {
    const href = link.getAttribute('href');
    if (!href || href === '#') return;
    if (href === currentPath || (href !== '/' && currentPath.startsWith(href))) {
        link.classList.add('active');
        const parentDropdown = link.closest('.dropdown');
        if (parentDropdown) {
            const toggle = parentDropdown.querySelector('.dropdown-toggle');
            if (toggle) toggle.classList.add('active');
        }
    }
});
